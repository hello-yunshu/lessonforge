from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
import warnings

from PIL import Image, UnidentifiedImageError

from document_intelligence.exceptions import CorruptInputError, UnsupportedInputError
from document_intelligence.schema import ParseRequest

Image.MAX_IMAGE_PIXELS = 120_000_000


@dataclass(frozen=True, slots=True)
class IngestionPolicy:
    max_upload_bytes: int
    allowed_mime_types: frozenset[str] = frozenset(
        {"application/pdf", "image/png", "image/jpeg", "image/webp"}
    )


def detect_mime(filename: str, content: bytes) -> str:
    header = content[:1024]
    if b"%PDF-" in header:
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _safe_filename(filename: str) -> str:
    value = filename.strip()
    if not value:
        raise CorruptInputError("filename is required")
    if PurePath(value).name != value or any(ord(char) < 32 for char in value):
        raise CorruptInputError("filename must be a control-character-free basename")
    if len(value) > 255:
        raise CorruptInputError("filename is too long")
    return value


def _verify_image(content: bytes, mime_type: str) -> None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                image.verify()
                detected = (image.format or "").upper()
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise CorruptInputError(f"invalid image payload: {exc}") from exc
    expected = {
        "image/png": "PNG",
        "image/jpeg": "JPEG",
        "image/webp": "WEBP",
    }[mime_type]
    if detected != expected:
        raise CorruptInputError(
            f"image signature/decoder mismatch: expected {expected}, got {detected}"
        )


def ingest_bytes(
    filename: str,
    content: bytes,
    *,
    policy: IngestionPolicy,
    parser_id: str | None = None,
    domain_pack: str | None = None,
    options: dict[str, object] | None = None,
) -> ParseRequest:
    safe_name = _safe_filename(filename)
    if not content:
        raise CorruptInputError("empty upload")
    if len(content) > policy.max_upload_bytes:
        raise CorruptInputError(
            f"upload exceeds limit: {len(content)} > {policy.max_upload_bytes} bytes"
        )
    mime_type = detect_mime(safe_name, content)
    if mime_type not in policy.allowed_mime_types:
        raise UnsupportedInputError("unsupported or unrecognized file signature")
    if mime_type.startswith("image/"):
        _verify_image(content, mime_type)
    return ParseRequest(
        filename=safe_name,
        mime_type=mime_type,
        content=content,
        parser_id=parser_id,
        domain_pack=domain_pack,
        options=options or {},
    )
