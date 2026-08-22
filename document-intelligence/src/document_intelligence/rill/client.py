from __future__ import annotations

import hashlib
import json
import os
import queue
import random
import subprocess
import shutil
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field

from document_intelligence import __version__
from document_intelligence.exceptions import (
    RillProtocolError,
    RillUnavailableError,
)
from document_intelligence.rill.models import (
    ACTION_ARMS,
    ACTION_TO_ARM,
    PolicySuggestion,
    RillObserveEvent,
    RuntimeIdentity,
    ShadowAction,
    stable_rill_id,
)
from document_intelligence.rill.protocol import (
    DecideRequestV3,
    EnvelopeV3,
    ErrorBodyV3,
    FeedbackRequestV3,
    HandshakeBodyV3,
    HandshakeRequestV3,
    HealthBodyV3,
    HealthRequestV3,
    IdentityV3,
    InspectRequestV3,
    InspectionBodyV3,
    ObserveRequestV3,
    ResetBodyV3,
    ResetRequestV3,
    ResultBodyV3,
    RuntimeResponseV3,
    SnapshotBodyV3,
    SnapshotRequestV3,
)

CAPABILITY_OBSERVE = "org.document-intelligence.shadow.observe"
CAPABILITY_DECIDE = "org.document-intelligence.shadow.decide"
CAPABILITY_FEEDBACK = "org.document-intelligence.shadow.feedback"
CAPABILITY_INSPECT = "org.document-intelligence.shadow.inspect"
CAPABILITY_SNAPSHOT = "org.document-intelligence.shadow.snapshot"
CAPABILITY_RESET = "org.document-intelligence.shadow.reset"
REQUIRED_CAPABILITIES = (
    CAPABILITY_OBSERVE,
    CAPABILITY_DECIDE,
    CAPABILITY_FEEDBACK,
    CAPABILITY_INSPECT,
    CAPABILITY_SNAPSHOT,
    CAPABILITY_RESET,
)


class RillDecisionOutput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        alias_generator=lambda value: value.split("_")[0]
        + "".join(part.capitalize() for part in value.split("_")[1:]),
    )

    decision_id: str = Field(min_length=1, max_length=128)
    action: ShadowAction
    selected_arm: int = Field(ge=0)
    policy_version: str = Field(min_length=1, max_length=127)
    confidence: float = Field(ge=0.0, le=1.0)
    reason_codes: list[str] = Field(min_length=1, max_length=32)


@dataclass(frozen=True)
class RuntimeSnapshot:
    state_schema_version: int
    state_checksum: str
    state: str
    model_generation: int
    state_generation: int


class RillShadowClient(Protocol):

    @property
    def identity(self) -> RuntimeIdentity:
        ...

    @property
    def model_generation(self) -> int:
        ...

    @property
    def state_generation(self) -> int:
        ...

    def observe(self, event: RillObserveEvent) -> None:
        ...

    def decide(
        self,
        event: RillObserveEvent,
        *,
        static_suggestion: PolicySuggestion,
        deterministic_seed: int,
    ) -> PolicySuggestion:
        ...

    def feedback(
        self,
        *,
        decision_id: str,
        selected_arm: int,
        reward: float,
        outcome_time_ms: int,
        generation: int,
    ) -> None:
        ...

    def inspect(self) -> dict[str, Any]:
        ...

    def snapshot(self) -> RuntimeSnapshot:
        ...

    def reset(self, *, expected_state_generation: int) -> int:
        ...

    def close(self) -> None:
        ...


