from __future__ import annotations

from document_intelligence.rill.models import (
    ACTION_TO_ARM,
    FeedbackSeverity,
    PolicySuggestion,
    RillObserveEvent,
    ShadowAction,
    stable_rill_id,
)

STATIC_POLICY_VERSION = "document-static-shadow-0.5.0"


class StaticShadowPolicy:
    def decide(self, event: RillObserveEvent) -> PolicySuggestion:
        signals = event.signals
        parse = signals.parse
        reasons: list[str] = []
        action = ShadowAction.ACCEPT
        confidence = 0.90

        if parse.p0_warnings > 0:
            action = ShadowAction.QUARANTINE
            reasons.append("PARSE_P0_WARNING")
            confidence = 0.99
        elif signals.domain is not None and signals.domain.fallback_used:
            action = ShadowAction.HUMAN_REVIEW
            reasons.append("DOMAIN_FALLBACK")
            confidence = 0.96
        elif signals.domain is not None and signals.domain.error_findings > 0:
            action = ShadowAction.HUMAN_REVIEW
            reasons.append("DOMAIN_VALIDATION_ERROR")
            confidence = 0.95
        elif signals.structure is not None and signals.structure.diagnostics_error > 0:
            action = ShadowAction.HUMAN_REVIEW
            reasons.append("STRUCTURE_DIAGNOSTIC_ERROR")
            confidence = 0.95
        elif signals.matching is not None and signals.matching.decision == "ambiguous":
            action = ShadowAction.HUMAN_REVIEW
            reasons.append("AMBIGUOUS_STANDARD_MATCH")
            confidence = 0.94
        elif parse.empty_native_text:
            action = ShadowAction.USE_SECONDARY_PARSER
            reasons.append("EMPTY_NATIVE_TEXT")
            confidence = 0.93
        elif parse.average_confidence < 0.75 or parse.minimum_confidence < 0.35:
            action = ShadowAction.USE_SECONDARY_PARSER
            reasons.append("LOW_PARSE_CONFIDENCE")
            confidence = 0.88
        elif (
            signals.structure is not None
            and signals.structure.consistency_score < 0.70
        ):
            action = ShadowAction.HUMAN_REVIEW
            reasons.append("LOW_STRUCTURE_CONSISTENCY")
            confidence = 0.86
        elif (
            signals.matching is not None
            and signals.matching.decision == "no_match"
            and signals.matching.top1_score >= 0.70
        ):
            action = ShadowAction.HUMAN_REVIEW
            reasons.append("NEAR_MATCH_WITHOUT_SAFE_REUSE")
            confidence = 0.82
        else:
            reasons.append("STATIC_GATES_PASSED")

        decision_id = stable_rill_id(
            "static-decision",
            event.event_id,
            action.value,
            STATIC_POLICY_VERSION,
        )
        return PolicySuggestion(
            decision_id=decision_id,
            action=action,
            selected_arm=ACTION_TO_ARM[action],
            policy_version=STATIC_POLICY_VERSION,
            confidence=confidence,
            reason_codes=reasons,
            source="static_policy",
        )


def calculate_reward(
    *,
    decision_correct: bool,
    severity: FeedbackSeverity,
    human_edit_seconds: float,
    suggested_action: ShadowAction,
    actual_action: ShadowAction,
) -> float:
    reward = 1.0 if decision_correct else -1.0
    if not decision_correct:
        reward -= {
            FeedbackSeverity.P0: 50.0,
            FeedbackSeverity.P1: 10.0,
            FeedbackSeverity.P2: 2.0,
        }[severity]
    if suggested_action == ShadowAction.ACCEPT and severity in {
        FeedbackSeverity.P0,
        FeedbackSeverity.P1,
    }:
        reward -= 20.0
    if suggested_action != actual_action:
        reward -= 0.5
    reward -= min(2.0, human_edit_seconds / 300.0)
    return max(-100.0, min(10.0, round(reward, 6)))
