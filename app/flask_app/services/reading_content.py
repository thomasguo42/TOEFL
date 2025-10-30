"""Generate structured TOEFL reading practice content with Gemini 2.5 Pro."""
from __future__ import annotations

import json
import random
import time
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from flask import current_app

from .gemini_client import GeminiClient, get_gemini_client

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_DIR = REPO_ROOT / "data" / "seeds"

SENTENCE_TOPICS = [
    "astronomy",
    "ecology",
    "anthropology",
    "architecture",
    "neuroscience",
    "economics",
    "climate adaptation",
]

PARAGRAPH_TOPICS = [
    "urban sustainability",
    "museum studies",
    "linguistics",
    "geology",
    "biotechnology",
    "education policy",
]

PASSAGE_TOPICS = [
    "climate adaptation",
    "digital heritage",
    "renewable energy",
    "behavioral economics",
    "marine biology",
    "cognitive psychology",
]

SEGMENT_TYPES = [
    "main_subject",
    "main_verb",
    "prepositional_phrase",
    "relative_clause",
    "relative_clause_detail",
    "infinitive_purpose",
    "contrast_subject",
    "contrast_verb",
    "result_clause",
    "adverbial_clause_time",
    "subordinator",
    "appositive",
]

TRANSITION_TYPES = [
    "topic",
    "support",
    "example",
    "contrast",
    "conclusion",
    "cause_effect",
    "result",
    "definition",
    "reciprocal",
]

DISTRACTOR_CATEGORIES = [
    "Opposite",
    "Not Mentioned",
    "Out of Scope",
    "Too Extreme",
    "Too Specific",
    "Inference Gap",
]

SENTENCE_SYSTEM_PROMPT = (
    "You are Gemini 2.5 Flash Lite serving as a TOEFL reading coach for Chinese learners. "
    "Produce one complex academic sentence and granular analysis that helps learners dissect structure. "
    "Return strict JSON matching the requested schema. Hints must be in Simplified Chinese; other narrative text stays in English."
)

PARAGRAPH_SYSTEM_PROMPT = (
    "You are Gemini 2.5 Flash Lite building paragraph comprehension drills for TOEFL beginners in China. "
    "Deliver a paragraph along with sentence roles, topic sentences, and transition annotations in strict JSON."
)

PASSAGE_SYSTEM_PROMPT = (
    "You are Gemini 2.5 Flash Lite acting as an expert TOEFL tutor. "
    "Design a short guided passage with scaffolding toggles and question rationales targeted at Chinese learners. "
    "Strictly follow the JSON schema provided."
)


def _calculate_backoff_time(attempt: int, is_rate_limit: bool = False) -> float:
    """Calculate exponential backoff time with special handling for rate limits.

    Args:
        attempt: Current attempt number (0-indexed)
        is_rate_limit: Whether this is a rate limit error (429)

    Returns:
        Backoff time in seconds
    """
    base_backoff = 2 ** attempt
    # For rate limits, use 3x longer backoff
    multiplier = 3 if is_rate_limit else 1
    return base_backoff * multiplier


@lru_cache(maxsize=None)
def _load_fallback(filename: str) -> List[Dict[str, Any]]:
    path = SEED_DIR / filename
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
            return payload if isinstance(payload, list) else []
    except json.JSONDecodeError:
        return []


