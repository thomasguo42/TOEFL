"""
TOEFL Vocabulary Studio - Flask Application
Main application file with all routes and session management.
"""
import os
import json
import random
import re
import time
import logging
from logging.handlers import RotatingFileHandler
import threading
from difflib import SequenceMatcher
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Optional, List, Dict, Any, Tuple

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    current_app,
    g,
    has_request_context,
)
from werkzeug.exceptions import HTTPException
from flask_cors import CORS
from sqlalchemy import and_, or_, inspect, text, func
from sqlalchemy.orm.attributes import flag_modified
from markupsafe import Markup

from config import config
from models import db, User, Word, UserWord, ReviewLog, UnfamiliarWord, NewToeflMockRecord
from scheduler import compute_schedule
from utils import (
    hash_password,
    verify_password,
    login_required,
    get_current_user,
    get_due_words,
    get_fallback_words,
    get_or_create_user_word,
    log_review,
    get_todays_progress,
    get_mastery_breakdown,
    get_memorize_curve,
    get_words_by_mastery,
    get_smart_session_composition,
    get_learning_velocity,
    get_study_streak,
    search_words,
    get_words_reviewed_today,
    get_words_in_stage_range,
    get_unfamiliar_words_for_study
)
from services.audio import ensure_pronunciation_audio
from services.exercise_generator import (
    generate_gap_fill_single,
    generate_reading_passage_single,
    generate_synonym_single,
)
from services.gemini_client import get_gemini_client
from services.drill_store import (
    set_drill as store_drill,
    get_drill as load_drill,
    delete_drill as remove_drill,
    update_drill as save_drill,
    count as count_drill_store,
)
from services.locale_loader import load_locale
from services.new_toefl_mock import (
    generate_listening_mock,
    generate_reading_mock,
    generate_speaking_mock,
    generate_writing_mock,
    get_interview_sets,
)
from services.full_length_tests import (
    list_full_length_tests,
    get_reading_section,
    get_listening_section,
    get_writing_section,
)
from services.full_length_mock import (
    build_full_length_reading_mock,
    build_full_length_listening_mock,
    build_full_length_writing_mock,
)
from services.reading_content import (
    evaluate_paraphrase,
    get_paragraph,
    get_passage,
    get_sentence,
)
from services.question_types import (
    generate_question_type_drill,
    get_question_types_by_category,
    get_question_type_metadata,
)
from services.tts_service import get_tts_service
from services.listening_generator import (
    generate_dictation_sentence,
    generate_dictation_sentences_batch,
    generate_signpost_segment,
    generate_signpost_segments_batch,
    generate_lecture,
    generate_conversation,
    find_answer_timestamps,
)
from services.speech_rater import get_speech_rater
from services.speaking_feedback_engine import get_feedback_engine
from services.writing_analyzer import get_writing_analyzer
from models import (
    ListeningSentence,
    ListeningSignpost,
    ListeningLecture,
    ListeningConversation,
    ListeningQuestion,
    ListeningUserProgress,
)


def _load_new_toefl_speaking_rubrics() -> Dict[str, str]:
    """Load TOEFL speaking rubrics text for New TOEFL mock feedback pages."""
    rubrics_path = Path(__file__).resolve().parents[2] / "TOEFL_Practice_Test" / "speaking-rubrics.txt"
    if not rubrics_path.exists():
        return {"repeat": "", "interview": "", "full": ""}
    text = rubrics_path.read_text(encoding="utf-8", errors="ignore")
    lower = text.lower()
    guide_idx = lower.find("speaking scoring guide")
    repeat_idx = 0 if text else -1
    interview_idx = guide_idx if guide_idx != -1 else -1
    repeat_text = ""
    interview_text = ""
    if repeat_idx != -1 and interview_idx != -1:
        repeat_text = text[repeat_idx:interview_idx].strip()
        interview_text = text[interview_idx:].strip()
    elif repeat_idx != -1:
        repeat_text = text[repeat_idx:].strip()
    elif interview_idx != -1:
        interview_text = text[interview_idx:].strip()
    return {"repeat": repeat_text, "interview": interview_text, "full": text.strip()}


def _map_overall_to_band(score: Optional[float]) -> int:
    if score is None:
        return 0
    if score >= 90:
        return 5
    if score >= 80:
        return 4
    if score >= 70:
        return 3
    if score >= 60:
        return 2
    if score >= 50:
        return 1
    return 0


