from __future__ import annotations

from document_intelligence.rill.models import (
    DomainSignals,
    FeedbackSeverity,
    MatchSignals,
    ParseSignals,
    RillObserveEvent,
    ShadowAction,
    ShadowSignals,
    StructureSignals,
)
from document_intelligence.rill.policy import StaticShadowPolicy, calculate_reward


def parse(**updates) -> ParseSignals:
    values = dict(page_count=1, element_count=2, average_confidence=.95,
                  minimum_confidence=.9, p0_warnings=0, p1_warnings=0,
                  p2_warnings=0, empty_native_text=False, duration_ms=1,
                  estimated_cost_usd=0)
    values.update(updates)
    return ParseSignals(**values)


def structure(**updates) -> StructureSignals:
    values = dict(reading_order_coverage=1, relation_evidence_coverage=1,
                  consistency_score=.95, diagnostics_info=0,
                  diagnostics_warning=0, diagnostics_error=0,
                  cross_page_relations=0)
    values.update(updates)
    return StructureSignals(**values)


def domain(**updates) -> DomainSignals:
    values = dict(status="succeeded", annotations=1, relations=0,
                  validation_findings=0, error_findings=0,
                  evidence_coverage=1, fallback_used=False)
    values.update(updates)
    return DomainSignals(**values)


def match(**updates) -> MatchSignals:
    values = dict(decision="safe_standard_reuse", top1_score=.95,
                  margin=.2, candidate_count=1, safe_standard_reuse=True)
    values.update(updates)
    return MatchSignals(**values)


def action(*, p=None, m=None, s=None, d=None) -> ShadowAction:
    event = RillObserveEvent(event_id="observe-policy", parse_run_id="run-policy",
                             parser_id="fixture", signals=ShadowSignals(
                                 parse=p or parse(), matching=m, structure=s, domain=d))
    return StaticShadowPolicy().decide(event).action


def test_static_policy_covers_every_gate() -> None:
    assert action(p=parse(p0_warnings=1)) == ShadowAction.QUARANTINE
    assert (
        action(d=domain(status="fallback_generic", fallback_used=True))
        == ShadowAction.HUMAN_REVIEW
    )
    assert action(d=domain(error_findings=1)) == ShadowAction.HUMAN_REVIEW
    assert action(s=structure(diagnostics_error=1)) == ShadowAction.HUMAN_REVIEW
    assert (
        action(m=match(decision="ambiguous", safe_standard_reuse=False))
        == ShadowAction.HUMAN_REVIEW
    )
    assert action(p=parse(empty_native_text=True)) == ShadowAction.USE_SECONDARY_PARSER
    assert action(p=parse(average_confidence=.7)) == ShadowAction.USE_SECONDARY_PARSER
    assert action(p=parse(minimum_confidence=.3)) == ShadowAction.USE_SECONDARY_PARSER
    assert action(s=structure(consistency_score=.6)) == ShadowAction.HUMAN_REVIEW
    assert action(m=match(decision="no_match", top1_score=.75,
                          safe_standard_reuse=False)) == ShadowAction.HUMAN_REVIEW
    assert action() == ShadowAction.ACCEPT


def test_reward_has_severity_cost_and_bounds() -> None:
    assert calculate_reward(decision_correct=True, severity=FeedbackSeverity.P2,
                            human_edit_seconds=0, suggested_action=ShadowAction.ACCEPT,
                            actual_action=ShadowAction.ACCEPT) == 1
    severe = calculate_reward(decision_correct=False, severity=FeedbackSeverity.P0,
                              human_edit_seconds=99999, suggested_action=ShadowAction.ACCEPT,
                              actual_action=ShadowAction.QUARANTINE)
    assert severe < -70
    assert calculate_reward(decision_correct=False, severity=FeedbackSeverity.P1,
                            human_edit_seconds=0, suggested_action=ShadowAction.HUMAN_REVIEW,
                            actual_action=ShadowAction.QUARANTINE) < -10
