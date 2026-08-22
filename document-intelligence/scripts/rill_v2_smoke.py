from __future__ import annotations

import argparse
import json
from pathlib import Path

from document_intelligence.rill.adoption import (
    load_adoption_lock,
    select_runtime,
    verify_artifact_file,
    verify_locked_release_index,
)
from document_intelligence.rill.stable_client import StableV2RillClient


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Handshake, Health and Invoke against official RillML v1.2.0"
    )
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("handler", type=Path)
    args = parser.parse_args()
    lock = load_adoption_lock()
    raw_index = args.index.read_bytes()
    index = verify_locked_release_index(raw_index, lock=lock)
    runtime_artifact = select_runtime(index, target=("linux", "x86_64", "gnu"), lock=lock)
    model_artifact = next(
        artifact
        for artifact in index.payload.artifacts
        if artifact.kind == "model" and artifact.id == "rillml.example.default"
    )
    handler_artifact = next(
        artifact
        for artifact in index.payload.artifacts
        if artifact.kind == "handler" and artifact.id == "rillml.echo.handler"
    )
    verify_artifact_file(args.runtime, runtime_artifact)
    verify_artifact_file(args.model, model_artifact)
    verify_artifact_file(args.handler, handler_artifact)
    key_id, public_key = next(iter(lock.trust.model.items()))
    handler_key_id, handler_public_key = next(iter(lock.trust.handler.items()))
    command = [
        str(args.runtime),
        "serve",
        "--pack",
        str(args.model),
        "--handler",
        str(args.handler),
        "--model-trust-key",
        f"{key_id}={public_key}",
        "--handler-trust-key",
        f"{handler_key_id}={handler_public_key}",
    ]
    client = StableV2RillClient(
        command,
        feature_schema_hash="0" * 64,
        evaluate_capability="rillml.linearRegression.predict",
        feedback_capability=None,
        expected_runtime_sha256=None,
        startup_timeout_seconds=10,
        request_timeout_seconds=10,
    )
    try:
        output = client.invoke("rillml.linearRegression.predict", {"features": [1.0, 2.0]})
        if output != {"features": [1.0, 2.0]}:
            raise SystemExit("official echo handler returned an unexpected v2 Invoke output")
        print(
            json.dumps(
                {"status": "PASS", "protocol": "stable-v2", "output": output},
                sort_keys=True,
            )
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
