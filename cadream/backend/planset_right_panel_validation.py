from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from jsonschema import Draft202012Validator


_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "right-panel-metadata-v1.schema.json"
_SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
_VALIDATOR = Draft202012Validator(_SCHEMA)


def validate_right_panel_payload(payload: dict[str, Any]) -> list[str]:
    errors = []
    for error in sorted(_VALIDATOR.iter_errors(payload), key=lambda e: list(e.path)):
        path = ".".join(str(part) for part in error.path) if error.path else "payload"
        errors.append(f"{path}: {error.message}")
    return errors