def _round_to_half(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    return round(float(value) * 2) / 2


def _map_delivery_score_to_band(score: Optional[float]) -> float:
    if score is None:
        return 0.0
    score = float(score)
    if score >= 92:
        return 5.0
    if score >= 88:
        return 4.5
    if score >= 82:
        return 4.0
    if score >= 76:
        return 3.5
    if score >= 70:
        return 3.0
    if score >= 64:
        return 2.5
    if score >= 58:
        return 2.0
    if score >= 52:
        return 1.5
    if score >= 46:
        return 1.0
    if score >= 40:
        return 0.5
    return 0.0


# Initialize Flask app
app = Flask(__name__)
app.config.from_object(config[os.getenv('FLASK_ENV', 'development')])

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------

def _configure_logging(flask_app: Flask) -> None:
    root_logger = logging.getLogger()

    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level_name, logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s [req=%(request_id)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    class _RequestIdFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - name mandated by stdlib
            if has_request_context():
                record.request_id = getattr(g, "request_id", "-")
            else:
                record.request_id = "-"
            return True

    request_filter = _RequestIdFilter()

    log_dir_value = os.getenv("LOG_DIR")
    if log_dir_value:
        log_dir = Path(log_dir_value).expanduser()
    else:
        repo_root = Path(__file__).resolve().parents[3]
        log_dir = repo_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"

    def _has_handler_named(name: str) -> bool:
        return any(getattr(handler, "name", None) == name for handler in root_logger.handlers)

    def _has_file_handler(target: Path) -> bool:
        target_str = str(target)
        for handler in root_logger.handlers:
            if isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", "") == target_str:
                return True
        return False

    if not _has_handler_named("toefl_stream"):
        stream = logging.StreamHandler()
        stream.name = "toefl_stream"
        stream.setLevel(level)
        stream.setFormatter(formatter)
        stream.addFilter(request_filter)
        root_logger.addHandler(stream)

    if not _has_file_handler(log_path):
        file_handler = RotatingFileHandler(
            log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
        file_handler.name = "toefl_file"
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(request_filter)
        root_logger.addHandler(file_handler)

    root_logger.setLevel(level)
    logging.getLogger("werkzeug").setLevel(level)
    flask_app.logger.setLevel(level)
    flask_app.logger.propagate = True


_configure_logging(app)

# Initialize extensions
db.init_app(app)
CORS(app, resources={r"/*": {"origins": "*"}})

# Session management for vocabulary learning
# Structure: {session_id: {'user_id': int, 'queue': deque, 'seen': set}}
active_sessions = {}

# Server-side cache for reading practice batches
# Structure: {batch_id: [item1, item2, ...]}
# This avoids exceeding browser cookie limits when storing large content
if not hasattr(app, '_reading_batches'):
    app._reading_batches = {}

# Server-side cache for question type drills
# Structure: {drill_id: {passage, topic, questions, ...}}
# This avoids session cookie size limits when storing 5 questions
if not hasattr(app, '_question_drills'):
    app._question_drills = {}

# Server-side cache for new TOEFL mocks (reading/listening/writing)
if not hasattr(app, '_new_toefl_cache'):
    app._new_toefl_cache = {}
if not hasattr(app, '_new_toefl_jobs'):
    app._new_toefl_jobs = {}
if not hasattr(app, '_new_toefl_jobs_lock'):
    app._new_toefl_jobs_lock = threading.Lock()

_WORD_COUNT_NOTE_PATTERN = re.compile(r'\(\s*\d+\s*words?\s*\)', re.IGNORECASE)
_MULTISPACE_PATTERN = re.compile(r'[ \t]{2,}')
_CHOICE_PREFIX_PATTERN = re.compile(r'^\s*([A-Z])[\)\.\:\-]')

def _prewarm_tts_blocking() -> None:
    """Block server start until Kokoro is warm (prevents Cloudflare 524 on first request)."""
    if os.getenv("PREWARM_TTS", "true").strip().lower() not in {"1", "true", "yes", "y"}:
        return
    try:
        with app.app_context():
            tts = get_tts_service()
            t0 = time.monotonic()
            current_app.logger.info("Startup: prewarming TTS...")
            tts.prewarm()
            current_app.logger.info("Startup: TTS prewarm done in %.2fs", time.monotonic() - t0)
    except Exception:
        app.logger.exception("Startup: TTS prewarm failed")

@app.before_request
def _assign_request_id():
    # Prefer incoming header for tracing through proxies/tunnels.
    rid = request.headers.get("X-Request-Id") or request.headers.get("CF-Ray") or uuid4().hex[:12]
    g.request_id = rid
    g._request_start = time.monotonic()


@app.after_request
def _log_request(response):
    start = getattr(g, "_request_start", None)
    if start is not None:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        current_app.logger.info("%s %s -> %s (%sms)", request.method, request.path, response.status_code, elapsed_ms)
    response.headers["X-Request-Id"] = getattr(g, "request_id", "-")
    return response


@app.errorhandler(Exception)
def _unhandled_exception(exc):
    if isinstance(exc, HTTPException):
        return exc
    current_app.logger.exception("Unhandled exception: %s", exc)
    return jsonify({"success": False, "message": "Internal server error", "request_id": getattr(g, "request_id", None)}), 500


def _sanitize_generated_text(text: Optional[str]) -> str:
    if not text:
        return ''

    cleaned = _WORD_COUNT_NOTE_PATTERN.sub('', text)
    # Normalize spaces around newlines
    cleaned = re.sub(r'\s+\n', '\n', cleaned)
    cleaned = re.sub(r'\n\s+', '\n', cleaned)
    cleaned = _MULTISPACE_PATTERN.sub(' ', cleaned)
    return cleaned.strip()


def _extract_choice_letter(text: Optional[str]) -> str:
    if not text:
        return ''
    stripped = text.strip()
    if not stripped:
        return ''
    if len(stripped) == 1 and stripped.isalpha():
        return stripped.upper()
    match = _CHOICE_PREFIX_PATTERN.match(stripped)
    if match:
        return match.group(1).upper()
    return ''


def _option_lookup(options: Optional[List[str]]) -> tuple[dict[str, str], dict[str, str]]:
    letter_map: dict[str, str] = {}
    text_map: dict[str, str] = {}
    auto_letters = [chr(ord('A') + i) for i in range(26)]

    for idx, option in enumerate(options or []):
        sanitized = _sanitize_generated_text(option)
        if not sanitized:
            continue
        letter = _extract_choice_letter(sanitized)

        if not letter and idx < len(auto_letters):
            fallback_letter = auto_letters[idx]
            if fallback_letter not in letter_map:
                letter = fallback_letter

        if letter and letter not in letter_map:
            letter_map[letter] = sanitized
        text_map[sanitized.lower()] = sanitized
    return letter_map, text_map


def _answers_match(user_answer: str, correct_answer: str, options: Optional[List[str]]) -> bool:
    user = (user_answer or '').strip()
    correct = (correct_answer or '').strip()
    if not user or not correct:
        return False
    if user.casefold() == correct.casefold():
        return True

    letter_map, _ = _option_lookup(options)
    user_letter = _extract_choice_letter(user)
    correct_letter = _extract_choice_letter(correct)

    if user_letter and correct_letter and user_letter == correct_letter:
        return True

    if correct_letter and correct_letter in letter_map:
        correct_option = letter_map[correct_letter]
        if user.casefold() == correct_option.casefold():
            return True
        if user_letter and user_letter in letter_map:
            return letter_map[user_letter].casefold() == correct_option.casefold()

    if user_letter and user_letter in letter_map:
        user_option = letter_map[user_letter]
        if correct.casefold() == user_option.casefold():
            return True

    if correct_letter and correct.casefold() == correct_letter.casefold():
        return user_letter == correct_letter

    if user_letter and user.casefold() == user_letter.casefold():
        return correct_letter == user_letter

    return False


def _format_answer_display(answer: str, options: Optional[List[str]]) -> str:
    answer = (answer or '').strip()
    if not answer:
        return ''
    letter_map, _ = _option_lookup(options)
    letter = _extract_choice_letter(answer)
    if letter and letter in letter_map:
        return letter_map[letter]
    return answer


def _normalize_sentence(text: str) -> str:
    if not text:
        return ''
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9\\s]", "", lowered)
    lowered = _MULTISPACE_PATTERN.sub(' ', lowered)
    return lowered.strip()

def _normalize_for_similarity(text: str) -> str:
    if not text:
        return ""
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9\\s]", " ", lowered)
    lowered = _MULTISPACE_PATTERN.sub(" ", lowered)
    return lowered.strip()


def _too_similar(candidate: str, existing: List[str], threshold: float = 0.88) -> bool:
    cand = _normalize_for_similarity(candidate)
    if not cand or not existing:
        return False
    for prior in existing:
        prev = _normalize_for_similarity(prior)
        if not prev:
            continue
        ratio = SequenceMatcher(None, cand, prev).ratio()
        if ratio >= threshold:
            return True
    return False


def _extract_practice_text(item: Dict[str, Any], practice_type: str) -> str:
    if not isinstance(item, dict):
        return ""
    if practice_type == "sentence":
        return str(item.get("text") or "")
    if practice_type == "paragraph":
        return str(item.get("paragraph") or "")
    if practice_type == "passage":
        paragraphs = item.get("paragraphs") or []
        if isinstance(paragraphs, list):
            return "\n".join(str(p.get("text") or "") for p in paragraphs if isinstance(p, dict))
        return ""
    return ""


def _expand_topic_variants(base_topic: str, count: int) -> List[str]:
    base = (base_topic or "").strip()
    if not base:
        return []
    facets = [
        "history",
        "recent research",
        "case study",
        "methodology",
        "applications",
        "trade-offs",
        "ethical debate",
        "policy impact",
        "data trends",
        "future directions",
    ]
    random.shuffle(facets)
    variants = []
    for idx in range(count):
        facet = facets[idx % len(facets)]
        variants.append(f"{base} ({facet})")
    return variants


def _store_new_toefl_payload(section: str, user_id: int, payload: Dict[str, Any]) -> str:
    cache = getattr(current_app, '_new_toefl_cache', {})
    cache_id = f"new_toefl_{section}_{user_id}_{int(time.time())}"
    cache[cache_id] = payload
    current_app._new_toefl_cache = cache
    session[f'new_toefl_{section}_id'] = cache_id
    return cache_id


def _reserve_new_toefl_payload(section: str, user_id: int) -> str:
    cache = getattr(current_app, '_new_toefl_cache', {})
    cache_id = f"new_toefl_{section}_{user_id}_{int(time.time())}"
    cache[cache_id] = {}
    current_app._new_toefl_cache = cache
    session[f'new_toefl_{section}_id'] = cache_id
    return cache_id


def _get_new_toefl_job(job_id: str) -> Optional[Dict[str, Any]]:
    jobs = getattr(current_app, "_new_toefl_jobs", {})
    return jobs.get(job_id) if isinstance(jobs, dict) else None


def _put_new_toefl_job(job_id: str, payload: Dict[str, Any]) -> None:
    lock = getattr(current_app, "_new_toefl_jobs_lock", None)
    jobs = getattr(current_app, "_new_toefl_jobs", {})
    if not isinstance(jobs, dict):
        jobs = {}
    if lock:
        with lock:
            jobs[job_id] = payload
            current_app._new_toefl_jobs = jobs
    else:
        jobs[job_id] = payload
        current_app._new_toefl_jobs = jobs


def _get_new_toefl_payload(section: str) -> Optional[Dict[str, Any]]:
    cache_id = session.get(f'new_toefl_{section}_id')
    if not cache_id:
        return None
    cache = getattr(current_app, '_new_toefl_cache', {})
    return cache.get(cache_id)


def _clear_new_toefl_payload(section: str) -> None:
    cache_id = session.pop(f'new_toefl_{section}_id', None)
    if not cache_id:
        return
    cache = getattr(current_app, '_new_toefl_cache', {})
    if cache_id in cache:
        del cache[cache_id]
        current_app._new_toefl_cache = cache


def _throttle_new_toefl(section: str, window_seconds: int = 90) -> bool:
    now = time.time()
    key = f'new_toefl_{section}_last'
    last = session.get(key)
    if last and isinstance(last, (int, float)) and now - last < window_seconds:
        return True
    session[key] = now
    return False

def _normalize_gap_fill_items(exercises: list[dict]) -> list[dict]:
    normalized = []
    for item in exercises or []:
        if not isinstance(item, dict):
            continue
        sentence = item.get('sentence')
        options = item.get('options', [])
        if not sentence:
            fallback_word = item.get('word') if isinstance(item, dict) else ''
            sentence = f"_____ best completes the idea related to {fallback_word}."
        options = [opt for opt in options if isinstance(opt, str)]
        if not options:
            continue
        answer_field = item.get('answer')
        if isinstance(answer_field, int) and 0 <= answer_field < len(options):
            answer_value = options[answer_field]
        elif isinstance(answer_field, str):
            answer_value = answer_field
            if answer_value not in options:
                options.append(answer_value)
        else:
            answer_value = item.get('word')
            if answer_value and answer_value not in options:
                options.append(answer_value)
        if not answer_value:
            continue
        rationale_source = item.get('rationales', {}) if isinstance(item, dict) else {}
        rationales = {}
        for opt in options:
            rationale_text = rationale_source.get(opt)
            if not rationale_text:
                if opt == answer_value:
                    rationale_text = "该选项与句意完全匹配。"
                else:
                    rationale_text = "此选项无法契合句子的语气或语义。"
            rationales[opt] = rationale_text
        normalized.append({
            'sentence': sentence,
            'options': options,
            'answer': answer_value,
            'rationales': rationales
        })
    return normalized


def _normalize_synonym_items(exercises: list[dict]) -> list[dict]:
    normalized = []
    for item in exercises or []:
        if not isinstance(item, dict):
            continue
        sentence = item.get('sentence') if isinstance(item, dict) else ''
        options = item.get('options', []) if isinstance(item, dict) else []
        options = [opt for opt in options if isinstance(opt, str)]
        if not options:
            continue
        answer_field = item.get('answer')
        if isinstance(answer_field, int) and 0 <= answer_field < len(options):
            answer_value = options[answer_field]
        elif isinstance(answer_field, str):
            answer_value = answer_field
        else:
            answer_value = item.get('word')
        if not answer_value:
            continue
        if answer_value not in options:
            options.append(answer_value)
        explanation = item.get('explanation_cn') or item.get('explanation') or '最佳答案最符合语境。'
        rationale_source = item.get('rationales', {}) if isinstance(item, dict) else {}
        rationales = {}
        for opt in options:
            rationale_text = rationale_source.get(opt)
            if not rationale_text:
                if opt == answer_value:
                    rationale_text = "该同义词最贴合句子的语气。"
                else:
                    rationale_text = "语义相近但在此语境下不够准确。"
            rationales[opt] = rationale_text
        normalized.append({
            'sentence': sentence or f"Choose the synonym closest to '{answer_value}'.",
            'options': options,
            'answer': answer_value,
            'explanation_cn': explanation,
            'rationales': rationales
        })
    return normalized


def _prepare_gap_fill_payload(user: User):
    """Generate 5 sets of gap-fill exercises by calling DeepSeek 5 times."""
    import time

    words = get_words_reviewed_today(user.id)
    if not words:
        return None, None, 'Start studying some words first to unlock exercises.'

    client = get_gemini_client()
    if not client or not client.is_configured:
        return None, None, 'DeepSeek API is not configured. Please check your API key in the config.'

    # Generate 5 sets, one at a time - DeepSeekClient handles retries and backoff for API errors
    exercises = []
    for i in range(5):
        # Pick a word for this set
        word = words[i % len(words)]

        try:
            exercise = generate_gap_fill_single(word, client)
            if exercise:
                exercises.append(exercise)
                current_app.logger.info(f"Successfully generated gap-fill exercise #{i+1}")
            else:
                current_app.logger.warning(f"Failed to generate gap-fill exercise #{i+1}")
        except Exception as e:
            current_app.logger.error(f"Error generating gap-fill exercise #{i+1}: {e}")
            # Continue to try remaining exercises

    if not exercises:
        return None, None, 'DeepSeek failed to generate gap-fill exercises. Please try again in a moment.'

    normalized = _normalize_gap_fill_items(exercises)
    return normalized, True, None


def _prepare_synonym_payload(user: User):
    """Generate 5 sets of synonym exercises by calling DeepSeek 5 times."""
    import time

    words = get_words_reviewed_today(user.id)
    if not words:
        return None, None, 'Start studying some words first to unlock exercises.'

    client = get_gemini_client()
    if not client or not client.is_configured:
        return None, None, 'DeepSeek API is not configured. Please check your API key in the config.'

    # Generate 5 sets, one at a time - DeepSeekClient handles retries and backoff for API errors
    exercises = []
    for i in range(5):
        # Pick a word for this set
        word = words[i % len(words)]

        try:
            exercise = generate_synonym_single(word, client)
            if exercise:
                exercises.append(exercise)
                current_app.logger.info(f"Successfully generated synonym exercise #{i+1}")
            else:
                current_app.logger.warning(f"Failed to generate synonym exercise #{i+1}")
        except Exception as e:
            current_app.logger.error(f"Error generating synonym exercise #{i+1}: {e}")
            # Continue to try remaining exercises

    if not exercises:
        return None, None, 'DeepSeek failed to generate synonym exercises. Please try again in a moment.'

    normalized = _normalize_synonym_items(exercises)
    return normalized, True, None


def _prepare_reading_passage_payload(user: User, topic: Optional[str]):
    """Generate 5 sets of reading passages by calling DeepSeek 5 times."""
    import time

    topics = [
        'Astronomy',
        'Ecology',
        'Anthropology',
        'Economics',
        'Architecture',
        'Geology',
        'Neuroscience',
    ]

    client = get_gemini_client()
    if not client or not client.is_configured:
        return None, None, None, 'DeepSeek API is not configured. Please check your API key in the config.'

    # Generate 5 sets, one at a time - DeepSeekClient handles retries and backoff for API errors
    passages = []
    for i in range(5):
        # Pick a topic for this set (rotate through topics if not specified)
        chosen_topic = topic or topics[i % len(topics)]

        # Get words for this passage
        srs_candidates = get_words_in_stage_range(user.id, min_repetitions=2, max_repetitions=8, limit=7)
        supplemental = get_words_reviewed_today(user.id)

        seen_ids = {word.id for word in srs_candidates}
        for word in supplemental:
            if word.id not in seen_ids and len(srs_candidates) < 7:
                srs_candidates.append(word)
                seen_ids.add(word.id)

        if not srs_candidates:
            current_app.logger.warning(f"No words available for reading passage #{i+1}")
            continue

        try:
            passage = generate_reading_passage_single(srs_candidates, chosen_topic, client)
            if passage:
                # Add highlight words to passage data
                passage['highlight_words'] = [word.lemma for word in srs_candidates]
                passages.append(passage)
                current_app.logger.info(f"Successfully generated reading passage #{i+1}")
            else:
                current_app.logger.warning(f"Failed to generate reading passage #{i+1}")
        except Exception as e:
            current_app.logger.error(f"Error generating reading passage #{i+1}: {e}")
            # Continue to try remaining passages

    if not passages:
        return None, None, None, 'DeepSeek failed to generate reading passages. Please try again in a moment.'

    # Return first passage (for single-passage view) but store all 5 for batch navigation
    first_passage = passages[0]
    highlight_words = first_passage.get('highlight_words', [])

    # Store all 5 passages in session for navigation
    session['reading_passage_batch'] = passages
    session['reading_passage_batch_index'] = 0
    session.modified = True

    return first_passage, highlight_words, True, None

# Register Jinja filters
@app.template_filter('markdown_bold')
def markdown_bold_filter(text):
    """Jinja filter to convert **word** to <strong>word</strong>."""
    return markdown_bold_to_html(text if text else '')


def highlight_vocabulary(paragraph: str, words: list[str]) -> Markup:
    """Wrap target words with markup for highlighting in templates."""
    if not words:
        return Markup(paragraph)

    escaped = [re.escape(w) for w in words if w]
    if not escaped:
        return Markup(paragraph)

    pattern = re.compile(r'\b(' + '|'.join(escaped) + r')\b', flags=re.IGNORECASE)

    def replacer(match: re.Match) -> str:
        token = match.group(0)
        return f'<mark class="vocab-highlight" data-word="{token.lower()}">{token}</mark>'

    highlighted = pattern.sub(replacer, paragraph)
    return Markup(highlighted)


def markdown_bold_to_html(text: str) -> Markup:
    """Convert **word** markdown syntax to <strong>word</strong> HTML."""
    if not text:
        return Markup('')
    # Replace **text** with <strong>text</strong>
    converted = re.sub(r'\*\*([^*]+)\*\*', r'<strong style="color: var(--teal-400);">\1</strong>', text)
    return Markup(converted)


def init_database():
    """Initialize database and seed words if needed."""
    with app.app_context():
        db.create_all()

        inspector = inspect(db.engine)
        with db.engine.begin() as conn:
            word_columns = {col['name'] for col in inspector.get_columns('words')}
            signpost_columns = {col['name'] for col in inspector.get_columns('listening_signposts')}
            if 'pronunciation_audio_url' not in word_columns:
                conn.execute(text('ALTER TABLE words ADD COLUMN pronunciation_audio_url VARCHAR(500)'))
            if 'pronunciation_pitfall_cn' not in word_columns:
                conn.execute(text('ALTER TABLE words ADD COLUMN pronunciation_pitfall_cn TEXT'))
            if 'option_explanations_cn' not in signpost_columns:
                conn.execute(text('ALTER TABLE listening_signposts ADD COLUMN option_explanations_cn TEXT'))

        # Seed words from CSV files
        repo_root = Path(__file__).resolve().parents[3]
        seed_dir = repo_root / "data" / "seeds"

        if seed_dir.exists():
            csv_files = sorted(seed_dir.glob("*.csv"))
            for csv_file in csv_files:
                seed_words_from_file(csv_file)

        print("[DATABASE] Initialized successfully")


def seed_words_from_file(csv_path: Path):
    """Seed words from a CSV file."""
    import csv

    if not csv_path.exists():
        return

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            lemma = row.get('lemma', '').strip()
            if not lemma:
                continue

            existing = Word.query.filter_by(lemma=lemma).first()
            if existing:
                continue

            word = Word(
                lemma=lemma,
                definition=row.get('definition', '').strip(),
                example=row.get('example', '').strip(),
                cn_gloss=row.get('cn_gloss', '').strip() or None,
                pronunciation_audio_url=row.get('pronunciation_audio_url', '').strip() or None,
                pronunciation_pitfall_cn=row.get('pronunciation_pitfall_cn', '').strip() or None
            )
            db.session.add(word)

    try:
        db.session.commit()
        print(f"[SEED] Loaded words from {csv_path.name}")
    except Exception as e:
        db.session.rollback()
        print(f"[SEED ERROR] {csv_path.name}: {e}")


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.route('/')
def index():
    """Home page - redirect to main dashboard or login."""
    if 'user_id' in session:
        return redirect(url_for('main_dashboard'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration page."""
    if 'user_id' in session:
        return redirect(url_for('main_dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        daily_goal = request.form.get('daily_goal', '20')

        # Validation
        if not email or not password:
            flash('Email and password are required.', 'danger')
            return render_template('register.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('register.html')

        # Check if user exists
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash('Email already registered. Please log in.', 'warning')
            return redirect(url_for('login'))

        # Create user
        try:
            goal = int(daily_goal)
            goal = max(1, min(goal, 1000))  # Clamp between 1-1000
        except ValueError:
            goal = 20

        password_hash = hash_password(password)
        user = User(email=email, password_hash=password_hash, daily_goal=goal)
        db.session.add(user)
        db.session.commit()

        # Log in user
        session['user_id'] = user.id
        session['user_email'] = user.email
        session.permanent = True
        flash(f'Welcome, {email}! Your account has been created.', 'success')
        return redirect(url_for('main_dashboard'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page."""
    if 'user_id' in session:
        return redirect(url_for('main_dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()

        if user and verify_password(password, user.password_hash):
            session['user_id'] = user.id
            session['user_email'] = user.email
            session.permanent = True
            flash(f'Welcome back, {email}!', 'success')
            return redirect(url_for('main_dashboard'))
        else:
            flash('Invalid email or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Log out the user."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ============================================================================
# VOCABULARY SESSION ROUTES
# ============================================================================

@app.route('/session')
@login_required
def vocab_session():
    """Main vocabulary session page."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    # Get today's progress
    total, new_cards, review_cards = get_todays_progress(user.id)
    remaining = max(user.daily_goal - total, 0)
    goal_met = user.daily_goal > 0 and remaining <= 0

    session_id = session.get('vocab_session_id')
    card = None

    if goal_met:
        sess = None
    else:
        if not session_id or session_id not in active_sessions:
            session_id = create_vocab_session(user.id, remaining)
            session['vocab_session_id'] = session_id

        sess = active_sessions.get(session_id)
        if not sess or not sess['queue']:
            session_id = create_vocab_session(user.id, remaining)
            session['vocab_session_id'] = session_id
            sess = active_sessions[session_id]

        if sess.get('_normalized') is not True:
            sess['queue'] = deque(
                [item.id if isinstance(item, Word) else item for item in list(sess['queue'])]
            )
            sess['queue_ids'] = {
                item.id if isinstance(item, Word) else item for item in sess.get('queue_ids', set())
            }
            sess['seen'] = {
                item.id if isinstance(item, Word) else item for item in sess.get('seen', set())
            }
            sess['_normalized'] = True

        if sess['queue']:
            current_entry = sess['queue'][0]
            if isinstance(current_entry, Word):
                current_id = current_entry.id
                sess['queue'][0] = current_id
            else:
                current_id = current_entry
            current_word = Word.query.get(current_id)
            if current_word is not None:
                audio_path = ensure_pronunciation_audio(current_word)
                card = {
                    'word': current_word.to_dict(),
                    'remaining': len(sess['queue']),
                    'audio_url': url_for('static', filename=audio_path) if audio_path else None
                }

    todays_words = get_words_reviewed_today(user.id)
    exercise_ready = goal_met and len(todays_words) > 0

    return render_template(
        'session.html',
        user=user,
        card=card,
        progress={
            'goal': user.daily_goal,
            'reviewed': total,
            'new_count': new_cards,
            'review_count': review_cards,
            'remaining': remaining
        },
        session_id=session_id,
        goal_met=goal_met,
        todays_words=todays_words,
        exercise_ready=exercise_ready
    )


def create_vocab_session(user_id: int, goal_remaining: int):
    """Create a new vocabulary session with smart composition including unfamiliar words."""
    now = datetime.now(timezone.utc)
    batch_size = min(goal_remaining if goal_remaining > 0 else 20, 100)
    batch_size = max(batch_size, 10)

    # Get smart composition recommendation
    composition = get_smart_session_composition(user_id, batch_size)

    queue_words = []

    # Priority 1: Unfamiliar words (highest priority)
    if composition['unfamiliar'] > 0:
        unfamiliar = get_unfamiliar_words_for_study(user_id, limit=composition['unfamiliar'])
        queue_words.extend(unfamiliar)

    # Priority 2: Struggling words
    if composition['struggling'] > 0:
        struggling = db.session.query(Word).join(
            UserWord,
            (UserWord.word_id == Word.id) & (UserWord.user_id == user_id)
        ).filter(
            or_(
                UserWord.last_grade == 'not',
                UserWord.easiness < 1.7,
                and_(UserWord.interval < 1.0, UserWord.repetitions > 0)
            ),
            ~Word.id.in_([w.id for w in queue_words])
        ).order_by(UserWord.next_due).limit(composition['struggling']).all()
        queue_words.extend(struggling)

    # Priority 3: Due reviews
    if composition['due_review'] > 0:
        due = db.session.query(Word).join(
            UserWord,
            (UserWord.word_id == Word.id) & (UserWord.user_id == user_id)
        ).filter(
            UserWord.next_due <= now,
            UserWord.repetitions > 0,
            ~Word.id.in_([w.id for w in queue_words])
        ).order_by(UserWord.next_due).limit(composition['due_review']).all()
        queue_words.extend(due)

    # Priority 4: New words
    if composition['new'] > 0:
        new_words = get_fallback_words(
            user_id,
            exclude_ids=[w.id for w in queue_words],
            limit=composition['new']
        )
        queue_words.extend(new_words)

    # Shuffle to mix card types
    from random import shuffle
    shuffle(queue_words)

    queue_ids = [w.id for w in queue_words]

    session_id = uuid4().hex
    active_sessions[session_id] = {
        'user_id': user_id,
        'queue': deque(queue_ids),
        'seen': set(),
        'queue_ids': set(queue_ids),
        'composition': composition
    }

    return session_id


@app.route('/session/<session_id>/grade', methods=['POST'])
@login_required
def grade_card(session_id):
    """Grade a vocabulary card."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401

    sess = active_sessions.get(session_id)
    if not sess or sess['user_id'] != user.id:
        return jsonify({'error': 'Invalid session'}), 400

    # Normalize any legacy queue entries that still hold Word objects
    if sess.get('_normalized') is not True:
        sess['queue'] = deque(
            [item.id if isinstance(item, Word) else item for item in list(sess['queue'])]
        )
        sess['queue_ids'] = {
            item.id if isinstance(item, Word) else item for item in sess.get('queue_ids', set())
        }
        sess['seen'] = {
            item.id if isinstance(item, Word) else item for item in sess.get('seen', set())
        }
        sess['_normalized'] = True

    word_id = request.json.get('word_id')
    grade = request.json.get('grade')
    latency_ms = request.json.get('latency_ms')

    if grade not in ['recognize', 'barely', 'not']:
        return jsonify({'error': 'Invalid grade'}), 400

    # Get or create user_word
    user_word = get_or_create_user_word(user.id, word_id)
    if not user_word:
        return jsonify({'error': 'Word not found'}), 404

    was_new = user_word.repetitions == 0

    # Update schedule
    updated, next_due = compute_schedule(user_word, grade, user.id)
    db.session.add(updated)

    # Log review
    log_review(
        user.id,
        word_id,
        grade,
        latency_ms,
        is_new=was_new,
        easiness=updated.easiness,
        interval=updated.interval
    )
    db.session.commit()

    # Update session queue
    current_entry = sess['queue'].popleft() if sess['queue'] else None
    if isinstance(current_entry, Word):
        current_id = current_entry.id
    else:
        current_id = current_entry
    current_word = Word.query.get(current_id) if current_id else None
    if current_id:
        sess['seen'].add(current_id)
        sess['queue_ids'].discard(current_id)

    # Requeue if needed
    if grade in ['barely', 'not'] and current_id:
        offset = 2 if grade == 'barely' else 1
        items = list(sess['queue'])
        insert_at = min(len(items), offset)
        items.insert(insert_at, current_id)
        sess['queue'] = deque(items)
        sess['queue_ids'].add(current_id)

    # Get next card
    next_card = None
    if sess['queue']:
        next_entry = sess['queue'][0]
        if isinstance(next_entry, Word):
            next_id = next_entry.id
            sess['queue'][0] = next_id
        else:
            next_id = next_entry
        next_word = Word.query.get(next_id)
        if next_word:
            audio_path = ensure_pronunciation_audio(next_word)
            next_card = {
                'word': next_word.to_dict(),
                'remaining': len(sess['queue']),
                'audio_url': url_for('static', filename=audio_path) if audio_path else None
            }

    # Get updated progress
    total, new_cards, review_cards = get_todays_progress(user.id)
    remaining = max(user.daily_goal - total, 0)

    return jsonify({
        'card': next_card,
        'remaining': len(sess['queue']) if sess['queue'] else 0,
        'progress': {
            'goal': user.daily_goal,
            'reviewed': total,
            'new_count': new_cards,
            'review_count': review_cards,
            'remaining': remaining
        },
        'review': {
            'word': current_word.to_dict() if current_word else None,
            'grade': grade,
            'is_new': was_new,
            'easiness': updated.easiness,
            'interval': updated.interval,
            'next_due': next_due.isoformat()
        }
    })


# ============================================================================
# DASHBOARD & ANALYTICS ROUTES
# ============================================================================

@app.route('/dashboard')
@login_required
def main_dashboard():
    """Main TOEFL dashboard with all sections."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    # Get basic progress stats
    total, new_cards, review_cards = get_todays_progress(user.id)
    remaining = max(user.daily_goal - total, 0)

    progress = {
        'goal': user.daily_goal,
        'reviewed': total,
        'new_count': new_cards,
        'review_count': review_cards,
        'remaining': remaining
    }

    return render_template(
        'main_dashboard.html',
        user=user,
        progress=progress
    )


@app.route('/old-toefl')
@login_required
def old_toefl_dashboard():
    """Old TOEFL hub for existing section practice tools."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('old_toefl_dashboard.html', user=user)


@app.route('/new-toefl')
@login_required
def new_toefl_dashboard():
    """New TOEFL hub page (mock + practice)."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('new_toefl_dashboard.html', user=user)


@app.route('/new-toefl/mock')
@login_required
def new_toefl_mock_hub():
    """New TOEFL full-length mock hub."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('new_toefl/mock_dashboard.html', user=user)


@app.route('/new-toefl/practice')
@login_required
def new_toefl_practice_hub():
    """New TOEFL AI practice hub."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('new_toefl/practice_dashboard.html', user=user)


@app.route('/new-toefl/reading-mock')
@login_required
def new_toefl_reading_mock():
    """New TOEFL reading mock exam (full-length tests)."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('new_toefl/reading_full_mock.html', user=user)


@app.route('/new-toefl/listening-mock')
@login_required
def new_toefl_listening_mock():
    """New TOEFL listening mock exam (full-length tests)."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('new_toefl/listening_full_mock.html', user=user)


@app.route('/new-toefl/speaking-mock')
@login_required
def new_toefl_speaking_mock():
    """New TOEFL speaking mock exam (full-length tests)."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('new_toefl/speaking_full_mock.html', user=user)


@app.route('/new-toefl/writing-mock')
@login_required
def new_toefl_writing_mock():
    """New TOEFL writing mock exam (full-length tests)."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('new_toefl/writing_full_mock.html', user=user)


@app.route('/new-toefl/reading-practice')
@login_required
def new_toefl_reading_practice():
    """New TOEFL reading practice (AI generated)."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('new_toefl/reading_mock.html', user=user)


@app.route('/new-toefl/listening-practice')
@login_required
def new_toefl_listening_practice():
    """New TOEFL listening practice (AI generated)."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('new_toefl/listening_mock.html', user=user)


@app.route('/new-toefl/speaking-practice')
@login_required
def new_toefl_speaking_practice():
    """New TOEFL speaking practice (AI generated)."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('new_toefl/speaking_mock.html', user=user)


@app.route('/new-toefl/writing-practice')
@login_required
def new_toefl_writing_practice():
    """New TOEFL writing practice (AI generated)."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('new_toefl/writing_mock.html', user=user)


@app.route('/new-toefl/speaking/task/<int:task_id>')
@login_required
def new_toefl_speaking_task(task_id):
    """Launch a single New TOEFL speaking mock task."""
    from models import SpeakingTask

    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    task = SpeakingTask.query.get_or_404(task_id)
    return render_template(
        'speaking/practice.html',
        task=task,
        user=user,
        mock_back_url=url_for('new_toefl_speaking_mock'),
        hide_regenerate=True,
        mock_mode=True,
    )


@app.route('/new-toefl/api/reading/generate', methods=['POST'])
@login_required
def new_toefl_reading_generate():
    """Generate a New TOEFL reading mock exam."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    if _throttle_new_toefl('reading'):
        cached = _get_new_toefl_payload('reading')
        if cached:
            return jsonify({'success': True, 'cached': True, 'mock': cached})
        return jsonify({'success': False, 'message': 'Please wait a minute before generating again.'}), 429

    client = get_gemini_client()
    if not client or not client.is_configured:
        return jsonify({'success': False, 'message': 'DeepSeek API is not configured'}), 503

    mock = generate_reading_mock(client)
    if not mock:
        cached = _get_new_toefl_payload('reading')
        if cached:
            return jsonify({'success': True, 'cached': True, 'mock': cached})
        return jsonify({'success': False, 'message': 'AI is busy right now. Please try again shortly.'}), 503

    cache_id = _store_new_toefl_payload('reading', user.id, mock)
    return jsonify({'success': True, 'cache_id': cache_id, 'mock': mock})


@app.route('/new-toefl/api/listening/generate', methods=['POST'])
@login_required
def new_toefl_listening_generate():
    """Generate a New TOEFL listening mock exam."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    current_app.logger.info("New TOEFL listening generation requested (user_id=%s)", user.id)

    # If a job is already in progress for this session, return it to avoid duplicates.
    existing_job_id = session.get("new_toefl_listening_job_id")
    if isinstance(existing_job_id, str):
        existing = _get_new_toefl_job(existing_job_id)
        if isinstance(existing, dict) and existing.get("status") in {"queued", "running"}:
            return jsonify({'success': True, 'job_id': existing_job_id, 'status': existing.get("status")})

    if _throttle_new_toefl('listening'):
        cached = _get_new_toefl_payload('listening')
        if cached:
            return jsonify({'success': True, 'cached': True, 'mock': cached})
        return jsonify({'success': False, 'message': 'Please wait a minute before generating again.'}), 429

    client = get_gemini_client()
    if not client or not client.is_configured:
        return jsonify({'success': False, 'message': 'DeepSeek API is not configured'}), 503

    # Async generation to avoid Cloudflare 524 timeouts (TTS can take minutes).
    cache_id = _reserve_new_toefl_payload('listening', user.id)
    job_id = f"job_listening_{user.id}_{uuid4().hex[:10]}"
    session["new_toefl_listening_job_id"] = job_id

    _put_new_toefl_job(job_id, {
        "status": "queued",
        "section": "listening",
        "user_id": user.id,
        "cache_id": cache_id,
        "created_at": time.time(),
        "error": None,
    })

    def _worker(job_id_value: str, cache_id_value: str, user_id_value: int) -> None:
        try:
            with app.app_context():
                _put_new_toefl_job(job_id_value, {
                    **(_get_new_toefl_job(job_id_value) or {}),
                    "status": "running",
                    "started_at": time.time(),
                })
                t0 = time.monotonic()
                client_local = get_gemini_client()
                if not client_local or not client_local.is_configured:
                    _put_new_toefl_job(job_id_value, {
                        **(_get_new_toefl_job(job_id_value) or {}),
                        "status": "failed",
                        "finished_at": time.time(),
                        "error": "DeepSeek API is not configured",
                    })
                    return

                tts = get_tts_service()
                current_app.logger.info("Listening mock (async): acquired TTS service (job_id=%s)", job_id_value)
                mock = generate_listening_mock(client_local, tts)
                elapsed = time.monotonic() - t0
                current_app.logger.info("Listening mock (async): finished in %.2fs (job_id=%s)", elapsed, job_id_value)

                if not mock:
                    _put_new_toefl_job(job_id_value, {
                        **(_get_new_toefl_job(job_id_value) or {}),
                        "status": "failed",
                        "finished_at": time.time(),
                        "error": "AI is busy right now. Please try again shortly.",
                    })
                    return

                cache = getattr(current_app, "_new_toefl_cache", {})
                cache[cache_id_value] = mock
                current_app._new_toefl_cache = cache

                _put_new_toefl_job(job_id_value, {
                    **(_get_new_toefl_job(job_id_value) or {}),
                    "status": "done",
                    "finished_at": time.time(),
                    "error": None,
                })
        except Exception as exc:
            with app.app_context():
                current_app.logger.exception("Listening mock (async) crashed (job_id=%s): %s", job_id_value, exc)
                _put_new_toefl_job(job_id_value, {
                    **(_get_new_toefl_job(job_id_value) or {}),
                    "status": "failed",
                    "finished_at": time.time(),
                    "error": "Generation crashed. Check server logs.",
                })

    threading.Thread(target=_worker, args=(job_id, cache_id, user.id), daemon=True).start()
    return jsonify({'success': True, 'job_id': job_id, 'cache_id': cache_id, 'status': 'queued'})


@app.route('/new-toefl/api/listening/job/<job_id>', methods=['GET'])
@login_required
def new_toefl_listening_job(job_id: str):
    """Poll listening mock generation job status."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    job = _get_new_toefl_job(job_id)
    if not isinstance(job, dict) or job.get("section") != "listening":
        return jsonify({'success': False, 'message': 'Job not found'}), 404
    if job.get("user_id") != user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    status = job.get("status")
    response: Dict[str, Any] = {
        "success": True,
        "job_id": job_id,
        "status": status,
        "error": job.get("error"),
    }
    if status == "done":
        payload = _get_new_toefl_payload("listening")
        response["mock"] = payload
    return jsonify(response)


@app.route('/new-toefl/api/speaking/generate', methods=['POST'])
@login_required
def new_toefl_speaking_generate():
    """Generate a New TOEFL speaking mock exam and persist tasks."""
    from models import SpeakingTask

    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    payload = request.get_json(silent=True) or {}
    interview_set_id = payload.get('interview_set_id')
    prebuilt_only = os.getenv("TOEFL_PREBUILT_ONLY", "false").lower() in {"1", "true", "yes"}

    if _throttle_new_toefl('speaking'):
        task_ids = session.get('new_toefl_speaking_task_ids') or []
        if task_ids:
            tasks = [{'id': task_id, 'label': f'Task {idx + 1}', 'task_type': 'new_toefl_cached', 'response_time': 45} for idx, task_id in enumerate(task_ids)]
            return jsonify({'success': True, 'cached': True, 'tasks': tasks})
        return jsonify({'success': False, 'message': 'Please wait a minute before generating again.'}), 429

    tts = get_tts_service()
    mock = generate_speaking_mock(
        client=None,
        tts=tts,
        interview_set_id=interview_set_id,
        allow_ai=not prebuilt_only,
    )
    if not mock:
        task_ids = session.get('new_toefl_speaking_task_ids') or []
        if task_ids:
            tasks = [{'id': task_id, 'label': f'Task {idx + 1}', 'task_type': 'new_toefl_cached', 'response_time': 45} for idx, task_id in enumerate(task_ids)]
            return jsonify({'success': True, 'cached': True, 'tasks': tasks})
        if prebuilt_only:
            return jsonify({'success': False, 'message': 'Prebuilt speaking mock missing. Run prebuild once.'}), 503
        return jsonify({'success': False, 'message': 'AI is busy right now. Please try again shortly.'}), 503

    tasks: List[Dict[str, Any]] = []
    repeat_items = mock.get('repeat', [])
    interview_items = mock.get('interview', [])

    for idx, item in enumerate(repeat_items, start=1):
        prompt = (item.get('prompt') or '').strip()
        if not prompt:
            continue
        task = SpeakingTask(
            task_number=100 + idx,
            task_type='new_toefl_repeat',
            topic='Listen and Repeat',
            prompt=prompt,
            listening_audio_url=item.get('audio_url'),
            listening_transcript=prompt,
            preparation_time=0,
            response_time=item.get('response_time_seconds', 10),
        )
        db.session.add(task)
        db.session.flush()
        tasks.append({
            'id': task.id,
            'label': f'Repeat {idx}',
            'task_type': task.task_type,
            'response_time': task.response_time,
        })

    for idx, item in enumerate(interview_items, start=1):
        prompt = (item.get('prompt') or '').strip()
        if not prompt:
            continue
        task = SpeakingTask(
            task_number=200 + idx,
            task_type='new_toefl_interview',
            topic='Interview',
            prompt=prompt,
            listening_audio_url=item.get('audio_url'),
            listening_transcript=prompt,
            preparation_time=0,
            response_time=item.get('response_time_seconds', 45),
            response_template='; '.join(item.get('focus_points') or []),
        )
        db.session.add(task)
        db.session.flush()
        tasks.append({
            'id': task.id,
            'label': f'Interview {idx}',
            'task_type': task.task_type,
            'response_time': task.response_time,
        })

    db.session.commit()
    session['new_toefl_speaking_task_ids'] = [task['id'] for task in tasks]

    return jsonify({'success': True, 'tasks': tasks})


@app.route('/new-toefl/api/speaking/interview-sets', methods=['GET'])
@login_required
def new_toefl_speaking_interview_sets():
    """Return available interview sets for New TOEFL speaking mock."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    sets = get_interview_sets()
    summary = [{'id': item.get('id'), 'title': item.get('title')} for item in sets]
    return jsonify({'success': True, 'sets': summary})


@app.route('/new-toefl/api/mock/tests', methods=['GET'])
@login_required
def new_toefl_mock_tests():
    """Return available full-length mock tests."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    return jsonify({'success': True, 'tests': list_full_length_tests()})


@app.route('/new-toefl/api/mock/records', methods=['GET'])
@login_required
def new_toefl_mock_records():
    """List saved full-length mock records for a section."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    section = request.args.get('section')
    test_id = request.args.get('test_id')
    allowed_sections = {'reading', 'listening', 'writing', 'speaking'}
    if section not in allowed_sections:
        return jsonify({'success': False, 'message': 'Invalid section'}), 400

    query = NewToeflMockRecord.query.filter_by(user_id=user.id, section=section)
    if test_id:
        query = query.filter_by(test_id=test_id)

    records = query.order_by(NewToeflMockRecord.updated_at.desc()).limit(25).all()
    return jsonify({'success': True, 'records': [record.to_summary() for record in records]})


@app.route('/new-toefl/api/mock/records/<int:record_id>', methods=['GET'])
@login_required
def new_toefl_mock_record(record_id: int):
    """Return a single saved full-length mock record."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    record = NewToeflMockRecord.query.get_or_404(record_id)
    if record.user_id != user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if record.section == 'speaking':
        from models import SpeakingResponse

        answers = record.answers or {}
        existing_responses = dict(answers.get('responses') or {})
        meta = record.meta or {}
        tasks_meta = meta.get('tasks') or []
        task_ids = [
            int(item.get('id')) for item in tasks_meta
            if isinstance(item, dict) and str(item.get('id', '')).isdigit()
        ]

        if task_ids:
            responses = (
                SpeakingResponse.query
                .filter(SpeakingResponse.user_id == user.id)
                .filter(SpeakingResponse.task_id.in_(task_ids))
                .order_by(SpeakingResponse.created_at.desc())
                .all()
            )
            latest_by_task: Dict[int, SpeakingResponse] = {}
            for response in responses:
                if response.task_id not in latest_by_task:
                    latest_by_task[response.task_id] = response

            updated = False
            new_responses = dict(existing_responses)
            for task_id, response in latest_by_task.items():
                task_key = str(task_id)
                if task_key in new_responses:
                    continue
                feedback = response.feedback
                new_responses[task_key] = {
                    'task_id': response.task_id,
                    'response_id': response.id,
                    'audio_url': response.audio_url,
                    'feedback_id': feedback.id if feedback else None,
                    'overall_score': feedback.overall_score if feedback else None,
                    'created_at': response.created_at.isoformat() if response.created_at else None,
                }
                updated = True

            if updated:
                record.answers = {**answers, 'responses': new_responses}
                flag_modified(record, 'answers')
                db.session.commit()

    return jsonify({'success': True, 'record': record.to_dict()})


@app.route('/new-toefl/api/mock/records/save', methods=['POST'])
@login_required
def new_toefl_mock_records_save():
    """Create or update a full-length mock record."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    payload = request.get_json(silent=True) or {}
    section = payload.get('section')
    test_id = payload.get('test_id')
    status = payload.get('status') or 'in_progress'
    answers = payload.get('answers') or {}
    meta = payload.get('meta') or {}
    record_id = payload.get('record_id')
    allowed_sections = {'reading', 'listening', 'writing', 'speaking'}
    if section not in allowed_sections or not test_id:
        return jsonify({'success': False, 'message': 'Invalid record payload'}), 400

    record = None
    if record_id:
        record = NewToeflMockRecord.query.get(record_id)
        if not record or record.user_id != user.id:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if not record:
        record = NewToeflMockRecord(
            user_id=user.id,
            section=section,
            test_id=test_id,
        )
        db.session.add(record)

    record.status = status
    if record.section == 'speaking' and record.answers:
        existing = record.answers or {}
        existing_responses = existing.get('responses') or {}
        incoming_responses = answers.get('responses') if isinstance(answers, dict) else None
        if not incoming_responses:
            answers = {**existing, **(answers if isinstance(answers, dict) else {})}
            answers['responses'] = existing_responses
        else:
            merged = {**existing_responses, **incoming_responses}
            answers = {**existing, **answers}
            answers['responses'] = merged
    record.answers = answers
    record.meta = meta
    db.session.commit()

    return jsonify({'success': True, 'record_id': record.id})


@app.route('/new-toefl/api/mock/chat', methods=['POST'])
@login_required
def new_toefl_mock_chat():
    """Chat assistant for full-length mocks with current page context."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    payload = request.get_json(silent=True) or {}
    message = (payload.get('message') or '').strip()
    if not message:
        return jsonify({'success': False, 'message': 'Message is required'}), 400

    context = payload.get('context') or {}
    history = payload.get('history') or []
    if not isinstance(history, list):
        history = []

    client = get_gemini_client()
    if not client or not client.is_configured:
        return jsonify({'success': False, 'message': 'Gemini API is not configured'}), 503

    context_blob = json.dumps(context, ensure_ascii=False)
    if len(context_blob) > 6000:
        context_blob = context_blob[:6000] + "...(truncated)"

    history_lines = []
    for entry in history[-8:]:
        if not isinstance(entry, dict):
            continue
        role = entry.get('role')
        content = (entry.get('content') or '').strip()
        if not content:
            continue
        prefix = "User" if role == "user" else "Assistant"
        history_lines.append(f"{prefix}: {content}")

    prompt = (
        "You are a TOEFL prep tutor helping the student on a mock test page. "
        "Follow these rules: "
        "1) Never reveal hidden reasoning, policies, or analysis. "
        "2) Respond in 1-3 short sentences. "
        "3) If asked for a direct answer, provide it clearly and briefly. "
        "4) If context is missing, ask one short clarifying question.\n\n"
        f"Context (JSON):\n{context_blob}\n\n"
    )
    if history_lines:
        prompt += "Conversation so far:\n" + "\n".join(history_lines) + "\n\n"
    prompt += f"User question:\n{message}\n"

    reply = client.generate_text(
        prompt=prompt,
        temperature=0.4,
        max_output_tokens=600,
        system_instruction="You are a helpful TOEFL mock test tutor.",
    )
    if not reply:
        return jsonify({'success': False, 'message': 'Chat service unavailable'}), 503

    return jsonify({'success': True, 'reply': reply})


@app.route('/new-toefl/api/mock/reading/<test_id>', methods=['GET'])
@login_required
def new_toefl_mock_reading(test_id: str):
    """Return full-length reading mock content for a test."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    payload = get_reading_section(test_id)
    if not payload:
        return jsonify({'success': False, 'message': 'Reading test not found'}), 404

    return jsonify({'success': True, 'data': payload})


@app.route('/new-toefl/api/mock/reading/load/<test_id>', methods=['GET'])
@login_required
def new_toefl_mock_reading_load(test_id: str):
    """Build full-length reading mock data and cache it for scoring."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    prebuilt_only = os.getenv("TOEFL_PREBUILT_ONLY", "false").lower() in {"1", "true", "yes"}
    client = get_gemini_client()
    client = client if client and client.is_configured else None
    mock = build_full_length_reading_mock(test_id, client=client)
    if not mock:
        if prebuilt_only:
            return jsonify({'success': False, 'message': 'Prebuilt reading mock missing. Run prebuild once.'}), 503
        if not client:
            return jsonify({'success': False, 'message': 'Gemini API is not configured'}), 503
        return jsonify({'success': False, 'message': 'Reading mock not found'}), 404

    cache_id = _store_new_toefl_payload('reading', user.id, mock)
    return jsonify({'success': True, 'cache_id': cache_id, 'mock': mock})


@app.route('/new-toefl/api/mock/listening/<test_id>', methods=['GET'])
@login_required
def new_toefl_mock_listening(test_id: str):
    """Return full-length listening mock content for a test."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    payload = get_listening_section(test_id)
    if not payload:
        return jsonify({'success': False, 'message': 'Listening test not found'}), 404

    return jsonify({'success': True, 'data': payload})


@app.route('/new-toefl/api/mock/listening/generate/<test_id>', methods=['POST'])
@login_required
def new_toefl_mock_listening_generate(test_id: str):
    """Generate a full-length listening mock with audio in the background."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    prebuilt = build_full_length_listening_mock(test_id, client=None, tts=None)
    if prebuilt:
        cache_id = _store_new_toefl_payload('listening', user.id, prebuilt)
        return jsonify({'success': True, 'cache_id': cache_id, 'mock': prebuilt, 'status': 'done', 'prebuilt': True})
    if os.getenv("TOEFL_PREBUILT_ONLY", "false").lower() in {"1", "true", "yes"}:
        return jsonify({'success': False, 'message': 'Prebuilt listening mock missing. Run prebuild once.'}), 503

    existing_job_id = session.get("new_toefl_mock_listening_job_id")
    if isinstance(existing_job_id, str):
        existing = _get_new_toefl_job(existing_job_id)
        if isinstance(existing, dict) and existing.get("status") in {"queued", "running"}:
            return jsonify({'success': True, 'job_id': existing_job_id, 'status': existing.get("status")})

    client = get_gemini_client()
    if not client or not client.is_configured:
        return jsonify({'success': False, 'message': 'Gemini API is not configured'}), 503

    cache_id = _reserve_new_toefl_payload('listening', user.id)
    job_id = f"job_listening_full_{user.id}_{uuid4().hex[:10]}"
    session["new_toefl_mock_listening_job_id"] = job_id

    _put_new_toefl_job(job_id, {
        "status": "queued",
        "section": "listening_full",
        "user_id": user.id,
        "cache_id": cache_id,
        "created_at": time.time(),
        "error": None,
    })

    def _worker(job_id_value: str, cache_id_value: str, user_id_value: int, test_id_value: str) -> None:
        try:
            with app.app_context():
                _put_new_toefl_job(job_id_value, {
                    **(_get_new_toefl_job(job_id_value) or {}),
                    "status": "running",
                    "started_at": time.time(),
                })
                client_local = get_gemini_client()
                if not client_local or not client_local.is_configured:
                    _put_new_toefl_job(job_id_value, {
                        **(_get_new_toefl_job(job_id_value) or {}),
                        "status": "failed",
                        "finished_at": time.time(),
                        "error": "Gemini API is not configured",
                    })
                    return

                tts = get_tts_service()
                mock = build_full_length_listening_mock(test_id_value, client=client_local, tts=tts)
                if not mock:
                    _put_new_toefl_job(job_id_value, {
                        **(_get_new_toefl_job(job_id_value) or {}),
                        "status": "failed",
                        "finished_at": time.time(),
                        "error": "Listening mock not found",
                    })
                    return

                cache = getattr(current_app, "_new_toefl_cache", {})
                cache[cache_id_value] = mock
                current_app._new_toefl_cache = cache

                _put_new_toefl_job(job_id_value, {
                    **(_get_new_toefl_job(job_id_value) or {}),
                    "status": "done",
                    "finished_at": time.time(),
                    "error": None,
                })
        except Exception as exc:
            with app.app_context():
                current_app.logger.exception("Listening full mock crashed (job_id=%s): %s", job_id_value, exc)
                _put_new_toefl_job(job_id_value, {
                    **(_get_new_toefl_job(job_id_value) or {}),
                    "status": "failed",
                    "finished_at": time.time(),
                    "error": "Generation crashed. Check server logs.",
                })

    threading.Thread(target=_worker, args=(job_id, cache_id, user.id, test_id), daemon=True).start()
    return jsonify({'success': True, 'job_id': job_id, 'cache_id': cache_id, 'status': 'queued'})


@app.route('/new-toefl/api/mock/listening/job/<job_id>', methods=['GET'])
@login_required
def new_toefl_mock_listening_job(job_id: str):
    """Poll full-length listening mock generation status."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    job = _get_new_toefl_job(job_id)
    if not isinstance(job, dict) or job.get("section") != "listening_full":
        return jsonify({'success': False, 'message': 'Job not found'}), 404
    if job.get("user_id") != user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    response: Dict[str, Any] = {
        "success": True,
        "job_id": job_id,
        "status": job.get("status"),
        "error": job.get("error"),
    }
    if job.get("status") == "done":
        payload = _get_new_toefl_payload("listening")
        response["mock"] = payload
    return jsonify(response)


@app.route('/new-toefl/api/mock/writing/<test_id>', methods=['GET'])
@login_required
def new_toefl_mock_writing(test_id: str):
    """Return full-length writing mock content for a test."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    payload = get_writing_section(test_id)
    if not payload:
        return jsonify({'success': False, 'message': 'Writing test not found'}), 404

    return jsonify({'success': True, 'data': payload})


@app.route('/new-toefl/api/mock/writing/load/<test_id>', methods=['GET'])
@login_required
def new_toefl_mock_writing_load(test_id: str):
    """Build full-length writing mock data and cache it for scoring."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    mock = build_full_length_writing_mock(test_id)
    if not mock:
        if os.getenv("TOEFL_PREBUILT_ONLY", "false").lower() in {"1", "true", "yes"}:
            return jsonify({'success': False, 'message': 'Prebuilt writing mock missing. Run prebuild once.'}), 503
        return jsonify({'success': False, 'message': 'Writing mock not found'}), 404

    cache_id = _store_new_toefl_payload('writing', user.id, mock)
    return jsonify({'success': True, 'cache_id': cache_id, 'mock': mock})


@app.route('/new-toefl/api/mock/speaking/<test_id>', methods=['GET'])
@login_required
def new_toefl_mock_speaking(test_id: str):
    """Return full-length speaking mock prompts for a test."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    sets = get_interview_sets()
    selected = next((item for item in sets if item.get('id') == test_id), None)
    if not selected:
        return jsonify({'success': False, 'message': 'Speaking test not found'}), 404

    return jsonify({'success': True, 'data': selected})


@app.route('/new-toefl/api/mock/speaking/generate/<test_id>', methods=['POST'])
@login_required
def new_toefl_mock_speaking_generate(test_id: str):
    """Generate full-length speaking mock tasks for a selected test."""
    from models import SpeakingTask

    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    tts = get_tts_service()
    prebuilt_only = os.getenv("TOEFL_PREBUILT_ONLY", "false").lower() in {"1", "true", "yes"}
    mock = generate_speaking_mock(
        client=None,
        tts=tts,
        interview_set_id=test_id,
        allow_ai=not prebuilt_only,
    )
    if not mock:
        if prebuilt_only:
            return jsonify({'success': False, 'message': 'Prebuilt speaking mock missing. Run prebuild once.'}), 503
        return jsonify({'success': False, 'message': 'Speaking mock not found'}), 404

    tasks: List[Dict[str, Any]] = []
    repeat_items = mock.get('repeat', [])
    interview_items = mock.get('interview', [])

    for idx, item in enumerate(repeat_items, start=1):
        prompt = (item.get('prompt') or '').strip()
        if not prompt:
            continue
        task = SpeakingTask(
            task_number=500 + idx,
            task_type='new_toefl_repeat',
            topic='Listen and Repeat',
            prompt=prompt,
            listening_audio_url=item.get('audio_url'),
            listening_transcript=prompt,
            preparation_time=0,
            response_time=item.get('response_time_seconds', 10),
        )
        db.session.add(task)
        db.session.flush()
        tasks.append({
            'id': task.id,
            'label': f'Repeat {idx}',
            'task_type': task.task_type,
            'response_time': task.response_time,
        })

    for idx, item in enumerate(interview_items, start=1):
        prompt = (item.get('prompt') or '').strip()
        if not prompt:
            continue
        task = SpeakingTask(
            task_number=600 + idx,
            task_type='new_toefl_interview',
            topic='Interview',
            prompt=prompt,
            listening_audio_url=item.get('audio_url'),
            listening_transcript=prompt,
            preparation_time=0,
            response_time=item.get('response_time_seconds', 45),
            response_template='; '.join(item.get('focus_points') or []),
        )
        db.session.add(task)
        db.session.flush()
        tasks.append({
            'id': task.id,
            'label': f'Interview {idx}',
            'task_type': task.task_type,
            'response_time': task.response_time,
        })

    db.session.commit()
    session['new_toefl_speaking_task_ids'] = [task['id'] for task in tasks]

    return jsonify({'success': True, 'tasks': tasks})


@app.route('/new-toefl/api/speaking/tasks', methods=['GET'])
@login_required
def new_toefl_speaking_tasks_lookup():
    """Lookup New TOEFL speaking tasks by id list."""
    from models import SpeakingTask

    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    raw_ids = (request.args.get('ids') or '').strip()
    if not raw_ids:
        return jsonify({'success': False, 'message': 'No task ids provided'}), 400

    ids: List[int] = []
    for token in raw_ids.split(','):
        token = token.strip()
        if token.isdigit():
            ids.append(int(token))
    if not ids:
        return jsonify({'success': False, 'message': 'No valid task ids provided'}), 400

    tasks = SpeakingTask.query.filter(SpeakingTask.id.in_(ids)).all()
    tasks_by_id = {task.id: task for task in tasks}

    def _label_for(task: SpeakingTask) -> str:
        if task.task_type == 'new_toefl_repeat':
            if isinstance(task.task_number, int) and task.task_number >= 500:
                return f'Repeat {task.task_number - 500}'
            return 'Repeat'
        if task.task_type == 'new_toefl_interview':
            if isinstance(task.task_number, int) and task.task_number >= 600:
                return f'Interview {task.task_number - 600}'
            return 'Interview'
        return task.topic or f'Task {task.id}'

    ordered_tasks = sorted(tasks, key=lambda item: (item.task_number or 0, item.id))
    ordered_ids = [task.id for task in ordered_tasks]
    payload_ids = [task_id for task_id in ordered_ids if task_id in tasks_by_id]

    payload = []
    for task_id in payload_ids:
        task = tasks_by_id.get(task_id)
        if not task:
            continue
        payload.append({
            'id': task.id,
            'label': _label_for(task),
            'task_type': task.task_type,
            'response_time': task.response_time,
        })

    return jsonify({'success': True, 'tasks': payload})


@app.route('/new-toefl/api/writing/generate', methods=['POST'])
@login_required
def new_toefl_writing_generate():
    """Generate a New TOEFL writing mock exam."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    if _throttle_new_toefl('writing'):
        cached = _get_new_toefl_payload('writing')
        if cached:
            return jsonify({'success': True, 'cached': True, 'mock': cached})
        return jsonify({'success': False, 'message': 'Please wait a minute before generating again.'}), 429

    client = get_gemini_client()
    if not client or not client.is_configured:
        return jsonify({'success': False, 'message': 'DeepSeek API is not configured'}), 503

    mock = generate_writing_mock(client)
    if not mock:
        cached = _get_new_toefl_payload('writing')
        if cached:
            return jsonify({'success': True, 'cached': True, 'mock': cached})
        return jsonify({'success': False, 'message': 'AI is busy right now. Please try again shortly.'}), 503

    cache_id = _store_new_toefl_payload('writing', user.id, mock)
    return jsonify({'success': True, 'cache_id': cache_id, 'mock': mock})


@app.route('/new-toefl/api/reading/submit', methods=['POST'])
@login_required
def new_toefl_reading_submit():
    """Score New TOEFL reading mock answers."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    payload = _get_new_toefl_payload('reading')
    if not payload:
        return jsonify({'success': False, 'message': 'Reading mock not found'}), 404

    data = request.get_json() or {}
    answers = data.get('answers') or {}

    results = {'cloze': [], 'daily_life': [], 'academic': []}
    correct = 0
    total = 0

    for cloze in payload.get('cloze', []) or []:
        blanks = cloze.get('blanks', [])
        entry_answers = (answers.get('cloze') or {}).get(cloze.get('id'), {})
        for blank in blanks:
            token = blank.get('token')
            expected = blank.get('answer')
            user_answer = entry_answers.get(token, '')
            is_correct = (user_answer or '').strip().casefold() == (expected or '').strip().casefold()
            results['cloze'].append({
                'id': cloze.get('id'),
                'token': token,
                'correct': is_correct,
                'expected': expected,
                'user': user_answer,
                'hint': blank.get('hint'),
            })
            total += 1
            correct += 1 if is_correct else 0

    for daily in payload.get('daily_life', []) or []:
        entry_answers = (answers.get('daily_life') or {}).get(daily.get('id'), {})
        for idx, question in enumerate(daily.get('questions', []) or []):
            selected = entry_answers.get(str(idx), '')
            is_correct = _answers_match(selected, question.get('answer', ''), question.get('options'))
            results['daily_life'].append({
                'id': daily.get('id'),
                'index': idx,
                'question': question.get('question'),
                'options': question.get('options'),
                'correct': is_correct,
                'expected': question.get('answer'),
                'selected': selected,
                'rationales': question.get('rationales', {}),
                'evidence_quote': question.get('evidence_quote') or question.get('evidenceQuote'),
            })
            total += 1
            correct += 1 if is_correct else 0

    academic_payload = payload.get('academic')
    academic_sets = academic_payload if isinstance(academic_payload, list) else [academic_payload] if academic_payload else []
    academic_answers = answers.get('academic') or {}
    for academic in academic_sets:
        if not academic:
            continue
        academic_id = academic.get('id') or 'academic'
        entry_answers = academic_answers.get(academic_id, {}) if isinstance(academic_answers, dict) else {}
        for idx, question in enumerate(academic.get('questions', []) or []):
            selected = entry_answers.get(str(idx), '')
            is_correct = _answers_match(selected, question.get('answer', ''), question.get('options'))
            results['academic'].append({
                'id': academic_id,
                'index': idx,
                'question': question.get('question'),
                'options': question.get('options'),
                'correct': is_correct,
                'expected': question.get('answer'),
                'selected': selected,
                'rationales': question.get('rationales', {}),
                'evidence_quote': question.get('evidence_quote') or question.get('evidenceQuote'),
            })
            total += 1
            correct += 1 if is_correct else 0

    score = round((correct / total) * 100, 1) if total else 0.0
    return jsonify({'success': True, 'score': score, 'correct': correct, 'total': total, 'results': results})


@app.route('/new-toefl/api/listening/submit', methods=['POST'])
@login_required
def new_toefl_listening_submit():
    """Score New TOEFL listening mock answers."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    payload = _get_new_toefl_payload('listening')
    if not payload:
        return jsonify({'success': False, 'message': 'Listening mock not found'}), 404

    data = request.get_json() or {}
    answers = data.get('answers') or {}

    results = {'responses': [], 'conversation': [], 'talk': []}
    correct = 0
    total = 0

    response_answers = answers.get('responses') or {}
    for idx, item in enumerate(payload.get('responses', []) or []):
        selected = response_answers.get(str(idx), '')
        is_correct = _answers_match(selected, item.get('answer', ''), item.get('options'))
        results['responses'].append({
            'index': idx,
            'prompt': item.get('prompt'),
            'question': item.get('question'),
            'options': item.get('options'),
            'correct': is_correct,
            'expected': item.get('answer'),
            'selected': selected,
            'rationales': item.get('rationales', {}),
        })
        total += 1
        correct += 1 if is_correct else 0

    conversation_payload = payload.get('conversation')
    conv_sets = conversation_payload if isinstance(conversation_payload, list) else [conversation_payload] if conversation_payload else []
    conv_answers = answers.get('conversation') or {}
    for conv in conv_sets:
        if not conv:
            continue
        conv_id = conv.get('id') or f"conv_{len(results['conversation'])}"
        entry_answers = conv_answers.get(conv_id, {}) if isinstance(conv_answers, dict) else {}
        for idx, question in enumerate(conv.get('questions', []) or []):
            selected = entry_answers.get(str(idx), '')
            is_correct = _answers_match(selected, question.get('answer', ''), question.get('options'))
            results['conversation'].append({
                'id': conv_id,
                'index': idx,
                'question': question.get('question'),
                'options': question.get('options'),
                'correct': is_correct,
                'expected': question.get('answer'),
                'selected': selected,
                'rationales': question.get('rationales', {}),
            })
            total += 1
            correct += 1 if is_correct else 0

    talk_payload = payload.get('talk')
    talk_sets = talk_payload if isinstance(talk_payload, list) else [talk_payload] if talk_payload else []
    talk_answers = answers.get('talk') or {}
    for talk in talk_sets:
        if not talk:
            continue
        talk_id = talk.get('id') or f"talk_{len(results['talk'])}"
        entry_answers = talk_answers.get(talk_id, {}) if isinstance(talk_answers, dict) else {}
        for idx, question in enumerate(talk.get('questions', []) or []):
            selected = entry_answers.get(str(idx), '')
            is_correct = _answers_match(selected, question.get('answer', ''), question.get('options'))
            results['talk'].append({
                'id': talk_id,
                'index': idx,
                'question': question.get('question'),
                'options': question.get('options'),
                'correct': is_correct,
                'expected': question.get('answer'),
                'selected': selected,
                'rationales': question.get('rationales', {}),
            })
            total += 1
            correct += 1 if is_correct else 0

    score = round((correct / total) * 100, 1) if total else 0.0
    return jsonify({'success': True, 'score': score, 'correct': correct, 'total': total, 'results': results})


@app.route('/new-toefl/api/writing/submit', methods=['POST'])
@login_required
def new_toefl_writing_submit():
    """Score New TOEFL writing mock answers."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    payload = _get_new_toefl_payload('writing')
    if not payload:
        return jsonify({'success': False, 'message': 'Writing mock not found'}), 404

    data = request.get_json() or {}
    answers = data.get('answers') or {}

    sentence_results = []
    correct = 0
    total = 0
    for idx, item in enumerate(payload.get('sentence_build', []) or []):
        expected = _normalize_sentence(item.get('answer', ''))
        user_answer = _normalize_sentence((answers.get('sentence_build') or {}).get(str(idx), ''))
        is_correct = bool(expected) and expected == user_answer
        sentence_results.append({
            'index': idx,
            'prompt': item.get('prompt'),
            'tokens': item.get('tokens'),
            'correct': is_correct,
            'expected': item.get('answer'),
            'user': (answers.get('sentence_build') or {}).get(str(idx), ''),
        })
        total += 1
        correct += 1 if is_correct else 0

    analyzer = get_writing_analyzer()
    email_text = (answers.get('email_text') or '').strip()
    discussion_text = (answers.get('discussion_text') or '').strip()

    email_task = payload.get('email') or {}
    email_prompt = (
        f"{email_task.get('scenario', '')}\n\nRequirements:\n- "
        + "\n- ".join(email_task.get('instructions', []) or [])
    )
    email_feedback = analyzer.analyze_essay(
        essay_text=email_text,
        task_type='email',
        prompt=email_prompt,
        reading_text=None,
        listening_transcript=None,
        discussion_context=None,
    )

    discussion_task = payload.get('discussion') or {}
    discussion_context = {
        'professor_question': discussion_task.get('professor_prompt'),
        'student_posts': discussion_task.get('student_posts', []),
    }
    discussion_feedback = analyzer.analyze_essay(
        essay_text=discussion_text,
        task_type='discussion',
        prompt=discussion_task.get('professor_prompt', ''),
        reading_text=None,
        listening_transcript=None,
        discussion_context=discussion_context,
    )

    score = round((correct / total) * 100, 1) if total else 0.0
    return jsonify({
        'success': True,
        'sentence_score': score,
        'sentence_correct': correct,
        'sentence_total': total,
        'sentence_results': sentence_results,
        'email_text': email_text,
        'email_feedback': email_feedback,
        'discussion_text': discussion_text,
        'discussion_feedback': discussion_feedback,
    })


@app.route('/vocab/dashboard')
@login_required
def vocab_dashboard():
    """Vocabulary section dashboard with analytics and progress."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    # Get progress
    total, new_cards, review_cards = get_todays_progress(user.id)
    remaining = max(user.daily_goal - total, 0)

    progress = {
        'goal': user.daily_goal,
        'reviewed': total,
        'new_count': new_cards,
        'review_count': review_cards,
        'remaining': remaining
    }

    # Get mastery breakdown
    breakdown = get_mastery_breakdown(user.id)

    # Get memorization curve
    curve = get_memorize_curve(user.id, days=14)

    # Get study streak
    streak = get_study_streak(user.id)

    # Get learning velocity
    velocity_data, avg_velocity = get_learning_velocity(user.id, days=30)

    # Get session composition recommendation
    composition = get_smart_session_composition(user.id, user.daily_goal)

    # Get unfamiliar words count
    unfamiliar_count = UnfamiliarWord.query.filter_by(user_id=user.id).count()

    return render_template(
        'vocab_dashboard.html',
        user=user,
        progress=progress,
        breakdown=breakdown,
        curve=curve,
        streak=streak,
        avg_velocity=avg_velocity,
        composition=composition,
        unfamiliar_count=unfamiliar_count
    )


@app.route('/vocab/unfamiliar-words')
@login_required
def unfamiliar_words_page():
    """Display user's unfamiliar words list."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    words = UnfamiliarWord.query.filter_by(user_id=user.id).order_by(
        UnfamiliarWord.created_at.desc()
    ).all()

    return render_template('unfamiliar_words.html', user=user, words=words)


@app.route('/test/unfamiliar-words')
@login_required
def test_unfamiliar_words():
    """Test page for unfamiliar words feature."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('test_unfamiliar.html', user=user)


@app.route('/reading/dashboard')
@login_required
def reading_dashboard():
    """Reading section dashboard with practice options."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('reading_dashboard.html', user=user)


@app.route('/api/dashboard')
@login_required
def api_dashboard():
    """API endpoint for dashboard data."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401

    total, new_cards, review_cards = get_todays_progress(user.id)
    remaining = max(user.daily_goal - total, 0)

    return jsonify({
        'goal': {
            'goal': user.daily_goal,
            'reviewed': total,
            'new_count': new_cards,
            'review_count': review_cards,
            'remaining': remaining
        },
        'breakdown': get_mastery_breakdown(user.id),
        'memorize_curve': get_memorize_curve(user.id, days=14)
    })


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """User settings page."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        daily_goal = request.form.get('daily_goal')
        try:
            goal = int(daily_goal)
            goal = max(1, min(goal, 1000))
            user.daily_goal = goal
            db.session.commit()
            flash(f'Daily goal updated to {goal} words.', 'success')
        except ValueError:
            flash('Invalid goal value.', 'danger')

    return render_template('settings.html', user=user)


@app.route('/api/daily-goal', methods=['POST'])
@login_required
def api_update_daily_goal():
    """Update the user's daily goal via JSON request."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401

    payload = request.get_json(silent=True) or {}
    daily_goal = payload.get('daily_goal')

    if daily_goal is None:
        return jsonify({'error': 'Missing daily_goal'}), 400

    try:
        goal_value = int(daily_goal)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid daily_goal value'}), 400

    goal_value = max(1, min(goal_value, 1000))
    user.daily_goal = goal_value
    db.session.commit()

    return jsonify({'message': 'Daily goal updated.', 'daily_goal': goal_value})


# ============================================================================
# WORD BROWSING & SEARCH
# ============================================================================

@app.route('/words')
@login_required
def browse_words():
    """Browse words by mastery category."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    category = request.args.get('category', 'new')
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page

    words, total_count = get_words_by_mastery(user.id, category, limit=per_page, offset=offset)
    total_pages = (total_count + per_page - 1) // per_page

    # Get breakdown for tabs
    breakdown = get_mastery_breakdown(user.id)

    # Enrich words with user_word data if available
    enriched_words = []
    for word in words:
        user_word = UserWord.query.filter_by(user_id=user.id, word_id=word.id).first()
        enriched_words.append({
            'word': word,
            'user_word': user_word
        })

    return render_template(
        'words.html',
        enriched_words=enriched_words,
        category=category,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        breakdown=breakdown
    )


@app.route('/search')
@login_required
def search():
    """Search for words."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('browse_words'))

    results = search_words(query, limit=100)

    # Enrich with user_word data
    enriched_words = []
    for word in results:
        user_word = UserWord.query.filter_by(user_id=user.id, word_id=word.id).first()
        enriched_words.append({
            'word': word,
            'user_word': user_word
        })

    return render_template(
        'search.html',
        query=query,
        enriched_words=enriched_words,
        count=len(results)
    )


# ============================================================================
# LOADING WORKFLOW
# ============================================================================


@app.route('/loading')
@login_required
def loading_page():
    """Generic loading screen that triggers DeepSeek generation before redirect."""
    target = request.args.get('target')
    if not target:
        flash('Missing target for loading redirect.', 'warning')
        return redirect(url_for('main_dashboard'))

    generator = request.args.get('generator')
    title = request.args.get('title') or "Generating AI Content"
    message = request.args.get('message') or "DeepSeek is preparing your personalized exercises..."

    return render_template(
        'loading.html',
        target_url=target,
        generator_url=generator,
        title=title,
        message=message,
    )


# ============================================================================
# ASYNC GENERATORS
# ============================================================================


@app.route('/reading/api/bootstrap', methods=['POST'])
@login_required
def reading_bootstrap():
    """Pre-generate reading coach content and stash it in the session."""
    import time

    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    # Generate content - DeepSeekClient handles retries and backoff for API errors
    sentence = get_sentence()
    paragraph = get_paragraph()
    passage = get_passage()

    if not sentence or not paragraph or not passage:
        return jsonify({'success': False, 'message': 'DeepSeek currently unavailable.'}), 503

    # Store in server-side cache instead of session to avoid cookie size issues
    import time
    cache_id = f"reading_bootstrap_{user.id}_{int(time.time())}"
    cache = getattr(current_app, '_reading_cache', None)
    if cache is None:
        cache = current_app._reading_cache = {}
    cache[cache_id] = {
        'sentence': sentence,
        'paragraph': paragraph,
        'passage': passage,
    }

    session['reading_bootstrap_id'] = cache_id
    session.modified = True
    return jsonify({'success': True, 'redirect': url_for('reading_home')})


@app.route('/reading/practice/<practice_type>/start')
@login_required
def reading_practice_generate_page(practice_type):
    """Show the generation page with topic selection for a specific practice type."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    if practice_type not in ['sentence', 'paragraph', 'passage']:
        flash('Invalid practice type', 'danger')
        return redirect(url_for('reading_dashboard'))

    # Map practice types to display info
    practice_info = {
        'sentence': {
            'display': 'Sentence Gym',
            'icon': 'text-width',
            'description': 'Master complex sentence structures with detailed grammatical analysis and paraphrase practice.',
            'examples': 'Astronomy, Ecology, Anthropology, Neuroscience, Economics'
        },
        'paragraph': {
            'display': 'Paragraph Lab',
            'icon': 'align-left',
            'description': 'Analyze paragraph structure, identify topic sentences, and understand logical flow patterns.',
            'examples': 'Museum Studies, Linguistics, Geology, Urban Sustainability, Biotechnology'
        },
        'passage': {
            'display': 'Passage Simulator',
            'icon': 'book-open',
            'description': 'Practice full TOEFL-style reading passages with scaffolded questions and detailed explanations.',
            'examples': 'Climate Adaptation, Marine Biology, Digital Heritage, Renewable Energy, Cognitive Psychology'
        }
    }

    info = practice_info[practice_type]

    return render_template(
        'reading/generate.html',
        practice_type=practice_type,
        practice_type_display=info['display'],
        icon=info['icon'],
        description=info['description'],
        examples=info['examples']
    )


@app.route('/reading/practice/<practice_type>/generate', methods=['POST'])
@login_required
def generate_reading_batch(practice_type):
    """Generate a batch of 5 reading practice sets (sentence/paragraph/passage)."""
    import time

    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    if practice_type not in ['sentence', 'paragraph', 'passage']:
        return jsonify({'success': False, 'message': 'Invalid practice type'}), 400

    # Get optional topic from request
    data = request.get_json() or {}
    topic = data.get('topic', None)
    if topic:
        topic = topic.strip() or None

    # Generate 5 sets with diversity guards.
    batch = []
    generator_map = {
        'sentence': get_sentence,
        'paragraph': get_paragraph,
        'passage': get_passage
    }
    generator = generator_map[practice_type]

    requested_topic_variants = _expand_topic_variants(topic, 5) if topic else []
    used_texts: List[str] = []
    used_topics: set[str] = set()

    for i in range(5):
        item = None
        attempts = 0
        while attempts < 6 and item is None:
            attempts += 1
            topic_for_item = None
            if requested_topic_variants:
                topic_for_item = requested_topic_variants[i]
            elif topic:
                topic_for_item = topic

            try:
                candidate = generator(topic=topic_for_item)
                if not candidate:
                    continue

                candidate_topic = str(candidate.get("topic") or topic_for_item or "").strip()
                text_blob = _extract_practice_text(candidate, practice_type)

                if candidate_topic and candidate_topic in used_topics:
                    continue
                if text_blob and _too_similar(text_blob, used_texts, threshold=0.88):
                    continue

                item = candidate
                if candidate_topic:
                    used_topics.add(candidate_topic)
                if text_blob:
                    used_texts.append(text_blob)
            except Exception as e:
                current_app.logger.error(f"Error generating {practice_type} #{i+1}: {e}")

        if item:
            batch.append(item)
            current_app.logger.info(
                "Generated %s #%s (attempts=%s, topic=%s)",
                practice_type,
                i + 1,
                attempts,
                (item.get("topic") or topic or ""),
            )
        else:
            current_app.logger.warning("Failed to generate diverse %s #%s after retries", practice_type, i + 1)

    if not batch:
        return jsonify({'success': False, 'message': f'Failed to generate {practice_type} practice sets.'}), 503

    # Store batch IDs in session (lightweight) and cache full content server-side
    batch_id = f"reading_{practice_type}_{user.id}_{int(time.time())}"

    cache = getattr(current_app, '_reading_batches', None)
    if cache is None:
        cache = current_app._reading_batches = {}
    cache[batch_id] = batch
    
    # Only store lightweight reference in session
    session[f'reading_{practice_type}_batch_id'] = batch_id
    session[f'reading_{practice_type}_index'] = 0
    session[f'reading_{practice_type}_count'] = len(batch)
    session.modified = True

    return jsonify({
        'success': True,
        'count': len(batch),
        'redirect': url_for('reading_practice', practice_type=practice_type)
    })


@app.route('/exercises/api/gap-fill/generate', methods=['POST'])
@login_required
def generate_gap_fill_async():
    """Prepare gap-fill exercises and store them in the session."""
    import time

    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    current_app.logger.info(f"[GAP-FILL] Starting generation for user {user.id}")

    normalized, ai_generated, error = _prepare_gap_fill_payload(user)

    if error:
        current_app.logger.error(f"[GAP-FILL] Generation failed: {error}")
        return jsonify({'success': False, 'message': error}), 400

    # Store in server-side cache instead of session to avoid cookie size issues
    cache_id = f"gap_fill_{user.id}_{int(time.time())}"
    cache = getattr(current_app, '_exercise_cache', None)
    if cache is None:
        cache = current_app._exercise_cache = {}
    cache[cache_id] = {
        'exercises': normalized,
        'ai_generated': ai_generated,
    }

    current_app.logger.info(f"[GAP-FILL] Generation complete! Generated {len(normalized)} exercises, stored in cache {cache_id}")

    # Only store cache ID in session (lightweight)
    session['gap_fill_cache_id'] = cache_id
    session.modified = True
    return jsonify({'success': True, 'redirect': url_for('contextual_gap_fill')})


@app.route('/exercises/api/synonym/generate', methods=['POST'])
@login_required
def generate_synonym_async():
    """Prepare synonym showdown exercises and store results in session."""
    import time

    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    normalized, ai_generated, error = _prepare_synonym_payload(user)
    if error:
        return jsonify({'success': False, 'message': error}), 400

    # Store in server-side cache instead of session to avoid cookie size issues
    cache_id = f"synonym_{user.id}_{int(time.time())}"
    cache = getattr(current_app, '_exercise_cache', None)
    if cache is None:
        cache = current_app._exercise_cache = {}
    cache[cache_id] = {
        'exercises': normalized,
        'ai_generated': ai_generated,
    }

    # Only store cache ID in session (lightweight)
    session['synonym_cache_id'] = cache_id
    session.modified = True
    return jsonify({'success': True, 'redirect': url_for('synonym_showdown')})


@app.route('/exercises/api/reading/generate', methods=['POST'])
@login_required
def generate_reading_passage_async():
    """Prepare a reading immersion passage for a chosen topic."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    payload = request.get_json(silent=True) or {}
    topic = payload.get('topic') or request.args.get('topic')

    passage, highlight_words, ai_generated, error = _prepare_reading_passage_payload(user, topic)
    if error or not passage:
        return jsonify({'success': False, 'message': error or 'Generation failed.'}), 400

    session['reading_passage_payload'] = {
        'topic': topic,
        'passage': passage,
        'highlight_words': highlight_words,
        'ai_generated': ai_generated,
    }
    session.modified = True
    redirect_url = url_for('reading_immersion', topic=topic) if topic else url_for('reading_immersion')
    return jsonify({'success': True, 'redirect': redirect_url})


# ============================================================================
# READING MODULE
# ============================================================================


@app.route('/reading')
@login_required
def reading_home():
    """Primary entry point for the TOEFL reading module."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    locale_cn = load_locale('cn', 'reading')

    # Try to retrieve from server-side cache
    bootstrap_id = session.get('reading_bootstrap_id')
    if bootstrap_id:
        cache = getattr(current_app, '_reading_cache', {})
        bootstrap = cache.get(bootstrap_id)
        if bootstrap:
            sentence = bootstrap.get('sentence')
            paragraph = bootstrap.get('paragraph')
            passage = bootstrap.get('passage')
            # Remove cache ID from session after use
            del session['reading_bootstrap_id']
            session.modified = True
        else:
            sentence = None
            paragraph = None
            passage = None
    else:
        sentence = None
        paragraph = None
        passage = None

    if not sentence:
        sentence = get_sentence()
    if not paragraph:
        paragraph = get_paragraph()
    if not passage:
        passage = get_passage()

    return render_template(
        'reading/index.html',
        sentence=sentence or {},
        paragraph=paragraph or {},
        passage=passage or {},
        locale_cn=locale_cn,
    )


@app.route('/reading/practice/<practice_type>')
@login_required
def reading_practice(practice_type):
    """Display current item from batch with navigation."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    if practice_type not in ['sentence', 'paragraph', 'passage']:
        flash('Invalid practice type', 'danger')
        return redirect(url_for('reading_dashboard'))

    # Retrieve from server-side cache
    batch_id_key = f'reading_{practice_type}_batch_id'
    index_key = f'reading_{practice_type}_index'
    count_key = f'reading_{practice_type}_count'

    batch_id = session.get(batch_id_key)
    current_index = session.get(index_key, 0)
    total_count = session.get(count_key, 0)

    if not batch_id:
        flash(f'No {practice_type} batch found. Please generate one first.', 'warning')
        return redirect(url_for('reading_dashboard'))

    cache = getattr(current_app, '_reading_batches', {})
    batch = cache.get(batch_id, [])

    if not batch:
        flash(f'{practice_type.title()} batch expired. Please generate a new one.', 'warning')
        return redirect(url_for('reading_dashboard'))

    current_item = batch[current_index] if 0 <= current_index < len(batch) else None
    locale_cn = load_locale('cn', 'reading')

    # Store current sentence in session for paraphrase evaluation
    if practice_type == 'sentence' and current_item:
        session['reading_last_sentence'] = current_item
        session.modified = True

    return render_template(
        f'reading/{practice_type}_practice.html',
        item=current_item,
        current_index=current_index,
        total_count=total_count,
        practice_type=practice_type,
        locale_cn=locale_cn,
        user=user
    )


@app.route('/reading/practice/<practice_type>/navigate', methods=['POST'])
@login_required
def navigate_reading_batch(practice_type):
    """Navigate through the batch (next/prev)."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    if practice_type not in ['sentence', 'paragraph', 'passage']:
        return jsonify({'success': False, 'message': 'Invalid practice type'}), 400

    direction = request.json.get('direction')  # 'next' or 'prev'
    batch_id_key = f'reading_{practice_type}_batch_id'
    index_key = f'reading_{practice_type}_index'
    count_key = f'reading_{practice_type}_count'

    batch_id = session.get(batch_id_key)
    current_index = session.get(index_key, 0)
    total_count = session.get(count_key, 0)

    if not batch_id:
        return jsonify({'success': False, 'message': 'No batch found'}), 400

    if direction == 'next':
        new_index = min(current_index + 1, total_count - 1)
    elif direction == 'prev':
        new_index = max(current_index - 1, 0)
    else:
        return jsonify({'success': False, 'message': 'Invalid direction'}), 400

    session[index_key] = new_index

    # Get item from server cache
    cache = getattr(current_app, '_reading_batches', {})
    batch = cache.get(batch_id, [])
    item = batch[new_index] if 0 <= new_index < len(batch) else None

    # Store current sentence in session for paraphrase evaluation
    if practice_type == 'sentence' and item:
        session['reading_last_sentence'] = item

    session.modified = True

    return jsonify({
        'success': True,
        'index': new_index,
        'total': total_count,
        'item': item
    })


@app.route('/reading/api/sentence')
@login_required
def reading_sentence_api():
    """Return a sentence gym exercise."""
    topic = request.args.get('topic')
    sentence = get_sentence(topic=topic)
    if not sentence:
        return jsonify({'error': 'Sentence not found.'}), 404
    session['reading_last_sentence'] = sentence
    session.modified = True
    return jsonify({
        'id': sentence.get('id'),
        'text': sentence.get('text'),
        'topic': sentence.get('topic'),
        'analysis': sentence.get('analysis', []),
        'focusPoints': sentence.get('focus_points', []),
        'reference': sentence.get('paraphrase_reference'),
    })


@app.route('/reading/api/paraphrase', methods=['POST'])
@login_required
def reading_paraphrase_api():
    """Evaluate a paraphrase attempt."""
    payload = request.get_json(silent=True) or {}
    sentence_id = payload.get('sentenceId')
    user_text = payload.get('text', '')
    if not sentence_id:
        return jsonify({'error': 'Missing sentenceId'}), 400
    last_sentence = session.get('reading_last_sentence')
    if isinstance(last_sentence, dict) and last_sentence.get('id') != sentence_id:
        last_sentence = None
    result = evaluate_paraphrase(sentence_id, user_text, source_sentence=last_sentence)
    if not result:
        return jsonify({'error': 'Sentence not found.'}), 404

    locale_cn = load_locale('cn', 'reading') or {}
    paraphrase_locale = locale_cn.get('paraphrase', {})
    category_key = result.get('category', 'needs_work')
    base_feedback = paraphrase_locale.get(category_key, '')
    prefix = paraphrase_locale.get('missing_point_prefix', '提示')
    missing = result.get('missing_points') or []
    missing_feedback = [f"{prefix}：{hint}" for hint in missing]

    return jsonify({
        'score': result.get('score', 0.0),
        'category': category_key,
        'feedback': base_feedback,
        'detailedFeedback': result.get('gemini_feedback'),
        'missing': missing_feedback,
        'modelAnswerLabel': paraphrase_locale.get('model_intro', '参考表达'),
        'modelAnswer': result.get('model_answer', ''),
    })


@app.route('/reading/api/paragraph')
@login_required
def reading_paragraph_api():
    """Return a paragraph lab scenario."""
    topic = request.args.get('topic')
    paragraph = get_paragraph(topic=topic)
    if not paragraph:
        return jsonify({'error': 'Paragraph not found.'}), 404
    session['reading_last_paragraph'] = paragraph
    session.modified = True
    return jsonify({
        'id': paragraph.get('id'),
        'topic': paragraph.get('topic'),
        'paragraph': paragraph.get('paragraph'),
        'sentences': paragraph.get('sentences', []),
        'topicSentenceIndex': paragraph.get('topicSentenceIndex'),
        'transitions': paragraph.get('transitions', []),
    })


@app.route('/reading/api/passage')
@login_required
def reading_passage_api():
    """Return a guided strategy simulator passage."""
    topic = request.args.get('topic')
    passage = get_passage(topic=topic)
    if not passage:
        return jsonify({'error': 'Passage not found.'}), 404
    session['reading_last_passage'] = passage
    session.modified = True
    return jsonify({
        'id': passage.get('id'),
        'topic': passage.get('topic'),
        'title': passage.get('title'),
        'readingTimeMinutes': passage.get('readingTimeMinutes'),
        'tools': passage.get('tools', {}),
        'paragraphs': passage.get('paragraphs', []),
        'questions': passage.get('questions', []),
    })


# ============================================================================
# LISTENING MODULE
# ============================================================================

@app.route('/listening/dashboard')
@login_required
def listening_dashboard():
    """Listening section dashboard with all three features."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    # Get user's listening progress stats
    total_dictation = ListeningUserProgress.query.filter_by(
        user_id=user.id,
        exercise_type='dictation',
        completed=True
    ).count()

    total_signpost = ListeningUserProgress.query.filter_by(
        user_id=user.id,
        exercise_type='signpost',
        completed=True
    ).count()

    total_lectures = ListeningUserProgress.query.filter_by(
        user_id=user.id,
        exercise_type='lecture',
        completed=True
    ).count()

    total_conversations = ListeningUserProgress.query.filter_by(
        user_id=user.id,
        exercise_type='conversation',
        completed=True
    ).count()

    return render_template(
        'listening/dashboard.html',
        user=user,
        stats={
            'dictation_completed': total_dictation,
            'signpost_completed': total_signpost,
            'lectures_completed': total_lectures,
            'conversations_completed': total_conversations
        }
    )


# ============================================================================
# FEATURE 1: AI DICTATION TRAINER
# ============================================================================

@app.route('/listening/dictation')
@login_required
def dictation_trainer():
    """Main dictation trainer page - shows all 5 generated sentences."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    # Get the 5 most recent sentences (from batch generation)
    sentence_records = ListeningSentence.query.order_by(
        ListeningSentence.created_at.desc()
    ).limit(5).all()
    sentences = [sentence.to_dict() for sentence in sentence_records]
    dictation_filters = session.get('dictation_filters', {'topic': '', 'difficulty': 'medium'})

    return render_template(
        'listening/dictation.html',
        user=user,
        sentences=sentences,
        dictation_filters=dictation_filters
    )


@app.route('/listening/api/dictation/generate', methods=['POST'])
@login_required
def generate_dictation():
    """Generate 5 new dictation sentences using DeepSeek and TTS (batch generation)."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json() or {}
    topic = data.get('topic')
    difficulty = data.get('difficulty', 'medium')
    session['dictation_filters'] = {
        'topic': topic or '',
        'difficulty': difficulty
    }
    session.modified = True

    # Get DeepSeek client
    client = get_gemini_client()
    if not client or not client.is_configured:
        return jsonify({
            'success': False,
            'message': 'AI service not configured'
        }), 503

    # Generate 5 sentences at once
    try:
        sentences_data = generate_dictation_sentences_batch(client, count=5, topic=topic, difficulty=difficulty)
        if not sentences_data:
            return jsonify({
                'success': False,
                'message': 'Failed to generate sentences'
            }), 500

        tts_service = get_tts_service()
        generated_sentences = []

        # Generate audio for each sentence and save to database
        for sentence_data in sentences_data:
            text = sentence_data['text']
            topic_used = sentence_data.get('topic', 'General')
            difficulty_used = sentence_data.get('difficulty', difficulty)

            # Generate audio with TTS
            tts_result = tts_service.generate_audio(
                text=text,
                filename_prefix=f"dictation_{topic_used.lower().replace(' ', '_')}",
                voice="default"
            )

            if not tts_result:
                current_app.logger.warning(f"Failed to generate audio for sentence: {text[:50]}...")
                continue

            # Save to database
            sentence = ListeningSentence(
                text=text,
                topic=topic_used,
                difficulty=difficulty_used,
                audio_url=tts_result.audio_path,
                audio_duration_seconds=tts_result.duration_seconds,
                word_timestamps=tts_result.word_timestamps
            )
            db.session.add(sentence)
            db.session.flush()  # Get ID

            generated_sentences.append(sentence.to_dict())

        db.session.commit()

        if not generated_sentences:
            return jsonify({
                'success': False,
                'message': 'Failed to generate any audio'
            }), 500

        # Store first sentence in session as current
        session['dictation_current_id'] = generated_sentences[0]['id']
        session.modified = True

        return jsonify({
            'success': True,
            'sentence': generated_sentences[0],  # Return first sentence
            'total_generated': len(generated_sentences)
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error generating dictation batch: {e}")
        return jsonify({
            'success': False,
            'message': f'An error occurred during generation: {str(e)}'
        }), 500


@app.route('/listening/api/dictation/<int:sentence_id>', methods=['GET'])
@login_required
def get_dictation(sentence_id):
    """Get a specific dictation sentence."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    sentence = ListeningSentence.query.get(sentence_id)
    if not sentence:
        return jsonify({'error': 'Sentence not found'}), 404

    # Store in session as current
    session['dictation_current_id'] = sentence.id
    session.modified = True

    return jsonify({'sentence': sentence.to_dict()})


@app.route('/listening/api/dictation/<int:sentence_id>/submit', methods=['POST'])
@login_required
def submit_dictation(sentence_id):
    """Submit and evaluate user's dictation attempt."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    sentence = ListeningSentence.query.get(sentence_id)
    if not sentence:
        return jsonify({'error': 'Sentence not found'}), 404

    data = request.get_json() or {}
    user_text = data.get('text', '').strip()

    # Perform word-by-word comparison
    correct_words = sentence.text.lower().split()
    user_words = user_text.lower().split()

    # Analysis
    word_analysis = []
    correct_count = 0
    total_words = len(correct_words)

    for i, correct_word in enumerate(correct_words):
        user_word = user_words[i] if i < len(user_words) else ''

        # Simple matching (can be enhanced with fuzzy matching)
        is_correct = user_word == correct_word

        if is_correct:
            correct_count += 1

        analysis_item = {
            'index': i,
            'correct_word': correct_word,
            'user_word': user_word,
            'is_correct': is_correct,
            'timestamp': sentence.word_timestamps[i] if sentence.word_timestamps and i < len(sentence.word_timestamps) else None
        }
        word_analysis.append(analysis_item)

    # Calculate score
    score = (correct_count / total_words * 100) if total_words > 0 else 0

    # Identify error patterns
    error_patterns = _analyze_dictation_errors(word_analysis)

    # Save progress
    progress = ListeningUserProgress(
        user_id=user.id,
        exercise_type='dictation',
        exercise_id=sentence.id,
        score=score,
        completed=True,
        user_answer={'text': user_text, 'word_analysis': word_analysis}
    )
    db.session.add(progress)
    db.session.commit()

    return jsonify({
        'success': True,
        'score': round(score, 2),
        'correct_count': correct_count,
        'total_words': total_words,
        'word_analysis': word_analysis,
        'error_patterns': error_patterns,
        'correct_text': sentence.text
    })


def _analyze_dictation_errors(word_analysis: List[Dict]) -> Dict:
    """Analyze common error patterns in dictation."""
    patterns = {
        'missing_words': [],
        'extra_words': [],
        'misspellings': [],
        'wrong_words': []
    }

    for item in word_analysis:
        if not item['is_correct']:
            if not item['user_word']:
                patterns['missing_words'].append(item['correct_word'])
            elif item['user_word'] != item['correct_word']:
                # Check if it's a misspelling (similar) or completely wrong
                # Simple heuristic: if length difference is small, it's likely a misspelling
                if abs(len(item['user_word']) - len(item['correct_word'])) <= 2:
                    patterns['misspellings'].append({
                        'correct': item['correct_word'],
                        'user': item['user_word']
                    })
                else:
                    patterns['wrong_words'].append({
                        'correct': item['correct_word'],
                        'user': item['user_word']
                    })

    return patterns


# ============================================================================
# FEATURE 2: SIGNPOST SIGNAL TRAINER
# ============================================================================

@app.route('/listening/signpost')
@login_required
def signpost_trainer():
    """Main signpost trainer page - shows all 5 generated exercises."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    signpost_queue = session.get('signpost_queue', []) or []
    signpost_index = session.get('signpost_index', 0)
    if signpost_queue:
        if signpost_index >= len(signpost_queue):
            signpost_index = len(signpost_queue) - 1
            session['signpost_index'] = max(signpost_index, 0)
            session.modified = True
    signpost_filters = session.get('signpost_filters', {'topic': ''})

    signpost_id = session.get('signpost_current_id')

    if signpost_queue and signpost_index < len(signpost_queue):
        signpost_id = signpost_queue[signpost_index]

    signpost = None
    if signpost_id:
        signpost_record = ListeningSignpost.query.get(signpost_id)
        if signpost_record:
            signpost = signpost_record.to_dict()

    if not signpost:
        signpost_record = ListeningSignpost.query.order_by(ListeningSignpost.created_at.desc()).first()
        if signpost_record:
            signpost = signpost_record.to_dict()
            session['signpost_current_id'] = signpost_record.id
            session.modified = True

    return render_template(
        'listening/signpost.html',
        user=user,
        signpost=signpost,
        signpost_filters=signpost_filters,
        signpost_queue_remaining=max(len(signpost_queue) - signpost_index - 1, 0)
    )


@app.route('/listening/api/signpost/generate', methods=['POST'])
@login_required
def generate_signpost():
    """Generate 5 new signpost exercises using DeepSeek and TTS (batch generation)."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json() or {}
    topic = data.get('topic')
    session['signpost_filters'] = {'topic': topic or ''}
    session.modified = True

    # Get DeepSeek client
    client = get_gemini_client()
    if not client or not client.is_configured:
        return jsonify({
            'success': False,
            'message': 'AI service not configured'
        }), 503

    # Generate 5 signpost segments at once
    try:
        segments_data = generate_signpost_segments_batch(client, count=5, topic=topic)
        if not segments_data:
            return jsonify({
                'success': False,
                'message': 'Failed to generate signpost segments'
            }), 500

        tts_service = get_tts_service()
        generated_signposts = []

        # Generate audio for each segment and save to database
        for segment_data in segments_data:
            # Generate audio with TTS
            segment_text = _sanitize_generated_text(segment_data.get('text', ''))
            signpost_phrase = _sanitize_generated_text(segment_data.get('signpost_phrase', ''))
            question_text = _sanitize_generated_text(segment_data.get('question_text', ''))
            options = [
                _sanitize_generated_text(opt)
                for opt in (segment_data.get('options') or [])
                if opt
            ]
            correct_answer = _sanitize_generated_text(segment_data.get('correct_answer', ''))
            explanation_cn = _sanitize_generated_text(segment_data.get('explanation_cn', ''))
            raw_option_explanations = segment_data.get('option_explanations_cn') or segment_data.get('option_explanations') or {}
            sanitized_option_explanations = {}
            if isinstance(raw_option_explanations, dict):
                for key, value in raw_option_explanations.items():
                    sanitized = _sanitize_generated_text(value)
                    if sanitized:
                        sanitized_option_explanations[key] = sanitized

            option_letters = [chr(ord('A') + idx) for idx in range(len(options))]
            option_explanations_cn = {}
            for idx, opt in enumerate(options):
                explanation = sanitized_option_explanations.get(opt)
                if not explanation and idx < len(option_letters):
                    explanation = sanitized_option_explanations.get(option_letters[idx])
                if not explanation:
                    explanation = sanitized_option_explanations.get(str(idx))
                if not explanation:
                    explanation = '解析暂缺，请稍后重试。'
                option_explanations_cn[opt] = explanation

            if not segment_text or not question_text or not options or not correct_answer:
                current_app.logger.warning("Skipping malformed signpost segment (missing required fields).")
                continue

            tts_result = tts_service.generate_audio(
                text=segment_text,
                filename_prefix=f"signpost_{segment_data['category']}",
                voice="default"
            )

            if not tts_result:
                current_app.logger.warning(f"Failed to generate audio for signpost: {segment_data['signpost_phrase']}")
                continue

            # Save to database
            signpost = ListeningSignpost(
                text=segment_text,
                signpost_phrase=signpost_phrase,
                signpost_category=segment_data['category'],
                audio_url=tts_result.audio_path,
                audio_duration_seconds=tts_result.duration_seconds,
                question_text=question_text,
                options=options,
                correct_answer=correct_answer,
                explanation_cn=explanation_cn,
                option_explanations_cn=option_explanations_cn
            )
            db.session.add(signpost)
            db.session.flush()  # Get ID

            generated_signposts.append(signpost.to_dict())

        db.session.commit()

        if not generated_signposts:
            return jsonify({
                'success': False,
                'message': 'Failed to generate any audio'
            }), 500

        signpost_queue = [item['id'] for item in generated_signposts]
        session['signpost_queue'] = signpost_queue
        session['signpost_index'] = 0
        session['signpost_current_id'] = signpost_queue[0]
        session.modified = True

        return jsonify({
            'success': True,
            'signpost': generated_signposts[0],  # Return first signpost
            'total_generated': len(generated_signposts),
            'remaining': max(len(signpost_queue) - 1, 0)
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error generating signpost batch: {e}")
        return jsonify({
            'success': False,
            'message': f'An error occurred during generation: {str(e)}'
        }), 500


@app.route('/listening/api/signpost/next', methods=['POST'])
@login_required
def next_signpost():
    """Advance to the next signpost exercise in the current batch."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    queue = session.get('signpost_queue', []) or []
    index = session.get('signpost_index', 0) + 1

    while index < len(queue):
        signpost_id = queue[index]
        signpost_record = ListeningSignpost.query.get(signpost_id)
        if signpost_record:
            session['signpost_index'] = index
            session['signpost_current_id'] = signpost_record.id
            session.modified = True
            return jsonify({
                'success': True,
                'signpost': signpost_record.to_dict(),
                'remaining': max(len(queue) - index - 1, 0)
            })
        index += 1

    return jsonify({
        'success': False,
        'message': 'No more signpost exercises in this batch. Generate new ones to continue.'
    }), 404


@app.route('/listening/api/signpost/<int:signpost_id>/submit', methods=['POST'])
@login_required
def submit_signpost(signpost_id):
    """Submit user's answer to signpost question."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    signpost = ListeningSignpost.query.get(signpost_id)
    if not signpost:
        return jsonify({'error': 'Signpost not found'}), 404

    data = request.get_json() or {}
    user_answer = data.get('answer', '')

    is_correct = user_answer == signpost.correct_answer
    score = 100 if is_correct else 0

    # Save progress
    progress = ListeningUserProgress(
        user_id=user.id,
        exercise_type='signpost',
        exercise_id=signpost.id,
        score=score,
        completed=True,
        user_answer={'answer': user_answer}
    )
    db.session.add(progress)
    db.session.commit()

    return jsonify({
        'success': True,
        'is_correct': is_correct,
        'correct_answer': signpost.correct_answer,
        'explanation_cn': signpost.explanation_cn,
        'option_explanations_cn': signpost.option_explanations_cn or {opt: '解析暂缺，请稍后重试。' for opt in (signpost.options or [])},
        'score': score
    })


# ============================================================================
# FEATURE 3: FULL LECTURE & CONVERSATION SIMULATOR
# ============================================================================

@app.route('/listening/lecture')
@login_required
def lecture_simulator():
    """Full lecture simulator page."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    lecture_id = session.get('lecture_current_id')
    lecture = None

    if lecture_id:
        lecture = ListeningLecture.query.get(lecture_id)

    return render_template(
        'listening/lecture.html',
        user=user,
        lecture=lecture
    )


@app.route('/listening/conversation')
@login_required
def conversation_simulator():
    """Conversation simulator page."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    conversation_id = session.get('conversation_current_id')
    conversation = None

    if conversation_id:
        conversation = ListeningConversation.query.get(conversation_id)

    return render_template(
        'listening/conversation.html',
        user=user,
        conversation=conversation
    )


@app.route('/listening/api/lecture/generate', methods=['POST'])
@login_required
def generate_lecture_exercise():
    """Generate a full lecture with questions using DeepSeek and TTS."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json() or {}
    topic = data.get('topic', 'Biology')

    client = get_gemini_client()
    if not client or not client.is_configured:
        return jsonify({
            'success': False,
            'message': 'AI service not configured'
        }), 503

    try:
        # Generate lecture content (this may take a while)
        lecture_data = generate_lecture(client, topic)
        if not lecture_data:
            return jsonify({
                'success': False,
                'message': 'Failed to generate lecture'
            }), 500

        # Sanitize generated content
        transcript = _sanitize_generated_text(lecture_data.get('transcript', ''))
        expert_notes = _sanitize_generated_text(lecture_data.get('expert_notes', ''))
        if not transcript:
            return jsonify({
                'success': False,
                'message': 'Generated lecture transcript was empty'
            }), 500

        lecture_data['transcript'] = transcript
        lecture_data['expert_notes'] = expert_notes

        # Generate audio with TTS
        tts_service = get_tts_service()
        tts_result = tts_service.generate_audio(
            text=transcript,
            filename_prefix=f"lecture_{topic.lower().replace(' ', '_')}",
            voice="default"
        )

        if not tts_result:
            return jsonify({
                'success': False,
                'message': 'Failed to generate audio'
            }), 500

        # Create lecture in database
        lecture = ListeningLecture(
            title=lecture_data['title'],
            topic=topic,
            transcript=transcript,
            audio_url=tts_result.audio_path,
            audio_duration_seconds=tts_result.duration_seconds,
            word_timestamps=tts_result.word_timestamps,
            expert_notes=expert_notes
        )
        db.session.add(lecture)
        db.session.flush()  # Get lecture.id

        # Create questions
        for q_data in lecture_data.get('questions', []):
            question_text = _sanitize_generated_text(q_data.get('question_text', ''))
            if not question_text:
                continue

            options = [
                _sanitize_generated_text(opt) for opt in q_data.get('options', [])
                if isinstance(opt, str)
            ]
            options = [opt for opt in options if opt]
            correct_answer = _sanitize_generated_text(q_data.get('correct_answer', ''))
            explanation = _sanitize_generated_text(q_data.get('explanation', ''))
            distractor_explanations = {
                key: _sanitize_generated_text(value)
                for key, value in (q_data.get('distractor_explanations') or {}).items()
                if value
            }

            # Refine timestamps using word timestamps if available
            answer_range = q_data.get('answer_time_range', {})
            start_time = answer_range.get('start')
            end_time = answer_range.get('end')

            transcript_quote = _sanitize_generated_text(q_data.get('transcript_quote', ''))
            if (start_time is None or end_time is None) and transcript_quote and tts_result.word_timestamps:
                estimate = find_answer_timestamps(
                    transcript,
                    tts_result.word_timestamps,
                    transcript_quote
                )
                if estimate:
                    start_time = estimate.get('start', start_time)
                    end_time = estimate.get('end', end_time)

            transcript_quote = _sanitize_generated_text(q_data.get('transcript_quote', ''))
            if (start_time is None or end_time is None) and transcript_quote and tts_result.word_timestamps:
                estimate = find_answer_timestamps(
                    transcript,
                    tts_result.word_timestamps,
                    transcript_quote
                )
                if estimate:
                    start_time = estimate.get('start', start_time)
                    end_time = estimate.get('end', end_time)

            question = ListeningQuestion(
                lecture_id=lecture.id,
                question_order=q_data.get('question_order', len(lecture.questions) + 1),
                question_text=question_text,
                question_type=q_data.get('question_type', 'detail'),
                options=options,
                correct_answer=correct_answer,
                explanation=explanation,
                distractor_explanations=distractor_explanations,
                answer_start_time=start_time,
                answer_end_time=end_time
            )
            db.session.add(question)

        db.session.commit()

        # Store in session
        session['lecture_current_id'] = lecture.id
        session.modified = True

        return jsonify({
            'success': True,
            'lecture': lecture.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error generating lecture: {e}")
        return jsonify({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }), 500


@app.route('/listening/api/conversation/generate', methods=['POST'])
@login_required
def generate_conversation_exercise():
    """Generate a conversation with questions using DeepSeek and TTS."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json() or {}
    situation = data.get('situation', 'office hours')

    client = get_gemini_client()
    if not client or not client.is_configured:
        return jsonify({
            'success': False,
            'message': 'AI service not configured'
        }), 503

    try:
        # Generate conversation content
        conv_data = generate_conversation(client, situation)
        if not conv_data:
            return jsonify({
                'success': False,
                'message': 'Failed to generate conversation'
            }), 500

        tts_service = get_tts_service()
        transcript = _sanitize_generated_text(conv_data.get('transcript', ''))
        expert_notes = _sanitize_generated_text(conv_data.get('expert_notes', ''))

        if not transcript:
            return jsonify({
                'success': False,
                'message': 'Generated conversation transcript was empty'
            }), 500

        conv_data['transcript'] = transcript
        conv_data['expert_notes'] = expert_notes

        # Parse transcript into segments for multi-speaker audio when possible
        segments = []
        for line in transcript.splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            speaker = 'Narrator'
            text = cleaned
            if cleaned.startswith('[') and ']' in cleaned:
                speaker_part, remainder = cleaned.split(']', 1)
                speaker = speaker_part.strip('[] ').strip() or 'Narrator'
                text = remainder.strip()

            if text:
                segments.append({'speaker': speaker, 'text': text})

        if segments:
            tts_result = tts_service.generate_multi_speaker_audio(
                segments,
                filename_prefix=f"conversation_{situation.replace(' ', '_')}"
            )
        else:
            tts_result = tts_service.generate_audio(
                text=transcript,
                filename_prefix=f"conversation_{situation.replace(' ', '_')}",
                voice="default"
            )

        if not tts_result:
            return jsonify({
                'success': False,
                'message': 'Failed to generate audio'
            }), 500

        # Create conversation in database
        conversation = ListeningConversation(
            title=conv_data['title'],
            situation=situation,
            transcript=transcript,
            audio_url=tts_result.audio_path,
            audio_duration_seconds=tts_result.duration_seconds,
            word_timestamps=tts_result.word_timestamps,
            expert_notes=expert_notes
        )
        db.session.add(conversation)
        db.session.flush()

        # Create questions
        for q_data in conv_data.get('questions', []):
            question_text = _sanitize_generated_text(q_data.get('question_text', ''))
            if not question_text:
                continue

            options = [
                _sanitize_generated_text(opt) for opt in q_data.get('options', [])
                if isinstance(opt, str)
            ]
            options = [opt for opt in options if opt]
            correct_answer = _sanitize_generated_text(q_data.get('correct_answer', ''))
            explanation = _sanitize_generated_text(q_data.get('explanation', ''))
            distractor_explanations = {
                key: _sanitize_generated_text(value)
                for key, value in (q_data.get('distractor_explanations') or {}).items()
                if value
            }

            answer_range = q_data.get('answer_time_range', {})
            start_time = answer_range.get('start')
            end_time = answer_range.get('end')

            question = ListeningQuestion(
                conversation_id=conversation.id,
                question_order=q_data.get('question_order', len(conversation.questions) + 1),
                question_text=question_text,
                question_type=q_data.get('question_type', 'purpose'),
                options=options,
                correct_answer=correct_answer,
                explanation=explanation,
                distractor_explanations=distractor_explanations,
                answer_start_time=start_time,
                answer_end_time=end_time
            )
            db.session.add(question)

        db.session.commit()

        # Store in session
        session['conversation_current_id'] = conversation.id
        session.modified = True

        return jsonify({
            'success': True,
            'conversation': conversation.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error generating conversation: {e}")
        return jsonify({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }), 500


@app.route('/listening/api/lecture/<int:lecture_id>/submit', methods=['POST'])
@login_required
def submit_lecture(lecture_id):
    """Submit user's answers to lecture questions."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    lecture = ListeningLecture.query.get(lecture_id)
    if not lecture:
        return jsonify({'error': 'Lecture not found'}), 404

    data = request.get_json() or {}
    user_answers = data.get('answers', {})  # {question_id: answer}

    # Evaluate answers
    results = []
    correct_count = 0
    total_questions = len(lecture.questions)

    for question in lecture.questions:
        user_answer = user_answers.get(str(question.id), '')
        if isinstance(user_answer, str):
            user_answer = user_answer.strip()
        correct_answer = (question.correct_answer or '').strip()
        options = question.options or []
        is_correct = _answers_match(user_answer, correct_answer, options)

        if is_correct:
            correct_count += 1

        results.append({
            'question_id': question.id,
            'is_correct': is_correct,
            'user_answer': _format_answer_display(user_answer, options),
            'correct_answer': _format_answer_display(correct_answer, options),
            'raw_user_answer': user_answer,
            'raw_correct_answer': correct_answer,
            'explanation': question.explanation,
            'distractor_explanations': question.distractor_explanations,
            'options': options,
            'answer_start_time': question.answer_start_time,
            'answer_end_time': question.answer_end_time
        })

    score = (correct_count / total_questions * 100) if total_questions > 0 else 0

    # Save progress
    progress = ListeningUserProgress(
        user_id=user.id,
        exercise_type='lecture',
        exercise_id=lecture.id,
        score=score,
        completed=True,
        user_answer=user_answers
    )
    db.session.add(progress)
    db.session.commit()

    return jsonify({
        'success': True,
        'score': round(score, 2),
        'correct_count': correct_count,
        'total_questions': total_questions,
        'results': results,
        'expert_notes': lecture.expert_notes
    })


@app.route('/listening/api/conversation/<int:conversation_id>/submit', methods=['POST'])
@login_required
def submit_conversation(conversation_id):
    """Submit user's answers to conversation questions."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    conversation = ListeningConversation.query.get(conversation_id)
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404

    data = request.get_json() or {}
    user_answers = data.get('answers', {})

    # Evaluate answers
    results = []
    correct_count = 0
    total_questions = len(conversation.questions)

    for question in conversation.questions:
        user_answer = user_answers.get(str(question.id), '')
        if isinstance(user_answer, str):
            user_answer = user_answer.strip()
        correct_answer = (question.correct_answer or '').strip()
        options = question.options or []
        is_correct = _answers_match(user_answer, correct_answer, options)

        if is_correct:
            correct_count += 1

        results.append({
            'question_id': question.id,
            'is_correct': is_correct,
            'user_answer': _format_answer_display(user_answer, options),
            'correct_answer': _format_answer_display(correct_answer, options),
            'raw_user_answer': user_answer,
            'raw_correct_answer': correct_answer,
            'explanation': question.explanation,
            'distractor_explanations': question.distractor_explanations,
            'options': options,
            'answer_start_time': question.answer_start_time,
            'answer_end_time': question.answer_end_time
        })

    score = (correct_count / total_questions * 100) if total_questions > 0 else 0

    # Save progress
    progress = ListeningUserProgress(
        user_id=user.id,
        exercise_type='conversation',
        exercise_id=conversation.id,
        score=score,
        completed=True,
        user_answer=user_answers
    )
    db.session.add(progress)
    db.session.commit()

    return jsonify({
        'success': True,
        'score': round(score, 2),
        'correct_count': correct_count,
        'total_questions': total_questions,
        'results': results,
        'expert_notes': conversation.expert_notes
    })


# ============================================================================
# QUESTION TYPE STRATEGY LAB
# ============================================================================

@app.route('/reading/question-types')
@login_required
def question_types_hub():
    """Question Type Strategy Lab - Main hub for selecting question types."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    # Get question types organized by category
    categories = get_question_types_by_category()

    return render_template(
        'reading/question_types_hub.html',
        user=user,
        categories=categories
    )


@app.route('/reading/question-types/<question_type_id>/learn')
@login_required
def question_type_learn(question_type_id):
    """Learn Mode - Strategy guide for a specific question type."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    # Get metadata for this question type
    q_type = get_question_type_metadata(question_type_id)
    if not q_type:
        flash('Question type not found.', 'danger')
        return redirect(url_for('question_types_hub'))

    return render_template(
        'reading/question_type_learn.html',
        user=user,
        q_type=q_type
    )


@app.route('/reading/question-types/<question_type_id>/practice')
@login_required
def question_type_practice(question_type_id):
    """Practice Mode - Display current drill for this question type."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    # Get metadata
    q_type = get_question_type_metadata(question_type_id)
    if not q_type:
        flash('Question type not found.', 'danger')
        return redirect(url_for('question_types_hub'))

    # Check if we have a drill_id in the session
    session_key = f'question_type_drill_{question_type_id}'
    drill_id = session.get(session_key)

    if not drill_id:
        # Redirect to loading page to generate drill
        return redirect(url_for(
            'loading_page',
            target=url_for('question_type_practice', question_type_id=question_type_id),
            generator=url_for('generate_question_type_drill_async', question_type_id=question_type_id),
            title=f"生成 {q_type['name_cn']} 练习",
            message="DeepSeek 正在为你精心准备题型练习..."
        ))

    # Retrieve drill from persistent store
    drill = load_drill(drill_id)

    if not drill:
        # Drill expired or not found, clear session and show error
        current_app.logger.error(
            f"Drill {drill_id} not found in store (store has {count_drill_store()} items)"
        )
        del session[session_key]
        session.modified = True
        flash('练习已过期，请重新生成。', 'warning')
        return redirect(url_for('question_types_hub'))

    return render_template(
        'reading/question_type_practice.html',
        user=user,
        q_type=q_type,
        drill=drill
    )


@app.route('/reading/api/question-types/<question_type_id>/generate', methods=['POST'])
@login_required
def generate_question_type_drill_async(question_type_id):
    """Generate a drill for a specific question type using DeepSeek."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    # Verify question type exists
    q_type = get_question_type_metadata(question_type_id)
    if not q_type:
        return jsonify({'success': False, 'message': 'Question type not found'}), 404

    # Get DeepSeek client
    client = get_gemini_client()
    if not client or not client.is_configured:
        return jsonify({'success': False, 'message': 'DeepSeek API is not configured'}), 503

    # Generate drill
    raw_drill = generate_question_type_drill(question_type_id, client)

    if not raw_drill:
        return jsonify({
            'success': False,
            'message': 'DeepSeek 生成失败，请稍后重试。'
        }), 503

    # Transform drill data for template
    # DeepSeek returns: {passage, topic, questions: [{question_text, options, correct_answer, ...}]}
    # Store all questions (3-5) and track current index

    if not raw_drill.get('questions') or len(raw_drill['questions']) < 5:
        return jsonify({
            'success': False,
            'message': f'DeepSeek 返回的数据格式不正确（生成了{len(raw_drill.get("questions", []))}个问题，需要5个）。请重试。'
        }), 503

    # Transform all questions
    transformed_questions = []
    for question_data in raw_drill['questions']:
        correct_answer_text = question_data.get('correct_answer', '')
        options = question_data.get('options', [])
        answer_index = next((i for i, opt in enumerate(options) if opt == correct_answer_text), 0)

        # Build explanations array
        distractor_explanations = question_data.get('distractor_explanations', {})
        explanations = []
        for opt in options:
            if opt == correct_answer_text:
                explanations.append(question_data.get('strategy_analysis_cn', '这是正确答案'))
            else:
                explanations.append(distractor_explanations.get(opt, '此选项不正确'))

        transformed_questions.append({
            'question_text': question_data.get('question_text', ''),
            'options': options,
            'answer': answer_index,
            'explanations': explanations,
            'analysis': question_data.get('strategy_analysis_cn', '')
        })

    drill = {
        'passage': raw_drill.get('passage', ''),
        'topic': raw_drill.get('topic', ''),
        'questions': transformed_questions,
        'current_index': 0,  # Track which question user is on
        'total_questions': len(transformed_questions)
    }

    # Store in persistent server-side store to avoid session cookie limits and dev reload losses
    import time
    drill_id = f"drill_{question_type_id}_{user.id}_{int(time.time())}"
    store_drill(drill_id, drill)

    # Only store drill_id in session (lightweight)
    session_key = f'question_type_drill_{question_type_id}'

    # AGGRESSIVELY trim heavy keys to keep cookie under 4KB
    keys_to_remove = [
        'reading_bootstrap',
        'reading_last_sentence',
        'reading_last_paragraph',
        'reading_last_passage',
        'gap_fill_payload',
        'synonym_payload',
        'reading_passage_payload'
    ]

    # Also remove old drill IDs for other question types to save space
    for key in list(session.keys()):
        if key.startswith('question_type_drill_') and key != session_key:
            keys_to_remove.append(key)
        elif key.startswith('reading_'):
            keys_to_remove.append(key)

    for k in keys_to_remove:
        if k in session:
            try:
                del session[k]
                current_app.logger.debug(f"Removed session key: {k}")
            except Exception:
                pass

    session[session_key] = drill_id
    session.modified = True

    current_app.logger.info(f"Stored drill {drill_id} with {len(transformed_questions)} questions")

    return jsonify({
        'success': True,
        'redirect': url_for('question_type_practice', question_type_id=question_type_id)
    })


@app.route('/reading/api/question-types/<question_type_id>/navigate', methods=['POST'])
@login_required
def navigate_question_type_drill(question_type_id):
    """Navigate to next/previous question in the drill."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    direction = request.json.get('direction', 'next')
    session_key = f'question_type_drill_{question_type_id}'
    drill_id = session.get(session_key)

    if not drill_id:
        return jsonify({'success': False, 'message': 'No drill found'}), 404

    # Get drill from persistent store
    drill = load_drill(drill_id)

    if not drill:
        current_app.logger.error(f"Drill {drill_id} not found in cache during navigation")
        return jsonify({'success': False, 'message': 'Drill expired'}), 404

    current_index = drill.get('current_index', 0)
    total_questions = drill.get('total_questions', 5)

    if direction == 'next' and current_index < total_questions - 1:
        drill['current_index'] = current_index + 1
    elif direction == 'prev' and current_index > 0:
        drill['current_index'] = current_index - 1

    # Update in store
    save_drill(drill_id, drill)

    return jsonify({
        'success': True,
        'current_index': drill['current_index']
    })


@app.route('/reading/api/question-types/<question_type_id>/regenerate', methods=['POST'])
@login_required
def regenerate_question_type_drill(question_type_id):
    """Regenerate a new drill for the same question type."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    # Clear existing drill from session and store
    session_key = f'question_type_drill_{question_type_id}'
    if session_key in session:
        drill_id = session[session_key]
        # Remove from persistent store
        remove_drill(drill_id)
        current_app.logger.info(f"Removed drill {drill_id} from store")
        # Remove from session
        del session[session_key]
        session.modified = True
    
    # Clear reading bootstrap to reduce session size
    if 'reading_bootstrap' in session:
        del session['reading_bootstrap']
        current_app.logger.info("Cleared reading_bootstrap from session to reduce cookie size")

    # Redirect to generate
    return jsonify({
        'success': True,
        'redirect': url_for('question_type_practice', question_type_id=question_type_id)
    })


# ============================================================================
# DAILY EXERCISES
# ============================================================================

@app.route('/exercises')
@login_required
def exercises_hub():
    """Exercises hub page - main entrance to all exercises."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    # Aggressively clean session to prevent cookie overflow
    keys_to_remove = [
        'reading_bootstrap', 'reading_bootstrap_id',
        'reading_last_sentence', 'reading_last_paragraph', 'reading_last_passage',
        'gap_fill_payload', 'synonym_payload', 'reading_passage_payload',
        'gap_fill_cache_id', 'synonym_cache_id'
    ]
    for key in keys_to_remove:
        if key in session:
            try:
                del session[key]
            except:
                pass
    session.modified = True

    return render_template('exercises_hub.html', user=user)


@app.route('/exercises/dictation')
@login_required
def dictation_challenge():
    """Audio dictation drill for vocabulary."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    # Try today's words first, then fall back to any studied words
    words = get_words_reviewed_today(user.id)
    if not words:
        # Get any words user has studied (fallback)
        words = db.session.query(Word).join(
            UserWord,
            (UserWord.word_id == Word.id) & (UserWord.user_id == user.id)
        ).filter(UserWord.repetitions > 0).order_by(UserWord.next_due.desc()).limit(20).all()

    if not words:
        flash('Start studying some words first to unlock exercises.', 'warning')
        return redirect(url_for('vocab_session'))

    prioritized = sorted(words, key=lambda w: bool(w.pronunciation_pitfall_cn), reverse=True)
    random.shuffle(prioritized)

    exercises = []
    for word in prioritized[:10]:
        audio_path = ensure_pronunciation_audio(word)
        if not audio_path:
            continue
        exercises.append({
            'lemma': word.lemma,
            'audio_url': url_for('static', filename=audio_path),
            'cn_gloss': word.cn_gloss,
            'definition': word.definition,
            'pitfall': word.pronunciation_pitfall_cn,
        })

    if not exercises:
        flash('Pronunciation audio is unavailable at the moment. Try again later.', 'danger')
        return redirect(url_for('vocab_session'))

    return render_template(
        'exercises/dictation.html',
        exercises=exercises,
        studied_count=len(words)
    )


@app.route('/exercises/gap-fill')
@login_required
def contextual_gap_fill():
    """Multiple-choice gap-fill exercises for vocabulary."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    # Try to retrieve from server-side cache
    cache_id = session.get('gap_fill_cache_id')
    if cache_id:
        cache = getattr(current_app, '_exercise_cache', {})
        payload = cache.get(cache_id)
        if payload:
            normalized = payload.get('exercises', [])
            ai_generated = payload.get('ai_generated', False)
            # Remove cache ID from session after use
            del session['gap_fill_cache_id']
            session.modified = True
        else:
            normalized, ai_generated, error = _prepare_gap_fill_payload(user)
            if error:
                flash(error, 'danger' if 'Unable' in error else 'warning')
                return redirect(url_for('vocab_session'))
    else:
        normalized, ai_generated, error = _prepare_gap_fill_payload(user)
        if error:
            flash(error, 'danger' if 'Unable' in error else 'warning')
            return redirect(url_for('vocab_session'))

    return render_template(
        'exercises/gap_fill.html',
        exercises=normalized,
        ai_generated=ai_generated
    )


@app.route('/exercises/synonym-showdown')
@login_required
def synonym_showdown():
    """Synonym nuance discrimination exercises."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    # Try to retrieve from server-side cache
    cache_id = session.get('synonym_cache_id')
    if cache_id:
        cache = getattr(current_app, '_exercise_cache', {})
        payload = cache.get(cache_id)
        if payload:
            normalized = payload.get('exercises', [])
            ai_generated = payload.get('ai_generated', False)
            # Remove cache ID from session after use
            del session['synonym_cache_id']
            session.modified = True
        else:
            normalized, ai_generated, error = _prepare_synonym_payload(user)
            if error:
                flash(error, 'danger' if 'Unable' in error else 'warning')
                return redirect(url_for('vocab_session'))
    else:
        normalized, ai_generated, error = _prepare_synonym_payload(user)
        if error:
            flash(error, 'danger' if 'Unable' in error else 'warning')
            return redirect(url_for('vocab_session'))

    return render_template(
        'exercises/synonym.html',
        exercises=normalized,
        ai_generated=ai_generated
    )


@app.route('/exercises/reading')
@login_required
def reading_immersion():
    """Reading immersion mode with highlighted vocabulary."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    topics = [
        'Astronomy',
        'Ecology',
        'Anthropology',
        'Economics',
        'Architecture',
        'Geology',
        'Neuroscience',
    ]
    topic = request.args.get('topic')

    if topic:
        payload = session.pop('reading_passage_payload', None)
        if payload and payload.get('topic') == topic:
            passage = payload.get('passage')
            highlight_words = payload.get('highlight_words', [])
            ai_flag = payload.get('ai_generated', False)
        else:
            passage, highlight_words, ai_flag, error = _prepare_reading_passage_payload(user, topic)
            if error or not passage:
                flash(error or 'Unable to craft a reading passage right now. Please try again later.', 'danger')
                return redirect(url_for('reading_immersion'))
        session['reading_last_passage'] = passage
        session.modified = True

        highlighted = highlight_vocabulary(passage.get('paragraph', ''), highlight_words or [])
        quiz_raw = passage.get('quiz', [])
        quiz_items = []
        for item in quiz_raw:
            if not isinstance(item, dict):
                continue
            options = [opt for opt in item.get('options', []) if isinstance(opt, str)]
            if not options:
                continue
            answer_field = item.get('answer')
            if isinstance(answer_field, int) and 0 <= answer_field < len(options):
                answer_value = options[answer_field]
            else:
                answer_value = answer_field if isinstance(answer_field, str) else options[0]
            if answer_value not in options:
                options.append(answer_value)
            explanation = item.get('explanation_cn') or item.get('explanation') or '结合上下文理解含义。'
            rationale_source = item.get('rationales', {}) if isinstance(item, dict) else {}
            if isinstance(rationale_source, list):
                # Map list entries to corresponding options by index
                rationale_source = {
                    opt: rationale_source[idx]
                    for idx, opt in enumerate(options)
                    if idx < len(rationale_source)
                }
            rationales = {}
            for opt in options:
                rationale_text = rationale_source.get(opt)
                if not rationale_text:
                    if opt == answer_value:
                        rationale_text = "与段落语境一致，释义最准确。"
                    else:
                        rationale_text = "与上下文的含义或语气不匹配。"
                rationales[opt] = rationale_text
            quiz_items.append({
                'question': item.get('question', ''),
                'options': options,
                'answer': answer_value,
                'explanation_cn': explanation,
                'rationales': rationales
            })

        return render_template(
            'exercises/reading.html',
            topic=topic,
            passage_html=highlighted,
            quiz=quiz_items,
            ai_generated=ai_flag,
            topics=topics,
            highlight_words=highlight_words or [],
        )

    # Base view with topic selection
    srs_candidates = get_words_in_stage_range(user.id, min_repetitions=2, max_repetitions=8, limit=7)
    supplemental = get_words_reviewed_today(user.id)
    seen_ids = {word.id for word in srs_candidates}
    for word in supplemental:
        if word.id not in seen_ids and len(srs_candidates) < 7:
            srs_candidates.append(word)
            seen_ids.add(word.id)

    return render_template(
        'exercises/reading.html',
        topics=topics,
        highlight_words=[word.lemma for word in srs_candidates]
    )


# ============================================================================
# UNFAMILIAR WORDS API
# ============================================================================

@app.route('/api/unfamiliar-words', methods=['GET'])
@login_required
def get_unfamiliar_words():
    """Get all unfamiliar words for the current user."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401

    unfamiliar_words = UnfamiliarWord.query.filter_by(user_id=user.id).order_by(
        UnfamiliarWord.created_at.desc()
    ).all()

    return jsonify({
        'words': [{
            'id': uw.id,
            'word': uw.word_text,
            'context': uw.context,
            'source': uw.source,
            'created_at': uw.created_at.isoformat()
        } for uw in unfamiliar_words]
    })


@app.route('/api/unfamiliar-words', methods=['POST'])
@login_required
def add_unfamiliar_word():
    """Add a word to the unfamiliar words list."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    word_text = data.get('word', '').strip().lower()
    context = data.get('context', '').strip()
    source = data.get('source', 'manual')

    if not word_text:
        return jsonify({'error': 'Word text is required'}), 400

    # Check if already exists
    existing = UnfamiliarWord.query.filter_by(
        user_id=user.id,
        word_text=word_text
    ).first()

    if existing:
        return jsonify({
            'message': 'Word already in unfamiliar list',
            'id': existing.id
        }), 200

    # Create new unfamiliar word
    unfamiliar = UnfamiliarWord(
        user_id=user.id,
        word_text=word_text,
        context=context[:500] if context else None,  # Limit context length
        source=source
    )
    db.session.add(unfamiliar)

    # Also check if this word exists in our vocabulary database
    # If it does, create or get UserWord and mark it as needing review
    word = Word.query.filter(
        func.lower(Word.lemma) == word_text
    ).first()

    if word:
        user_word = get_or_create_user_word(user.id, word.id)
        # Reset the word to be reviewed immediately, similar to "red button" behavior
        user_word.repetitions = 0
        user_word.interval = 0.0
        user_word.easiness = max(1.3, user_word.easiness - 0.3)  # Lower easiness
        user_word.next_due = datetime.now(timezone.utc)
        user_word.last_grade = 'not'
        db.session.add(user_word)

    db.session.commit()

    return jsonify({
        'message': 'Word added to unfamiliar list',
        'id': unfamiliar.id,
        'matched_vocabulary': word is not None
    }), 201


@app.route('/api/unfamiliar-words/<int:word_id>', methods=['DELETE'])
@login_required
def remove_unfamiliar_word(word_id):
    """Remove a word from the unfamiliar words list."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401

    unfamiliar = UnfamiliarWord.query.filter_by(
        id=word_id,
        user_id=user.id
    ).first()

    if not unfamiliar:
        return jsonify({'error': 'Unfamiliar word not found'}), 404

    db.session.delete(unfamiliar)
    db.session.commit()

    return jsonify({'message': 'Word removed from unfamiliar list'}), 200


# ============================================================================
# SPEAKING MODULE
# ============================================================================


_POSITIVE_DELIVERY_KEYWORDS = {
    'excellent', 'very good', 'strong', 'great job', 'well done', 'solid', 'good fluency', 'clear pronunciation'
}


def _split_delivery_feedback(messages: List[str]) -> Tuple[List[str], List[str]]:
    """Split delivery feedback into strengths vs improvements using simple heuristics."""
    positives: List[str] = []
    improvements: List[str] = []
    for raw in messages or []:
        text = (raw or '').strip()
        if not text:
            continue
        lowered = text.lower()
        if any(keyword in lowered for keyword in _POSITIVE_DELIVERY_KEYWORDS):
            positives.append(text)
        elif lowered.startswith('excellent') or lowered.startswith('very good'):
            positives.append(text)
        else:
            improvements.append(text)
    return positives, improvements


def _unique_list(items: List[str]) -> List[str]:
    """Preserve order while removing duplicates and empty strings."""
    seen = set()
    ordered: List[str] = []
    for item in items or []:
        text = (item or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _score_listen_and_repeat(prompt: str, transcript: str) -> Dict[str, Any]:
    """Score listen-and-repeat responses using rubric-aligned similarity checks."""
    def _tokens(text: str) -> List[str]:
        return re.findall(r"[A-Za-z']+", (text or "").lower())

    prompt_tokens = _tokens(prompt)
    response_tokens = _tokens(transcript)

    if not response_tokens:
        return {
            "score_5": 0.0,
            "similarity": 0.0,
            "note": "No response or unintelligible response.",
            "rubric_evidence": [
                "No response or unintelligible; does not meet rubric requirements.",
            ],
        }

    if response_tokens == prompt_tokens:
        return {
            "score_5": 5.0,
            "similarity": 1.0,
            "note": "Exact repetition with fully intelligible delivery.",
            "rubric_evidence": [
                "Fully intelligible and exact repetition of the prompt.",
            ],
        }

    similarity = SequenceMatcher(None, prompt_tokens, response_tokens).ratio()
    length_ratio = (len(response_tokens) / len(prompt_tokens)) if prompt_tokens else 0.0

    if similarity >= 0.95:
        score = 4.5
        note = "Meaning captured with only minor changes."
        evidence = "Minor word/grammar changes that do not change meaning."
    elif similarity >= 0.90:
        score = 4.0
        note = "Meaning captured with minor changes in words or grammar."
        evidence = "Minor changes but original meaning preserved."
    elif similarity >= 0.85:
        score = 3.5
        note = "Response is essentially full with some meaning shifts."
        evidence = "Mostly full sentence; some word changes affect meaning."
    elif similarity >= 0.80:
        score = 3.0
        note = "Response is essentially full but meaning shifts in places."
        evidence = "Majority of content words present, but meaning shifts."
    elif similarity >= 0.70:
        score = 2.5
        note = "Significant parts are missing or inaccurate."
        evidence = "Large portions missing or inaccurate; meaning unclear."
    elif similarity >= 0.60:
        score = 2.0
        note = "Significant parts are missing or inaccurate."
        evidence = "Missing important content; response fragmentary."
    elif similarity >= 0.50:
        score = 1.5
        note = "Only a small portion of the prompt is captured."
        evidence = "Very limited capture of prompt content."
    elif similarity >= 0.40:
        score = 1.0
        note = "Only a small portion of the prompt is captured."
        evidence = "Mostly unintelligible; few recognizable words."
    elif similarity >= 0.30:
        score = 0.5
        note = "Response is largely unintelligible or unrelated to the prompt."
        evidence = "Minimal response; largely unintelligible."
    else:
        score = 0.0
        note = "Response is largely unintelligible or unrelated to the prompt."
        evidence = "No meaningful repetition of the prompt."

    if length_ratio < 0.3:
        score = min(score, 1.0)
        note = "Very short response; most of the prompt is missing."
        evidence = "Response is fragmentary; most of the prompt is missing."

    return {
        "score_5": score,
        "similarity": round(similarity, 3),
        "note": note,
        "rubric_evidence": [evidence],
    }


@app.route('/speaking')
@app.route('/speaking/dashboard')
@login_required
def speaking_dashboard():
    """Speaking practice dashboard."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    return render_template('speaking/dashboard.html', user=user)


@app.route('/speaking/task/<int:task_number>/start')
@login_required
def speaking_task_start(task_number):
    """Start a speaking task - show existing or redirect to generation."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    if task_number not in [1, 2, 3, 4]:
        flash('Invalid task number', 'danger')
        return redirect(url_for('speaking_dashboard'))

    # Try to get an existing task from database
    from models import SpeakingTask
    task = SpeakingTask.query.filter_by(task_number=task_number).first()

    # If no task exists, redirect to generating page
    if not task:
        return redirect(url_for('speaking_task_generate', task_number=task_number))

    return render_template('speaking/practice.html', task=task, user=user)


@app.route('/speaking/task/<int:task_number>/regenerate')
@login_required
def speaking_task_regenerate(task_number):
    """Regenerate a speaking task (delete old one and create new)."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    if task_number not in [1, 2, 3, 4]:
        flash('Invalid task number', 'danger')
        return redirect(url_for('speaking_dashboard'))

    # Delete existing task for this task number
    from models import SpeakingTask
    SpeakingTask.query.filter_by(task_number=task_number).delete()
    db.session.commit()

    # Redirect to generating page
    return redirect(url_for('speaking_task_generate', task_number=task_number))


@app.route('/speaking/task/<int:task_number>/generate')
@login_required
def speaking_task_generate(task_number):
    """Show generating page and trigger background generation."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    if task_number not in [1, 2, 3, 4]:
        flash('Invalid task number', 'danger')
        return redirect(url_for('speaking_dashboard'))

    task_names = {
        1: "Independent Speaking",
        2: "Campus Situation",
        3: "Academic Concept",
        4: "Academic Lecture"
    }

    # Start generation in background (we'll use a simple approach - generate on check)
    return render_template(
        'speaking/generating.html',
        task_number=task_number,
        task_name=task_names.get(task_number, f"Task {task_number}"),
        user=user
    )


@app.route('/speaking/task/<int:task_number>/check')
@login_required
def speaking_task_check(task_number):
    """Check if task generation is complete (and generate if needed)."""
    user = get_current_user()
    if not user:
        return jsonify({'ready': False, 'error': 'Unauthorized'}), 401

    if task_number not in [1, 2, 3, 4]:
        return jsonify({'ready': False, 'error': 'Invalid task number'}), 400

    from models import SpeakingTask

    # Check if task already exists
    task = SpeakingTask.query.filter_by(task_number=task_number).first()

    if task:
        # Task ready
        return jsonify({
            'ready': True,
            'redirect_url': url_for('speaking_task_start', task_number=task_number)
        })

    # Task doesn't exist - generate it now
    from services.speaking_generator import generate_task_by_number
    task_data = generate_task_by_number(task_number)

    if not task_data:
        return jsonify({'ready': False, 'error': 'Failed to generate task'}), 500

    # Save to database
    task = SpeakingTask(
        task_number=task_data['task_number'],
        task_type=task_data['task_type'],
        topic=task_data['topic'],
        prompt=task_data['prompt'],
        reading_text=task_data.get('reading_text'),
        listening_transcript=task_data.get('listening_transcript'),
        listening_audio_url=task_data.get('listening_audio_url'),
        preparation_time=task_data.get('preparation_time', 15),
        response_time=task_data.get('response_time', 45),
        sample_response=task_data.get('sample_response'),
        response_template=task_data.get('response_template')
    )
    db.session.add(task)
    db.session.commit()

    return jsonify({
        'ready': True,
        'redirect_url': url_for('speaking_task_start', task_number=task_number)
    })


@app.route('/speaking/task/<int:task_id>/submit', methods=['POST'])
@login_required
def speaking_submit_response(task_id):
    """Handle audio submission, speech analysis, and AI feedback."""
    import os
    import uuid
    from models import SpeakingTask, SpeakingResponse, SpeakingFeedback

    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    task = SpeakingTask.query.get_or_404(task_id)

    audio_file = request.files.get('audio')
    record_id = request.form.get('record_id') or request.args.get('record_id')
    if not audio_file or audio_file.filename == '':
        return jsonify({'success': False, 'message': 'No audio file provided'}), 400

    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'speaking')
    os.makedirs(upload_dir, exist_ok=True)

    filename = f"{user.id}_{task_id}_{uuid.uuid4().hex}.webm"
    audio_path = os.path.join(upload_dir, filename)
    audio_file.save(audio_path)

    audio_url = f"/static/uploads/speaking/{filename}"
    attempt_number = SpeakingResponse.query.filter_by(user_id=user.id, task_id=task_id).count() + 1

    response = SpeakingResponse(
        user_id=user.id,
        task_id=task_id,
        audio_url=audio_url,
        attempt_number=attempt_number
    )
    db.session.add(response)
    db.session.flush()

    transcription = ''
    audio_duration = None
    delivery_score = None
    fluency_score = None
    pronunciation_score = None
    rhythm_score = None
    speech_metrics: Dict[str, Any] = {}
    delivery_strengths: List[str] = []
    delivery_improvements: List[str] = []
    specific_feedback: List[str] = []

    speech_rater = get_speech_rater()
    if speech_rater and getattr(speech_rater, 'is_available', False):
        try:
            speech_result = speech_rater.rate_speech(audio_path)
            if speech_result and not speech_result.get('error'):
                transcription = (speech_result.get('transcription') or '').strip()
                speech_metrics = speech_result.get('metrics') or {}
                audio_duration = speech_metrics.get('total_duration')
                delivery_score = speech_result.get('overall_score')
                fluency_score = (speech_result.get('fluency') or {}).get('overall')
                pronunciation_score = (speech_result.get('pronunciation') or {}).get('overall')
                rhythm_score = (speech_result.get('rhythm') or {}).get('overall')
                specific_feedback = speech_result.get('feedback') or []
                delivery_strengths, delivery_improvements = _split_delivery_feedback(specific_feedback)
            else:
                current_app.logger.warning('SpeechRater returned error payload: %s', speech_result)
        except Exception as exc:  # pragma: no cover - defensive
            current_app.logger.error('SpeechRater analysis failed: %s', exc)
    else:
        current_app.logger.info('SpeechRater unavailable; skipping delivery analysis.')

    repeat_task = task.task_type == 'new_toefl_repeat'
    is_new_toefl_task = task.task_type in {'new_toefl_repeat', 'new_toefl_interview'}
    engine = get_feedback_engine()
    language_result = None
    topic_result = None
    if not repeat_task:
        language_result = engine.evaluate_language_use(transcription)
        topic_result = engine.evaluate_topic_development(
            task.prompt,
            transcription,
            task.reading_text,
            task.listening_transcript,
            task.task_type,
        )

    response.transcription = transcription
    response.audio_duration_seconds = audio_duration

    if language_result:
        if isinstance(speech_metrics, dict):
            speech_metrics.setdefault('lexical_diversity', language_result.lexical_diversity)
            speech_metrics.setdefault('total_words', language_result.total_words)
            speech_metrics.setdefault('average_sentence_length', language_result.average_sentence_length)
            speech_metrics.setdefault('academic_word_count', language_result.academic_word_count)
            speech_metrics.setdefault('academic_words_used', language_result.academic_words_used)
        else:
            speech_metrics = {
                'lexical_diversity': language_result.lexical_diversity,
                'total_words': language_result.total_words,
                'average_sentence_length': language_result.average_sentence_length,
                'academic_word_count': language_result.academic_word_count,
                'academic_words_used': language_result.academic_words_used,
            }

    if repeat_task:
        repeat_eval = _score_listen_and_repeat(task.listening_transcript or task.prompt or "", transcription)
        repeat_band = float(repeat_eval.get("score_5") or 0.0)
        overall_band = _round_to_half(repeat_band)
        overall_score_30 = round(overall_band * 6, 1)
        delivery_score = None
        fluency_score = None
        pronunciation_score = None
        rhythm_score = None
        language_use_score = None
        topic_development_score = None
        overall_score = overall_score_30 if is_new_toefl_task else repeat_eval.get("score_100", 0.0)
        speech_metrics = speech_metrics or {}
        if isinstance(speech_metrics, dict):
            speech_metrics["repeat_score_5"] = repeat_band
            speech_metrics["repeat_similarity"] = repeat_eval.get("similarity")
            speech_metrics["repeat_note"] = repeat_eval.get("note")
            if is_new_toefl_task:
                speech_metrics["overall_band_5"] = overall_band
                speech_metrics["overall_score_30"] = overall_score_30
                speech_metrics["rubric_evidence"] = repeat_eval.get("rubric_evidence") or []

        repeat_strengths: List[str] = []
        repeat_improvements: List[str] = []
        if repeat_band >= 4.5:
            repeat_strengths.append("Exact or near-exact repetition with fully intelligible delivery.")
        elif repeat_band >= 4.0:
            repeat_strengths.append("Meaning is captured with only minor changes.")
        elif repeat_band >= 3.0:
            repeat_strengths.append("Most content is present, but meaning shifts in places.")
            repeat_improvements.append("Preserve original meaning by avoiding substitutions or omissions.")
        elif repeat_band >= 2.0:
            repeat_improvements.append("Include the full sentence; several key words are missing.")
        else:
            repeat_improvements.append("Repeat the entire sentence clearly, not fragments or unrelated words.")

        combined_strengths = _unique_list(delivery_strengths + repeat_strengths)
        combined_improvements = _unique_list(delivery_improvements + repeat_improvements)
        specific_feedback = _unique_list(repeat_eval.get("rubric_evidence") or [
            f"Similarity to prompt: {repeat_eval.get('similarity')}",
            repeat_eval.get("note"),
        ])
        task_fulfillment = repeat_eval.get("note")
        clarity_coherence = "Intelligibility based on how closely the response matches the prompt."
        support_sufficiency = "Not applicable for listen-and-repeat tasks."
        grammar_errors = []
        vocabulary_suggestions = []
        lexical_diversity = None
        academic_word_count = None
    else:
        if is_new_toefl_task:
            delivery_band = _map_delivery_score_to_band(delivery_score if delivery_score is not None else (60.0 if transcription else 0.0))
            delivery_band = _round_to_half(delivery_band)
            fluency_score = _round_to_half(_map_delivery_score_to_band(fluency_score if fluency_score is not None else delivery_score))
            pronunciation_score = _round_to_half(_map_delivery_score_to_band(pronunciation_score if pronunciation_score is not None else delivery_score))
            rhythm_score = _round_to_half(_map_delivery_score_to_band(rhythm_score if rhythm_score is not None else delivery_score))
            language_use_score = language_result.score if language_result else 0.0
            topic_development_score = topic_result.score if topic_result else 0.0
            subscores = [score for score in [delivery_band, language_use_score, topic_development_score] if isinstance(score, (int, float))]
            overall_band = _round_to_half(sum(subscores) / len(subscores)) if subscores else 0.0
            overall_score = round(overall_band * 6, 1)

            speech_metrics = speech_metrics or {}
            if isinstance(speech_metrics, dict):
                speech_metrics["overall_band_5"] = overall_band
                speech_metrics["overall_score_30"] = overall_score
                speech_metrics["delivery_band_5"] = delivery_band
                speech_metrics["language_use_band_5"] = language_use_score
                speech_metrics["topic_development_band_5"] = topic_development_score
                rubric_evidence = []
                if language_result and language_result.rubric_evidence:
                    rubric_evidence.extend(language_result.rubric_evidence)
                if topic_result and topic_result.rubric_evidence:
                    rubric_evidence.extend(topic_result.rubric_evidence)
                if rubric_evidence:
                    speech_metrics["rubric_evidence"] = _unique_list(rubric_evidence)

            delivery_score = delivery_band
        else:
            delivery_score = delivery_score if delivery_score is not None else (60.0 if transcription else 0.0)
            fluency_score = fluency_score if fluency_score is not None else delivery_score
            pronunciation_score = pronunciation_score if pronunciation_score is not None else delivery_score
            rhythm_score = rhythm_score if rhythm_score is not None else delivery_score
            language_use_score = (language_result.score * 20) if language_result else 0.0
            topic_development_score = (topic_result.score * 20) if topic_result else 0.0

            scores = [score for score in [delivery_score, language_use_score, topic_development_score] if score]
            overall_score = round(sum(scores) / len(scores), 1) if scores else 0.0

        combined_strengths = _unique_list(delivery_strengths + (language_result.strengths if language_result else []) + (topic_result.strengths if topic_result else []))
        combined_improvements = _unique_list(delivery_improvements + (language_result.improvements if language_result else []) + (topic_result.improvements if topic_result else []))
        rubric_feedback = []
        if language_result and language_result.rubric_evidence:
            rubric_feedback.extend(language_result.rubric_evidence)
        if topic_result and topic_result.rubric_evidence:
            rubric_feedback.extend(topic_result.rubric_evidence)
        specific_feedback = _unique_list(rubric_feedback or (language_result.improvements[:1] if language_result else []) + (topic_result.improvements[:1] if topic_result else []))
        task_fulfillment = topic_result.task_fulfillment if topic_result else None
        clarity_coherence = topic_result.clarity_coherence if topic_result else None
        support_sufficiency = topic_result.support_sufficiency if topic_result else None
        grammar_errors = language_result.grammar_issues if language_result else []
        vocabulary_suggestions = language_result.vocabulary_suggestions if language_result else []
        lexical_diversity = language_result.lexical_diversity if language_result else None
        academic_word_count = language_result.academic_word_count if language_result else None

    if is_new_toefl_task and isinstance(speech_metrics, dict):
        if not speech_metrics.get("rubric_evidence"):
            fallback_evidence: List[str] = []
            if combined_strengths:
                fallback_evidence.extend(combined_strengths[:2])
            if combined_improvements:
                fallback_evidence.extend(combined_improvements[:2])
            if fallback_evidence:
                speech_metrics["rubric_evidence"] = _unique_list(fallback_evidence)

    feedback = SpeakingFeedback(
        response_id=response.id,
        overall_score=overall_score,
        delivery_score=delivery_score,
        language_use_score=language_use_score,
        topic_development_score=topic_development_score,
        fluency_score=fluency_score,
        pronunciation_score=pronunciation_score,
        rhythm_score=rhythm_score,
        speech_metrics=speech_metrics,
        lexical_diversity=lexical_diversity,
        academic_word_count=academic_word_count,
        grammar_errors=grammar_errors,
        vocabulary_suggestions=vocabulary_suggestions,
        task_fulfillment=task_fulfillment,
        clarity_coherence=clarity_coherence,
        support_sufficiency=support_sufficiency,
        strengths=combined_strengths,
        areas_for_improvement=combined_improvements,
        specific_feedback=specific_feedback,
    )
    db.session.add(feedback)
    db.session.commit()

    if record_id and task.task_type in {'new_toefl_repeat', 'new_toefl_interview'}:
        record = NewToeflMockRecord.query.get(record_id)
        if record and record.user_id == user.id and record.section == 'speaking':
            answers = record.answers or {}
            responses = dict(answers.get('responses') or {})
            responses[str(task.id)] = {
                'task_id': task.id,
                'response_id': response.id,
                'audio_url': response.audio_url,
                'feedback_id': feedback.id,
                'overall_score': feedback.overall_score,
                'created_at': response.created_at.isoformat() if response.created_at else None,
            }
            record.answers = {**answers, 'responses': responses}
            flag_modified(record, 'answers')
            record.status = 'in_progress'
            db.session.commit()

    if task.task_type in {'new_toefl_repeat', 'new_toefl_interview'}:
        redirect_url = url_for('new_toefl_speaking_feedback', response_id=response.id)
    else:
        redirect_url = url_for('speaking_feedback', response_id=response.id)

    return jsonify({
        'success': True,
        'redirect': redirect_url,
    })


@app.route('/speaking/feedback/<int:response_id>')
@login_required
def speaking_feedback(response_id):
    """Display feedback for a speaking response."""
    from models import SpeakingResponse, SpeakingFeedback

    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    response = SpeakingResponse.query.get_or_404(response_id)

    # Verify ownership
    if response.user_id != user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('speaking_dashboard'))

    task = response.task
    feedback = response.feedback

    if not feedback:
        flash('Feedback not available yet', 'warning')
        return redirect(url_for('speaking_dashboard'))

    mock_back_url = None
    if task and task.task_type in {'new_toefl_repeat', 'new_toefl_interview'}:
        mock_back_url = url_for('new_toefl_speaking_practice')

    return render_template(
        'speaking/feedback.html',
        response=response,
        task=task,
        feedback=feedback,
        user=user,
        mock_back_url=mock_back_url,
    )


@app.route('/new-toefl/speaking/feedback/<int:response_id>')
@login_required
def new_toefl_speaking_feedback(response_id):
    """Display feedback for New TOEFL mock speaking responses."""
    from models import SpeakingResponse

    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    response = SpeakingResponse.query.get_or_404(response_id)
    if response.user_id != user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('new_toefl_speaking_mock'))

    task = response.task
    feedback = response.feedback
    if not feedback:
        flash('Feedback not available yet', 'warning')
        return redirect(url_for('new_toefl_speaking_mock'))

    is_repeat = task.task_type == 'new_toefl_repeat'
    metrics = feedback.speech_metrics or {}
    rubric_text = _load_new_toefl_speaking_rubrics()
    if is_repeat:
        repeat_band = metrics.get('repeat_score_5')
    else:
        repeat_band = metrics.get('overall_band_5')
        if repeat_band is None and feedback.overall_score is not None:
            repeat_band = _round_to_half(feedback.overall_score / 6)

    record = None
    try:
        records = (
            NewToeflMockRecord.query
            .filter_by(user_id=user.id, section='speaking')
            .order_by(NewToeflMockRecord.updated_at.desc())
            .limit(50)
            .all()
        )
        for item in records:
            answers = item.answers or {}
            responses = answers.get('responses') or {}
            for entry in responses.values():
                if str(entry.get('response_id')) == str(response.id):
                    record = item
                    break
            if record:
                break
        if not record:
            for item in records:
                meta = item.meta or {}
                tasks = meta.get('tasks') or []
                if any(isinstance(task_meta, dict) and task_meta.get('id') == task.id for task_meta in tasks):
                    record = item
                    break
    except Exception:
        record = None

    mock_back_url = url_for('new_toefl_speaking_mock')
    if record:
        mock_back_url = url_for('new_toefl_speaking_mock', test_id=record.test_id, record_id=record.id)

    return render_template(
        'speaking/new_toefl_feedback.html',
        response=response,
        task=task,
        feedback=feedback,
        user=user,
        is_repeat=is_repeat,
        rubric_text=rubric_text,
        repeat_band=repeat_band,
        mock_back_url=mock_back_url,
    )


# ============================================================================
# WRITING SECTION ROUTES
# ============================================================================

@app.route('/writing')
@app.route('/writing/dashboard')
@login_required
def writing_dashboard():
    """Writing section dashboard - choose between integrated and discussion tasks."""
    from models import WritingResponse, WritingFeedback

    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    # Get user's recent writing responses with feedback
    recent_responses = WritingResponse.query.filter_by(
        user_id=user.id
    ).order_by(
        WritingResponse.created_at.desc()
    ).limit(10).all()

    return render_template(
        'writing/dashboard.html',
        user=user,
        recent_responses=recent_responses
    )


@app.route('/writing/task/<task_type>/generate')
@login_required
def generate_writing_task(task_type):
    """Generate a new writing task (integrated or academic discussion)."""
    from models import WritingTask
    from services.writing_generator import generate_task_by_type

    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401

    if task_type not in ['integrated', 'discussion']:
        return jsonify({'error': 'Invalid task type'}), 400

    # Generate task using AI
    task_data = generate_task_by_type(task_type)

    if not task_data:
        return jsonify({'error': 'Failed to generate task'}), 500

    reading_text = task_data.get('reading_text')
    listening_audio_url = task_data.get('listening_audio_url')
    listening_transcript = task_data.get('listening_transcript')
    deconstruction_data = task_data.get('deconstruction_data')
    outline_data = task_data.get('outline_data')

    if task_type == 'discussion':
        reading_text = None
        listening_audio_url = None
        listening_transcript = None
        deconstruction_data = task_data.get('discussion_context')
        outline_data = task_data.get('outline_data')

    # Save to database
    task = WritingTask(
        task_type=task_type,
        topic=task_data.get('topic', ''),
        prompt=task_data.get('prompt', ''),
        reading_text=reading_text,
        listening_audio_url=listening_audio_url,
        listening_transcript=listening_transcript,
        deconstruction_data=deconstruction_data,
        outline_data=outline_data,
        word_limit=task_data.get('word_limit', 300),
        time_limit_minutes=task_data.get('time_limit_minutes', 20)
    )
    db.session.add(task)
    db.session.commit()

    return jsonify({
        'success': True,
        'task_id': task.id,
        'redirect': url_for('writing_practice', task_id=task.id)
    })


@app.route('/writing/practice/<int:task_id>')
@login_required
def writing_practice(task_id):
    """Unified practice page with 3-phase flow: deconstruction -> drafting -> feedback."""
    from models import WritingTask, WritingResponse

    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    task = WritingTask.query.get_or_404(task_id)

    # Check if user has already submitted for this task
    existing_response = WritingResponse.query.filter_by(
        user_id=user.id,
        task_id=task_id,
        parent_response_id=None  # Original submission, not revision
    ).first()

    return render_template(
        'writing/practice.html',
        task=task,
        user=user,
        existing_response=existing_response
    )


@app.route('/writing/task/<int:task_id>/submit', methods=['POST'])
@login_required
def submit_writing(task_id):
    """Submit an essay for analysis and feedback."""
    from models import WritingTask, WritingResponse, WritingFeedback
    from services.writing_analyzer import get_writing_analyzer

    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401

    task = WritingTask.query.get_or_404(task_id)

    data = request.get_json()
    essay_text = data.get('essay_text', '').strip()
    is_revision = data.get('is_revision', False)
    parent_response_id = data.get('parent_response_id')

    if not essay_text:
        return jsonify({'error': 'Essay text is required'}), 400

    word_count = len(essay_text.split())

    # Create response record
    response = WritingResponse(
        user_id=user.id,
        task_id=task_id,
        essay_text=essay_text,
        word_count=word_count,
        is_revised=is_revision,
        parent_response_id=parent_response_id,
        attempt_number=1
    )

    # If revision, increment attempt number
    if is_revision and parent_response_id:
        parent = WritingResponse.query.get(parent_response_id)
        if parent:
            response.attempt_number = parent.attempt_number + 1

    db.session.add(response)
    db.session.commit()

    # Analyze essay using AI
    current_app.logger.info(f"Analyzing essay for task_id={task_id}, task_type={task.task_type}, word_count={word_count}")
    analyzer = get_writing_analyzer()
    feedback_data = analyzer.analyze_essay(
        essay_text=essay_text,
        task_type=task.task_type,
        prompt=task.prompt,
        reading_text=task.reading_text,
        listening_transcript=task.listening_transcript,
        discussion_context=task.deconstruction_data if task.task_type == 'discussion' else None
    )
    current_app.logger.info(f"Essay analysis complete. Feedback keys: {list(feedback_data.keys())}")

    # Save feedback
    feedback = WritingFeedback(
        response_id=response.id,
        overall_score=feedback_data.get('overall_score', 0),
        content_development_score=feedback_data.get('content_development_score', 0),
        organization_structure_score=feedback_data.get('organization_structure_score', 0),
        vocabulary_language_score=feedback_data.get('vocabulary_language_score', 0),
        grammar_mechanics_score=feedback_data.get('grammar_mechanics_score', 0),
        annotations=feedback_data.get('annotations', []),
        coach_summary=feedback_data.get('coach_summary', ''),
        strengths=feedback_data.get('strengths', []),
        improvements=feedback_data.get('improvements', []),
        grammar_issues=feedback_data.get('grammar_issues', []),
        vocabulary_suggestions=feedback_data.get('vocabulary_suggestions', []),
        organization_notes=feedback_data.get('organization_notes', []),
        content_suggestions=feedback_data.get('content_suggestions', []),
        content_accuracy=feedback_data.get('content_accuracy'),
        point_coverage=feedback_data.get('point_coverage', []),
        example_accuracy=feedback_data.get('example_accuracy'),
        paraphrase_quality=feedback_data.get('paraphrase_quality'),
        source_integration=feedback_data.get('source_integration')
    )
    db.session.add(feedback)
    db.session.commit()

    return jsonify({
        'success': True,
        'response_id': response.id,
        'redirect': url_for('writing_feedback', response_id=response.id)
    })


@app.route('/writing/feedback/<int:response_id>')
@login_required
def writing_feedback(response_id):
    """Display comprehensive feedback for a writing response."""
    from models import WritingResponse, WritingFeedback

    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    response = WritingResponse.query.get_or_404(response_id)

    # Verify ownership
    if response.user_id != user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('writing_dashboard'))

    task = response.task
    feedback = response.feedback

    if not feedback:
        flash('Feedback not available yet', 'warning')
        return redirect(url_for('writing_dashboard'))

    return render_template(
        'writing/feedback.html',
        response=response,
        task=task,
        feedback=feedback,
        user=user
    )


@app.route('/writing/api/paraphrase', methods=['POST'])
@login_required
def paraphrase_text():
    """Generate paraphrases for a given sentence (real-time assistant)."""
    from services.writing_analyzer import get_writing_analyzer

    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    sentence = data.get('sentence', '').strip()
    count = data.get('count', 3)

    if not sentence:
        return jsonify({'error': 'Sentence is required'}), 400

    analyzer = get_writing_analyzer()
    paraphrases = analyzer.generate_paraphrases(sentence, count)

    return jsonify({
        'success': True,
        'paraphrases': paraphrases
    })


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/healthz')
def healthcheck():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})


# ============================================================================
# STANDALONE ESSAY GRADING ROUTES (Not TOEFL-related)
# ============================================================================

@app.route('/essay-grading')
@login_required
def essay_grading_home():
    """Home page for standalone essay grading feature."""
    return render_template('essay_grading/home.html')


@app.route('/essay-grading/upload', methods=['GET', 'POST'])
@login_required
def essay_grading_upload():
    """Upload handwritten essay for grading."""
    from models import EssaySubmission, EssayGrading
    from services.image_analyzer import get_image_analyzer
    from services.essay_grader import get_essay_grader
    import os
    from uuid import uuid4

    if request.method == 'GET':
        return render_template('essay_grading/upload.html')

    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401

    # Check for image file
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    image_file = request.files['image']
    if image_file.filename == '':
        return jsonify({'error': 'No image selected'}), 400

    # Validate file type
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}
    if not ('.' in image_file.filename and
            image_file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
        return jsonify({'error': 'Invalid file type. Allowed: PNG, JPG, PDF'}), 400

    # Get topic from form data
    topic = request.form.get('topic', '').strip()
    if not topic:
        return jsonify({'error': 'Please provide an essay topic'}), 400

    # Save image file
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'essay_grading')
    os.makedirs(upload_dir, exist_ok=True)

    filename = f"{user.id}_{uuid4().hex}.{image_file.filename.rsplit('.', 1)[1].lower()}"
    image_path = os.path.join(upload_dir, filename)
    image_file.save(image_path)

    image_url = f"/static/uploads/essay_grading/{filename}"

    # Extract text from image
    current_app.logger.info(f"Extracting text from essay image: {image_path}")
    analyzer = get_image_analyzer()
    ocr_result = analyzer.analyze_essay_image(image_path, task_type='independent', topic=topic)

    if not ocr_result['success']:
        current_app.logger.warning(f"OCR failed for {image_path}: {ocr_result.get('error')}")
        return jsonify({
            'error': 'Could not extract text from image. Please ensure the image is clear and try again.',
            'image_quality': ocr_result.get('image_quality', 'unknown'),
            'recommendations': ocr_result.get('recommendations', [])
        }), 400

    extracted_text = ocr_result['extracted_text']
    ocr_confidence = ocr_result['ocr_confidence']

    if not extracted_text or len(extracted_text.strip()) < 10:
        return jsonify({
            'error': 'Could not extract sufficient text from image. Please upload a clearer image with more visible text.',
            'image_quality': ocr_result.get('image_quality'),
            'recommendations': ocr_result.get('recommendations', [])
        }), 400

    current_app.logger.info(f"Text extracted successfully. Length: {len(extracted_text)}, Confidence: {ocr_confidence}")

    # Create submission record
    submission = EssaySubmission(
        user_id=user.id,
        topic=topic,
        image_url=image_url,
        extracted_text=extracted_text,
        ocr_confidence=ocr_confidence,
        word_count=len(extracted_text.split()),
        image_quality=ocr_result.get('image_quality'),
        legibility_score=ocr_result.get('legibility_score')
    )

    db.session.add(submission)
    db.session.commit()

    # Grade the essay
    current_app.logger.info(f"Grading essay submission {submission.id} for topic: {topic}")
    grader = get_essay_grader()
    grading_result = grader.grade_essay(extracted_text, topic)

    if grading_result.get('success'):
        grading = EssayGrading(
            submission_id=submission.id,
            corrected_text=grading_result.get('corrected_text'),
            corrections_made=grading_result.get('corrections_made'),
            topic_relevance_score=grading_result.get('topic_relevance_score'),
            topic_coverage=grading_result.get('topic_coverage'),
            missing_aspects=grading_result.get('missing_aspects'),
            grammar_score=grading_result.get('grammar_score'),
            vocabulary_score=grading_result.get('vocabulary_score'),
            organization_score=grading_result.get('organization_score'),
            overall_score=grading_result.get('overall_score'),
            grammar_issues=grading_result.get('grammar_issues'),
            vocabulary_suggestions=grading_result.get('vocabulary_suggestions'),
            organization_feedback=grading_result.get('organization_feedback'),
            content_feedback=grading_result.get('content_feedback'),
            summary=grading_result.get('summary'),
            strengths=grading_result.get('strengths'),
            improvements=grading_result.get('improvements')
        )
        db.session.add(grading)
        db.session.commit()

    return jsonify({
        'success': True,
        'submission_id': submission.id,
        'redirect': url_for('essay_grading_feedback', submission_id=submission.id)
    })


@app.route('/essay-grading/feedback/<int:submission_id>')
@login_required
def essay_grading_feedback(submission_id):
    """Display grading feedback for a submission."""
    from models import EssaySubmission, EssayGrading

    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    submission = EssaySubmission.query.get_or_404(submission_id)

    # Ensure user owns this submission
    if submission.user_id != user.id:
        return "Unauthorized", 403

    grading = submission.grading

    return render_template('essay_grading/feedback.html',
                         submission=submission,
                         grading=grading)


@app.route('/essay-grading/history')
@login_required
def essay_grading_history():
    """View history of essay submissions."""
    from models import EssaySubmission

    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    submissions = EssaySubmission.query.filter_by(user_id=user.id).order_by(EssaySubmission.created_at.desc()).all()

    return render_template('essay_grading/history.html', submissions=submissions)


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """404 error handler."""
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    """500 error handler."""
    db.session.rollback()
    return render_template('errors/500.html'), 500


# ============================================================================
# INITIALIZATION
# ============================================================================

if __name__ == '__main__':
    init_database()
    _prewarm_tts_blocking()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 1111)), debug=True)
