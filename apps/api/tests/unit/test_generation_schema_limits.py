"""Local schema-projection regression for the maintainer's one-model Vertex bisect."""

import json

import pytest
from pydantic import ValidationError

from app.extraction import extraction_prompt
from app.generation import vertex_response_schema
from app.writes import CardDrafts


def assert_no_array_cardinality_keywords(value):
    if isinstance(value, dict):
        assert not ({"minItems", "maxItems"} & value.keys())
        for child in value.values():
            assert_no_array_cardinality_keywords(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_array_cardinality_keywords(child)


def test_card_draft_provider_schema_omits_array_limits_at_every_level():
    schema = vertex_response_schema(CardDrafts.model_json_schema())
    assert_no_array_cardinality_keywords(schema)
    card = schema["properties"]["cards"]["items"]
    assert card["properties"]["term"]["minLength"] == 1
    assert card["properties"]["term"]["maxLength"] == 255
    assert card["properties"]["learned_on"]["format"] == "date"
    assert card["properties"]["learned_on"]["nullable"] is True
    assert "other" in card["properties"]["part_of_speech"]["enum"]
    assert schema["required"] == ["cards"]
    assert card["required"] == ["term", "meaning"]


def test_nested_references_drop_only_array_limits_and_keep_other_supported_keywords():
    source = {
        "type": "object",
        "required": ["groups"],
        "properties": {
            "groups": {
                "type": "array",
                "minItems": 1,
                "maxItems": 20,
                "items": {"$ref": "#/$defs/Group"},
            },
        },
        "$defs": {
            "Group": {
                "type": "object",
                "required": ["terms"],
                "description": "Synthetic group",
                "properties": {
                    "terms": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 10,
                        "items": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 3,
                            "items": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 255,
                                "enum": ["harbor", "dawn"],
                            },
                        },
                    },
                    "score": {"type": "number", "minimum": 0, "maximum": 1},
                    "date": {
                        "anyOf": [
                            {"type": "string", "format": "date"},
                            {"type": "null"},
                        ]
                    },
                },
            },
        },
    }
    schema = vertex_response_schema(source)
    assert_no_array_cardinality_keywords(schema)
    assert schema["required"] == ["groups"]
    group = schema["properties"]["groups"]["items"]
    assert group["required"] == ["terms"]
    assert group["description"] == "Synthetic group"
    assert group["properties"]["score"] == {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
    }
    assert group["properties"]["date"] == {
        "type": "string",
        "format": "date",
        "nullable": True,
    }
    assert group["properties"]["terms"]["items"]["items"] == {
        "type": "string",
        "minLength": 1,
        "maxLength": 255,
        "enum": ["harbor", "dawn"],
    }
    assert source["properties"]["groups"]["minItems"] == 1
    assert source["$defs"]["Group"]["properties"]["terms"]["maxItems"] == 10


@pytest.mark.parametrize("count,expected_type", [(0, "too_short"), (21, "too_long")])
def test_full_card_drafts_model_still_rejects_out_of_range_output(count, expected_type):
    with pytest.raises(ValidationError) as error:
        CardDrafts.model_validate_json(
            json.dumps({"cards": [{"term": "harbor", "meaning": "shelter"}] * count}),
            strict=True,
        )
    assert any(
        detail["loc"] == ("cards",) and detail["type"] == expected_type
        for detail in error.value.errors()
    )


def test_prompt_already_states_card_count_boundary():
    assert "Return 1-20 cards" in extraction_prompt("en", "zh-TW")
