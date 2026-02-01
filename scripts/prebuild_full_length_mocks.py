"""Prebuild full-length New TOEFL mocks and cache them on disk."""
from __future__ import annotations

from app.flask_app.app import app
from app.flask_app.services.full_length_tests import list_full_length_tests
from app.flask_app.services.full_length_mock import (
    build_full_length_reading_mock,
    build_full_length_listening_mock,
    build_full_length_writing_mock,
)
from app.flask_app.services.new_toefl_mock import generate_speaking_mock, get_interview_sets
from app.flask_app.services.tts_service import get_tts_service
from app.flask_app.services.gemini_client import get_gemini_client


def main() -> None:
    tests = list_full_length_tests()
    if not tests:
        print("No full-length tests found.")
        return

    with app.app_context():
        client = get_gemini_client()
        tts = get_tts_service()
        for test in tests:
            test_id = test.get("id")
            title = test.get("title")
            if not test_id:
                continue
            print(f"Prebuilding {title} ({test_id})...")
            reading = build_full_length_reading_mock(test_id, client=client)
            if reading:
                print("  - reading: ok")
            else:
                print("  - reading: failed")

            listening = build_full_length_listening_mock(test_id, client=client, tts=tts)
            if listening:
                print("  - listening: ok")
            else:
                print("  - listening: failed")

            writing = build_full_length_writing_mock(test_id)
            if writing:
                print("  - writing: ok")
            else:
                print("  - writing: failed")

        interview_sets = get_interview_sets()
        if interview_sets:
            print("Prebuilding speaking audio...")
            for speaking_set in interview_sets:
                set_id = speaking_set.get("id")
                if not set_id:
                    continue
                mock = generate_speaking_mock(tts=tts, interview_set_id=set_id, allow_ai=False)
                if mock:
                    print(f"  - speaking {set_id}: ok")
                else:
                    print(f"  - speaking {set_id}: failed")


if __name__ == "__main__":
    main()
