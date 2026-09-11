"""Export the application OpenAPI document deterministically for frontend generation."""

import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = API_ROOT / "openapi.json"

sys.path.insert(0, str(API_ROOT))

from app.main import create_app


def main() -> None:
    """Write the schema without starting the API or loading runtime secrets."""

    schema = create_app().openapi()
    OUTPUT_PATH.write_text(
        json.dumps(schema, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
