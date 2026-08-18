from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable

import cv2
import numpy as np

from document_intelligence.schema import Element, Page

_WHITESPACE_RE = re.compile(r"\s+")
FINGERPRINT_VERSION = "2"


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def page_text(page: Page, elements: Iterable[Element]) -> str:
    relevant = [item for item in elements if item.page_id == page.page_id and item.content.text]
    relevant.sort(
        key=lambda item: (
            item.reading_order if item.reading_order is not None else 10**9,
            item.bbox.y1,
            item.bbox.x1,
        )
    )
    return normalize_text("\n".join(item.content.text or "" for item in relevant))


def text_ngram_hashes(value: str, n: int = 3, limit: int = 4096) -> list[str]:
    compact = value.replace(" ", "")
    if not compact:
        return []
    if len(compact) < n:
        compact = compact.ljust(n, "\0")
    hashes = {
        hashlib.blake2b(compact[index : index + n].encode("utf-8"), digest_size=8).hexdigest()
        for index in range(len(compact) - n + 1)
    }
    return sorted(hashes)[:limit]


def layout_digest(page: Page, elements: Iterable[Element]) -> str:
    tokens: list[str] = []
    for item in sorted(
        (value for value in elements if value.page_id == page.page_id),
        key=lambda value: (
            value.reading_order if value.reading_order is not None else 10**9,
            value.bbox.y1,
            value.bbox.x1,
        ),
    ):
        quantized = tuple(
            round(number * 20)
            for number in (item.bbox.x1, item.bbox.y1, item.bbox.x2, item.bbox.y2)
        )
        tokens.append(f"{item.base_type.value}:{quantized}")
    return hashlib.sha256("|".join(tokens).encode("utf-8")).hexdigest()


def image_sha256(image: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("unable to encode image")
    return hashlib.sha256(encoded.tobytes()).hexdigest()


def dhash(image: np.ndarray) -> str:
    gray = to_gray(image)
    resized = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = resized[:, 1:] > resized[:, :-1]
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def dhash_similarity(first: str, second: str) -> float:
    distance = (int(first, 16) ^ int(second, 16)).bit_count()
    return 1.0 - distance / 64.0


def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def extract_orb(image: np.ndarray, *, max_features: int = 2500) -> tuple[np.ndarray, np.ndarray]:
    gray = to_gray(image)
    detector = cv2.ORB_create(
        nfeatures=max_features,
        scaleFactor=1.2,
        nlevels=8,
        edgeThreshold=15,
        fastThreshold=7,
    )
    keypoints, descriptors = detector.detectAndCompute(gray, None)
    points = np.array([keypoint.pt for keypoint in keypoints], dtype=np.float32)
    if descriptors is None:
        descriptors = np.empty((0, 32), dtype=np.uint8)
    return points, descriptors


def text_jaccard(query_hashes: Iterable[str], candidate_hashes: Iterable[str]) -> float:
    first = set(query_hashes)
    second = set(candidate_hashes)
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)
