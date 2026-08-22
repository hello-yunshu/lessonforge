from __future__ import annotations

import json
import sys

CAPABILITIES = (
    sys.argv[1].split(",")
    if len(sys.argv) > 1
    else [
        "org.lessonforge.shadow.evaluate",
        "org.lessonforge.shadow.update",
    ]
)
MODE = sys.argv[2] if len(sys.argv) > 2 else "normal"
STATE = 0


def emit(request_id: str, body: dict[str, object]) -> None:
    print(
        json.dumps(
            {
                **body,
                "requestId": request_id,
                "apiVersion": 2,
            },
            separators=(",", ":"),
        ),
        flush=True,
    )


for line in sys.stdin:
    request = json.loads(line)
    request_id = request["requestId"]
    method = request["method"]
    if MODE == "malformed":
        print("not-json", flush=True)
        continue
    if method == "handshake":
        emit(
            request_id,
            {
                "kind": "handshake",
                "runtimeVersion": "1.2.0",
                "modelPackId": "lessonforge.test",
                "modelPackVersion": "1.2.0",
                "capabilities": CAPABILITIES,
                "handlerId": "lessonforge.test.handler",
                "handlerVersion": "1.2.0",
                "handlerApiVersion": 1,
                "effectiveCapabilities": CAPABILITIES,
            },
        )
    elif method == "health":
        emit(
            request_id,
            {
                "kind": "health",
                "healthy": MODE != "unhealthy",
                "modelPackId": "lessonforge.test",
                "modelPackVersion": "1.2.0",
            },
        )
    elif method == "invoke":
        capability = request["capability"]
        if capability == "org.lessonforge.shadow.evaluate":
            emit(
                request_id,
                {
                    "kind": "result",
                    "output": {
                        "decisionId": "v2-decision",
                        "action": "HUMAN_REVIEW",
                        "selectedArm": 7,
                        "policyVersion": "lessonforge-test-v2",
                        "confidence": 0.9,
                        "reasonCodes": ["TEST_STABLE_V2"],
                    },
                },
            )
        elif capability == "org.lessonforge.shadow.update":
            STATE += 1
            emit(request_id, {"kind": "result", "output": {"accepted": True}})
        elif capability == "rillml.linearRegression.predict":
            emit(request_id, {"kind": "result", "output": request["input"]})
        else:
            emit(
                request_id,
                {
                    "kind": "error",
                    "code": "unsupportedCapability",
                    "message": "unsupported capability",
                    "retryable": False,
                },
            )
