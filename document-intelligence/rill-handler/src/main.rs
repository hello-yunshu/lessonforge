//! LessonForge-owned Stable Handler API v1 component.
//!
//! This is consumer logic only: it contains no Rill Runtime code, no WASI
//! imports, no persistence, and no action execution. Host-owned feedback and
//! state remain outside the handler.

use std::collections::BTreeMap;
use std::sync::OnceLock;

use serde::{Deserialize, Serialize};
use sha2::Digest;

wit_bindgen::generate!({
    path: "wit/rill-handler.wit",
    world: "invoke-handler",
});

const HANDLER_ID: &str = "org.lessonforge.shadow.handler";
const EVALUATE: &str = "org.lessonforge.shadow.evaluate";
const MAX_INPUT_BYTES: usize = 64 * 1024;
const MAX_EVENT_ID_BYTES: usize = 128;
const MAX_OPERATION_BYTES: usize = 32;
const MAX_REASON_CODES: usize = 8;

const FEATURE_KEYS: [&str; 26] = [
    "parse.page_count",
    "parse.element_count",
    "parse.average_confidence",
    "parse.minimum_confidence",
    "parse.p0_warnings",
    "parse.p1_warnings",
    "parse.p2_warnings",
    "parse.empty_native_text",
    "parse.duration_ms_log1p",
    "parse.estimated_cost_usd_log1p",
    "match.present",
    "match.top1_score",
    "match.margin",
    "match.candidate_count",
    "match.safe_standard_reuse",
    "structure.present",
    "structure.reading_order_coverage",
    "structure.relation_evidence_coverage",
    "structure.consistency_score",
    "structure.diagnostics_warning",
    "structure.diagnostics_error",
    "structure.cross_page_relations",
    "domain.present",
    "domain.fallback_used",
    "domain.error_findings",
    "domain.evidence_coverage",
];

