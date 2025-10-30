
"""Speaking feedback helpers for language use and topic development analysis."""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from flask import current_app

from .gemini_client import get_gemini_client


_TOKEN_RE = re.compile(r"[A-Za-z']+")
_AWL_CACHE: Optional[set[str]] = None


def _load_awl_word_list() -> set[str]:
    """Load Academic Word List entries from seeds, caching the result."""
    global _AWL_CACHE
    if _AWL_CACHE is not None:
        return _AWL_CACHE

    words: set[str] = set()
    try:
        base = Path(current_app.root_path).parents[1]
        awl_path = base / 'data' / 'seeds' / 'awl_list1_sample.csv'
        if awl_path.exists():
            with awl_path.open(newline='', encoding='utf-8') as handle:
                reader = csv.DictReader(handle, fieldnames=['word', 'definition', 'example', 'cn'])
                for row in reader:
                    word = (row.get('word') or '').strip().lower()
                    if word and word != 'word':
                        words.add(word)
        else:
            current_app.logger.warning('AWL seed file not found at %s', awl_path)
    except Exception as exc:  # pragma: no cover - defensive logging
        current_app.logger.error('Failed loading AWL list: %s', exc)

    if not words:
        # Fallback to a small default set so scoring does not crash
        words.update({
            'analyze', 'approach', 'concept', 'data', 'environment', 'method',
            'principle', 'sector', 'structure', 'theory', 'vary', 'major'
        })

    _AWL_CACHE = words
    return words


@dataclass
class LanguageUseResult:
    score: float
    lexical_diversity: float
    academic_word_count: int
    academic_words_used: List[str]
    average_sentence_length: float
    total_words: int
    vocabulary_suggestions: List[str]
    word_choice_issues: List[Dict[str, str]]
    grammar_issues: List[Dict[str, str]]
    strengths: List[str]
    improvements: List[str]


@dataclass
class TopicDevelopmentResult:
    score: float
    task_fulfillment: Optional[str]
    clarity_coherence: Optional[str]
    support_sufficiency: Optional[str]
    content_accuracy: Optional[str]
    strengths: List[str]
    improvements: List[str]


