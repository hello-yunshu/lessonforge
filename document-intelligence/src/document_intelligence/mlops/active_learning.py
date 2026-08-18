from __future__ import annotations

import hashlib
import json

from document_intelligence.mlops.models import (
    ActiveLearningBatch,
    ActiveLearningSelection,
    stable_mlops_id,
)
from document_intelligence.rill.models import ShadowEvaluation, ShadowEvaluationStatus


class ActiveLearningSelector:
    """Deterministic Rill-aware selection without promoting labels to truth."""

    policy_version = "active-learning-v1"

    def select(
        self,
        evaluations: list[ShadowEvaluation],
        *,
        excluded_evaluation_ids: set[str] | None = None,
        active_drift_parser_ids: set[str] | None = None,
        max_items: int = 100,
        max_per_family: int = 20,
    ) -> ActiveLearningBatch:
        excluded = excluded_evaluation_ids or set()
        drift_parsers = active_drift_parser_ids or set()
        source_payload = {
            "evaluations": [
                {
                    "evaluation_id": item.evaluation_id,
                    "semantic": self._evaluation_digest(item),
                }
                for item in sorted(evaluations, key=lambda value: value.evaluation_id)
            ],
            "excluded_evaluation_ids": sorted(excluded),
            "active_drift_parser_ids": sorted(drift_parsers),
        }
        source_digest = hashlib.sha256(
            json.dumps(source_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        ranked: list[ActiveLearningSelection] = []
        for evaluation in evaluations:
            if evaluation.evaluation_id in excluded:
                continue
            score, reasons = self._score(evaluation, drift_parsers)
            if score <= 0 or not reasons:
                continue
            event = evaluation.observe_event
            ranked.append(
                ActiveLearningSelection(
                    evaluation_id=evaluation.evaluation_id,
                    parse_run_id=event.parse_run_id,
                    document_family=event.document_family or "unknown",
                    score=round(min(score, 100.0), 6),
                    reason_codes=reasons,
                )
            )
        ranked.sort(key=lambda item: (-item.score, item.evaluation_id))
        selected: list[ActiveLearningSelection] = []
        family_counts: dict[str, int] = {}
        for item in ranked:
            if len(selected) >= max_items:
                break
            count = family_counts.get(item.document_family, 0)
            if count >= max_per_family:
                continue
            selected.append(item)
            family_counts[item.document_family] = count + 1
        batch_id = stable_mlops_id(
            "active-learning",
            self.policy_version,
            source_digest,
            str(max_items),
            str(max_per_family),
        )
        return ActiveLearningBatch(
            batch_id=batch_id,
            policy_version=self.policy_version,
            source_digest=source_digest,
            max_items=max_items,
            max_per_family=max_per_family,
            selections=selected,
        )

    @staticmethod
    def _evaluation_digest(value: ShadowEvaluation) -> str:
        raw = value.model_dump(mode="json")
        raw.pop("created_at", None)
        return hashlib.sha256(
            json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _score(
        evaluation: ShadowEvaluation, active_drift_parser_ids: set[str]
    ) -> tuple[float, list[str]]:
        reasons: list[str] = []
        score = 0.0
        event = evaluation.observe_event
        parse = event.signals.parse
        match = event.signals.matching
        structure = event.signals.structure
        domain = event.signals.domain
        if evaluation.status != ShadowEvaluationStatus.SUCCEEDED:
            score += 35.0
            reasons.append("RUNTIME_FAILURE")
        if (
            evaluation.rill_suggestion is not None
            and evaluation.rill_suggestion.action != evaluation.static_suggestion.action
        ):
            score += 30.0
            reasons.append("POLICY_DISAGREEMENT")
        if event.parser_id in active_drift_parser_ids:
            score += 25.0
            reasons.append("ACTIVE_DRIFT")
        if parse.p0_warnings:
            score += min(30.0, 15.0 * parse.p0_warnings)
            reasons.append("P0_WARNING")
        if parse.p1_warnings:
            score += min(20.0, 6.0 * parse.p1_warnings)
            reasons.append("P1_WARNING")
        if parse.minimum_confidence < 0.5:
            score += (0.5 - parse.minimum_confidence) * 30.0
            reasons.append("LOW_CONFIDENCE")
        if parse.empty_native_text:
            score += 8.0
            reasons.append("EMPTY_NATIVE_TEXT")
        if match is not None and match.decision == "ambiguous":
            score += 18.0
            reasons.append("AMBIGUOUS_MATCH")
        if match is not None and match.candidate_count > 1 and match.margin < 0.08:
            score += 12.0
            reasons.append("LOW_MATCH_MARGIN")
        if structure is not None and structure.diagnostics_error:
            score += min(20.0, 5.0 * structure.diagnostics_error)
            reasons.append("STRUCTURE_ERROR")
        if structure is not None and structure.relation_evidence_coverage < 0.8:
            score += (0.8 - structure.relation_evidence_coverage) * 20.0
            reasons.append("LOW_RELATION_EVIDENCE")
        if domain is not None and domain.fallback_used:
            score += 12.0
            reasons.append("DOMAIN_FALLBACK")
        if domain is not None and domain.error_findings:
            score += min(20.0, 5.0 * domain.error_findings)
            reasons.append("DOMAIN_ERROR")
        return score, sorted(set(reasons))
