"""DeepSeek-powered content generation for the New TOEFL mock exams."""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional
from uuid import uuid4

from flask import current_app

from .gemini_client import GeminiClient, get_gemini_client
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

READING_SYSTEM_PROMPT = (
    "You are DeepSeek creating New TOEFL reading mock questions. "
    "Return strict JSON matching the requested schema. Avoid markdown or extra text."
)

LISTENING_SYSTEM_PROMPT = (
    "You are DeepSeek creating New TOEFL listening mock questions. "
    "Return strict JSON matching the requested schema. Avoid markdown or extra text."
)

SPEAKING_SYSTEM_PROMPT = (
    "You are DeepSeek creating New TOEFL speaking mock prompts. "
    "Return strict JSON matching the requested schema. Avoid markdown or extra text."
)

WRITING_SYSTEM_PROMPT = (
    "You are DeepSeek creating New TOEFL writing mock tasks. "
    "Return strict JSON matching the requested schema. Avoid markdown or extra text."
)


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


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
        "Create ONE New TOEFL reading cloze task (Complete the Words).\n"
        f"Topic: {focus_topic}\n\n"
        "OUTPUT RULES:\n"
        "1. Return a JSON object with keys: id, paragraph, blanks.\n"
        "2. paragraph must be 90-120 words. Replace each missing word with a PARTIAL blank, e.g., \"poll___\".\n"
        "   - Keep the first 2-4 letters of the target word, then add underscores for the missing letters.\n"
        "   - The number of underscores should match the number of missing letters.\n"
        f"3. Provide exactly {blank_count} blanks.\n"
        "4. blanks is an array with objects: token, answer, part_of_speech, hint.\n"
        "   - token must match the exact partial blank string used in the paragraph (e.g., \"poll___\").\n"
        "5. answer must be the full word that completes the blank.\n"
        "6. hint is a concise English clue (<= 12 words) describing meaning or grammar.\n"
        "7. Ensure the missing words are moderately advanced (CEFR B2-C1) and not proper nouns.\n"
        "8. Return strict JSON only."
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
    blanks = payload.get("blanks")
    if not paragraph or not isinstance(blanks, list) or len(blanks) != blank_count:
        return None
    tokens = [_safe_text(blank.get("token")) for blank in blanks]
    if not all(tokens):
        return None
    if not all("_" in token for token in tokens):
        return None
    if not all(token in paragraph for token in tokens):
        return None

    return {
        "id": payload.get("id") or f"cloze_{uuid4().hex[:8]}",
        "paragraph": paragraph,
        "blanks": blanks,
    }


def _generate_daily_life_set(client: GeminiClient) -> Optional[Dict[str, Any]]:
    if not client or not client.is_configured:
        return None

    prompt = (
        "Create ONE New TOEFL reading task using daily-life materials (email/notice/announcement).\n\n"
        "QUESTION STYLE RULES:\n"
        "- Focus on reading strategies: main idea, purpose, inference, vocabulary-in-context, or NOT/EXCEPT.\n"
        "- Avoid price/location/time-detail questions (no schedules, fees, addresses, dates as the focus).\n"
        "- At least one question must be about purpose or main idea.\n\n"
        "OUTPUT RULES:\n"
        "1. Return a JSON object with keys: id, source_text, source_type, questions.\n"
        "2. source_text is 90-130 words. source_type is one of: email, notice, memo, advertisement.\n"
        "3. questions is an array with exactly 2 objects.\n"
        "4. Each question has: question, options (array of 4), answer, rationales.\n"
        "5. answer must exactly match one option.\n"
        "6. rationales is an object mapping each option to a concise English explanation (<= 18 words).\n"
        "7. Keep language clear and realistic for real-life reading.\n"
        "8. Return strict JSON only."
    )

    payload = client.generate_json(
        prompt,
        temperature=0.35,
        system_instruction=READING_SYSTEM_PROMPT,
        max_output_tokens=1600,
    )
    if not isinstance(payload, dict):
        return None

    source_text = _safe_text(payload.get("source_text"))
    questions = payload.get("questions")
    if not source_text or not isinstance(questions, list) or len(questions) != 2:
        return None

    return {
        "id": payload.get("id") or f"daily_{uuid4().hex[:8]}",
        "source_text": source_text,
        "source_type": payload.get("source_type", "email"),
        "questions": questions,
    }


