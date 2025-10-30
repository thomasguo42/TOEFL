"""High-level helpers to generate individual exercise sets using Gemini 2.5 Flash Lite."""
from __future__ import annotations

from typing import Dict, List, Optional

from flask import current_app

from models import Word
from .gemini_client import GeminiClient, get_gemini_client

VOCAB_SYSTEM_PROMPT = (
    "You are Gemini 2.5 Flash Lite acting as an experienced TOEFL vocabulary coach for Chinese learners. "
    "Always return valid JSON that exactly follows the requested schema. Use an academic but encouraging tone, "
    "and provide concise Simplified Chinese rationales that explain why each option works or fails in context."
)


def generate_gap_fill_single(word: Word, client: Optional[GeminiClient] = None) -> Optional[Dict]:
    """Generate a single contextual gap-fill exercise for ONE word.

    Args:
        word: Word object to generate exercise for
        client: Optional GeminiClient instance (will create one if not provided)

    Returns:
        Dictionary with exercise data, or None on failure
    """
    client = client or get_gemini_client()

    if not client or not client.is_configured:
        current_app.logger.error("Gemini API not configured - cannot generate gap-fill exercise")
        return None

    prompt = (
        "Design ONE TOEFL-style contextual gap-fill question for an advanced Chinese learner.\n\n"
        "OUTPUT RULES:\n"
        "1. Return a JSON object (NOT an array) with keys: word, sentence, options, answer, rationales.\n"
        "2. Replace the target word in the sentence with '_____'. Keep sentence under 30 words.\n"
        "3. Provide exactly four options (strings). Only one option may be correct.\n"
        "4. The answer value must match one of the options exactly (case-sensitive).\n"
        "5. Distractors should be near synonyms or collocations that fail because of meaning, tone, or grammar.\n"
        "6. rationales must include ≤35 character Simplified Chinese feedback for EVERY option (all 4 options).\n"
        "7. Maintain an academic TOEFL register and ensure context clearly signals the correct choice.\n\n"
        f"Target word: {word.lemma}\n"
        f"Definition: {word.definition}\n"
        f"Example: {word.example or 'N/A'}\n\n"
        "Strict JSON example:\n"
        '{"word":"abundant","sentence":"The forest had _____ wildlife.","options":["abundant","scarce","minimal","lacking"],"answer":"abundant","rationales":{"abundant":"句意强调数量充足。","scarce":"与句意相反。","minimal":"数量不足。","lacking":"语义不符。"}}'
    )

    try:
        payload = client.generate_json(
            prompt,
            temperature=0.6,
            system_instruction=VOCAB_SYSTEM_PROMPT,
            max_output_tokens=1024,
        )

        if isinstance(payload, dict) and payload.get('word') and payload.get('sentence'):
            current_app.logger.info(f"Gap-fill generation succeeded for word: {word.lemma}")
            return payload
        current_app.logger.error(f"Gap-fill generation failed for word: {word.lemma} - invalid response format")
    except Exception as exc:
        current_app.logger.error(f"Gap-fill generation failed for word: {word.lemma}: {exc}")

    return None


