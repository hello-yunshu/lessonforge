"""Production consumer for the official RillML 1.2.0 Stable IPC v2."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from document_intelligence import __version__
from document_intelligence.exceptions import RillProtocolError, RillUnavailableError
from document_intelligence.rill.client import RillShadowClient, RuntimeSnapshot
from document_intelligence.rill.models import (
    ACTION_ARMS,
    ACTION_TO_ARM,
    PolicySuggestion,
    RillObserveEvent,
    RuntimeIdentity,
    ShadowAction,
    stable_rill_id,
)
from document_intelligence.rill.stable_protocol import (
    ErrorResponseV2,
    HandshakeRequestV2,
    HandshakeResponseV2,
    HealthRequestV2,
    HealthResponseV2,
    InvokeRequestV2,
    ResultResponseV2,
    encode_request,
    parse_response,
)

CAPABILITY_EVALUATE = "org.lessonforge.shadow.evaluate"
CAPABILITY_UPDATE = "org.lessonforge.shadow.update"


class _DecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    decision_id: str | None = Field(default=None, alias="decisionId", min_length=1, max_length=128)
    action: ShadowAction
    selected_arm: int | None = Field(default=None, alias="selectedArm", ge=0)
    policy_version: str = Field(default="rillml-1.2.0", alias="policyVersion", max_length=127)
    confidence: float = Field(ge=0.0, le=1.0)
    reason_codes: list[str] = Field(
        default_factory=lambda: ["RILL_STABLE_V2"], alias="reasonCodes", max_length=32
    )


class StableV2RillClient(RillShadowClient):
    """Strict, single-flight, newline JSON v2 client.

    The Runtime receives bounded business input and returns a suggestion. It
    never owns LessonForge persistence or executes a returned action.
    """

    host_owned_state = True

    def __init__(
        self,
        command: Sequence[str],
        *,
        feature_schema_hash: str,
        evaluate_capability: str = CAPABILITY_EVALUATE,
        feedback_capability: str | None = None,
        request_timeout_seconds: float = 5.0,
        startup_timeout_seconds: float = 5.0,
        max_message_bytes: int = 1024 * 1024,
        environment: Mapping[str, str] | None = None,
        expected_runtime_sha256: str | None = None,
        expected_runtime_version: str = "1.2.0",
        expected_model_pack_id: str | None = None,
        expected_model_pack_version: str | None = None,
        expected_handler_id: str | None = None,
        expected_handler_version: str | None = None,
        expected_effective_capabilities: Sequence[str] | None = None,
    ) -> None:
        if not command or any(not item or "\x00" in item for item in command):
            raise ValueError("Rill runtime command must be a non-empty argument vector")
        if not evaluate_capability or len(evaluate_capability) > 96:
            raise ValueError("Rill evaluate capability is invalid")
        if feedback_capability is not None and (
            not feedback_capability or len(feedback_capability) > 96
        ):
            raise ValueError("Rill feedback capability is invalid")
        self._command = tuple(command)
        self._feature_schema_hash = feature_schema_hash
        self._evaluate_capability = evaluate_capability
        self._feedback_capability = feedback_capability
        self._request_timeout_seconds = request_timeout_seconds
        self._startup_timeout_seconds = startup_timeout_seconds
        self._max_message_bytes = max_message_bytes
        self._environment = dict(environment) if environment is not None else None
        self._expected_runtime_sha256 = expected_runtime_sha256
        self._expected_runtime_version = expected_runtime_version
        self._expected_model_pack_id = expected_model_pack_id
        self._expected_model_pack_version = expected_model_pack_version
        self._expected_handler_id = expected_handler_id
        self._expected_handler_version = expected_handler_version
        self._expected_effective_capabilities = (
            tuple(expected_effective_capabilities)
            if expected_effective_capabilities is not None
            else None
        )
        self._process: subprocess.Popen[bytes] | None = None
        self._responses: queue.Queue[bytes | BaseException | None] = queue.Queue(maxsize=4)
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail = bytearray()
        self._lock = threading.Lock()
        self._identity: RuntimeIdentity | None = None
        self._model_pack_id = ""
        self._model_pack_version = ""
        self._handler_version = ""
        self._effective_capabilities: list[str] = []
        self._model_generation = 0
        self._state_generation = 0
        self._verify_runtime_binary()
        self._start()

    @property
    def identity(self) -> RuntimeIdentity:
        if self._identity is None:
            raise RillUnavailableError("Rill v2 handshake has not completed")
        return self._identity

    @property
    def model_generation(self) -> int:
        return self._model_generation

    @property
    def state_generation(self) -> int:
        return self._state_generation

    @property
    def protocol_api_version(self) -> int:
        return 2

    @property
    def model_pack_id(self) -> str:
        return self._model_pack_id

    @property
    def feedback_capability(self) -> str | None:
        return self._feedback_capability

    def _verify_runtime_binary(self) -> None:
        if self._expected_runtime_sha256 is None:
            return
        executable = Path(self._command[0])
        resolved = executable if executable.is_file() else None
        if resolved is None:
            found = shutil.which(self._command[0])
            resolved = Path(found) if found else None
        if resolved is None or not resolved.is_file() or resolved.is_symlink():
            raise RillUnavailableError("configured Rill runtime binary cannot be verified")
        digest = hashlib.sha256()
        with resolved.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != self._expected_runtime_sha256.lower():
            raise RillUnavailableError("configured Rill runtime binary digest mismatch")

    def _start(self) -> None:
        env = None
        if self._environment is not None:
            env = os.environ.copy()
            env.update(self._environment)
        try:
            self._process = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                close_fds=(os.name != "nt"),
                env=env,
            )
        except OSError as exc:
            raise RillUnavailableError("unable to start configured Rill v2 runtime") from exc
        self._reader_thread = threading.Thread(
            target=self._read_stdout, name="rill-v2-stdout", daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr, name="rill-v2-stderr", daemon=True
        )
        self._reader_thread.start()
        self._stderr_thread.start()
        response = self._exchange(
            HandshakeRequestV2(
                request_id=self._request_id("handshake"),
                client_name="document-intelligence",
                client_version=__version__,
            ),
            timeout_seconds=self._startup_timeout_seconds,
        )
        if not isinstance(response, HandshakeResponseV2):
            self.close()
            raise RillProtocolError("Rill runtime did not return a Stable IPC v2 handshake")
        capabilities = self._unique_capabilities(response.capabilities)
        effective = self._unique_capabilities(response.effective_capabilities)
        if not set(effective).issubset(capabilities):
            self.close()
            raise RillProtocolError(
                "Rill effective capabilities are not a subset of model capabilities"
            )
        required = [self._evaluate_capability]
        if self._feedback_capability is not None:
            required.append(self._feedback_capability)
        missing = sorted(set(required) - set(effective))
        if missing:
            self.close()
            raise RillProtocolError("Rill runtime is missing required Stable v2 capabilities")
        if response.runtime_version != self._expected_runtime_version:
            self.close()
            raise RillProtocolError("Rill runtime version differs from the qualified adoption lock")
        if (
            self._expected_model_pack_id is not None
            and response.model_pack_id != self._expected_model_pack_id
        ):
            self.close()
            raise RillProtocolError("Rill model identity differs from the managed bundle")
        if (
            self._expected_model_pack_version is not None
            and response.model_pack_version != self._expected_model_pack_version
        ):
            self.close()
            raise RillProtocolError("Rill model version differs from the managed bundle")
        if (
            self._expected_handler_id is not None
            and response.handler_id != self._expected_handler_id
        ):
            self.close()
            raise RillProtocolError("Rill handler identity differs from the managed bundle")
        if (
            self._expected_handler_version is not None
            and response.handler_version != self._expected_handler_version
        ):
            self.close()
            raise RillProtocolError("Rill handler version differs from the managed bundle")
        if self._expected_effective_capabilities is not None and tuple(effective) != tuple(
            self._expected_effective_capabilities
        ):
            self.close()
            raise RillProtocolError("Rill effective capabilities differ from the managed bundle")
        self._model_pack_id = response.model_pack_id
        self._model_pack_version = response.model_pack_version
        self._handler_version = response.handler_version
        self._effective_capabilities = effective
        self._identity = RuntimeIdentity(
            name=response.handler_id,
            version=response.runtime_version,
            feature_schema_hash=self._feature_schema_hash,
            handler_api_version=response.handler_api_version,
            capabilities=effective,
        )
        if not self.health():
            self.close()
            raise RillUnavailableError("Rill runtime health check is not healthy")

    @staticmethod
    def _unique_capabilities(values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(not value or len(value) > 96 for value in values):
            raise RillProtocolError("Rill v2 capabilities are not bounded and unique")
        return values

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            while True:
                line = process.stdout.readline(self._max_message_bytes + 2)
                if not line:
                    self._put_response(None)
                    return
                if len(line) > self._max_message_bytes + 1 or not line.endswith(b"\n"):
                    self._put_response(
                        RillProtocolError("Rill v2 response exceeded the line limit")
                    )
                    return
                self._put_response(line[:-1])
        except BaseException as exc:  # pragma: no cover - defensive reader boundary
            self._put_response(exc)

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        while True:
            chunk = process.stderr.read(1024)
            if not chunk:
                return
            self._stderr_tail.extend(chunk)
            if len(self._stderr_tail) > 8192:
                del self._stderr_tail[:-8192]

    def _put_response(self, item: bytes | BaseException | None) -> None:
        try:
            self._responses.put_nowait(item)
        except queue.Full:
            self.close()

    def _request_id(self, method: str) -> str:
        return stable_rill_id(
            "rill-v2-request", method, str(time.time_ns()), str(self._state_generation)
        )

    def _exchange(self, request: Any, *, timeout_seconds: float | None = None) -> Any:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None or process.stdin is None:
                raise RillUnavailableError("Rill v2 runtime process is not available")
            request_id = request.request_id
            timeout = timeout_seconds or self._request_timeout_seconds
            wire = encode_request(request, max_bytes=self._max_message_bytes) + b"\n"
            try:
                process.stdin.write(wire)
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self.close()
                raise RillUnavailableError("Rill v2 input channel failed") from exc
            try:
                item = self._responses.get(timeout=timeout)
            except queue.Empty as exc:
                self.close()
                raise RillUnavailableError("Rill v2 request timed out") from exc
            if item is None:
                stderr = self._stderr_tail.decode("utf-8", errors="replace")[-512:]
                self.close()
                raise RillUnavailableError(
                    "Rill v2 runtime exited before returning a response"
                    + (f"; stderr tail: {stderr}" if stderr else "")
                )
            if isinstance(item, BaseException):
                self.close()
                if isinstance(item, RillProtocolError):
                    raise item
                raise RillUnavailableError("Rill v2 reader failed") from item
            try:
                response = parse_response(item, max_bytes=self._max_message_bytes)
            except (ValueError, TypeError) as exc:
                self.close()
                raise RillProtocolError("Rill runtime returned invalid Stable IPC v2 JSON") from exc
            if response.request_id != request_id:
                self.close()
                raise RillProtocolError("Rill v2 response requestId does not match the request")
            if isinstance(response, ErrorResponseV2):
                exception = RillUnavailableError if response.retryable else RillProtocolError
                raise exception(f"Rill v2 runtime error {response.code}: {response.message}")
            return response

    def health(self) -> bool:
        response = self._exchange(HealthRequestV2(request_id=self._request_id("health")))
        if not isinstance(response, HealthResponseV2):
            raise RillProtocolError("Rill v2 health returned the wrong response kind")
        if (
            response.model_pack_id != self._model_pack_id
            or response.model_pack_version != self._model_pack_version
        ):
            raise RillProtocolError("Rill v2 health model identity differs from handshake")
        return response.healthy

    def invoke(self, capability: str, input_value: Any) -> Any:
        if capability not in self.identity.capabilities:
            raise RillProtocolError("Rill v2 invoke capability is not present in the handshake")
        response = self._exchange(
            InvokeRequestV2(
                request_id=self._request_id("invoke"), capability=capability, input=input_value
            )
        )
        if not isinstance(response, ResultResponseV2):
            raise RillProtocolError("Rill v2 invoke returned the wrong response kind")
        return response.output

    def observe(self, event: RillObserveEvent) -> None:
        del event
        # Stable v2 has no stateful observe request. Observation is included in
        # the bounded evaluate input and remains owned by the LessonForge Host.

    def decide(
        self,
        event: RillObserveEvent,
        *,
        static_suggestion: PolicySuggestion,
        deterministic_seed: int,
    ) -> PolicySuggestion:
        output = self.invoke(
            self._evaluate_capability,
            {
                "operation": "evaluate",
                "eventId": event.event_id,
                "observation": event.model_dump(mode="json"),
                "features": event.feature_dict(),
                "allowedActions": [item.value for item in ACTION_ARMS],
                "staticSuggestion": static_suggestion.model_dump(mode="json"),
                "deterministicSeed": deterministic_seed,
                "hostState": {
                    "modelGeneration": self.model_generation,
                    "stateGeneration": self.state_generation,
                },
            },
        )
        if not isinstance(output, dict):
            raise RillProtocolError("Rill v2 evaluate output must be a JSON object")
        candidate = output.get("suggestion", output)
        if not isinstance(candidate, dict) or "action" not in candidate:
            raise RillProtocolError("Rill v2 evaluate output lacks a bounded action suggestion")
        parsed = _DecisionOutput.model_validate(candidate)
        arm = (
            parsed.selected_arm if parsed.selected_arm is not None else ACTION_TO_ARM[parsed.action]
        )
        if arm >= len(ACTION_ARMS) or ACTION_ARMS[arm] != parsed.action:
            raise RillProtocolError("Rill v2 selected arm is outside the Host allowlist")
        return PolicySuggestion(
            decision_id=parsed.decision_id
            or stable_rill_id("rill-v2-decision", event.event_id, str(deterministic_seed)),
            action=parsed.action,
            selected_arm=arm,
            policy_version=parsed.policy_version,
            confidence=parsed.confidence,
            reason_codes=parsed.reason_codes,
            source="rill_runtime",
            model_generation=self.model_generation,
            state_generation=self.state_generation,
        )

    def feedback(
        self,
        *,
        decision_id: str,
        selected_arm: int,
        reward: float,
        outcome_time_ms: int,
        generation: int,
    ) -> None:
        if self._feedback_capability is None:
            raise RillProtocolError("Rill v2 update capability is not configured")
        self.invoke(
            self._feedback_capability,
            {
                "operation": "feedback",
                "decisionId": decision_id,
                "selectedArm": selected_arm,
                "reward": reward,
                "outcomeTimeMs": outcome_time_ms,
                "generation": generation,
                "hostOwnedState": True,
            },
        )

    def inspect(self) -> dict[str, Any]:
        return {
            "protocol": "stable-v2",
            "hostOwnedState": True,
            "modelPackId": self._model_pack_id,
            "modelPackVersion": self._model_pack_version,
            "handlerVersion": self._handler_version,
            "effectiveCapabilities": list(self._effective_capabilities),
            "evaluateCapability": self._evaluate_capability,
            "feedbackCapability": self._feedback_capability,
            "runtimeVersion": self.identity.version,
            "runtimeReset": False,
        }

    def snapshot(self) -> RuntimeSnapshot:
        state = json.dumps(self.inspect(), sort_keys=True, separators=(",", ":"))
        return RuntimeSnapshot(
            state_schema_version=1,
            state_checksum=hashlib.sha256(state.encode("utf-8")).hexdigest(),
            state=state,
            model_generation=self.model_generation,
            state_generation=self.state_generation,
        )

    def reset(self, *, expected_state_generation: int) -> int:
        if expected_state_generation != self.state_generation:
            raise RillProtocolError("Rill v2 host state generation mismatch")
        self._state_generation += 1
        return self._state_generation

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                with suppress(OSError):
                    stream.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)
