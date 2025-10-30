import os
from unittest import mock

import pytest
from flask import Flask

from app.flask_app.services.gemini_client import GeminiClient
from app.flask_app.services import reading_content


class _Resp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if 400 <= self.status_code:
            import requests

            raise requests.exceptions.HTTPError(response=self)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def app_context():
    app = Flask(__name__)
    with app.app_context():
        yield


def test_max_tokens_empty_text_falls_back_to_flash(monkeypatch):
    # Arrange: ensure fallback is enabled
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_FALLBACK_ON_MAX_TOKENS", "true")
    client = GeminiClient(api_key="test-key")

    # First response: MAX_TOKENS with empty text
    first = _Resp(200, {
        "candidates": [
            {
                "finishReason": "MAX_TOKENS",
                "content": {"parts": [{"text": ""}]},
            }
        ]
    })
    # Second (fallback model) response: valid JSON text
    second = _Resp(200, {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"parts": [{"text": "{\"ok\": true}"}]},
            }
        ]
    })

    calls = []

    def fake_post(url, json=None, timeout=None):  # noqa: A002 - shadowing builtin allowed in tests
        calls.append(url)
        return first if len(calls) == 1 else second

    with mock.patch("app.flask_app.services.gemini_client.requests.post", side_effect=fake_post):
        result = client.generate_json("prompt", response_mime="application/json")

    assert result == {"ok": True}
    # Ensure we tried the primary and then the fallback model
    assert "gemini-2.5-pro" in calls[0]
    assert "gemini-2.5-flash" in calls[1]


def test_robust_json_substring_extraction():
    text = "Some preface. Here is JSON: ```json\n{\n  \"a\": 1\n}\n``` and some trailer."
    parsed = GeminiClient._robust_parse_json(text)
    assert isinstance(parsed, dict)
    assert parsed.get("a") == 1


def test_seed_fallback_on_429(monkeypatch):
    # Make Gemini raise HTTPError (429) to trigger outer retry/fallback logic
    import requests

    def raise_429(*args, **kwargs):
        resp = mock.Mock()
        resp.status_code = 429
        raise requests.exceptions.HTTPError(response=resp)

    monkeypatch.setattr(reading_content.GeminiClient, "generate_json", staticmethod(lambda *a, **k: raise_429()))

    # Speed up backoff during test
    monkeypatch.setattr(reading_content, "time", mock.Mock(sleep=lambda *_: None))

    # Execute
    sentence = reading_content.get_sentence()
    paragraph = reading_content.get_paragraph()
    passage = reading_content.get_passage()

    # We expect non-None fallbacks from seeds
    assert isinstance(sentence, dict) and sentence.get("text")
    assert isinstance(paragraph, dict) and paragraph.get("paragraph")
    assert isinstance(passage, dict) and passage.get("paragraphs")