def generate_synonym_single(word: Word, client: Optional[GeminiClient] = None) -> Optional[Dict]:
    """Generate a single synonym multiple-choice question with explanations.

    Args:
        word: Word object to generate exercise for
        client: Optional GeminiClient instance (will create one if not provided)

    Returns:
        Dictionary with exercise data, or None on failure
    """
    client = client or get_gemini_client()

    if not client or not client.is_configured:
        current_app.logger.error("Gemini API not configured - cannot generate synonym exercise")
        return None

    prompt = (
        "Compose ONE synonym nuance challenge that sharpens TOEFL reading precision.\n\n"
        "OUTPUT RULES:\n"
        "1. Return a JSON object (NOT an array) with keys: word, sentence, options, answer, explanation_cn, rationales.\n"
        "2. Provide exactly four options (strings). Only one should perfectly match the nuance required by the sentence.\n"
        "3. Highlight the target word inside the sentence with double asterisks, for example **resilient**.\n"
        "4. The sentence should be 22-30 words, academic TOEFL tone, and reveal why the answer is best.\n"
        "5. answer must equal one of the options exactly. explanation_cn must be ≤40 Simplified Chinese characters summarising the winning nuance.\n"
        "6. rationales must exist for EVERY option (all 4) and be ≤35 Simplified Chinese characters describing why the option works or fails.\n"
        "7. Avoid markdown fences; return strict JSON only.\n\n"
        f"Target word: {word.lemma}\n"
        f"Definition: {word.definition}\n"
        f"Example: {word.example or 'N/A'}\n\n"
        "Strict JSON example:\n"
        '{"word":"abundant","sentence":"The rainforest contained **abundant** species of birds and mammals, revealing unmatched biodiversity.","options":["plentiful","excessive","sufficient","adequate"],"answer":"plentiful","explanation_cn":"plentiful 最能体现"充足"。","rationales":{"plentiful":"准确呈现数量充足。","excessive":"带有过度语气。","sufficient":"仅表示够用。","adequate":"语气太弱。"}}'
    )

    try:
        payload = client.generate_json(
            prompt,
            temperature=0.65,
            system_instruction=VOCAB_SYSTEM_PROMPT,
            max_output_tokens=1024,
        )

        if isinstance(payload, dict) and payload.get('word') and payload.get('sentence'):
            current_app.logger.info(f"Synonym generation succeeded for word: {word.lemma}")
            return payload
        current_app.logger.error(f"Synonym generation failed for word: {word.lemma} - invalid response format")
    except Exception as exc:
        current_app.logger.error(f"Synonym generation failed for word: {word.lemma}: {exc}")

    return None


def generate_reading_passage_single(words: List[Word], topic: str, client: Optional[GeminiClient] = None) -> Optional[Dict]:
    """Generate a single reading immersion passage and follow-up quiz.

    Args:
        words: List of Word objects to incorporate (up to 7)
        topic: Topic for the reading passage
        client: Optional GeminiClient instance (will create one if not provided)

    Returns:
        Dictionary with paragraph and quiz, or None on failure
    """
    words = words[:7]
    if not words:
        return None

    client = client or get_gemini_client()

    if not client or not client.is_configured:
        current_app.logger.error("Gemini API not configured - cannot generate reading passage")
        return None

    word_list = ", ".join(w.lemma for w in words)
    prompt = (
        "Develop a 190-210 word TOEFL-style passage followed by vocabulary-in-context questions.\n\n"
        f"Topic: {topic}\n"
        f"You must incorporate ALL of these words naturally: {word_list}\n\n"
        "OUTPUT RULES:\n"
        "1. Return a JSON object with keys: paragraph (string) and quiz (array).\n"
        "2. The passage must read like a polished academic text with clear flow and transitions.\n"
        "3. quiz must contain 3 or 4 question objects. Each object requires keys: word, question, options (exactly 4 strings), answer, explanation_cn, rationales.\n"
        "4. Only one option per question may be correct; answer must match one option exactly.\n"
        "5. explanation_cn must be ≤50 Simplified Chinese characters explaining why the answer fits the passage.\n"
        "6. rationales must cover EVERY option (all 4) in ≤40 Simplified Chinese characters, identifying error types (反向, 未提及, 语义不符, etc.).\n"
        "7. Questions should test contextual understanding of the vocabulary, not direct dictionary recall.\n"
        "8. Avoid markdown fencing; output strict JSON only.\n\n"
        "Return nothing besides the JSON object."
    )

    try:
        payload = client.generate_json(
            prompt,
            temperature=0.55,
            system_instruction=(
                "You are Gemini 2.5 Flash Lite designing TOEFL reading immersion for Chinese learners. "
                "Follow the JSON schema exactly, embed every requested vocabulary item naturally, "
                "and deliver succinct Simplified Chinese rationales."
            ),
            max_output_tokens=2048,
        )

        if isinstance(payload, dict) and payload.get('paragraph') and payload.get('quiz'):
            current_app.logger.info(f"Reading passage generation succeeded for topic: {topic}")
            return payload
        current_app.logger.error(f"Reading passage generation failed for topic: {topic} - invalid response format")
    except Exception as exc:
        current_app.logger.error(f"Reading passage generation failed for topic: {topic}: {exc}")

    return None
