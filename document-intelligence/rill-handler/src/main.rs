//! LessonForge-owned Stable Handler API v1 component.
//!
//! This is consumer logic only: it contains no Rill Runtime code, no WASI
//! imports, no persistence, and no action execution. Host-owned feedback and
//! state remain outside the handler.

use std::sync::OnceLock;

use serde::{Deserialize, Serialize};

wit_bindgen::generate!({
    path: "../wit/rill-handler.wit",
    world: "invoke-handler",
});

const HANDLER_ID: &str = "org.lessonforge.shadow.handler";
const EVALUATE: &str = "org.lessonforge.shadow.evaluate";
const MAX_INPUT_BYTES: usize = 64 * 1024;

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct ModelConfig {
    default_action: String,
    policy_version: String,
    confidence: f64,
    reason_codes: Vec<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct EvaluateInput {
    operation: String,
    allowed_actions: Vec<String>,
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

fn validate_model(value: ModelConfig) -> Result<ModelConfig, HandlerError> {
    if value.default_action.is_empty()
        || value.default_action.len() > 48
        || value.policy_version.is_empty()
        || value.policy_version.len() > 127
        || !(0.0..=1.0).contains(&value.confidence)
        || value.reason_codes.is_empty()
        || value.reason_codes.len() > 32
        || value.reason_codes.iter().any(|item| {
            item.is_empty()
                || item.len() > 127
                || !item.chars().all(|character| character.is_ascii_alphanumeric() || character == '_' || character == '-')
        })
    {
        return Err(HandlerError::InvalidModel("bounded model validation failed".into()));
    }
    Ok(value)
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
        let config: ModelConfig = serde_json::from_slice(&model_json)
            .map_err(|_| HandlerError::InvalidModel("model JSON is invalid".into()))?;
        let config = validate_model(config)?;
        MODEL
            .set(config)
            .map_err(|_| HandlerError::InvalidModel("model was configured twice".into()))
    }

    fn invoke(capability: String, input_json: Vec<u8>) -> Result<Vec<u8>, HandlerError> {
        if capability != EVALUATE {
            return Err(HandlerError::UnsupportedCapability(capability));
        }
        if input_json.len() > MAX_INPUT_BYTES {
            return Err(HandlerError::InvalidInput("input exceeds handler bound".into()));
        }
        let input: EvaluateInput = serde_json::from_slice(&input_json)
            .map_err(|_| HandlerError::InvalidInput("input JSON is invalid".into()))?;
        if input.operation != "evaluate" && input.operation != "qualification"
            || input.allowed_actions.is_empty()
            || input.allowed_actions.len() > 16
        {
            return Err(HandlerError::InvalidInput("bounded evaluate input is invalid".into()));
        }
        let model = MODEL
            .get()
            .ok_or_else(|| HandlerError::InvalidModel("handler was not configured".into()))?;
        if !input.allowed_actions.iter().any(|action| action == &model.default_action) {
            return Err(HandlerError::InvalidInput("default action is outside Host allowlist".into()));
        }
        let selected_arm = match model.default_action.as_str() {
            "ACCEPT" => 0,
            "RETRY" => 1,
            "REPROCESS_HIGH_RES" => 2,
            "USE_SECONDARY_PARSER" => 3,
            "USE_SPECIALIST_PARSER" => 4,
            "USE_DOMAIN_ADAPTER" => 5,
            "VLM_REVIEW" => 6,
            "HUMAN_REVIEW" => 7,
            "QUARANTINE" => 8,
            _ => return Err(HandlerError::InvalidModel("unknown action arm".into())),
        };
        let output = EvaluateOutput {
            suggestion: Suggestion {
                decision_id: "lessonforge-rill-1.2.0".into(),
                action: model.default_action.clone(),
                selected_arm,
                policy_version: model.policy_version.clone(),
                confidence: model.confidence,
                reason_codes: model.reason_codes.clone(),
            },
        };
        serde_json::to_vec(&output)
            .map_err(|_| HandlerError::ExecutionFailed("output serialization failed".into()))
    }
}

export!(LessonforgeShadowHandler);

fn main() {}
