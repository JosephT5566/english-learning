"""Deterministic review validation, hashing, and scheduling tests."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.reviews import ReviewSubmission, _request_hash, _transition

CARD_ID = UUID("20000000-0000-0000-0000-000000000001")
REVIEWED_AT = datetime(2026, 9, 4, 16, 30, tzinfo=UTC)


def submission(items: list[dict[str, object]]) -> ReviewSubmission:
    return ReviewSubmission.model_validate({"items": items})


def test_request_hash_is_canonical_but_preserves_item_order() -> None:
    first = submission([{"card_id": CARD_ID, "decision": "yes", "expected_version": 2}])
    equivalent = ReviewSubmission.model_validate_json(
        '{"items":[{"expected_version":2,"decision":"yes",'
        '"card_id":"20000000-0000-0000-0000-000000000001"}]}'
    )
    reordered = submission(
        [
            {"card_id": CARD_ID, "decision": "yes", "expected_version": 2},
            {
                "card_id": "20000000-0000-0000-0000-000000000002",
                "decision": "no",
                "expected_version": 4,
            },
        ]
    )

    assert _request_hash(first) == _request_hash(equivalent)
    assert _request_hash(first) != _request_hash(reordered)


def test_submission_rejects_duplicate_cards_and_server_fields() -> None:
    with pytest.raises(ValidationError):
        submission(
            [
                {"card_id": CARD_ID, "decision": "yes", "expected_version": 2},
                {"card_id": CARD_ID, "decision": "no", "expected_version": 2},
            ]
        )

    with pytest.raises(ValidationError):
        ReviewSubmission.model_validate(
            {
                "items": [
                    {
                        "card_id": CARD_ID,
                        "decision": "yes",
                        "expected_version": 2,
                        "next_review_at": "2026-09-05T00:00:00Z",
                    }
                ]
            }
        )


@pytest.mark.parametrize(
    (
        "decision",
        "expected_quality",
        "expected_stage",
        "expected_ease",
        "expected_interval",
    ),
    [
        ("no", 0, 1, Decimal("1.50"), 2),
        ("no_a_bit", 2, 1, Decimal("1.98"), 2),
        ("yes_a_bit", 3, 3, Decimal("2.16"), 15),
        ("yes", 5, 3, Decimal("2.40"), 17),
    ],
)
def test_transition_uses_corrected_ease_arguments_and_taipei_midnight(
    decision: str,
    expected_quality: int,
    expected_stage: int,
    expected_ease: Decimal,
    expected_interval: int,
) -> None:
    row = SimpleNamespace(
        review_stage=2,
        ease_factor=Decimal("2.30"),
        version=7,
    )

    transition = _transition(row, decision, REVIEWED_AT)

    assert transition["quality"] == expected_quality
    assert transition["resulting_review_stage"] == expected_stage
    assert transition["resulting_ease_factor"] == expected_ease
    assert transition["resulting_interval_days"] == expected_interval
    assert transition["resulting_version"] == 8
    assert transition["resulting_next_review_at"] == datetime(
        2026, 9, 4 + expected_interval, 16, tzinfo=UTC
    )