def _generate_academic_passage_set(client: GeminiClient) -> Optional[Dict[str, Any]]:
    if not client or not client.is_configured:
        return None

    prompt = (
        "Create ONE New TOEFL academic reading passage with multiple-choice questions.\n\n"
        "QUESTION STYLE RULES:\n"
        "- Use TOEFL-style questions: vocabulary-in-context, rhetorical purpose (\"Why does the author mention...\"),\n"
        "  inference, main idea/theme, or NOT/EXCEPT.\n"
        "- Avoid price/location/time-detail questions.\n"
        "- Include at least one vocabulary-in-context question and one purpose/inference question.\n\n"
        "OUTPUT RULES:\n"
        "1. Return a JSON object with keys: id, passage, questions.\n"
        "2. passage is 190-230 words, academic tone, cohesive.\n"
        "3. questions is an array with exactly 4 objects.\n"
        "4. Each question has: question, options (array of 4), answer, rationales.\n"
        "5. answer must exactly match one option.\n"
        "6. rationales is an object mapping each option to a concise English explanation (<= 20 words).\n"
        "7. Return strict JSON only."
    )

    payload = client.generate_json(
        prompt,
        temperature=0.35,
        system_instruction=READING_SYSTEM_PROMPT,
        max_output_tokens=2200,
    )
    if not isinstance(payload, dict):
        return None

    passage = _safe_text(payload.get("passage"))
    questions = payload.get("questions")
    if not passage or not isinstance(questions, list) or len(questions) != 4:
        return None

    return {
        "id": payload.get("id") or f"academic_{uuid4().hex[:8]}",
        "passage": passage,
        "questions": questions,
    }


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

    for _ in range(2):
        item = _generate_daily_life_set(client)
        if item:
            daily_life_tasks.append(item)

    academic = _generate_academic_passage_set(client)

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

    prompt = (
        "Create New TOEFL listen-and-choose-response items.\n\n"
        "OUTPUT RULES:\n"
        "1. Return JSON with key: items (array).\n"
        f"2. items must contain exactly {count} objects.\n"
        "3. Each item has: prompt, options (array of 4), answer, rationales.\n"
        "4. prompt is a short sentence or question suitable for spoken audio (8-12 words).\n"
        "5. answer must exactly match one option.\n"
        "6. rationales maps each option to a concise English reason (<= 14 words).\n"
        "7. Avoid cultural references; keep campus or everyday situations.\n"
        "8. Return strict JSON only."
    )

    payload = client.generate_json(
        prompt,
        temperature=0.35,
        system_instruction=LISTENING_SYSTEM_PROMPT,
        max_output_tokens=1500,
    )
    if not isinstance(payload, dict):
        return None

    items = payload.get("items")
    if not isinstance(items, list) or len(items) != count:
        return None

    return items


def _generate_conversation_set(client: GeminiClient) -> Optional[Dict[str, Any]]:
    if not client or not client.is_configured:
        return None

    prompt = (
        "Create ONE New TOEFL conversation listening task.\n\n"
        "OUTPUT RULES:\n"
        "1. Return JSON with keys: id, segments, questions.\n"
        "2. segments is an array of 8-10 objects with speaker and text. Speakers: Woman, Man.\n"
        "3. The conversation should be 120-150 words total, natural campus setting.\n"
        "4. questions is an array of exactly 3 objects.\n"
        "5. Each question has: question, options (array of 4), answer, rationales.\n"
        "6. rationales maps each option to concise English reasons (<= 18 words).\n"
        "7. Return strict JSON only."
    )

    payload = client.generate_json(
        prompt,
        temperature=0.35,
        system_instruction=LISTENING_SYSTEM_PROMPT,
        max_output_tokens=2000,
    )
    if not isinstance(payload, dict):
        return None

    segments = payload.get("segments")
    questions = payload.get("questions")
    if not isinstance(segments, list) or not isinstance(questions, list) or len(questions) != 3:
        return None

    return {
        "id": payload.get("id") or f"conv_{uuid4().hex[:8]}",
        "segments": segments,
        "questions": questions,
    }


