from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import yaml
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.schema import SHA256_PATTERN, BaseType

DOMAIN_PACK_FORMAT_VERSION = 1
_ALLOWED_PERMISSIONS = frozenset(
    {
        "object-classification",
        "relation-recovery",
        "validation",
        "review-export",
        "model-adapter-metadata",
        "family-detection-metadata",
    }
)
_ALLOWED_ENTRYPOINTS = frozenset({"rules", "validators", "review", "family"})


class DomainPackModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DomainPackManifest(DomainPackModel):
    format_version: int = DOMAIN_PACK_FORMAT_VERSION
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    version: str = Field(min_length=1, max_length=63)
    core_schema: str = Field(min_length=1, max_length=127)
    engine: str = Field(default=">=0.4,<1.0", min_length=1, max_length=127)
    supported_languages: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    entrypoints: dict[str, str] = Field(default_factory=dict)
    file_digests: dict[str, str] = Field(default_factory=dict)
    signing_key_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,127}$")
    signature: str | None = Field(default=None, min_length=1, max_length=512)

    @field_validator("version")
    @classmethod
    def valid_version(cls, value: str) -> str:
        try:
            parsed = Version(value)
        except InvalidVersion as exc:
            raise ValueError("domain pack version must be a valid PEP 440 version") from exc
        if parsed.local is not None or parsed.epoch != 0:
            raise ValueError("local and epoch version identifiers are not allowed")
        return str(parsed)

    @field_validator("core_schema", "engine")
    @classmethod
    def valid_specifier(cls, value: str) -> str:
        try:
            SpecifierSet(value)
        except InvalidSpecifier as exc:
            raise ValueError("compatibility range is not a valid specifier set") from exc
        return value

    @field_validator("supported_languages", "capabilities", "permissions")
    @classmethod
    def unique_strings(cls, values: list[str]) -> list[str]:
        normalized = [item.strip() for item in values]
        if any(not item for item in normalized):
            raise ValueError("manifest string lists cannot contain empty values")
        if len(normalized) != len(set(normalized)):
            raise ValueError("manifest string lists cannot contain duplicates")
        return normalized

    @field_validator("permissions")
    @classmethod
    def allowed_permissions(cls, values: list[str]) -> list[str]:
        unsupported = sorted(set(values) - _ALLOWED_PERMISSIONS)
        if unsupported:
            raise ValueError(f"unsupported domain pack permissions: {unsupported}")
        return values

    @field_validator("entrypoints")
    @classmethod
    def safe_entrypoints(cls, values: dict[str, str]) -> dict[str, str]:
        unsupported = sorted(set(values) - _ALLOWED_ENTRYPOINTS)
        if unsupported:
            raise ValueError(f"unsupported domain pack entrypoints: {unsupported}")
        for name, raw_path in values.items():
            path = PurePosixPath(raw_path)
            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or path.suffix.lower() not in {".yaml", ".yml", ".json"}
            ):
                raise ValueError(f"unsafe declarative entrypoint for {name}: {raw_path}")
        return values

    @field_validator("file_digests")
    @classmethod
    def safe_file_digests(cls, values: dict[str, str]) -> dict[str, str]:
        for raw_path, digest in values.items():
            path = PurePosixPath(raw_path)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError(f"unsafe domain pack file path: {raw_path}")
            if raw_path == "manifest.yaml":
                raise ValueError("manifest.yaml must not appear in file_digests")
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ValueError(f"invalid SHA-256 for {raw_path}")
        return dict(sorted(values.items()))

    @model_validator(mode="after")
    def signature_pair(self) -> DomainPackManifest:
        if (self.signing_key_id is None) != (self.signature is None):
            raise ValueError("signing_key_id and signature must be provided together")
        if self.signature is not None:
            try:
                decoded = base64.b64decode(self.signature, validate=True)
            except ValueError as exc:
                raise ValueError("signature must be valid base64") from exc
            if len(decoded) != 64:
                raise ValueError("Ed25519 signature must be 64 bytes")
        for entrypoint in self.entrypoints.values():
            if entrypoint not in self.file_digests:
                raise ValueError(f"entrypoint is missing from file_digests: {entrypoint}")
        if not set(self.permissions).issubset(set(self.capabilities)):
            raise ValueError("permissions must be declared in capabilities")
        return self

    def canonical_signing_payload(self) -> bytes:
        payload = self.model_dump(mode="json", exclude={"signature"})
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def supports(self, *, core_schema_version: str, engine_version: str) -> bool:
        return Version(core_schema_version) in SpecifierSet(self.core_schema) and Version(
            engine_version
        ) in SpecifierSet(self.engine)


