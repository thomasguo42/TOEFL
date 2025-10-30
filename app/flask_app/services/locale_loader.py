"""Lightweight loader for locale JSON files stored under app/shared/locales."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

LOCALES_ROOT = Path(__file__).resolve().parents[3] / "app" / "shared" / "locales"


@lru_cache(maxsize=None)
def load_locale(language: str, namespace: str) -> Dict[str, Any]:
    """Load a locale dictionary (e.g., language='cn', namespace='reading')."""
    path = LOCALES_ROOT / language / f"{namespace}.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        try:
            payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}
