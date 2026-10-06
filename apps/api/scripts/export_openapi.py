"""Export public OpenAPI and card-draft JSON Schema for frontend generation."""

import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = API_ROOT / "openapi.json"

sys.path.insert(0, str(API_ROOT))

from app.main import create_app
from app.writes import CardDrafts


def main() -> None:
    """Write public schemas without starting the API or loading runtime secrets."""

    schema = create_app().openapi()
    OUTPUT_PATH.write_text(
        json.dumps(schema, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    draft_schema = CardDrafts.model_json_schema(mode="validation")
    draft_schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    draft_path = API_ROOT.parents[1] / "src/lib/api/card-drafts.schema.json"
    draft_path.write_text(
        json.dumps(draft_schema, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