class SubprocessRillClient:
    """Preview-only newline-delimited IPC v3 client.

    This client is retained for future RillML Preview qualification tests. It
    is not imported by the LessonForge 1.2 production bootstrap and must not
    be used to claim Stable RillML 1.2 support.

    The command is executed directly with ``shell=False``.  A timed-out or
    malformed exchange closes the process so that a late response can never be
    mistaken for a later request.
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        feature_schema_hash: str,
        request_timeout_seconds: float = 5.0,
        startup_timeout_seconds: float = 5.0,
        max_message_bytes: int = 1024 * 1024,
        environment: Mapping[str, str] | None = None,
        expected_runtime_sha256: str | None = None,
    ) -> None:
        if not command or any(not item or "\x00" in item for item in command):
            raise ValueError("Rill runtime command must be a non-empty argument vector")
        self._command = tuple(command)
        self._feature_schema_hash = feature_schema_hash
        self._request_timeout_seconds = request_timeout_seconds
        self._startup_timeout_seconds = startup_timeout_seconds
        self._max_message_bytes = max_message_bytes
        self._process: subprocess.Popen[bytes] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._responses: queue.Queue[bytes | BaseException | None] = queue.Queue(maxsize=4)
        self._lock = threading.Lock()
        self._stderr_tail = bytearray()
        self._identity: RuntimeIdentity | None = None
        self._model_generation = 0
        self._state_generation = 0
        self._environment = dict(environment) if environment is not None else None
        self._expected_runtime_sha256 = expected_runtime_sha256
        self._verify_runtime_binary()
        self._start()

    def _verify_runtime_binary(self) -> None:
        if self._expected_runtime_sha256 is None:
            return
        executable = self._command[0]
        candidate = Path(executable)
        try:
            # Preview compatibility accepts interpreter symlinks and hashes
            # their resolved target; production Stable v2 remains strict.
            resolved = candidate.resolve(strict=True) if candidate.is_file() else None
        except OSError:
            resolved = None
        if resolved is None:
            found = shutil.which(executable)
            if found is not None:
                try:
                    resolved = Path(found).resolve(strict=True)
                except OSError:
                    resolved = None
        if resolved is None or not resolved.is_file():
            raise RillUnavailableError("configured Rill runtime binary cannot be verified")
        digest = hashlib.sha256()
        with resolved.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != self._expected_runtime_sha256:
            raise RillUnavailableError("configured Rill runtime binary digest mismatch")

    @property
    def identity(self) -> RuntimeIdentity:
        if self._identity is None:
            raise RillUnavailableError("Rill runtime handshake has not completed")
        return self._identity

    @property
    def model_generation(self) -> int:
        return self._model_generation

    @property
    def state_generation(self) -> int:
        return self._state_generation

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
            raise RillUnavailableError("unable to start configured Rill runtime") from exc
        self._reader_thread = threading.Thread(
            target=self._read_stdout,
            name="rill-runtime-stdout",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr,
            name="rill-runtime-stderr",
            daemon=True,
        )
        self._reader_thread.start()
        self._stderr_thread.start()
        response = self._exchange(
            HandshakeRequestV3(),
            capability=None,
            feature_schema_hash=None,
            timeout_seconds=self._startup_timeout_seconds,
        )
        if not isinstance(response.response, HandshakeBodyV3):
            self.close()
            raise RillProtocolError("Rill runtime did not return an IPC v3 handshake")
        body = response.response
        if body.feature_schema_hash != self._feature_schema_hash:
            self.close()
            raise RillProtocolError("Rill feature schema hash differs from the host schema")
        missing = sorted(set(REQUIRED_CAPABILITIES) - set(body.capabilities))
        if missing:
            self.close()
            raise RillProtocolError("Rill runtime is missing required shadow capabilities")
        self._identity = RuntimeIdentity(
            name=response.runtime_identity.name,
            version=response.runtime_identity.version,
            feature_schema_hash=body.feature_schema_hash,
            handler_api_version=body.handler_api_version,
            capabilities=body.capabilities,
        )

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
                    self._put_response(RillProtocolError("Rill response exceeded the line limit"))
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
            "rill-request",
            method,
            str(time.time_ns()),
            str(self._model_generation),
            str(self._state_generation),
        )

    def _exchange(
        self,
        request: Any,
        *,
        capability: str | None,
        feature_schema_hash: str | None = None,
        timeout_seconds: float | None = None,
        accepted_error_codes: frozenset[str] = frozenset(),
    ) -> RuntimeResponseV3:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None or process.stdin is None:
                raise RillUnavailableError("Rill runtime process is not available")
            request_id = self._request_id(request.method)
            timeout = timeout_seconds or self._request_timeout_seconds
            envelope = EnvelopeV3(
                request_id=request_id,
                client_identity=IdentityV3(
                    name="document-intelligence",
                    version=__version__,
                ),
                capability=capability,
                deadline_unix_ms=int(time.time() * 1000 + timeout * 1000),
                feature_schema_hash=feature_schema_hash,
                model_generation=self._model_generation,
                state_generation=self._state_generation,
                payload_limit=self._max_message_bytes,
                request=request,
            )
            wire = envelope.to_wire_bytes() + b"\n"
            try:
                process.stdin.write(wire)
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self.close()
                raise RillUnavailableError("Rill runtime input channel failed") from exc
            try:
                item = self._responses.get(timeout=timeout)
            except queue.Empty as exc:
                self.close()
                raise RillUnavailableError("Rill runtime request timed out") from exc
            if item is None:
                stderr = self._stderr_tail.decode("utf-8", errors="replace")[-512:]
                self.close()
                raise RillUnavailableError(
                    "Rill runtime exited before returning a response"
                    + (f"; stderr tail: {stderr}" if stderr else "")
                )
            if isinstance(item, BaseException):
                self.close()
                if isinstance(item, RillProtocolError):
                    raise item
                raise RillUnavailableError("Rill runtime reader failed") from item
            try:
                response = RuntimeResponseV3.from_wire_bytes(
                    item,
                    max_bytes=self._max_message_bytes,
                )
            except (ValueError, json.JSONDecodeError) as exc:
                self.close()
                raise RillProtocolError("Rill runtime returned invalid IPC v3 JSON") from exc
            if response.request_id != request_id:
                self.close()
                raise RillProtocolError("Rill response requestId does not match the request")
            self._model_generation = response.model_generation
            self._state_generation = response.state_generation
            if isinstance(response.response, ErrorBodyV3):
                error = response.response.error
                if error.code in accepted_error_codes:
                    return response
                exc_type = RillUnavailableError if error.retryable else RillProtocolError
                raise exc_type(f"Rill runtime error {error.code}: {error.message}")
            return response

    def health(self) -> bool:
        response = self._exchange(
            HealthRequestV3(),
            capability=None,
            feature_schema_hash=None,
        )
        if not isinstance(response.response, HealthBodyV3):
            raise RillProtocolError("Rill health request returned the wrong response kind")
        return response.response.healthy

    def observe(self, event: RillObserveEvent) -> None:
        response = self._exchange(
            ObserveRequestV3(event=event.model_dump(mode="json")),
            capability=CAPABILITY_OBSERVE,
            feature_schema_hash=self._feature_schema_hash,
        )
        if not isinstance(response.response, ResultBodyV3):
            raise RillProtocolError("Rill observe returned the wrong response kind")

    def decide(
        self,
        event: RillObserveEvent,
        *,
        static_suggestion: PolicySuggestion,
        deterministic_seed: int,
    ) -> PolicySuggestion:
        context = {
            "features": event.feature_dict(),
            "allowedActions": [item.value for item in ACTION_ARMS],
            "staticSuggestion": static_suggestion.model_dump(mode="json"),
            "shadowOnly": True,
        }
        response = self._exchange(
            DecideRequestV3(context=context, deterministic_seed=deterministic_seed),
            capability=CAPABILITY_DECIDE,
            feature_schema_hash=self._feature_schema_hash,
        )
        if not isinstance(response.response, ResultBodyV3):
            raise RillProtocolError("Rill decide returned the wrong response kind")
        output = RillDecisionOutput.model_validate(response.response.output)
        if output.selected_arm >= len(ACTION_ARMS):
            raise RillProtocolError("Rill selected arm is outside the host allowlist")
        if ACTION_ARMS[output.selected_arm] != output.action:
            raise RillProtocolError("Rill selected arm does not match the requested action")
        return PolicySuggestion(
            decision_id=output.decision_id,
            action=output.action,
            selected_arm=output.selected_arm,
            policy_version=output.policy_version,
            confidence=output.confidence,
            reason_codes=output.reason_codes,
            source="rill_runtime",
            model_generation=response.model_generation,
            state_generation=response.state_generation,
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
        response = self._exchange(
            FeedbackRequestV3(
                decision_id=decision_id,
                selected_arm=selected_arm,
                reward=reward,
                outcome_time_ms=outcome_time_ms,
                generation=generation,
            ),
            capability=CAPABILITY_FEEDBACK,
            feature_schema_hash=self._feature_schema_hash,
            # A prior runtime acceptance followed by a local persistence failure
            # must be safely retryable without learning the same outcome twice.
            accepted_error_codes=frozenset({"duplicateFeedback"}),
        )
        if isinstance(response.response, ErrorBodyV3):
            return
        if not isinstance(response.response, ResultBodyV3):
            raise RillProtocolError("Rill feedback returned the wrong response kind")

    def inspect(self) -> dict[str, Any]:
        response = self._exchange(
            InspectRequestV3(),
            capability=CAPABILITY_INSPECT,
            feature_schema_hash=self._feature_schema_hash,
        )
        if not isinstance(response.response, InspectionBodyV3):
            raise RillProtocolError("Rill inspect returned the wrong response kind")
        if not isinstance(response.response.summary, dict):
            raise RillProtocolError("Rill inspection summary must be a JSON object")
        return cast(dict[str, Any], response.response.summary)

    def snapshot(self) -> RuntimeSnapshot:
        response = self._exchange(
            SnapshotRequestV3(),
            capability=CAPABILITY_SNAPSHOT,
            feature_schema_hash=self._feature_schema_hash,
        )
        if not isinstance(response.response, SnapshotBodyV3):
            raise RillProtocolError("Rill snapshot returned the wrong response kind")
        body = response.response
        actual = hashlib.sha256(body.state.encode("utf-8")).hexdigest()
        if actual != body.state_checksum:
            raise RillProtocolError("Rill snapshot state checksum is invalid")
        return RuntimeSnapshot(
            state_schema_version=body.state_schema_version,
            state_checksum=body.state_checksum,
            state=body.state,
            model_generation=response.model_generation,
            state_generation=response.state_generation,
        )

    def reset(self, *, expected_state_generation: int) -> int:
        response = self._exchange(
            ResetRequestV3(expected_state_generation=expected_state_generation),
            capability=CAPABILITY_RESET,
            feature_schema_hash=self._feature_schema_hash,
        )
        if not isinstance(response.response, ResetBodyV3) or not response.response.reset:
            raise RillProtocolError("Rill runtime did not acknowledge reset")
        return response.state_generation

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)


# Explicit name for callers and tests that need to make the Preview boundary
# visible without breaking the existing compatibility import.
PreviewSubprocessRillClient = SubprocessRillClient


class ReferenceRillShadowClient:
    """Deterministic test/development client with the Rill Shadow lifecycle.

    It is deliberately rejected unless the explicit reference-backend setting
    is enabled.  It is not presented as ``rill-runtime`` and never executes
    document-processing actions.
    """

    def __init__(self, feature_schema_hash: str) -> None:
        self._feature_schema_hash = feature_schema_hash
        self._model_generation = 1
        self._state_generation = 0
        self._observed = 0
        self._decisions: dict[str, int] = {}
        self._feedback: set[str] = set()
        self._counts = [0 for _ in ACTION_ARMS]
        self._rewards = [0.0 for _ in ACTION_ARMS]
        self._identity = RuntimeIdentity(
            name="document-rill-reference-shadow",
            version="0.5.0",
            feature_schema_hash=feature_schema_hash,
            handler_api_version=1,
            capabilities=list(REQUIRED_CAPABILITIES),
        )

    @property
    def identity(self) -> RuntimeIdentity:
        return self._identity

    @property
    def model_generation(self) -> int:
        return self._model_generation

    @property
    def state_generation(self) -> int:
        return self._state_generation

    def observe(self, event: RillObserveEvent) -> None:
        del event
        self._observed += 1
        self._state_generation += 1

    def decide(
        self,
        event: RillObserveEvent,
        *,
        static_suggestion: PolicySuggestion,
        deterministic_seed: int,
    ) -> PolicySuggestion:
        rng = random.Random(deterministic_seed)
        baseline_arm = static_suggestion.selected_arm
        scored: list[tuple[float, int]] = []
        total = max(1, sum(self._counts))
        for arm, count in enumerate(self._counts):
            if count == 0:
                score = 0.0
            else:
                mean = self._rewards[arm] / count
                score = mean + (2.0 * (total ** 0.5) / count)
            if arm == baseline_arm:
                score += 1.0
            score += rng.random() * 1e-9
            scored.append((score, arm))
        _, selected_arm = max(scored)
        action = ACTION_ARMS[selected_arm]
        decision_id = stable_rill_id(
            "rill-decision",
            event.event_id,
            str(deterministic_seed),
            str(self._state_generation),
        )
        self._decisions[decision_id] = selected_arm
        return PolicySuggestion(
            decision_id=decision_id,
            action=action,
            selected_arm=selected_arm,
            policy_version="reference-shadow-ucb-0.5.0",
            confidence=0.65 if action != static_suggestion.action else 0.85,
            reason_codes=[
                "REFERENCE_SHADOW_ONLY",
                "STATIC_PRIOR" if action == static_suggestion.action else "ONLINE_REWARD_PRIOR",
            ],
            source="reference_runtime",
            model_generation=self._model_generation,
            state_generation=self._state_generation,
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
        del outcome_time_ms
        if decision_id in self._feedback:
            raise RillProtocolError("duplicate feedback")
        if generation > self._state_generation:
            raise RillProtocolError("feedback generation is ahead of runtime state")
        if self._decisions.get(decision_id) != selected_arm:
            raise RillProtocolError("feedback selected arm differs from the decision ledger")
        self._feedback.add(decision_id)
        self._counts[selected_arm] += 1
        self._rewards[selected_arm] += reward
        self._state_generation += 1

    def inspect(self) -> dict[str, Any]:
        return {
            "shadowOnly": True,
            "observed": self._observed,
            "decisions": len(self._decisions),
            "feedback": len(self._feedback),
            "counts": self._counts,
            "meanRewards": [
                self._rewards[index] / count if count else None
                for index, count in enumerate(self._counts)
            ],
        }

    def snapshot(self) -> RuntimeSnapshot:
        state = json.dumps(
            {
                "observed": self._observed,
                "decisions": self._decisions,
                "feedback": sorted(self._feedback),
                "counts": self._counts,
                "rewards": self._rewards,
                "modelGeneration": self._model_generation,
                "stateGeneration": self._state_generation,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        checksum = hashlib.sha256(state.encode("utf-8")).hexdigest()
        return RuntimeSnapshot(
            state_schema_version=1,
            state_checksum=checksum,
            state=state,
            model_generation=self._model_generation,
            state_generation=self._state_generation,
        )

    def restore(self, snapshot: RuntimeSnapshot) -> None:
        if hashlib.sha256(snapshot.state.encode("utf-8")).hexdigest() != snapshot.state_checksum:
            raise RillProtocolError("reference snapshot checksum mismatch")
        state = json.loads(snapshot.state)
        self._observed = int(state["observed"])
        self._decisions = {str(key): int(value) for key, value in state["decisions"].items()}
        self._feedback = {str(value) for value in state["feedback"]}
        self._counts = [int(value) for value in state["counts"]]
        self._rewards = [float(value) for value in state["rewards"]]
        self._model_generation = int(state["modelGeneration"])
        self._state_generation = int(state["stateGeneration"])

    def reset(self, *, expected_state_generation: int) -> int:
        if expected_state_generation != self._state_generation:
            raise RillProtocolError("state generation mismatch")
        self._observed = 0
        self._decisions.clear()
        self._feedback.clear()
        self._counts = [0 for _ in ACTION_ARMS]
        self._rewards = [0.0 for _ in ACTION_ARMS]
        self._state_generation += 1
        return self._state_generation

    def close(self) -> None:
        return None
