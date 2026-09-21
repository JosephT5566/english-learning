"""Canonical text and provider contract boundaries."""

import math

import pytest

from app.embeddings import EmbeddingFailure, validate_vector
from app.semantic_text import DIMENSIONS, canonical_text, content_hash


def test_canonical_text_normalizes_and_ignores_review_only_fields() -> None:
    card = {
        "language": "en",
        "term": " cafe\u0301 ",
        "meaning": "coffee shop",
        "synonyms": ["coffeehouse", " cafe "],
        "note": "private note",
        "review_stage": 3,
    }
    assert canonical_text(card) == (
        "language: en\nterm: café\nmeaning: coffee shop\n"
        "synonyms: coffeehouse\nsynonyms: cafe"
    )
    original = content_hash(card)
    assert content_hash({**card, "note": "other", "review_stage": 4}) == original
    assert content_hash({**card, "meaning": "different"}) != original


@pytest.mark.parametrize(
    "vector",
    [
        [1.0] * (DIMENSIONS - 1),
        [0.0] * DIMENSIONS,
        [math.inf] + [1.0] * (DIMENSIONS - 1),
    ],
)
def test_invalid_provider_vector_is_rejected(vector: list[float]) -> None:
    with pytest.raises(EmbeddingFailure):
        validate_vector(vector)
