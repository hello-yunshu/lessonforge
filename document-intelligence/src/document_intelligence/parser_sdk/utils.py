from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def stable_id(prefix: str, *parts: object, length: int = 24) -> str:
    material = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(material).hexdigest()[:length]}"


def digest_mapping(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_bbox(
    bbox: tuple[float, float, float, float], width: float, height: float
) -> tuple[float, float, float, float]:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    x1, y1, x2, y2 = bbox
    values = (x1 / width, y1 / height, x2 / width, y2 / height)
    return tuple(min(1.0, max(0.0, float(item))) for item in values)  # type: ignore[return-value]