class SpeakingFeedbackEngine:
    """Aggregate helper that augments SpeechRater output."""

    def __init__(self) -> None:
        self.awl_words = _load_awl_word_list()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_gemini_client()
        return self._client

    def _tokenize(self, transcript: str) -> List[str]:
        return [match.group(0).lower() for match in _TOKEN_RE.finditer(transcript or '')]

    def evaluate_language_use(self, transcript: str) -> LanguageUseResult:
        tokens = self._tokenize(transcript)
        total_words = len(tokens)
        unique_words = len(set(tokens)) if tokens else 0
        lexical_diversity = unique_words / total_words if total_words else 0.0
        academic_tokens = [w for w in tokens if w in self.awl_words]
        academic_word_count = len(academic_tokens)
        academic_words_used = sorted(set(academic_tokens))
        academic_density = academic_word_count / total_words if total_words else 0.0

        sentences = [s.strip() for s in re.split(r'[.!?]+', transcript or '') if s.strip()]
        avg_sentence_len = (total_words / len(sentences)) if sentences else 0.0

        lexical_score = min(1.0, lexical_diversity / 0.55)  # 0.55~high diversity target
        academic_score = min(1.0, academic_density / 0.05)  # 5% AWL target (more lenient)
        length_bonus = 1.0 if total_words >= 110 else total_words / 110

        # Reduced academic word weight from 0.4 to 0.25 (more lenient)
        heuristics_score = max(0.45, (lexical_score * 0.75 + academic_score * 0.25)) * 80 * length_bonus
        heuristics_score = min(95.0, heuristics_score)

        vocab_suggestions: List[str] = []
        word_choice_issues: List[Dict[str, str]] = []
        grammar_issues: List[Dict[str, str]] = []
        strengths: List[str] = []
        improvements: List[str] = []
        score_adjustment = 0.0

        llm_payload = self._call_llm_for_language(transcript)
        if llm_payload:
            vocab_suggestions = llm_payload.get('vocabulary_suggestions') or []
            word_choice_issues = llm_payload.get('word_choice_issues') or []
            grammar_issues = llm_payload.get('grammar_issues') or []
            strengths = llm_payload.get('strengths') or []
            improvements = llm_payload.get('improvements') or []
            try:
                score_adjustment = float(llm_payload.get('score_adjustment', 0.0))
            except (TypeError, ValueError):
                score_adjustment = 0.0

        score = max(40.0, min(100.0, heuristics_score + score_adjustment)) if total_words else 0.0

        if not strengths and total_words:
            strengths.append('Uses a range of vocabulary and complete sentences.')
        if not improvements:
            improvements.append('Incorporate more precise academic vocabulary and connect ideas smoothly.')

        return LanguageUseResult(
            score=round(score, 1),
            lexical_diversity=round(lexical_diversity, 3),
            academic_word_count=academic_word_count,
            academic_words_used=academic_words_used,
            average_sentence_length=round(avg_sentence_len, 1),
            total_words=total_words,
            vocabulary_suggestions=vocab_suggestions,
            word_choice_issues=word_choice_issues,
            grammar_issues=grammar_issues,
            strengths=strengths,
            improvements=improvements,
        )

    def evaluate_topic_development(
        self,
        task_prompt: str,
        transcript: str,
        reading_text: Optional[str] = None,
        listening_summary: Optional[str] = None,
    ) -> TopicDevelopmentResult:
        tokens = self._tokenize(transcript)
        base_score = 55.0 if len(tokens) >= 80 else len(tokens) / 80 * 55.0
        llm_payload = self._call_llm_for_topic(task_prompt, transcript, reading_text, listening_summary)

        strengths: List[str] = []
        improvements: List[str] = []
        task_fulfillment = None
        clarity = None
        support = None
        content_accuracy = None
        score = base_score

        if llm_payload:
            try:
                score = float(llm_payload.get('score', base_score))
            except (TypeError, ValueError):
                score = base_score
            task_fulfillment = llm_payload.get('task_fulfillment')
            clarity = llm_payload.get('clarity_coherence')
            support = llm_payload.get('support_sufficiency')
            content_accuracy = llm_payload.get('content_accuracy')
            strengths = llm_payload.get('strengths') or []
            improvements = llm_payload.get('improvements') or []

        if not strengths and transcript.strip():
            strengths.append('Addresses the prompt with a clear main idea.')
        if not improvements:
            improvements.append('Add specific supporting details and transitions between ideas.')

        return TopicDevelopmentResult(
            score=round(max(40.0, min(100.0, score)), 1) if transcript.strip() else 0.0,
            task_fulfillment=task_fulfillment,
            clarity_coherence=clarity,
            support_sufficiency=support,
            content_accuracy=content_accuracy,
            strengths=strengths,
            improvements=improvements,
        )

    # ------------------------------------------------------------------
    # LLM helpers

    def _call_llm_for_language(self, transcript: str) -> Optional[Dict]:
        client = self.client
        if not client or not client.is_configured or not transcript.strip():
            return None

        prompt = f"""
You are an expert TOEFL Speaking evaluator. Perform a HOLISTIC analysis of the student's response for language use, word choice, grammar, and vocabulary.

TOEFL Speaking Language Use Criteria:
1. Grammar: Evaluate sentence structure, verb tenses, subject-verb agreement, articles, prepositions
2. Vocabulary: Assess word choice appropriateness, academic vocabulary use, precision, range
3. Idioms & Expressions: Check if expressions are natural and appropriate
4. Clarity: Evaluate if ideas are expressed clearly without ambiguity

Analyze the transcript and return STRICT JSON with this schema:
{{
  "grammar_issues": [{{"snippet": "string", "issue": "string", "suggestion": "string"}}],
  "vocabulary_suggestions": ["Specific suggestions to improve word choice and use more precise/academic vocabulary", ...],
  "word_choice_issues": [{{"word_used": "string", "better_alternative": "string", "reason": "string"}}],
  "strengths": ["Specific strengths in grammar, vocabulary, or expression", ...],
  "improvements": ["Specific actionable improvements for grammar and vocabulary", ...],
  "score_adjustment": number  # Range -10 to +10, based on overall language sophistication
}}

Keep entries concise (under 140 characters each).

Transcript:
""" + transcript.strip()

        try:
            result = client.generate_json(
                prompt=prompt,
                temperature=0.4,
                system_instruction="You are a meticulous TOEFL Speaking scorer who outputs compact JSON only.",
                max_output_tokens=768,
            )
            if isinstance(result, dict):
                return result
            if isinstance(result, str):
                return json.loads(result)
        except Exception as exc:  # pragma: no cover - network/JSON errors
            current_app.logger.warning('Language LLM analysis failed: %s', exc)
        return None

    def _call_llm_for_topic(
        self,
        task_prompt: str,
        transcript: str,
        reading_text: Optional[str],
        listening_summary: Optional[str],
    ) -> Optional[Dict]:
        client = self.client
        if not client or not client.is_configured or not transcript.strip():
            return None

        context_parts = [f"Prompt: {task_prompt.strip()}"]
        if reading_text:
            context_parts.append(f"Reading: {reading_text.strip()[:900]}")
        if listening_summary:
            context_parts.append(f"Listening transcript: {listening_summary.strip()[:900]}")
        context_str = "\n\n".join(context_parts)

        prompt = f"""
You are an expert TOEFL Speaking rater. Perform a HOLISTIC evaluation of how well the student's response addresses the task.

TOEFL Speaking Content Evaluation Criteria:
1. Task Fulfillment: Did the response fully address all parts of the question?
2. Content Development: Are ideas developed with sufficient detail and examples?
3. Clarity & Coherence: Is the response well-organized with clear progression of ideas?
4. Relevance: Are all points relevant to the task?
5. Use of Source Material (for integrated tasks): Are key points from reading/listening accurately incorporated?

Provide a comprehensive evaluation. Return STRICT JSON:
{{
  "score": number between 40 and 100,
  "task_fulfillment": "Detailed assessment of whether all parts were addressed (2-3 sentences)",
  "clarity_coherence": "Assessment of organization, transitions, and logical flow (2-3 sentences)",
  "support_sufficiency": "Assessment of detail, examples, and development (2-3 sentences)",
  "content_accuracy": "For integrated tasks: accuracy of source material use (2-3 sentences, or null for independent)",
  "strengths": ["Specific content strengths", ...],
  "improvements": ["Specific actionable content improvements", ...]
}}

Do not include newlines inside strings. Be specific and constructive.

Context:
{context_str}

Student response:
{transcript.strip()}
"""

        try:
            result = client.generate_json(
                prompt=prompt,
                temperature=0.4,
                system_instruction="You are a TOEFL Speaking evaluator outputting compact JSON only.",
                max_output_tokens=768,
            )
            if isinstance(result, dict):
                return result
            if isinstance(result, str):
                return json.loads(result)
        except Exception as exc:  # pragma: no cover - network/JSON errors
            current_app.logger.warning('Topic LLM analysis failed: %s', exc)
        return None


_engine: Optional[SpeakingFeedbackEngine] = None


def get_feedback_engine() -> SpeakingFeedbackEngine:
    global _engine
    if _engine is None:
        _engine = SpeakingFeedbackEngine()
    return _engine