class DomainObjectType(DomainPackModel):
    base_types: list[BaseType] = Field(min_length=1)
    description: str | None = Field(default=None, max_length=1000)
    properties: dict[str, Any] = Field(default_factory=dict)


class DomainRelationType(DomainPackModel):
    base_type: str = Field(min_length=1, max_length=127)
    source_types: list[str] = Field(default_factory=list)
    target_types: list[str] = Field(default_factory=list)
    description: str | None = Field(default=None, max_length=1000)


class DomainOntology(DomainPackModel):
    version: int = 1
    object_types: dict[str, DomainObjectType] = Field(default_factory=dict)
    relation_types: dict[str, DomainRelationType] = Field(default_factory=dict)

    @field_validator("object_types", "relation_types")
    @classmethod
    def safe_type_names(cls, values: dict[str, Any]) -> dict[str, Any]:
        for name in values:
            if not name or len(name) > 127 or not name.replace("_", "").replace("-", "").isalnum():
                raise ValueError(f"invalid ontology type name: {name}")
        return values


class LabelsFile(DomainPackModel):
    version: int = 1
    labels: dict[str, dict[str, str]] = Field(default_factory=dict)


class ObjectRule(DomainPackModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    domain_type: str = Field(min_length=1, max_length=127)
    base_types: list[BaseType] = Field(min_length=1)
    subtypes: list[str] = Field(default_factory=list)
    text_contains_any: list[str] = Field(default_factory=list)
    text_starts_with_any: list[str] = Field(default_factory=list)
    require_text: bool = False
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    properties: dict[str, Any] = Field(default_factory=dict)
    stop_on_match: bool = False

    @field_validator("text_contains_any", "text_starts_with_any")
    @classmethod
    def bounded_text_terms(cls, values: list[str]) -> list[str]:
        if len(values) > 64:
            raise ValueError("a rule cannot contain more than 64 text terms")
        if any(not value or len(value) > 256 for value in values):
            raise ValueError("rule text terms must contain 1-256 characters")
        return values


class RelationRule(DomainPackModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    domain_type: str = Field(min_length=1, max_length=127)
    source_domain_types: list[str] = Field(min_length=1)
    target_domain_types: list[str] = Field(min_length=1)
    base_relation_types: list[str] = Field(default_factory=list)
    max_reading_distance: int = Field(default=3, ge=0, le=100)
    confidence: float = Field(default=0.80, ge=0.0, le=1.0)


class RulesFile(DomainPackModel):
    version: int = 1
    object_rules: list[ObjectRule] = Field(default_factory=list)
    relation_rules: list[RelationRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_rule_ids(self) -> RulesFile:
        ids = [rule.id for rule in [*self.object_rules, *self.relation_rules]]
        if len(ids) != len(set(ids)):
            raise ValueError("domain pack rule IDs must be unique")
        return self


class RequiredTypeConstraint(DomainPackModel):
    code: str = Field(min_length=1, max_length=127)
    domain_types: list[str] = Field(min_length=1)
    min_count: int = Field(default=1, ge=1)
    severity: Literal["info", "warning", "error"] = "warning"
    message: str = Field(min_length=1, max_length=2000)


class RelationEndpointConstraint(DomainPackModel):
    code: str = Field(min_length=1, max_length=127)
    relation_type: str = Field(min_length=1, max_length=127)
    source_types: list[str] = Field(default_factory=list)
    target_types: list[str] = Field(default_factory=list)
    severity: Literal["info", "warning", "error"] = "error"
    message: str = Field(min_length=1, max_length=2000)


class ValidatorsFile(DomainPackModel):
    version: int = 1
    required_types: list[RequiredTypeConstraint] = Field(default_factory=list)
    relation_endpoints: list[RelationEndpointConstraint] = Field(default_factory=list)


class ReviewConfig(DomainPackModel):
    version: int = 1
    adapter: Literal["labelu-json-v1"] = "labelu-json-v1"
    object_labels: list[str] = Field(default_factory=list)
    relation_labels: list[str] = Field(default_factory=list)


class FamilyCue(DomainPackModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    terms: list[str] = Field(min_length=1, max_length=64)
    weight: float = Field(gt=0.0, le=100.0)
    match_mode: Literal["contains", "starts_with", "equals"] = "contains"
    base_types: list[BaseType] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list, max_length=64)
    required: bool = False

    @field_validator("terms", "subtypes")
    @classmethod
    def normalized_unique_strings(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 256 for value in normalized):
            raise ValueError("family cue strings must contain 1-256 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("family cue strings cannot contain duplicates")
        return normalized

    @field_validator("base_types")
    @classmethod
    def unique_base_types(cls, values: list[BaseType]) -> list[BaseType]:
        if len(values) != len(set(values)):
            raise ValueError("family cue base types cannot contain duplicates")
        return values


class DocumentFamilyProfile(DomainPackModel):
    version: int = 1
    family_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    aliases: list[str] = Field(default_factory=list, max_length=32)
    supported_mime_types: list[str] = Field(default_factory=list, max_length=32)
    priority: int = Field(default=100, ge=0, le=10000)
    min_score: float = Field(default=0.55, ge=0.0, le=1.0)
    min_margin: float = Field(default=0.10, ge=0.0, le=1.0)
    min_positive_cues: int = Field(default=1, ge=1, le=128)
    required_base_types: dict[BaseType, int] = Field(default_factory=dict)
    positive_cues: list[FamilyCue] = Field(min_length=1, max_length=128)
    negative_cues: list[FamilyCue] = Field(default_factory=list, max_length=128)

    @field_validator("aliases", "supported_mime_types")
    @classmethod
    def normalized_unique_profile_strings(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 127 for value in normalized):
            raise ValueError("family profile strings must contain 1-127 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("family profile strings cannot contain duplicates")
        return normalized

    @field_validator("required_base_types")
    @classmethod
    def bounded_required_base_types(
        cls, values: dict[BaseType, int]
    ) -> dict[BaseType, int]:
        if any(count < 1 or count > 100000 for count in values.values()):
            raise ValueError("required base type counts must be between 1 and 100000")
        return values

    @model_validator(mode="after")
    def validate_cues(self) -> DocumentFamilyProfile:
        cues = [*self.positive_cues, *self.negative_cues]
        cue_ids = [cue.id for cue in cues]
        if len(cue_ids) != len(set(cue_ids)):
            raise ValueError("family cue IDs must be unique")
        if self.min_positive_cues > len(self.positive_cues):
            raise ValueError("min_positive_cues exceeds available positive cues")
        return self


class LoadedDomainPack(DomainPackModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    root: Path
    manifest: DomainPackManifest
    ontology: DomainOntology
    labels: LabelsFile
    rules: RulesFile = Field(default_factory=RulesFile)
    validators: ValidatorsFile = Field(default_factory=ValidatorsFile)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    family: DocumentFamilyProfile | None = None
    content_digest: str = Field(pattern=SHA256_PATTERN)
    signature_verified: bool = False


def _read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_file(root: Path, relative: str) -> Path:
    path = root / relative
    if path.is_symlink():
        raise ValueError(f"domain pack files cannot be symlinks: {relative}")
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved_root not in resolved.parents or not resolved.is_file():
        raise FileNotFoundError(relative)
    return resolved


def load_domain_pack(root: Path, *, signature_verified: bool = False) -> LoadedDomainPack:
    root = root.resolve()
    if not root.is_dir() or root.is_symlink():
        raise FileNotFoundError(f"domain pack directory is missing or unsafe: {root}")
    manifest_path = _safe_file(root, "manifest.yaml")
    manifest = DomainPackManifest.model_validate(_read_yaml(manifest_path))
    actual_files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"domain pack files cannot be symlinks: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if relative not in {"manifest.yaml", ".installed.json"}:
                actual_files[relative] = _sha256_file(path)
    if actual_files != manifest.file_digests:
        missing = sorted(set(manifest.file_digests) - set(actual_files))
        extra = sorted(set(actual_files) - set(manifest.file_digests))
        changed = sorted(
            name
            for name in set(actual_files) & set(manifest.file_digests)
            if actual_files[name] != manifest.file_digests[name]
        )
        raise ValueError(
            f"domain pack file digest mismatch: missing={missing}, extra={extra}, changed={changed}"
        )

    ontology = DomainOntology.model_validate(_read_yaml(_safe_file(root, "ontology.yaml")))
    labels_path = root / "labels.yaml"
    labels = (
        LabelsFile.model_validate(_read_yaml(_safe_file(root, "labels.yaml")))
        if labels_path.exists()
        else LabelsFile()
    )
    rules = RulesFile()
    validators = ValidatorsFile()
    review = ReviewConfig()
    family: DocumentFamilyProfile | None = None
    if "rules" in manifest.entrypoints:
        rules = RulesFile.model_validate(
            _read_yaml(_safe_file(root, manifest.entrypoints["rules"]))
        )
    if "validators" in manifest.entrypoints:
        validators = ValidatorsFile.model_validate(
            _read_yaml(_safe_file(root, manifest.entrypoints["validators"]))
        )
    if "review" in manifest.entrypoints:
        review = ReviewConfig.model_validate(
            _read_yaml(_safe_file(root, manifest.entrypoints["review"]))
        )
    if "family" in manifest.entrypoints:
        family = DocumentFamilyProfile.model_validate(
            _read_yaml(_safe_file(root, manifest.entrypoints["family"]))
        )
        if family.family_id != manifest.id:
            raise ValueError("family profile family_id must equal the domain pack id")
        if "family-detection-metadata" not in manifest.permissions:
            raise ValueError("family entrypoint requires family-detection-metadata permission")
    elif "family-detection-metadata" in manifest.permissions:
        raise ValueError("family-detection-metadata permission requires a family entrypoint")

    object_types = set(ontology.object_types)
    relation_types = set(ontology.relation_types)
    for rule in rules.object_rules:
        if rule.domain_type not in object_types:
            raise ValueError(f"object rule references unknown domain type: {rule.domain_type}")
        allowed_base_types = set(ontology.object_types[rule.domain_type].base_types)
        if not set(rule.base_types).issubset(allowed_base_types):
            raise ValueError(
                f"object rule {rule.id} uses base types outside ontology declaration"
            )
    for rule in rules.relation_rules:
        if rule.domain_type not in relation_types:
            raise ValueError(f"relation rule references unknown domain type: {rule.domain_type}")
        if not set(rule.source_domain_types).issubset(object_types):
            raise ValueError(f"relation rule {rule.id} has unknown source domain types")
        if not set(rule.target_domain_types).issubset(object_types):
            raise ValueError(f"relation rule {rule.id} has unknown target domain types")
    for constraint in validators.required_types:
        if not set(constraint.domain_types).issubset(object_types):
            raise ValueError(f"validator {constraint.code} references unknown domain type")
    for constraint in validators.relation_endpoints:
        if constraint.relation_type not in relation_types:
            raise ValueError(f"validator {constraint.code} references unknown relation type")
    if not set(review.object_labels).issubset(object_types):
        raise ValueError("review config references unknown object labels")
    if not set(review.relation_labels).issubset(relation_types):
        raise ValueError("review config references unknown relation labels")

    content_digest = hashlib.sha256(manifest.canonical_signing_payload()).hexdigest()
    return LoadedDomainPack(
        root=root,
        manifest=manifest,
        ontology=ontology,
        labels=labels,
        rules=rules,
        validators=validators,
        review=review,
        family=family,
        content_digest=content_digest,
        signature_verified=signature_verified,
    )
