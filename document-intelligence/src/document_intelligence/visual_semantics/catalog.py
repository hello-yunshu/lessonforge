from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from PIL import Image, ImageOps, ImageStat


def _bits_to_hex(bits: Sequence[int]) -> str:
    value = 0
    for bit in bits:
        value = (value << 1) | int(bool(bit))
    width = (len(bits) + 3) // 4
    return f"{value:0{width}x}"


def _hex_hamming(left: str, right: str) -> int:
    if len(left) != len(right):
        return 10**9
    return (int(left, 16) ^ int(right, 16)).bit_count()


def _normalised_image(image: Image.Image, size: int = 32) -> Image.Image:
    # White background avoids alpha-only differences becoming false identity cues.
    rgba = image.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    bg.alpha_composite(rgba)
    gray = ImageOps.grayscale(bg.convert("RGB"))
    return ImageOps.fit(gray, (size, size), method=Image.Resampling.LANCZOS)


def _dhash(image: Image.Image, hash_size: int = 16) -> str:
    gray = _normalised_image(image, hash_size + 1)
    gray = gray.resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    getter = getattr(gray, "get_flattened_data", None)
    px = list(getter() if getter is not None else gray.getdata())
    bits: list[int] = []
    row = hash_size + 1
    for y in range(hash_size):
        offset = y * row
        for x in range(hash_size):
            bits.append(px[offset + x] > px[offset + x + 1])
    return _bits_to_hex(bits)


def _image_information_score(image: Image.Image) -> float:
    gray = _normalised_image(image, 48)
    stat = ImageStat.Stat(gray)
    std = float(stat.stddev[0])
    extrema = gray.getextrema()
    contrast = float(extrema[1] - extrema[0])
    # Both all-black and all-white masks are rejected. A very flat icon is also
    # unsafe for perceptual matching because it can create spurious high scores.
    return min(1.0, (std / 32.0) * 0.7 + (contrast / 128.0) * 0.3)


def image_fingerprint(image_bytes: bytes) -> dict[str, object]:
    digest = sha256(image_bytes).hexdigest()
    with Image.open(BytesIO(image_bytes)) as image:
        image.load()
        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError("image has invalid dimensions")
        return {
            "sha256": digest,
            "dhash": _dhash(image),
            "width": width,
            "height": height,
            "aspect_ratio": width / height,
            "information_score": _image_information_score(image),
        }


@dataclass(frozen=True, slots=True)
class SemanticProfile:
    semantic_id: str
    category: str
    role_name: str | None
    speaker_type: str | None
    special_meaning: str
    exact_sha256: tuple[str, ...] = ()
    perceptual_hashes: tuple[str, ...] = ()
    min_aspect_ratio: float = 0.20
    max_aspect_ratio: float = 5.0
    review_status: str = "reviewed"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "SemanticProfile":
        return cls(
            semantic_id=str(raw["semantic_id"]),
            category=str(raw["category"]),
            role_name=(str(raw["role_name"]) if raw.get("role_name") else None),
            speaker_type=(str(raw["speaker_type"]) if raw.get("speaker_type") else None),
            special_meaning=str(raw.get("special_meaning", "")),
            exact_sha256=tuple(str(x) for x in raw.get("exact_sha256", [])),
            perceptual_hashes=tuple(str(x) for x in raw.get("perceptual_hashes", [])),
            min_aspect_ratio=float(raw.get("min_aspect_ratio", 0.20)),
            max_aspect_ratio=float(raw.get("max_aspect_ratio", 5.0)),
            review_status=str(raw.get("review_status", "reviewed")),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "semantic_id": self.semantic_id,
            "category": self.category,
            "role_name": self.role_name,
            "speaker_type": self.speaker_type,
            "special_meaning": self.special_meaning,
            "exact_sha256": list(self.exact_sha256),
            "perceptual_hashes": list(self.perceptual_hashes),
            "min_aspect_ratio": self.min_aspect_ratio,
            "max_aspect_ratio": self.max_aspect_ratio,
            "review_status": self.review_status,
        }


@dataclass(frozen=True, slots=True)
class MatchResult:
    status: str
    semantic_id: str | None
    confidence: float
    method: str
    evidence: dict[str, object]