def _generate_talk_set(client: GeminiClient) -> Optional[Dict[str, Any]]:
    if not client or not client.is_configured:
        return None

    prompt = (
        "Create ONE New TOEFL academic talk listening task.\n\n"
        "OUTPUT RULES:\n"
        "1. Return JSON with keys: id, talk, questions.\n"
        "2. talk is 180-220 words, academic mini-lecture.\n"
        "3. questions is an array of exactly 3 objects.\n"
        "4. Each question has: question, options (array of 4), answer, rationales.\n"
        "5. rationales maps each option to concise English reasons (<= 18 words).\n"
        "6. Return strict JSON only."
    )

    payload = client.generate_json(
        prompt,
        temperature=0.35,
        system_instruction=LISTENING_SYSTEM_PROMPT,
        max_output_tokens=2000,
    )
    if not isinstance(payload, dict):
        return None

    talk = _safe_text(payload.get("talk"))
    questions = payload.get("questions")
    if not talk or not isinstance(questions, list) or len(questions) != 3:
        return None

    return {
        "id": payload.get("id") or f"talk_{uuid4().hex[:8]}",
        "talk": talk,
        "questions": questions,
    }


def generate_listening_mock(
    client: Optional[GeminiClient] = None,
    tts: Optional[TTSService] = None,
) -> Optional[Dict[str, Any]]:
    client = client or get_gemini_client()
    if not client or not client.is_configured:
        return None

    tts = tts or TTSService()

    response_items = _generate_listen_response_items(client) or []
    for item in response_items:
        prompt_text = _safe_text(item.get("prompt"))
        if not prompt_text:
            continue
        audio = tts.generate_audio(prompt_text, filename_prefix="new_toefl_response")
        if audio:
            item["audio_url"] = f"/static/{audio.audio_path}"

    conversation = _generate_conversation_set(client)
    if conversation:
        segments = conversation.get("segments", [])
        audio = tts.generate_multi_speaker_audio(segments, filename_prefix="new_toefl_conversation")
        if audio:
            conversation["audio_url"] = f"/static/{audio.audio_path}"

    talk = _generate_talk_set(client)
    if talk:
        audio = tts.generate_audio(talk.get("talk", ""), filename_prefix="new_toefl_talk")
        if audio:
            talk["audio_url"] = f"/static/{audio.audio_path}"

    if not response_items and not conversation and not talk:
        return None

    return {
        "responses": response_items,
        "conversation": conversation,
        "talk": talk,
    }


# ---------------------------------------------------------------------------
# SPEAKING MOCK
# ---------------------------------------------------------------------------


def _generate_repeat_prompts(client: GeminiClient, count: int = 7) -> Optional[List[Dict[str, Any]]]:
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


def _generate_interview_prompts(client: GeminiClient, count: int = 4) -> Optional[List[Dict[str, Any]]]:
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


def generate_speaking_mock(
    client: Optional[GeminiClient] = None,
    tts: Optional[TTSService] = None,
) -> Optional[Dict[str, Any]]:
    client = client or get_gemini_client()
    if not client or not client.is_configured:
        return None

    tts = tts or TTSService()

    repeat_items = _generate_repeat_prompts(client) or []
    for item in repeat_items:
        prompt_text = _safe_text(item.get("prompt"))
        if not prompt_text:
            continue
        audio = tts.generate_audio(prompt_text, filename_prefix="new_toefl_repeat")
        if audio:
            item["audio_url"] = f"/static/{audio.audio_path}"

    interview_items = _generate_interview_prompts(client) or []
    for item in interview_items:
        prompt_text = _safe_text(item.get("prompt"))
        if not prompt_text:
            continue
        audio = tts.generate_audio(prompt_text, filename_prefix="new_toefl_interview")
        if audio:
            item["audio_url"] = f"/static/{audio.audio_path}"

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
