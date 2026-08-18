from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.schema import SAFE_ID_PATTERN, SHA256_PATTERN

FREEZE_FORMAT_VERSION = 1
FREEZE_SCHEMA_VERSION = "1.0"


class FreezeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ContractKind(StrEnum):
    CORE_SCHEMA = "core_schema"
    PARSER_SDK = "parser_sdk"
    DOMAIN_PACK_SDK = "domain_pack_sdk"
    RILL_PROTOCOL = "rill_protocol"
    REST_API = "rest_api"
    VERSION_SEMANTICS = "version_semantics"
    PERMISSION_BOUNDARY = "permission_boundary"
    RELEASE_GATES = "release_gates"
    ROLLBACK_BEHAVIOR = "rollback_behavior"
    AUDIT_LOG_FORMAT = "audit_log_format"


class FrozenContract(FreezeModel):
    contract_id: str = Field(pattern=SAFE_ID_PATTERN)
    kind: ContractKind
    contract_version: str = Field(min_length=1, max_length=32)
    digest: str = Field(pattern=SHA256_PATTERN)
    payload: dict[str, Any]

    @model_validator(mode="after")
    def digest_matches_payload(self) -> FrozenContract:
        if self.digest != canonical_digest(self.payload):
            raise ValueError("frozen contract digest does not match payload")
        return self


class FreezeManifest(FreezeModel):
    format_version: Literal[1] = FREEZE_FORMAT_VERSION
    schema_version: Literal["1.0"] = FREEZE_SCHEMA_VERSION
    freeze_id: str = Field(pattern=SAFE_ID_PATTERN)
    project: Literal["document-intelligence"] = "document-intelligence"
    project_version: str = Field(pattern=r"^1\.\d+\.\d+$")
    stable_major: Literal[1] = 1
    status: Literal["engineering_frozen"] = "engineering_frozen"
    production_qualified: Literal[False] = False
    contracts: list[FrozenContract] = Field(min_length=10, max_length=64)
    production_blockers: list[str] = Field(min_length=1, max_length=64)
    manifest_digest: str = Field(pattern=SHA256_PATTERN)

    @field_validator("contracts")
    @classmethod
    def contracts_unique_and_sorted(
        cls, values: list[FrozenContract]
    ) -> list[FrozenContract]:
        ids = [item.contract_id for item in values]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("contracts must be unique and sorted by contract_id")
        kinds = [item.kind for item in values]
        if len(kinds) != len(set(kinds)):
            raise ValueError("each frozen contract kind must appear exactly once")
        return values

    @field_validator("production_blockers")
    @classmethod
    def blockers_unique(cls, values: list[str]) -> list[str]:
        if values != sorted(values) or len(values) != len(set(values)):
            raise ValueError("production blockers must be unique and sorted")
        if any(not value or len(value) > 160 for value in values):
            raise ValueError("invalid production blocker")
        return values

    @model_validator(mode="after")
    def manifest_digest_matches(self) -> FreezeManifest:
        payload = self.model_dump(mode="json", exclude={"manifest_digest"})
        if self.manifest_digest != canonical_digest(payload):
            raise ValueError("freeze manifest digest does not match payload")
        return self


class ContractDifference(FreezeModel):
    contract_id: str = Field(pattern=SAFE_ID_PATTERN)
    expected_digest: str | None = Field(default=None, pattern=SHA256_PATTERN)
    actual_digest: str | None = Field(default=None, pattern=SHA256_PATTERN)
    reason: str = Field(min_length=1, max_length=160)


class FreezeVerification(FreezeModel):
    schema_version: Literal["1.0"] = FREEZE_SCHEMA_VERSION
    manifest_digest: str = Field(pattern=SHA256_PATTERN)
    project_version: str
    compatible: bool
    exact_match: bool
    differences: list[ContractDifference] = Field(default_factory=list)
    bounded_auto: Literal[False] = False
    production_qualified: Literal[False] = False

    @model_validator(mode="after")
    def status_matches_differences(self) -> FreezeVerification:
        if self.exact_match != (not self.differences):
            raise ValueError("exact_match must reflect differences")
        if self.compatible != self.exact_match:
            raise ValueError("1.0 freeze requires exact contract compatibility")
        return self


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class FreezeBenchmarkCase(FreezeModel):
    name: str = Field(pattern=SAFE_ID_PATTERN)
    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)


class FreezeBenchmarkReport(FreezeModel):
    schema_version: Literal["1.0"] = FREEZE_SCHEMA_VERSION
    phase: Literal[9] = 9
    project_version: str
    manifest_digest: str = Field(pattern=SHA256_PATTERN)
    contract_count: int = Field(ge=10)
    audit_record_count: int = Field(ge=1)
    api_operation_count: int = Field(ge=1)
    cases: list[FreezeBenchmarkCase] = Field(min_length=1)
    passed: bool
    bounded_auto: Literal[False] = False
    production_qualified: Literal[False] = False

    @model_validator(mode="after")
    def result_matches_cases(self) -> FreezeBenchmarkReport:
        if self.passed != all(item.passed for item in self.cases):
            raise ValueError("benchmark passed flag must match all cases")
        return self