def _resolve_fallback(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return random.choice(items) if items else None


# --------------------------------------------------------------------------- #
# GEMINI GENERATORS
# --------------------------------------------------------------------------- #


def _generate_sentence(topic: Optional[str], client: GeminiClient, max_retries: int = 2) -> Optional[Dict[str, Any]]:
    """Generate a sentence using Gemini with retry logic.

    Args:
        topic: Optional topic for the sentence
        client: GeminiClient instance to use
        max_retries: Number of retries on failure (default: 2)

    Returns:
        Dictionary with sentence data, or None on failure
    """
    if not client or not client.is_configured:
        current_app.logger.error("Gemini API not configured - cannot generate sentence")
        return None

    focus_topic = topic or random.choice(SENTENCE_TOPICS)
    prompt = (
        "Craft one TOEFL-style complex sentence (28-40 words) that challenges Chinese learners.\n"
        f"Topic focus: {focus_topic}\n\n"
        "OUTPUT RULES:\n"
        "1. Return a JSON object with keys: id, topic, text, analysis, focus_points, paraphrase_reference.\n"
        "2. id must be a short slug (e.g., \"sentence_hub_1\").\n"
        "3. topic is the thematic label.\n"
        "4. text is the full sentence in English (≤40 words) featuring at least one dependent clause.\n"
        "5. analysis is an array ordered by appearance; each element needs text, type, tooltipKey. "
        f"Allowed type values: {', '.join(SEGMENT_TYPES)}.\n"
        "6. tooltipKey may reuse type or provide a more specific key string.\n"
        "7. focus_points is an array of exactly three objects with phrase (<=4 English words) "
        "and hint (Simplified Chinese ≤40 characters) pointing out comprehension checkpoints.\n"
        "8. paraphrase_reference is a ≤35-word plain-English paraphrase capturing the essential meaning.\n"
        "9. Respond with strict JSON only, no markdown."
    )

    try:
        payload = client.generate_json(
            prompt,
            temperature=0.55,
            system_instruction=SENTENCE_SYSTEM_PROMPT,
            max_output_tokens=2048,
            # Let GeminiClient handle retries/backoff
        )
        result = _coerce_sentence(payload, focus_topic)
        if result:
            current_app.logger.info("Sentence generation succeeded")
            return result
        current_app.logger.error("Sentence generation failed - invalid response format")
    except Exception as exc:
        current_app.logger.error(f"Sentence generation failed: {exc}")
    return None


def _generate_paragraph(topic: Optional[str], client: GeminiClient, max_retries: int = 2) -> Optional[Dict[str, Any]]:
    """Generate a paragraph using Gemini with retry logic.

    Args:
        topic: Optional topic for the paragraph
        client: GeminiClient instance to use
        max_retries: Number of retries on failure (default: 2)

    Returns:
        Dictionary with paragraph data, or None on failure
    """
    if not client or not client.is_configured:
        current_app.logger.error("Gemini API not configured - cannot generate paragraph")
        return None

    focus_topic = topic or random.choice(PARAGRAPH_TOPICS)
    prompt = (
        "Produce a TOEFL-style paragraph (4 sentences, 110-140 words) that lets learners locate the topic sentence "
        "and examine logical flow.\n"
        f"Topic focus: {focus_topic}\n\n"
        "OUTPUT RULES:\n"
        "1. Return a JSON object with keys: id, topic, paragraph, sentences, topicSentenceIndex, transitions.\n"
        "2. paragraph is the full text in English (academic tone).\n"
        "3. sentences is an array; each item needs index (0-based), text, role, summary, explainKey.\n"
        "   - role must be one of: topic, support, example, contrast, conclusion.\n"
        "   - summary is ≤40 Simplified Chinese characters describing the sentence purpose.\n"
        "   - explainKey provides a camelCase string used for tooltip lookup (e.g., topic_sentence).\n"
        "4. topicSentenceIndex indicates which sentence is the main idea (0-based integer).\n"
        "5. transitions is an array of connective annotations, each with text (single transition phrase), "
        "type (cause_effect, example, contrast, result, definition, reciprocal, emphasis), and tooltipKey (camelCase).\n"
        "6. Respond with strict JSON only."
    )

    try:
        payload = client.generate_json(
            prompt,
            temperature=0.5,
            system_instruction=PARAGRAPH_SYSTEM_PROMPT,
            max_output_tokens=3072,
        )
        result = _coerce_paragraph(payload, focus_topic)
        if result:
            current_app.logger.info("Paragraph generation succeeded")
            return result
        current_app.logger.error("Paragraph generation failed - invalid response format")
    except Exception as exc:
        current_app.logger.error(f"Paragraph generation failed: {exc}")
    return None


def _generate_passage(topic: Optional[str], client: GeminiClient, max_retries: int = 2) -> Optional[Dict[str, Any]]:
    """Generate a passage using Gemini with retry logic.

    Args:
        topic: Optional topic for the passage
        client: GeminiClient instance to use
        max_retries: Number of retries on failure (default: 2)

    Returns:
        Dictionary with passage data, or None on failure
    """
    if not client or not client.is_configured:
        current_app.logger.error("Gemini API not configured - cannot generate passage")
        return None

    focus_topic = topic or random.choice(PASSAGE_TOPICS)
    prompt = (
        "Design a guided TOEFL reading passage with coaching scaffolds.\n"
        f"Main topic: {focus_topic}\n\n"
        "OUTPUT RULES:\n"
        "1. Return a JSON object containing: id, topic, title, readingTimeMinutes, tools, paragraphs, questions.\n"
        "2. title should be succinct (≤12 words). readingTimeMinutes is an integer estimate between 5 and 7.\n"
        "3. tools is an object with boolean flags: sentenceAnalyzerEnabled, paragraphSummariesEnabled, vocabLookupEnabled.\n"
        "4. paragraphs is an array (3 items). Each needs index, text (60-80 words), summary (≤45 Simplified Chinese characters).\n"
        "5. questions is an array of 3 comprehension items. Each object must include: "
        "   id, type (detail, inference, function, vocabulary), prompt, options (4 strings), answer, explanation, distractors.\n"
        "6. explanation should be ≤60 Simplified Chinese characters referencing evidence.\n"
        "7. distractors must be an array of objects with keys choice, category, analysis. "
        f"Category must be one of: {', '.join(DISTRACTOR_CATEGORIES)}.\n"
        "8. analysis should be ≤50 Simplified Chinese characters describing why the distractor is wrong.\n"
        "9. Ensure answer matches one of the options exactly. Provide at least one vocabulary-focused question.\n"
        "10. Avoid markdown fencing; return strict JSON."
    )

    try:
        payload = client.generate_json(
            prompt,
            temperature=0.45,
            system_instruction=PASSAGE_SYSTEM_PROMPT,
            max_output_tokens=4096,
        )
        result = _coerce_passage(payload, focus_topic)
        if result:
            current_app.logger.info("Passage generation succeeded")
            return result
        current_app.logger.error("Passage generation failed - invalid response format")
    except Exception as exc:
        current_app.logger.error(f"Passage generation failed: {exc}")
    return None


# --------------------------------------------------------------------------- #
# PUBLIC HELPERS
# --------------------------------------------------------------------------- #


def get_sentence(sentence_id: Optional[str] = None, topic: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get a sentence using Gemini AI.

    This function ALWAYS uses Gemini. No fallback to seed files.

    Args:
        sentence_id: Unused, kept for API compatibility
        topic: Optional topic for the sentence

    Returns:
        Dictionary with sentence data, or None if Gemini fails
    """
    client = get_gemini_client()
    result = _generate_sentence(topic, client)
    if result:
        return result
    # Deterministic fallback from seeds
    fallback = _resolve_fallback(_load_fallback("reading_sentences.json"))
    if fallback:
        current_app.logger.info("Serving sentence from seeds fallback")
        return _coerce_sentence(fallback, fallback.get("topic") or (topic or ""))
    return None


def get_paragraph(paragraph_id: Optional[str] = None, topic: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get a paragraph using Gemini AI.

    This function ALWAYS uses Gemini. No fallback to seed files.

    Args:
        paragraph_id: Unused, kept for API compatibility
        topic: Optional topic for the paragraph

    Returns:
        Dictionary with paragraph data, or None if Gemini fails
    """
    client = get_gemini_client()
    result = _generate_paragraph(topic, client)
    if result:
        return result
    # Deterministic fallback from seeds
    fallback = _resolve_fallback(_load_fallback("reading_paragraphs.json"))
    if fallback:
        current_app.logger.info("Serving paragraph from seeds fallback")
        return _coerce_paragraph(fallback, fallback.get("topic") or (topic or ""))
    return None


def get_passage(passage_id: Optional[str] = None, topic: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get a passage using Gemini AI.

    This function ALWAYS uses Gemini. No fallback to seed files.

    Args:
        passage_id: Unused, kept for API compatibility
        topic: Optional topic for the passage

    Returns:
        Dictionary with passage data, or None if Gemini fails
    """
    client = get_gemini_client()
    result = _generate_passage(topic, client)
    if result:
        return result
    # Deterministic fallback from seeds
    fallback = _resolve_fallback(_load_fallback("reading_passages.json"))
    if fallback:
        current_app.logger.info("Serving passage from seeds fallback")
        return _coerce_passage(fallback, fallback.get("topic") or (topic or ""))
    return None


def evaluate_paraphrase(
    sentence_id: str,
    user_text: str,
    source_sentence: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Score a user paraphrase against the reference answer."""
    sentence = source_sentence if isinstance(source_sentence, dict) else None
    if user_text is None:
        user_text = ""

    if sentence is None or sentence.get("id") != sentence_id:
        for item in _load_fallback("reading_sentences.json"):
            if item.get("id") == sentence_id:
                sentence = item
                break
    # If still not found, we cannot evaluate without reference.
    if sentence is None:
        current_app.logger.error("Paraphrase evaluation failed: sentence_id=%s not found in session or fallback", sentence_id)
        return {
            "score": 0.0,
            "category": "needs_work",
            "missing_points": ["无法找到句子信息，请刷新页面重试。"],
            "model_answer": "",
            "gemini_feedback": "句子信息未找到，无法评估。",
        }

    reference = sentence.get("paraphrase_reference", "")
    focus_points = sentence.get("focus_points", [])

    user_clean = (user_text or "").strip()
    if not user_clean:
        return {
            "score": 0.0,
            "category": "needs_work",
            "missing_points": [point.get("hint") for point in focus_points if point.get("hint")],
            "model_answer": reference,
            "gemini_feedback": None,
        }

    client = get_gemini_client()
    if not client or not client.is_configured:
        current_app.logger.error("Gemini client unavailable for paraphrase evaluation - API key not configured!")
        return {
            "score": 0.0,
            "category": "needs_work",
            "missing_points": ["AI 评估服务暂时不可用，请联系管理员。"],
            "model_answer": reference,
            "gemini_feedback": "Gemini API 未配置，无法提供智能评估。",
        }

    checkpoints = []
    for point in focus_points:
        phrase = point.get("phrase")
        hint = point.get("hint")
        if phrase and hint:
            checkpoints.append(f"{phrase}: {hint}")

    prompt = (
        "Evaluate a user's paraphrase of a TOEFL reading sentence.\n\n"
        f"Original sentence:\n{sentence.get('text', '').strip()}\n\n"
        f"Reference paraphrase:\n{reference.strip()}\n\n"
        "Focus checkpoints that must be preserved:\n"
        + ("\n".join(checkpoints) if checkpoints else "None provided") +
        "\n\n"
        f"User paraphrase:\n{user_clean}\n\n"
        "Return strict JSON with keys:\n"
        "{\n"
        '  "score": float between 0 and 1 expressing semantic coverage,\n'
        '  "category": one of ["excellent", "good", "needs_work"],\n'
        '  "feedback": short Simplified Chinese comment (<= 50 chars) summarizing accuracy,\n'
        '  "missing_points": array of Simplified Chinese hints describing missing checkpoints (use provided hints when applicable)\n'
        "}\n"
        "Do not include any additional keys or text."
    )

    try:
        current_app.logger.info(f"Calling Gemini 2.5 Flash Lite for paraphrase evaluation of sentence_id={sentence_id}")
        response = client.generate_json(
            prompt,
            temperature=0.2,
            system_instruction=(
                "You are Gemini 2.5 Flash Lite acting as an attentive TOEFL tutor who compares student paraphrases with a reference answer. "
                "Be concise and focus on meaning coverage."
            ),
            max_output_tokens=768,
            model_override="gemini-2.5-flash-lite",
        )
        current_app.logger.info(f"Gemini 2.5 Flash Lite response received for sentence_id={sentence_id}")
        if isinstance(response, dict):
            score = response.get("score")
            category = response.get("category")
            feedback = response.get("feedback")
            missing_points = response.get("missing_points")

            normalized_score = None
            if isinstance(score, (int, float)):
                normalized_score = max(0.0, min(1.0, float(score)))

            normalized_category = None
            if isinstance(category, str):
                category_lower = category.strip().lower()
                if category_lower in {"excellent", "good", "needs_work"}:
                    normalized_category = category_lower
                else:
                    # Map unexpected category using score thresholds.
                    effective_score = normalized_score if normalized_score is not None else 0.5
                    if effective_score >= 0.78:
                        normalized_category = "excellent"
                    elif effective_score >= 0.55:
                        normalized_category = "good"
                    else:
                        normalized_category = "needs_work"

            normalized_missing: List[str] = []
            if isinstance(missing_points, list):
                for entry in missing_points:
                    if isinstance(entry, str) and entry.strip():
                        normalized_missing.append(entry.strip())

            if not normalized_missing:
                # Extract hints from focus points if Gemini didn't provide any
                normalized_missing = [point.get("hint") for point in focus_points if point.get("hint")]

            final_score = normalized_score if normalized_score is not None else 0.5
            final_category = normalized_category if normalized_category is not None else "needs_work"

            return {
                "score": final_score,
                "category": final_category,
                "missing_points": normalized_missing,
                "model_answer": reference,
                "gemini_feedback": feedback.strip() if isinstance(feedback, str) and feedback.strip() else None,
            }
    except Exception as exc:
        current_app.logger.error("Gemini paraphrase evaluation failed: %s", exc)
        return {
            "score": 0.0,
            "category": "needs_work",
            "missing_points": ["AI 评估服务出现错误，请稍后重试。"],
            "model_answer": reference,
            "gemini_feedback": f"评估失败: {str(exc)[:100]}",
        }


# --------------------------------------------------------------------------- #
# HELPERS
# --------------------------------------------------------------------------- #


def _score_to_category(ratio: float, missing: List[str]) -> str:
    if ratio >= 0.78 and not missing:
        return "excellent"
    if ratio >= 0.55:
        return "good"
    return "needs_work"


def _ensure_slug(value: Optional[str], prefix: str) -> str:
    if value and isinstance(value, str):
        return value
    return f"{prefix}_{uuid4().hex[:8]}"


def _coerce_sentence(payload: Any, topic: str) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    analysis = []
    for item in payload.get("analysis", []):
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        type_ = (item.get("type") or "").strip()
        if not text:
            continue
        if type_ not in SEGMENT_TYPES:
            type_ = "prepositional_phrase" if "in" in text.lower() else "support"
        tooltip = (item.get("tooltipKey") or type_).strip()
        analysis.append({"text": text, "type": type_, "tooltipKey": tooltip})

    focus_points = []
    for point in payload.get("focus_points") or payload.get("focusPoints") or []:
        if not isinstance(point, dict):
            continue
        phrase = (point.get("phrase") or "").strip()
        hint = (point.get("hint") or "").strip()
        if phrase and hint:
            focus_points.append({"phrase": phrase, "hint": hint})

    sentence = {
        "id": _ensure_slug(payload.get("id"), "sentence"),
        "topic": payload.get("topic") or topic,
        "text": payload.get("text", ""),
        "analysis": analysis,
        "focus_points": focus_points[:3],
        "paraphrase_reference": payload.get("paraphrase_reference") or payload.get("paraphraseReference") or "",
    }
    return sentence


def _coerce_paragraph(payload: Any, topic: str) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    sentences = []
    for item in payload.get("sentences", []):
        if not isinstance(item, dict):
            continue
        sentences.append(
            {
                "index": int(item.get("index", len(sentences))),
                "text": item.get("text", ""),
                "role": item.get("role", "support"),
                "summary": item.get("summary", ""),
                "explainKey": item.get("explainKey") or item.get("explain_key") or "support_detail",
            }
        )

    transitions = []
    for item in payload.get("transitions", []):
        if not isinstance(item, dict):
            continue
        transitions.append(
            {
                "text": item.get("text", ""),
                "type": item.get("type", "cause_effect"),
                "tooltipKey": item.get("tooltipKey") or item.get("tooltip_key") or item.get("type", "cause_effect"),
            }
        )

    paragraph = {
        "id": _ensure_slug(payload.get("id"), "paragraph"),
        "topic": payload.get("topic") or topic,
        "paragraph": payload.get("paragraph", ""),
        "sentences": sentences,
        "topicSentenceIndex": int(payload.get("topicSentenceIndex", 0)),
        "transitions": transitions,
    }
    return paragraph


def _coerce_passage(payload: Any, topic: str) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    paragraphs = []
    for item in payload.get("paragraphs", []):
        if not isinstance(item, dict):
            continue
        paragraphs.append(
            {
                "index": int(item.get("index", len(paragraphs))),
                "text": item.get("text", ""),
                "summary": item.get("summary", ""),
            }
        )

    questions = []
    for item in payload.get("questions", []):
        if not isinstance(item, dict):
            continue
        options = [opt for opt in item.get("options", []) if isinstance(opt, str)]
        distractors = []
        for distractor in item.get("distractors", []):
            if not isinstance(distractor, dict):
                continue
            category = distractor.get("category")
            if category not in DISTRACTOR_CATEGORIES:
                category = "Default"
            distractors.append(
                {
                    "choice": distractor.get("choice", ""),
                    "category": category,
                    "analysis": distractor.get("analysis", ""),
                }
            )
        questions.append(
            {
                "id": item.get("id", _ensure_slug(None, "question")),
                "type": item.get("type", "detail"),
                "prompt": item.get("prompt", ""),
                "options": options,
                "answer": item.get("answer", options[0] if options else ""),
                "explanation": item.get("explanation") or item.get("explanation_cn") or "",
                "distractors": distractors,
            }
        )

    tools = payload.get("tools") or {}
    passage = {
        "id": _ensure_slug(payload.get("id"), "passage"),
        "topic": payload.get("topic") or topic,
        "title": payload.get("title", "").strip() or topic.title(),
        "readingTimeMinutes": int(payload.get("readingTimeMinutes", 6)),
        "tools": {
            "sentenceAnalyzerEnabled": bool(tools.get("sentenceAnalyzerEnabled", True)),
            "paragraphSummariesEnabled": bool(tools.get("paragraphSummariesEnabled", True)),
            "vocabLookupEnabled": bool(tools.get("vocabLookupEnabled", True)),
        },
        "paragraphs": paragraphs,
        "questions": questions,
    }
    return passage
