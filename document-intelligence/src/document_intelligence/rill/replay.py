from __future__ import annotations

from statistics import mean

from document_intelligence.rill.models import FeedbackSeverity, ReplayMetrics, ShadowAction
from document_intelligence.rill.store import RillShadowStore
from document_intelligence.rill.drift import ShadowDriftMonitor


class ShadowReplayService:
    def __init__(self, store: RillShadowStore, drift: ShadowDriftMonitor) -> None:
        self.store = store
        self.drift = drift

    def metrics(self) -> ReplayMetrics:
        evaluations = self.store.list_evaluations()
        feedback = self.store.list_feedback()
        evaluation_by_id = {item.evaluation_id: item for item in evaluations}
        rill_correct = 0
        static_correct = 0
        disagreements = 0
        rill_accept_severe = 0
        static_accept_severe = 0
        rewards: list[float] = []
        edit_seconds: list[float] = []
        for record in feedback:
            evaluation = evaluation_by_id.get(record.evaluation_id)
            if evaluation is None:
                continue
            static = evaluation.static_suggestion.action
            rill = (
                evaluation.rill_suggestion.action
                if evaluation.rill_suggestion is not None
                else None
            )
            static_correct += int(static == record.actual_action)
            if rill is not None:
                rill_correct += int(rill == record.actual_action)
                disagreements += int(rill != static)
                if (
                    rill == ShadowAction.ACCEPT
                    and record.severity in {FeedbackSeverity.P0, FeedbackSeverity.P1}
                ):
                    rill_accept_severe += 1
            if (
                static == ShadowAction.ACCEPT
                and record.severity in {FeedbackSeverity.P0, FeedbackSeverity.P1}
            ):
                static_accept_severe += 1
            rewards.append(record.reward)
            edit_seconds.append(record.human_edit_seconds)
        feedback_count = len(feedback)
        rill_denominator = sum(
            evaluation_by_id.get(item.evaluation_id) is not None
            and evaluation_by_id[item.evaluation_id].rill_suggestion is not None
            for item in feedback
        )
        blocking: list[str] = []
        if feedback_count < 30:
            blocking.append("INSUFFICIENT_FEEDBACK")
        if rill_accept_severe > 0:
            blocking.append("RILL_ACCEPTED_P0_P1")
        if feedback_count and rill_denominator < feedback_count:
            blocking.append("MISSING_RILL_SUGGESTIONS")
        if feedback_count and rill_correct < static_correct:
            blocking.append("RILL_BELOW_STATIC_BASELINE")
        drift_alerts = len(self.drift.list_alerts())
        if drift_alerts:
            blocking.append("ACTIVE_DRIFT_ALERT_HISTORY")
        return ReplayMetrics(
            total_evaluations=len(evaluations),
            feedback_records=feedback_count,
            rill_accuracy=(rill_correct / rill_denominator if rill_denominator else None),
            static_accuracy=(static_correct / feedback_count if feedback_count else None),
            suggestion_disagreements=disagreements,
            rill_accept_on_p0_p1=rill_accept_severe,
            static_accept_on_p0_p1=static_accept_severe,
            mean_reward=(mean(rewards) if rewards else None),
            mean_human_edit_seconds=(mean(edit_seconds) if edit_seconds else None),
            drift_alerts=drift_alerts,
            safe_for_assist_consideration=not blocking,
            blocking_reasons=blocking,
        )
