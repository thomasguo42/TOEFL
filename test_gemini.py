"""Manual Gemini SDK smoke script (disabled under pytest).

This file is named like a pytest test module, but it is intended as a manual
example. It is skipped during automated test runs unless explicitly enabled.
"""

import os

import pytest

if os.getenv("RUN_LIVE_GEMINI_TESTS", "").strip().lower() not in {"1", "true", "yes", "y"}:
    pytest.skip("Skipping live Gemini smoke script (set RUN_LIVE_GEMINI_TESTS=1 to enable).", allow_module_level=True)

import google.generativeai as genai  # noqa: E402

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("Missing GEMINI_API_KEY for live Gemini smoke script.")

genai.configure(api_key=api_key)

model = genai.GenerativeModel(model_name='gemini-2.5-flash')

# Text generation
response = model.generate_content("What are the main benefits of the Gemini 3 Flash API?")
print(response.text)

# Chat (multi-turn)
chat = model.start_chat(history=[])
chat.send_message("Hi, tell me a fun fact about space.")
print(chat.last.text)

