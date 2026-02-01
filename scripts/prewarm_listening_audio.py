#!/usr/bin/env python3
"""Pre-generate listening audio for full-length practice tests."""
from __future__ import annotations

import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLASK_ROOT = ROOT / "app" / "flask_app"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(FLASK_ROOT))

import app as flask_app
from services.full_length_tests import list_full_length_tests
from services.full_length_mock import build_full_length_listening_mock
from services.gemini_client import GeminiClient
from services.tts_service import TTSService


def main() -> int:
    tests = list_full_length_tests()
    if not tests:
        print("No full-length tests found.")
        return 1

    tts = TTSService()
    client = GeminiClient(api_key=None)
    with flask_app.app.app_context():
        for test in tests:
            test_id = test.get("id")
            title = test.get("title")
            if not test_id:
                continue
            print(f"Prewarming listening audio for {title} ({test_id})...")
            mock = build_full_length_listening_mock(test_id, client=client, tts=tts)
            if not mock:
                print(f"  Failed to build listening mock for {test_id}")
                continue
            print(
                f"  Responses: {len(mock.get('responses', []))}, "
                f"Conversations: {len(mock.get('conversation', []))}, "
                f"Talks: {len(mock.get('talk', []))}"
            )
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