const ACTIONS: [&str; 9] = [
    "ACCEPT",
    "RETRY",
    "REPROCESS_HIGH_RES",
    "USE_SECONDARY_PARSER",
    "USE_SPECIALIST_PARSER",
    "USE_DOMAIN_ADAPTER",
    "VLM_REVIEW",
    "HUMAN_REVIEW",
    "QUARANTINE",
];

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct Thresholds {
    accept: f64,
    retry: f64,
    quarantine: f64,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct ModelConfig {
    default_action: String,
    policy_version: String,
    thresholds: Thresholds,
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case", deny_unknown_fields)]
struct Observation {
    schema_version: String,
    event_id: String,
    parse_run_id: String,
    parser_id: String,
    document_family: Option<String>,
    structure_id: Option<String>,
    domain_result_id: Option<String>,
    signals: serde_json::Value,
    shadow_only: bool,
    generated_at: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case", deny_unknown_fields)]
struct StaticSuggestion {
    decision_id: String,
    action: String,
    selected_arm: u32,
    policy_version: String,
    confidence: f64,
    reason_codes: Vec<String>,
    source: String,
    model_generation: u64,
    state_generation: u64,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct HostState {
    model_generation: u64,
    state_generation: u64,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct EvaluateInput {
    operation: String,
    event_id: String,
    observation: Observation,
    features: BTreeMap<String, f64>,
    allowed_actions: Vec<String>,
    static_suggestion: StaticSuggestion,
    deterministic_seed: u64,
    host_state: HostState,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct Suggestion {
    decision_id: String,
    action: String,
    selected_arm: u32,
    policy_version: String,
    confidence: f64,
    reason_codes: Vec<String>,
}

#[derive(Serialize)]
struct EvaluateOutput {
    suggestion: Suggestion,
}

static MODEL: OnceLock<ModelConfig> = OnceLock::new();

struct LessonforgeShadowHandler;

fn bounded_text(value: &str, max_bytes: usize) -> bool {
    !value.is_empty() && value.len() <= max_bytes && value.is_ascii()
}

fn validate_model(value: ModelConfig) -> Result<ModelConfig, HandlerError> {
    let thresholds = &value.thresholds;
    if value.default_action.is_empty()
        || !ACTIONS.contains(&value.default_action.as_str())
        || value.policy_version.is_empty()
        || value.policy_version.len() > 127
        || !thresholds.accept.is_finite()
        || !thresholds.retry.is_finite()
        || !thresholds.quarantine.is_finite()
        || !(0.0..=1.0).contains(&thresholds.accept)
        || !(0.0..=1.0).contains(&thresholds.retry)
        || !(0.0..=1.0).contains(&thresholds.quarantine)
        || thresholds.accept > thresholds.retry
        || thresholds.retry > thresholds.quarantine
    {
        return Err(HandlerError::InvalidModel(
            "bounded model validation failed".into(),
        ));
    }
    Ok(value)
}

fn feature(input: &EvaluateInput, key: &str) -> f64 {
    *input.features.get(key).unwrap_or(&0.0)
}

fn validate_observation(observation: &Observation, event_id: &str) -> Result<(), HandlerError> {
    if observation.schema_version != "0.5"
        || observation.event_id != event_id
        || !bounded_text(&observation.event_id, MAX_EVENT_ID_BYTES)
        || !bounded_text(&observation.parse_run_id, MAX_EVENT_ID_BYTES)
        || !bounded_text(&observation.parser_id, 127)
        || observation
            .document_family
            .as_ref()
            .is_some_and(|v| v.len() > 127)
        || observation
            .structure_id
            .as_ref()
            .is_some_and(|v| v.len() > MAX_EVENT_ID_BYTES)
        || observation
            .domain_result_id
            .as_ref()
            .is_some_and(|v| v.len() > MAX_EVENT_ID_BYTES)
        || !observation.shadow_only
        || !observation.signals.is_object()
        || observation.generated_at.is_empty()
        || observation.generated_at.len() > 64
    {
        return Err(HandlerError::InvalidInput(
            "observation shape is invalid".into(),
        ));
    }
    Ok(())
}

fn validate_static_suggestion(value: &StaticSuggestion) -> Result<(), HandlerError> {
    if !bounded_text(&value.decision_id, 128)
        || !ACTIONS.contains(&value.action.as_str())
        || value.selected_arm as usize >= ACTIONS.len()
        || ACTIONS[value.selected_arm as usize] != value.action
        || value.policy_version.is_empty()
        || value.policy_version.len() > 127
        || !value.confidence.is_finite()
        || !(0.0..=1.0).contains(&value.confidence)
        || value.reason_codes.is_empty()
        || value.reason_codes.len() > MAX_REASON_CODES
        || value
            .reason_codes
            .iter()
            .any(|v| v.is_empty() || v.len() > 127)
        || value.source.is_empty()
        || value.model_generation > 1_000_000_000
        || value.state_generation > 1_000_000_000
    {
        return Err(HandlerError::InvalidInput(
            "static suggestion shape is invalid".into(),
        ));
    }
    Ok(())
}

fn validate_input(input: &EvaluateInput) -> Result<(), HandlerError> {
    if (input.operation != "evaluate" && input.operation != "qualification")
        || input.operation.len() > MAX_OPERATION_BYTES
        || !bounded_text(&input.event_id, MAX_EVENT_ID_BYTES)
        || input.features.len() != FEATURE_KEYS.len()
        || input
            .features
            .keys()
            .any(|key| !FEATURE_KEYS.contains(&key.as_str()))
        || input.features.values().any(|value| !value.is_finite())
        || input.allowed_actions.is_empty()
        || input.allowed_actions.len() > ACTIONS.len()
        || input
            .allowed_actions
            .iter()
            .any(|action| !ACTIONS.contains(&action.as_str()))
        || input.allowed_actions.len()
            != input
                .allowed_actions
                .iter()
                .collect::<std::collections::HashSet<_>>()
                .len()
        || input.deterministic_seed == 0
    {
        return Err(HandlerError::InvalidInput(
            "bounded evaluate input is invalid".into(),
        ));
    }
    validate_observation(&input.observation, &input.event_id)?;
    validate_static_suggestion(&input.static_suggestion)?;
    if !input
        .allowed_actions
        .iter()
        .any(|action| action == &input.static_suggestion.action)
        || input.host_state.model_generation > 1_000_000_000
        || input.host_state.state_generation > 1_000_000_000
    {
        return Err(HandlerError::InvalidInput(
            "host state or static action is invalid".into(),
        ));
    }
    Ok(())
}

fn risk_score(input: &EvaluateInput) -> (f64, Vec<&'static str>) {
    let mut risk = 0.0;
    let mut reasons = Vec::new();
    let average = feature(input, "parse.average_confidence");
    let minimum = feature(input, "parse.minimum_confidence");
    let p0 = feature(input, "parse.p0_warnings");
    let p1 = feature(input, "parse.p1_warnings");
    let empty_text = feature(input, "parse.empty_native_text") >= 0.5;
    let consistency = feature(input, "structure.consistency_score");
    let structure_errors = feature(input, "structure.diagnostics_error");
    let domain_errors = feature(input, "domain.error_findings");
    let domain_fallback = feature(input, "domain.fallback_used") >= 0.5;
    let match_margin = feature(input, "match.margin");

    risk += (1.0 - average).clamp(0.0, 1.0) * 0.30;
    risk += (1.0 - minimum).clamp(0.0, 1.0) * 0.20;
    risk += (1.0 - consistency).clamp(0.0, 1.0) * 0.15;
    risk += (p1 / 3.0).clamp(0.0, 1.0) * 0.12;
    risk += (structure_errors / 2.0).clamp(0.0, 1.0) * 0.10;
    risk += (domain_errors / 2.0).clamp(0.0, 1.0) * 0.08;
    risk += (1.0 - match_margin).clamp(0.0, 1.0) * 0.05;
    if p0 > 0.0 {
        risk = 1.0;
        reasons.push("PARSE_P0_WARNING");
    }
    if empty_text {
        risk = (risk + 0.18).min(1.0);
        reasons.push("EMPTY_NATIVE_TEXT");
    }
    if domain_fallback {
        risk = (risk + 0.20).min(1.0);
        reasons.push("DOMAIN_FALLBACK");
    }
    if average >= 0.9
        && minimum >= 0.8
        && p1 == 0.0
        && structure_errors == 0.0
        && domain_errors == 0.0
    {
        reasons.push("HIGH_PARSE_CONFIDENCE");
    } else if average < 0.75 || minimum < 0.5 {
        reasons.push("LOW_PARSE_CONFIDENCE");
    }
    if consistency < 0.7 {
        reasons.push("LOW_STRUCTURE_CONSISTENCY");
    }
    if p1 > 0.0 {
        reasons.push("RECOVERABLE_PARSE_WARNING");
    }
    (risk.clamp(0.0, 1.0), reasons)
}

fn preferred_action<'a>(risk: f64, input: &'a EvaluateInput, model: &'a ModelConfig) -> &'a str {
    let preferred = if risk >= model.thresholds.quarantine {
        "QUARANTINE"
    } else if risk >= model.thresholds.retry {
        "HUMAN_REVIEW"
    } else if risk >= model.thresholds.accept {
        "RETRY"
    } else {
        "ACCEPT"
    };
    if input
        .allowed_actions
        .iter()
        .any(|action| action == preferred)
    {
        preferred
    } else if input
        .allowed_actions
        .iter()
        .any(|action| action == &model.default_action)
    {
        model.default_action.as_str()
    } else {
        input.allowed_actions[0].as_str()
    }
}

fn decision_id(input: &EvaluateInput, action: &str, risk: f64) -> String {
    let mut digest = sha2::Sha256::new();
    digest.update(input.event_id.as_bytes());
    digest.update(action.as_bytes());
    digest.update(input.deterministic_seed.to_le_bytes());
    digest.update(input.host_state.model_generation.to_le_bytes());
    digest.update(input.host_state.state_generation.to_le_bytes());
    digest.update(risk.to_bits().to_le_bytes());
    let hex = format!("{:x}", digest.finalize());
    format!("lessonforge-rill-{}", &hex[..32])
}

impl Guest for LessonforgeShadowHandler {
    fn metadata() -> HandlerMetadata {
        HandlerMetadata {
            id: HANDLER_ID.into(),
            version: "1.2.0".into(),
            api_version: 1,
            capabilities: vec![EVALUATE.into()],
        }
    }

    fn configure(model_json: Vec<u8>) -> Result<(), HandlerError> {
        if model_json.len() > 16 * 1024 {
            return Err(HandlerError::InvalidModel(
                "model JSON exceeds its bound".into(),
            ));
        }
        let config: ModelConfig = serde_json::from_slice(&model_json)
            .map_err(|_| HandlerError::InvalidModel("model JSON is invalid".into()))?;
        MODEL
            .set(validate_model(config)?)
            .map_err(|_| HandlerError::InvalidModel("model was configured twice".into()))
    }

    fn invoke(capability: String, input_json: Vec<u8>) -> Result<Vec<u8>, HandlerError> {
        if capability != EVALUATE {
            return Err(HandlerError::UnsupportedCapability(capability));
        }
        if input_json.is_empty() || input_json.len() > MAX_INPUT_BYTES {
            return Err(HandlerError::InvalidInput(
                "input exceeds handler bound".into(),
            ));
        }
        let input: EvaluateInput = serde_json::from_slice(&input_json)
            .map_err(|_| HandlerError::InvalidInput("input JSON is invalid".into()))?;
        validate_input(&input)?;
        let model = MODEL
            .get()
            .ok_or_else(|| HandlerError::InvalidModel("handler was not configured".into()))?;
        let (risk, mut reasons) = risk_score(&input);
        let action = preferred_action(risk, &input, model);
        if reasons.is_empty() {
            reasons.push("MODEL_FALLBACK");
        }
        reasons.truncate(MAX_REASON_CODES);
        let output = EvaluateOutput {
            suggestion: Suggestion {
                decision_id: decision_id(&input, action, risk),
                action: action.into(),
                selected_arm: ACTIONS.iter().position(|item| *item == action).unwrap() as u32,
                policy_version: model.policy_version.clone(),
                confidence: (1.0 - risk).clamp(0.0, 1.0),
                reason_codes: reasons.into_iter().map(str::to_string).collect(),
            },
        };
        serde_json::to_vec(&output)
            .map_err(|_| HandlerError::ExecutionFailed("output serialization failed".into()))
    }
}

export!(LessonforgeShadowHandler);

fn main() {}
