"""DeepSeek-powered content generation for the New TOEFL mock exams."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from flask import current_app

from .gemini_client import GeminiClient, get_gemini_client
from .full_length_tests import get_speaking_section, list_full_length_tests
from .tts_service import TTSService

READING_CLOZE_TOPICS = [
    "behavioral economics",
    "environmental science",
    "urban planning",
    "cognitive psychology",
    "marine biology",
    "public health",
    "archaeology",
    "renewable energy",
]

READING_DAILY_TOPICS = [
    "campus services",
    "student housing",
    "library resources",
    "club activities",
    "class registration",
    "career center",
    "health center",
    "volunteer program",
]

READING_ACADEMIC_TOPICS = [
    "climate adaptation",
    "renewable energy",
    "marine biology",
    "cognitive psychology",
    "behavioral economics",
    "digital heritage",
    "public health",
    "urban planning",
]

LISTENING_CONVERSATION_TOPICS = [
    "office hours",
    "research assistantship",
    "lab schedule",
    "course project",
    "registration issue",
    "library fine dispute",
]

LISTENING_TALK_TOPICS = [
    "astronomy",
    "geology",
    "ecology",
    "art history",
    "psychology",
    "economics",
    "anthropology",
    "public health",
]

READING_SYSTEM_PROMPT = (
    "You are DeepSeek creating New TOEFL reading mock questions. "
    "Return strict JSON matching the requested schema. Avoid markdown or extra text. "
    "All multiple-choice items MUST be unambiguous: exactly ONE option is correct, and every distractor must be clearly wrong."
)

LISTENING_SYSTEM_PROMPT = (
    "You are DeepSeek creating New TOEFL listening mock questions. "
    "Return strict JSON matching the requested schema. Avoid markdown or extra text. "
    "All multiple-choice items MUST be unambiguous: exactly ONE option is correct, and every distractor must be clearly wrong. "
    "Before responding, mentally verify that the 3 wrong options are clearly wrong."
)

SPEAKING_SYSTEM_PROMPT = (
    "You are DeepSeek creating New TOEFL speaking mock prompts. "
    "Return strict JSON matching the requested schema. Avoid markdown or extra text."
)

WRITING_SYSTEM_PROMPT = (
    "You are DeepSeek creating New TOEFL writing mock tasks. "
    "Return strict JSON matching the requested schema. Avoid markdown or extra text."
)

INTERVIEW_SETS_PATH = Path(__file__).resolve().parents[3] / "data" / "seeds" / "new_toefl_interview_sets.json"


def _audio_cache_key(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "").strip()).lower()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def _safe_text(value: Any) -> str:
    return str(value or "").strip()

_WORD_RE = re.compile(r"\b[A-Za-z]{6,14}\b")
_STOPWORDS = {
    "about",
    "above",
    "after",
    "again",
    "below",
    "because",
    "between",
    "before",
    "during",
    "every",
    "first",
    "found",
    "however",
    "might",
    "never",
    "other",
    "their",
    "there",
    "these",
    "therefore",
    "through",
    "together",
    "under",
    "where",
    "which",
    "while",
    "without",
    "would",
}


def _build_cloze_from_paragraph(paragraph: str, blank_count: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Deterministically build a strict cloze task from a paragraph.

    Rules enforced here (no reliance on LLM correctness):
    - Choose 5–6 words (or `blank_count` if provided)
    - Replace each chosen word with a partial blank like `poll___`
    - Keep at least 1/3 of the characters (minimum 2), and remove >= 1 character
    - Ensure each `token` appears in the final paragraph
    """
    text = _safe_text(paragraph)
    if not text:
        return None

    # Collect candidate word occurrences with positions so we can replace safely.
    occurrences: List[Dict[str, Any]] = []
    for match in _WORD_RE.finditer(text):
        word = match.group(0)
        if not word:
            continue
        # Avoid proper nouns (capitalized). Keeps things simpler and matches "not proper nouns" intent.
        if word[0].isupper():
            continue
        if word.lower() in _STOPWORDS:
            continue
        occurrences.append({"word": word, "start": match.start(), "end": match.end()})

    if not occurrences:
        return None

    # Prefer unique words.
    seen = set()
    unique: List[Dict[str, Any]] = []
    for occ in occurrences:
        key = str(occ["word"]).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(occ)

    target_count = blank_count if isinstance(blank_count, int) else random.randint(5, 6)
    if len(unique) < target_count:
        # If we can't get enough unique words, fall back to occurrences (may include repeats).
        pool = occurrences
    else:
        pool = unique

    if len(pool) < target_count:
        return None

    chosen = random.sample(pool, k=target_count)

    blanks: List[Dict[str, Any]] = []
    paragraph_out = text
    for entry in chosen:
        answer = str(entry["word"])
        keep_len = max(2, int(math.ceil(len(answer) / 3.0)))
        if keep_len >= len(answer):
            keep_len = max(1, len(answer) - 1)
        missing = len(answer) - keep_len
        if missing <= 0:
            continue
        token = f"{answer[:keep_len]}{'_' * missing}"

        # Replace only the first exact word boundary occurrence.
        pattern = rf"\b{re.escape(answer)}\b"
        new_text, replaced = re.subn(pattern, token, paragraph_out, count=1)
        if replaced != 1:
            continue
        paragraph_out = new_text

        blanks.append(
            {
                "token": token,
                "answer": answer,
                "part_of_speech": "unknown",
                "hint": "Complete the word using context.",
            }
        )

    if len(blanks) != target_count:
        return None
    if not all(blank["token"] in paragraph_out for blank in blanks):
        return None

    return {
        "id": f"cloze_{uuid4().hex[:8]}",
        "paragraph": paragraph_out,
        "blanks": blanks,
    }


