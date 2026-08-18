from __future__ import annotations

import json

import pytest

from document_intelligence.rill.features import ShadowFeatureBuilder
from document_intelligence.rill.models import ACTION_ARMS, RILL_FEATURE_ORDER


def test_frozen_feature_schema_matches_extractor_and_action_arms() -> None:
    schema = json.loads(open("configs/rill_feature_schema.json", encoding="utf-8").read())
    ShadowFeatureBuilder._validate_feature_schema(schema)
    assert schema["featureOrder"] == list(RILL_FEATURE_ORDER)
    assert schema["actionArms"] == [item.value for item in ACTION_ARMS]


def test_feature_schema_rejects_order_or_shadow_drift() -> None:
    schema = json.loads(open("configs/rill_feature_schema.json", encoding="utf-8").read())
    schema["featureOrder"] = list(reversed(schema["featureOrder"]))
    with pytest.raises(ValueError):
        ShadowFeatureBuilder._validate_feature_schema(schema)
    schema = json.loads(open("configs/rill_feature_schema.json", encoding="utf-8").read())
    schema["shadowOnly"] = False
    with pytest.raises(ValueError):
        ShadowFeatureBuilder._validate_feature_schema(schema)
