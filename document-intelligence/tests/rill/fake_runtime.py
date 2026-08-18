from __future__ import annotations

import hashlib
import json
import sys

FEATURE_HASH = sys.argv[1]
CAPS = [
    "org.document-intelligence.shadow.observe",
    "org.document-intelligence.shadow.decide",
    "org.document-intelligence.shadow.feedback",
    "org.document-intelligence.shadow.inspect",
    "org.document-intelligence.shadow.snapshot",
    "org.document-intelligence.shadow.reset",
]
state_generation = 0
model_generation = 1
feedback_seen: set[str] = set()


def emit(request_id: str, body: dict) -> None:
    print(json.dumps({
        "requestId": request_id,
        "apiVersion": 3,
        "runtimeIdentity": {"name": "fake-rill-runtime", "version": "0.15.0"},
        "modelGeneration": model_generation,
        "stateGeneration": state_generation,
        "response": body,
    }, separators=(",", ":")), flush=True)

for line in sys.stdin:
    request = json.loads(line)
    request_id = request["requestId"]
    method = request["request"]["method"]
    if method == "handshake":
        emit(request_id, {"kind": "handshake", "capabilities": CAPS,
                          "featureSchemaHash": FEATURE_HASH, "handlerApiVersion": 1})
    elif method == "health":
        emit(request_id, {"kind": "health", "healthy": True})
    elif method == "observe":
        state_generation += 1
        emit(request_id, {"kind": "result", "output": {"observed": True}})
    elif method == "decide":
        static = request["request"]["context"]["staticSuggestion"]
        action = static["action"]
        arm = request["request"]["context"]["allowedActions"].index(action)
        decision_id = "decision-" + hashlib.sha256(request_id.encode()).hexdigest()[:24]
        emit(request_id, {"kind": "result", "output": {
            "decisionId": decision_id,
            "action": action,
            "selectedArm": arm,
            "policyVersion": "fake-v3",
            "confidence": 0.75,
            "reasonCodes": ["STATIC_SHADOW_REFERENCE"],
        }})
    elif method == "feedback":
        decision_id = request["request"]["decisionId"]
        if decision_id in feedback_seen:
            emit(request_id, {"kind": "error", "error": {
                "code": "duplicateFeedback", "message": "already learned", "retryable": False
            }})
        else:
            feedback_seen.add(decision_id)
            state_generation += 1
            emit(request_id, {"kind": "result", "output": {"accepted": True}})
    elif method == "inspect":
        emit(request_id, {"kind": "inspection", "summary": {
            "shadowOnly": True, "feedbackCount": len(feedback_seen)
        }})
    elif method == "snapshot":
        state = json.dumps({"generation": state_generation}, separators=(",", ":"))
        emit(request_id, {"kind": "snapshot", "stateSchemaVersion": 1,
                          "stateChecksum": hashlib.sha256(state.encode()).hexdigest(),
                          "state": state})
    elif method == "reset":
        expected = request["request"]["expectedStateGeneration"]
        if expected != state_generation:
            emit(request_id, {"kind": "error", "error": {
                "code": "stateMismatch", "message": "generation mismatch", "retryable": True
            }})
        else:
            state_generation += 1
            feedback_seen.clear()
            emit(request_id, {"kind": "reset", "reset": True})