class VisualSemanticCatalog:
    """Reviewed visual-semantic catalog with fail-closed matching.

    Matching order is exact SHA-256 -> reviewed perceptual templates. Profiles
    without reviewed image evidence stay unresolved; semantic names alone never
    produce a visual identity.
    """

    def __init__(
        self,
        profiles: Iterable[SemanticProfile],
        *,
        max_dhash_distance: int = 24,
        ambiguity_margin: int = 5,
        min_information_score: float = 0.08,
    ) -> None:
        self._profiles = tuple(profiles)
        self.max_dhash_distance = max_dhash_distance
        self.ambiguity_margin = ambiguity_margin
        self.min_information_score = min_information_score
        ids = [p.semantic_id for p in self._profiles]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate semantic_id in visual catalog")

    @property
    def profiles(self) -> tuple[SemanticProfile, ...]:
        return self._profiles

    @classmethod
    def load(cls, path: str | Path) -> "VisualSemanticCatalog":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(raw.get("schema_version", 0)) != 1:
            raise ValueError("unsupported visual catalog schema")
        settings = raw.get("matching", {})
        return cls(
            [SemanticProfile.from_mapping(p) for p in raw["profiles"]],
            max_dhash_distance=int(settings.get("max_dhash_distance", 24)),
            ambiguity_margin=int(settings.get("ambiguity_margin", 5)),
            min_information_score=float(settings.get("min_information_score", 0.08)),
        )

    def dump(self, path: str | Path) -> None:
        payload = {
            "schema_version": 1,
            "matching": {
                "max_dhash_distance": self.max_dhash_distance,
                "ambiguity_margin": self.ambiguity_margin,
                "min_information_score": self.min_information_score,
            },
            "profiles": [p.to_mapping() for p in self._profiles],
        }
        Path(path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def profile(self, semantic_id: str) -> SemanticProfile:
        for profile in self._profiles:
            if profile.semantic_id == semantic_id:
                return profile
        raise KeyError(semantic_id)

    def add_reviewed_template(self, semantic_id: str, image_bytes: bytes) -> "VisualSemanticCatalog":
        fp = image_fingerprint(image_bytes)
        if float(fp["information_score"]) < self.min_information_score:
            raise ValueError("refusing low-information visual template")
        updated: list[SemanticProfile] = []
        found = False
        for profile in self._profiles:
            if profile.semantic_id != semantic_id:
                updated.append(profile)
                continue
            found = True
            exact = tuple(dict.fromkeys((*profile.exact_sha256, str(fp["sha256"]))))
            perceptual = tuple(dict.fromkeys((*profile.perceptual_hashes, str(fp["dhash"]))))
            updated.append(replace(profile, exact_sha256=exact, perceptual_hashes=perceptual))
        if not found:
            raise KeyError(semantic_id)
        return VisualSemanticCatalog(
            updated,
            max_dhash_distance=self.max_dhash_distance,
            ambiguity_margin=self.ambiguity_margin,
            min_information_score=self.min_information_score,
        )

    def match(self, image_bytes: bytes) -> MatchResult:
        fp = image_fingerprint(image_bytes)
        info = float(fp["information_score"])
        if info < self.min_information_score:
            return MatchResult(
                status="unresolved",
                semantic_id=None,
                confidence=0.0,
                method="low-information-rejected",
                evidence=fp,
            )
        exact = [p for p in self._profiles if str(fp["sha256"]) in p.exact_sha256]
        if len(exact) == 1:
            return MatchResult(
                status="matched",
                semantic_id=exact[0].semantic_id,
                confidence=1.0,
                method="exact-sha256",
                evidence=fp,
            )
        if len(exact) > 1:
            return MatchResult(
                status="ambiguous",
                semantic_id=None,
                confidence=0.0,
                method="duplicate-exact-evidence",
                evidence={**fp, "candidate_ids": [p.semantic_id for p in exact]},
            )

        aspect = float(fp["aspect_ratio"])
        scored: list[tuple[int, SemanticProfile]] = []
        for profile in self._profiles:
            if profile.review_status != "reviewed" or not profile.perceptual_hashes:
                continue
            if not (profile.min_aspect_ratio <= aspect <= profile.max_aspect_ratio):
                continue
            distance = min(_hex_hamming(str(fp["dhash"]), h) for h in profile.perceptual_hashes)
            scored.append((distance, profile))
        scored.sort(key=lambda x: (x[0], x[1].semantic_id))
        if not scored or scored[0][0] > self.max_dhash_distance:
            return MatchResult(
                status="unresolved",
                semantic_id=None,
                confidence=0.0,
                method="no-reviewed-template-match",
                evidence={**fp, "best_distance": scored[0][0] if scored else None},
            )
        best_distance, best_profile = scored[0]
        second_distance = scored[1][0] if len(scored) > 1 else 10**9
        if second_distance - best_distance < self.ambiguity_margin:
            return MatchResult(
                status="ambiguous",
                semantic_id=None,
                confidence=0.0,
                method="perceptual-margin-too-small",
                evidence={
                    **fp,
                    "best": [best_profile.semantic_id, best_distance],
                    "second": [scored[1][1].semantic_id, second_distance],
                },
            )
        confidence = max(0.0, 1.0 - best_distance / max(1, self.max_dhash_distance + 8))
        return MatchResult(
            status="matched",
            semantic_id=best_profile.semantic_id,
            confidence=round(confidence, 6),
            method="reviewed-dhash",
            evidence={**fp, "distance": best_distance},
        )
