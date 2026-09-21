"""Versioned, deterministic text sent to the embedding provider."""

import hashlib
import unicodedata
from collections.abc import Mapping
from typing import Any

MODEL_VERSION = "vertex-ai/gemini-embedding-001/512/retrieval-v1/canonical-v1"
DIMENSIONS = 512
CANONICAL_VERSION = "canonical-v1"
FIELDS = (
    "language",
    "term",
    "meaning",
    "part_of_speech",
    "part_of_speech_detail",
    "reading",
    "pronunciation",
    "romanization",
    "target_language_definition",
    "example_sentence",
    "example_translation",
)
EDITABLE_SEMANTIC_FIELDS = frozenset(FIELDS[1:]) | {"synonyms", "antonyms"}


def canonical_text(card: Mapping[str, Any]) -> str:
    """Normalize only the approved semantic fields in their fixed order."""

    lines = []
    for field in FIELDS:
        value = card.get(field)
        if value is not None:
            normalized = unicodedata.normalize("NFC", str(value).strip())
            if normalized:
                lines.append(f"{field}: {normalized}")
    for field in ("synonyms", "antonyms"):
        for value in card.get(field) or ():
            normalized = unicodedata.normalize("NFC", str(value).strip())
            if normalized:
                lines.append(f"{field}: {normalized}")
    return "\n".join(lines)


def content_hash(card: Mapping[str, Any]) -> str:
    payload = f"{CANONICAL_VERSION}\n{canonical_text(card)}".encode()
    return hashlib.sha256(payload).hexdigest()