# ---------------------------------------------------------------------------
# READING MOCK
# ---------------------------------------------------------------------------


def _generate_cloze_paragraph(
    client: GeminiClient,
    blank_count: int = 5,
    topic: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not client or not client.is_configured:
        return None

    focus_topic = topic or "academic life"
    prompt = (
        "Create ONE New TOEFL reading cloze paragraph for \"Complete the Words\".\n"
        f"Topic: {focus_topic}\n\n"
        "OUTPUT RULES:\n"
        "1. Return a JSON object with keys: id, paragraph.\n"
        "2. paragraph must be 90-120 words, academic tone, cohesive.\n"
        "3. Do NOT include blanks. The system will create blanks deterministically.\n"
        "4. Return strict JSON only."
    )

    payload = client.generate_json(
        prompt,
        temperature=0.35,
        system_instruction=READING_SYSTEM_PROMPT,
        max_output_tokens=1400,
    )
    if not isinstance(payload, dict):
        return None

    paragraph = _safe_text(payload.get("paragraph"))
    if not paragraph:
        return None

    # Choose 5–6 blanks; keep strict behavior for callers that still pass blank_count.
    target = blank_count if isinstance(blank_count, int) else None
    # If blank_count was explicitly provided as 5, still allow 5–6 by default here.
    if target == 5:
        target = None
    built = _build_cloze_from_paragraph(paragraph, blank_count=target)
    if not built:
        return None
    built["id"] = payload.get("id") or built["id"]
    return built


def _generate_daily_life_set(client: GeminiClient, topic: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not client or not client.is_configured:
        return None

    focus_topic = topic or random.choice(READING_DAILY_TOPICS)
    prompt = (
        "Create ONE New TOEFL reading task using daily-life materials (email/notice/announcement).\n\n"
        f"Topic focus: {focus_topic}\n\n"
        "QUESTION STYLE RULES:\n"
        "- Focus on reading strategies: main idea, purpose, inference, vocabulary-in-context, or NOT/EXCEPT.\n"
        "- Avoid price/location/time-detail questions (no schedules, fees, addresses, dates as the focus).\n"
        "- At least one question must be about purpose or main idea.\n\n"
        "OUTPUT RULES:\n"
        "1. Return a JSON object with keys: id, source_text, source_type, questions.\n"
        "2. source_text is 90-130 words. source_type is one of: email, notice, memo, advertisement.\n"
        "3. questions is an array with exactly 2 objects.\n"
        "4. Each question has: question, options (array of 4), answer, rationales, evidence_quote.\n"
        "5. answer must exactly match one option.\n"
        "6. rationales is an object mapping each option to a concise English explanation (<= 18 words).\n"
        "7. evidence_quote MUST be an exact short quote (<= 120 chars) copied verbatim from source_text that supports the correct answer.\n"
        "8. UNAMBIGUITY: Only ONE option may be correct for each question. Make distractors plausible but decisively wrong.\n"
        "   - Avoid near-duplicates (synonyms that both fit).\n"
        "   - Avoid two general statements that both match the text.\n"
        "   - Before returning, mentally verify the 3 wrong options are wrong.\n"
        "9. Keep language clear and realistic for real-life reading.\n"
        "10. Return strict JSON only."
    )

    for _ in range(3):
        payload = client.generate_json(
            prompt,
            temperature=0.35,
            system_instruction=READING_SYSTEM_PROMPT,
            max_output_tokens=1600,
        )
        if not isinstance(payload, dict):
            continue

        source_text = _safe_text(payload.get("source_text"))
        questions = payload.get("questions")
        if not source_text or not isinstance(questions, list) or len(questions) != 2:
            continue

        return {
            "id": payload.get("id") or f"daily_{uuid4().hex[:8]}",
            "source_text": source_text,
            "source_type": payload.get("source_type", "email"),
            "questions": questions,
        }

    return None


def _generate_academic_passage_set(client: GeminiClient, topic: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not client or not client.is_configured:
        return None

    focus_topic = topic or random.choice(READING_ACADEMIC_TOPICS)
    prompt = (
        "Create ONE New TOEFL academic reading passage with multiple-choice questions.\n\n"
        f"Topic focus: {focus_topic}\n\n"
        "QUESTION STYLE RULES:\n"
        "- Use TOEFL-style questions: vocabulary-in-context, rhetorical purpose (\"Why does the author mention...\"),\n"
        "  inference, main idea/theme, or NOT/EXCEPT.\n"
        "- Avoid price/location/time-detail questions.\n"
        "- Include at least one vocabulary-in-context question and one purpose/inference question.\n\n"
        "OUTPUT RULES:\n"
        "1. Return a JSON object with keys: id, passage, questions.\n"
        "2. passage is 190-230 words, academic tone, cohesive.\n"
        "3. questions is an array with exactly 4 objects.\n"
        "4. Each question has: question, options (array of 4), answer, rationales, evidence_quote.\n"
        "5. answer must exactly match one option.\n"
        "6. rationales is an object mapping each option to a concise English explanation (<= 20 words).\n"
        "7. evidence_quote MUST be an exact short quote (<= 120 chars) copied verbatim from passage that supports the correct answer.\n"
        "8. UNAMBIGUITY: Only ONE option may be correct per question. Distractors must be clearly wrong given the passage.\n"
        "   - Avoid two options that are both supported by the passage.\n"
        "   - If two could be correct, rewrite distractors until only one remains.\n"
        "9. Return strict JSON only."
    )

    for _ in range(3):
        payload = client.generate_json(
            prompt,
            temperature=0.35,
            system_instruction=READING_SYSTEM_PROMPT,
            max_output_tokens=2200,
        )
        if not isinstance(payload, dict):
            continue

        passage = _safe_text(payload.get("passage"))
        questions = payload.get("questions")
        if not passage or not isinstance(questions, list) or len(questions) != 4:
            continue

        return {
            "id": payload.get("id") or f"academic_{uuid4().hex[:8]}",
            "passage": passage,
            "questions": questions,
        }

    return None


def generate_reading_mock(client: Optional[GeminiClient] = None) -> Optional[Dict[str, Any]]:
    client = client or get_gemini_client()
    if not client or not client.is_configured:
        return None

    cloze_tasks: List[Dict[str, Any]] = []
    daily_life_tasks: List[Dict[str, Any]] = []
    cloze_topics = random.sample(READING_CLOZE_TOPICS, k=min(2, len(READING_CLOZE_TOPICS)))
    while len(cloze_topics) < 2:
        cloze_topics.append("academic life")

    for topic in cloze_topics:
        item = _generate_cloze_paragraph(client, topic=topic)
        if item:
            cloze_tasks.append(item)

    daily_topics = random.sample(READING_DAILY_TOPICS, k=min(2, len(READING_DAILY_TOPICS)))
    while len(daily_topics) < 2:
        daily_topics.append(random.choice(READING_DAILY_TOPICS))

    for topic in daily_topics:
        item = _generate_daily_life_set(client, topic=topic)
        if item:
            daily_life_tasks.append(item)

    academic_topic = random.choice([t for t in READING_ACADEMIC_TOPICS if t not in set(cloze_topics + daily_topics)] or READING_ACADEMIC_TOPICS)
    academic = _generate_academic_passage_set(client, topic=academic_topic)

    # Ensure we have cloze tasks even if paragraph generation fails, by building from other text.
    if len(cloze_tasks) < 2:
        sources: List[str] = []
        if academic and isinstance(academic, dict) and academic.get("passage"):
            sources.append(str(academic.get("passage")))
        for daily in daily_life_tasks:
            if isinstance(daily, dict) and daily.get("source_text"):
                sources.append(str(daily.get("source_text")))

        for source in sources:
            if len(cloze_tasks) >= 2:
                break
            fallback = _build_cloze_from_paragraph(source)
            if fallback:
                cloze_tasks.append(fallback)

    if not cloze_tasks and not daily_life_tasks and not academic:
        return None

    return {
        "cloze": cloze_tasks,
        "daily_life": daily_life_tasks,
        "academic": academic,
    }


# ---------------------------------------------------------------------------
# LISTENING MOCK
# ---------------------------------------------------------------------------


def _generate_listen_response_items(client: GeminiClient, count: int = 6) -> Optional[List[Dict[str, Any]]]:
    if not client or not client.is_configured:
        return None

    scenarios = [
        "campus dining",
        "library help desk",
        "classroom clarification",
        "student housing",
        "career center",
        "health center",
        "club meeting",
        "group project",
    ]
    scenario_assignments = random.sample(scenarios, k=min(count, len(scenarios)))
    while len(scenario_assignments) < count:
        scenario_assignments.append(random.choice(scenarios))
    scenarios_block = "\n".join([f"{idx + 1}. {name}" for idx, name in enumerate(scenario_assignments)])

    prompt = (
        "Create New TOEFL listen-and-choose-response items.\n\n"
        "DIVERSITY RULES:\n"
        "- Each item must use a DIFFERENT scenario from the list below (in order).\n"
        "Scenario assignments (item order matters):\n"
        f"{scenarios_block}\n\n"
        "OUTPUT RULES:\n"
        "1. Return JSON with key: items (array).\n"
        f"2. items must contain exactly {count} objects.\n"
        "3. Each item has: prompt, options (array of 4), answer, rationales.\n"
        "4. prompt is a short sentence or question suitable for spoken audio (8-12 words).\n"
        "5. answer must exactly match one option.\n"
        "6. rationales maps each option to a concise English reason (<= 14 words).\n"
        "7. UNAMBIGUITY: Exactly ONE option must be the only pragmatically appropriate response.\n"
        "   - Make wrong options clearly mismatched in intent (wrong question type, contradictory, irrelevant, wrong tone).\n"
        "   - Do NOT include two polite variants that would both be acceptable.\n"
        "   - Before returning, check that ONLY the answer option is acceptable.\n"
        "8. Avoid cultural references; keep campus or everyday situations.\n"
        "9. Return strict JSON only."
    )

    for _ in range(3):
        payload = client.generate_json(
            prompt,
            temperature=0.35,
            system_instruction=LISTENING_SYSTEM_PROMPT,
            max_output_tokens=1500,
        )
        if not isinstance(payload, dict):
            continue

        items = payload.get("items")
        if not isinstance(items, list) or len(items) != count:
            continue

        return items
    return None


def _generate_conversation_set(client: GeminiClient) -> Optional[Dict[str, Any]]:
    if not client or not client.is_configured:
        return None

    focus_topic = random.choice(LISTENING_CONVERSATION_TOPICS)
    prompt = (
        "Create ONE New TOEFL conversation listening task.\n\n"
        f"Topic focus: {focus_topic}\n\n"
        "OUTPUT RULES:\n"
        "1. Return JSON with keys: id, segments, questions.\n"
        "2. segments is an array of 8-10 objects with speaker and text. Speakers: Woman, Man.\n"
        "3. The conversation should be 120-150 words total, natural campus setting.\n"
        "4. questions is an array of exactly 3 objects.\n"
        "5. Each question has: question, options (array of 4), answer, rationales.\n"
        "6. rationales maps each option to concise English reasons (<= 18 words).\n"
        "7. UNAMBIGUITY: Only ONE option may be correct for each question. Distractors must be clearly wrong.\n"
        "   - Ensure each wrong option contradicts or is unsupported by the conversation.\n"
        "8. Return strict JSON only."
    )

    for _ in range(3):
        payload = client.generate_json(
            prompt,
            temperature=0.35,
            system_instruction=LISTENING_SYSTEM_PROMPT,
            max_output_tokens=2000,
        )
        if not isinstance(payload, dict):
            continue

        segments = payload.get("segments")
        questions = payload.get("questions")
        if not isinstance(segments, list) or not isinstance(questions, list) or len(questions) != 3:
            continue

        return {
            "id": payload.get("id") or f"conv_{uuid4().hex[:8]}",
            "segments": segments,
            "questions": questions,
        }
    return None


def _generate_talk_set(client: GeminiClient) -> Optional[Dict[str, Any]]:
    if not client or not client.is_configured:
        return None

    focus_topic = random.choice(LISTENING_TALK_TOPICS)
    prompt = (
        "Create ONE New TOEFL academic talk listening task.\n\n"
        f"Topic focus: {focus_topic}\n\n"
        "OUTPUT RULES:\n"
        "1. Return JSON with keys: id, talk, questions.\n"
        "2. talk is 180-220 words, academic mini-lecture.\n"
        "3. questions is an array of exactly 3 objects.\n"
        "4. Each question has: question, options (array of 4), answer, rationales.\n"
        "5. rationales maps each option to concise English reasons (<= 18 words).\n"
        "6. UNAMBIGUITY: Only ONE option may be correct for each question. Distractors must be clearly wrong.\n"
        "   - Ensure each wrong option contradicts or is unsupported by the talk.\n"
        "7. Return strict JSON only."
    )

    for _ in range(3):
        payload = client.generate_json(
            prompt,
            temperature=0.35,
            system_instruction=LISTENING_SYSTEM_PROMPT,
            max_output_tokens=2000,
        )
        if not isinstance(payload, dict):
            continue

        talk = _safe_text(payload.get("talk"))
        questions = payload.get("questions")
        if not talk or not isinstance(questions, list) or len(questions) != 3:
            continue

        return {
            "id": payload.get("id") or f"talk_{uuid4().hex[:8]}",
            "talk": talk,
            "questions": questions,
        }
    return None


def generate_listening_mock(
    client: Optional[GeminiClient] = None,
    tts: Optional[TTSService] = None,
) -> Optional[Dict[str, Any]]:
    client = client or get_gemini_client()
    if not client or not client.is_configured:
        return None

    tts = tts or TTSService()

    current_app.logger.info("New TOEFL listening mock: generating response items...")
    response_items = _generate_listen_response_items(client) or []
    current_app.logger.info("New TOEFL listening mock: response items=%s", len(response_items))
    for item in response_items:
        prompt_text = _safe_text(item.get("prompt"))
        if not prompt_text:
            continue
        audio = tts.generate_audio_cached(
            prompt_text,
            filename_prefix="new_toefl_response",
            cache_key=_audio_cache_key(prompt_text),
        )
        if audio:
            item["audio_url"] = f"/static/{audio.audio_path}"

    current_app.logger.info("New TOEFL listening mock: generating conversation...")
    conversation = _generate_conversation_set(client)
    if conversation:
        segments = conversation.get("segments", [])
        segment_text = " ".join([f"{s.get('speaker', '')}:{s.get('text', '')}" for s in segments]).strip()
        audio = tts.generate_multi_speaker_audio_cached(
            segments,
            filename_prefix="new_toefl_conversation",
            cache_key=_audio_cache_key(segment_text),
        )
        if audio:
            conversation["audio_url"] = f"/static/{audio.audio_path}"

    current_app.logger.info("New TOEFL listening mock: generating talk...")
    talk = _generate_talk_set(client)
    if talk:
        talk_text = talk.get("talk", "")
        audio = tts.generate_audio_cached(
            talk_text,
            filename_prefix="new_toefl_talk",
            cache_key=_audio_cache_key(talk_text),
        )
        if audio:
            talk["audio_url"] = f"/static/{audio.audio_path}"

    if not response_items and not conversation and not talk:
        current_app.logger.warning("New TOEFL listening mock: nothing generated")
        return None

    return {
        "responses": response_items,
        "conversation": conversation,
        "talk": talk,
    }


# ---------------------------------------------------------------------------
# SPEAKING MOCK
# ---------------------------------------------------------------------------


def _load_interview_sets() -> List[Dict[str, Any]]:
    parsed_sets: List[Dict[str, Any]] = []
    tests = list_full_length_tests()
    for test in tests:
        test_id = test.get("id")
        if not test_id:
            continue
        speaking = get_speaking_section(test_id)
        if not speaking:
            continue
        repeat_items = speaking.get("repeat_items") or []
        interview_items = speaking.get("items") or []
        if not repeat_items and not interview_items:
            continue
        parsed_sets.append({
            "id": test_id,
            "title": test.get("title") or test_id,
            "repeat_items": repeat_items,
            "items": interview_items,
        })

    if parsed_sets:
        return parsed_sets

    sets: List[Dict[str, Any]] = []
    if not INTERVIEW_SETS_PATH.exists():
        current_app.logger.warning("Interview sets file not found: %s", INTERVIEW_SETS_PATH)
    else:
        try:
            payload = json.loads(INTERVIEW_SETS_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            current_app.logger.warning("Failed to parse interview sets: %s", exc)
            payload = {}

        raw_sets = payload.get("sets") if isinstance(payload, dict) else None
        if isinstance(raw_sets, list):
            sets = raw_sets

    cleaned: List[Dict[str, Any]] = []
    for entry in sets:
        if not isinstance(entry, dict):
            continue
        items = entry.get("items")
        repeat_items = entry.get("repeat_items") or []
        if not isinstance(items, list) or not items:
            continue
        cleaned_repeat = []
        if isinstance(repeat_items, list):
            for item in repeat_items:
                if not isinstance(item, dict):
                    continue
                prompt = _safe_text(item.get("prompt"))
                if not prompt:
                    continue
                cleaned_repeat.append({
                    "prompt": prompt,
                    "response_time_seconds": item.get("response_time_seconds", 10),
                })
        cleaned_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            prompt = _safe_text(item.get("prompt"))
            if not prompt:
                continue
            cleaned_items.append({
                "prompt": prompt,
                "response_time_seconds": item.get("response_time_seconds", 45),
                "focus_points": item.get("focus_points") or [],
            })
        if cleaned_items:
            cleaned.append({
                "id": entry.get("id") or f"set_{len(cleaned) + 1}",
                "title": entry.get("title") or "",
                "repeat_items": cleaned_repeat,
                "items": cleaned_items,
            })
    return cleaned


def get_interview_sets() -> List[Dict[str, Any]]:
    """Return available interview sets for UI selection."""
    return _load_interview_sets()


def _choose_speaking_set(interview_set_id: Optional[str]) -> Optional[Dict[str, Any]]:
    sets = _load_interview_sets()
    if not sets:
        return None
    if interview_set_id:
        for item in sets:
            if item.get("id") == interview_set_id:
                return item
    return random.choice(sets)


def _generate_interview_prompts(
    client: GeminiClient,
    count: int = 4,
    speaking_set: Optional[Dict[str, Any]] = None,
    allow_ai: bool = True,
) -> Optional[List[Dict[str, Any]]]:
    if speaking_set:
        items = speaking_set.get("items", [])
        if len(items) >= count:
            return items[:count]
        return items

    if not allow_ai:
        return None

    if not client or not client.is_configured:
        return None

    prompt = (
        "Create New TOEFL interview speaking prompts.\n\n"
        "OUTPUT RULES:\n"
        "1. Return JSON with key: items (array).\n"
        f"2. items must contain exactly {count} objects.\n"
        "3. Each item has: prompt, response_time_seconds, focus_points.\n"
        "4. prompt is a direct interview question (12-18 words).\n"
        "5. response_time_seconds should be 45.\n"
        "6. focus_points is an array of 3 short bullet phrases (<= 6 words) describing expected content.\n"
        "7. Return strict JSON only."
    )

    payload = client.generate_json(
        prompt,
        temperature=0.3,
        system_instruction=SPEAKING_SYSTEM_PROMPT,
        max_output_tokens=1200,
    )
    if not isinstance(payload, dict):
        return None

    items = payload.get("items")
    if not isinstance(items, list) or len(items) != count:
        return None

    return items


def _generate_repeat_prompts(
    client: GeminiClient,
    count: int = 7,
    speaking_set: Optional[Dict[str, Any]] = None,
    allow_ai: bool = True,
) -> Optional[List[Dict[str, Any]]]:
    if speaking_set:
        items = speaking_set.get("repeat_items", [])
        if items:
            return items[:count] if len(items) >= count else items

    if not allow_ai:
        return None

    return _generate_repeat_prompts_ai(client, count=count)


def _generate_repeat_prompts_ai(client: GeminiClient, count: int = 7) -> Optional[List[Dict[str, Any]]]:
    if not client or not client.is_configured:
        return None

    prompt = (
        "Create New TOEFL listen-and-repeat prompts.\n\n"
        "OUTPUT RULES:\n"
        "1. Return JSON with key: items (array).\n"
        f"2. items must contain exactly {count} objects.\n"
        "3. Each item has: prompt, response_time_seconds.\n"
        "4. prompt is a single sentence of 12-18 words, clear and academic.\n"
        "5. response_time_seconds should be 8-12 depending on sentence length.\n"
        "6. Return strict JSON only."
    )

    payload = client.generate_json(
        prompt,
        temperature=0.3,
        system_instruction=SPEAKING_SYSTEM_PROMPT,
        max_output_tokens=1200,
    )
    if not isinstance(payload, dict):
        return None

    items = payload.get("items")
    if not isinstance(items, list) or len(items) != count:
        return None

    return items


def generate_speaking_mock(
    client: Optional[GeminiClient] = None,
    tts: Optional[TTSService] = None,
    interview_set_id: Optional[str] = None,
    allow_ai: bool = True,
) -> Optional[Dict[str, Any]]:
    tts = tts or TTSService()

    speaking_set = _choose_speaking_set(interview_set_id)
    if interview_set_id and speaking_set:
        allow_ai = False
    if allow_ai:
        client = client or get_gemini_client()
        if (not speaking_set) and (not client or not client.is_configured):
            return None
        if not client or not client.is_configured:
            client = None
    else:
        client = None
    prebuilt_only = os.getenv("TOEFL_PREBUILT_ONLY", "false").lower() in {"1", "true", "yes"}
    missing_audio = False
    repeat_items = _generate_repeat_prompts(client, speaking_set=speaking_set, allow_ai=allow_ai) or []
    for item in repeat_items:
        prompt_text = _safe_text(item.get("prompt"))
        if not prompt_text:
            continue
        cache_key = _audio_cache_key(prompt_text)
        if prebuilt_only:
            audio = tts.get_cached_audio("new_toefl_repeat", cache_key, text=prompt_text)
        else:
            audio = tts.generate_audio_cached(
                prompt_text,
                filename_prefix="new_toefl_repeat",
                cache_key=cache_key,
            )
        if prebuilt_only and not audio:
            missing_audio = True
        if audio:
            item["audio_url"] = f"/static/{audio.audio_path}"

    interview_items = _generate_interview_prompts(client, speaking_set=speaking_set, allow_ai=allow_ai) or []
    for item in interview_items:
        prompt_text = _safe_text(item.get("prompt"))
        if not prompt_text:
            continue
        cache_key = _audio_cache_key(prompt_text)
        if prebuilt_only:
            audio = tts.get_cached_audio("new_toefl_interview", cache_key, text=prompt_text)
        else:
            audio = tts.generate_audio_cached(
                prompt_text,
                filename_prefix="new_toefl_interview",
                cache_key=cache_key,
            )
        if prebuilt_only and not audio:
            missing_audio = True
        if audio:
            item["audio_url"] = f"/static/{audio.audio_path}"

    if prebuilt_only and missing_audio:
        return None

    if not repeat_items and not interview_items:
        return None

    return {
        "repeat": repeat_items,
        "interview": interview_items,
    }


# ---------------------------------------------------------------------------
# WRITING MOCK
# ---------------------------------------------------------------------------


def _generate_sentence_build_items(client: GeminiClient, count: int = 10) -> Optional[List[Dict[str, Any]]]:
    if not client or not client.is_configured:
        return None

    prompt = (
        "Create New TOEFL Build-a-Sentence tasks.\n\n"
        "OUTPUT RULES:\n"
        "1. Return JSON with key: items (array).\n"
        f"2. items must contain exactly {count} objects.\n"
        "3. Each item has: prompt, tokens, answer.\n"
        "4. prompt is a short question or context sentence.\n"
        "5. tokens is an array of scrambled words (6-10 tokens).\n"
        "6. answer is the correct full sentence in proper grammar.\n"
        "7. Use everyday academic campus topics.\n"
        "8. Return strict JSON only."
    )

    payload = client.generate_json(
        prompt,
        temperature=0.35,
        system_instruction=WRITING_SYSTEM_PROMPT,
        max_output_tokens=2200,
    )
    if not isinstance(payload, dict):
        return None

    items = payload.get("items")
    if not isinstance(items, list) or len(items) != count:
        return None

    return items


def _generate_email_task(client: GeminiClient) -> Optional[Dict[str, Any]]:
    if not client or not client.is_configured:
        return None

    prompt = (
        "Create ONE New TOEFL writing email task.\n\n"
        "OUTPUT RULES:\n"
        "1. Return JSON with keys: id, scenario, instructions, to_name, subject.\n"
        "2. scenario is 90-120 words explaining the situation.\n"
        "3. instructions is an array of 3 bullet requirements.\n"
        "4. Provide realistic recipient name and subject.\n"
        "5. Return strict JSON only."
    )

    payload = client.generate_json(
        prompt,
        temperature=0.35,
        system_instruction=WRITING_SYSTEM_PROMPT,
        max_output_tokens=1200,
    )
    if not isinstance(payload, dict):
        return None

    scenario = _safe_text(payload.get("scenario"))
    instructions = payload.get("instructions")
    if not scenario or not isinstance(instructions, list) or len(instructions) != 3:
        return None

    return {
        "id": payload.get("id") or f"email_{uuid4().hex[:8]}",
        "scenario": scenario,
        "instructions": instructions,
        "to_name": payload.get("to_name") or "Student",
        "subject": payload.get("subject") or "Request",
    }


def _generate_discussion_task(client: GeminiClient) -> Optional[Dict[str, Any]]:
    if not client or not client.is_configured:
        return None

    prompt = (
        "Create ONE New TOEFL academic discussion writing task.\n\n"
        "OUTPUT RULES:\n"
        "1. Return JSON with keys: id, professor_prompt, student_posts.\n"
        "2. professor_prompt is 70-90 words.\n"
        "3. student_posts is an array of exactly 2 objects with name, stance, message (55-80 words each).\n"
        "4. Keep topic academic and balanced.\n"
        "5. Return strict JSON only."
    )

    payload = client.generate_json(
        prompt,
        temperature=0.35,
        system_instruction=WRITING_SYSTEM_PROMPT,
        max_output_tokens=1800,
    )
    if not isinstance(payload, dict):
        return None

    professor_prompt = _safe_text(payload.get("professor_prompt"))
    student_posts = payload.get("student_posts")
    if not professor_prompt or not isinstance(student_posts, list) or len(student_posts) != 2:
        return None

    return {
        "id": payload.get("id") or f"discussion_{uuid4().hex[:8]}",
        "professor_prompt": professor_prompt,
        "student_posts": student_posts,
    }


def generate_writing_mock(client: Optional[GeminiClient] = None) -> Optional[Dict[str, Any]]:
    client = client or get_gemini_client()
    if not client or not client.is_configured:
        return None

    sentence_build = _generate_sentence_build_items(client) or []
    email_task = _generate_email_task(client)
    discussion_task = _generate_discussion_task(client)

    if not sentence_build and not email_task and not discussion_task:
        return None

    return {
        "sentence_build": sentence_build,
        "email": email_task,
        "discussion": discussion_task,
    }
