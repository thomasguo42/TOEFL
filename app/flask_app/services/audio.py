"""Audio utilities for generating or retrieving pronunciation assets."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from flask import current_app
from gtts import gTTS
from werkzeug.utils import secure_filename

from models import Word, db


def ensure_pronunciation_audio(word: Word) -> Optional[str]:
    """
    Ensure the given word has an associated pronunciation audio file.

    Returns the static relative path to the audio asset, or None if generation fails.
    """
    if word.pronunciation_audio_url:
        return word.pronunciation_audio_url

    static_root = Path(current_app.root_path) / "static" / "audio"
    static_root.mkdir(parents=True, exist_ok=True)

    safe_name = secure_filename(f"{word.id}_{word.lemma.lower()}")
    filename = f"{safe_name}.mp3"
    file_path = static_root / filename

    if not file_path.exists():
        try:
            tts = gTTS(text=word.lemma, lang="en", slow=False)
            tts.save(str(file_path))
        except Exception as exc:  # pragma: no cover - gTTS errors are environment specific
            current_app.logger.warning("Failed to generate audio for %s: %s", word.lemma, exc)
            return None

    relative_path = f"audio/{filename}"
    word.pronunciation_audio_url = relative_path
    try:
        db.session.commit()
    except Exception as exc:  # pragma: no cover - commit failures handled upstream
        current_app.logger.error("Failed to persist audio URL for %s: %s", word.lemma, exc)
        db.session.rollback()
        return None

    return relative_path

