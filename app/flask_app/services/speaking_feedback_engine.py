
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
    rubric_evidence: List[str]


@dataclass
class TopicDevelopmentResult:
    score: float
    task_fulfillment: Optional[str]
    clarity_coherence: Optional[str]
    support_sufficiency: Optional[str]
    content_accuracy: Optional[str]
    strengths: List[str]
    improvements: List[str]
    rubric_evidence: List[str]


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

    @staticmethod
    def _round_to_half(value: float) -> float:
        return round(value * 2) / 2

    @staticmethod
    def _map_100_to_band(score: float) -> float:
        if score is None:
            return 0.0
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
        rubric_evidence: List[str] = []

        llm_payload = self._call_llm_for_language(transcript)
        if llm_payload:
            vocab_suggestions = llm_payload.get('vocabulary_suggestions') or []
            word_choice_issues = llm_payload.get('word_choice_issues') or []
            grammar_issues = llm_payload.get('grammar_issues') or []
            strengths = llm_payload.get('strengths') or []
            improvements = llm_payload.get('improvements') or []
            rubric_evidence = llm_payload.get('rubric_evidence') or []

        if llm_payload and llm_payload.get('score_5') is not None:
            try:
                score = float(llm_payload.get('score_5'))
            except (TypeError, ValueError):
                score = self._map_100_to_band(heuristics_score) if total_words else 0.0
        else:
            score = self._map_100_to_band(heuristics_score) if total_words else 0.0
        score = max(0.0, min(5.0, score))
        score = self._round_to_half(score)

        if not strengths and total_words:
            strengths.append('Uses a range of vocabulary and complete sentences.')
        if not improvements:
            improvements.append('Incorporate more precise academic vocabulary and connect ideas smoothly.')
        if not rubric_evidence:
            rubric_evidence.append('Language control allows ideas to be generally understood.')

        return LanguageUseResult(
            score=score,
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
            rubric_evidence=rubric_evidence,
        )

    def evaluate_topic_development(
        self,
        task_prompt: str,
        transcript: str,
        reading_text: Optional[str] = None,
        listening_summary: Optional[str] = None,
        task_type: Optional[str] = None,
    ) -> TopicDevelopmentResult:
        tokens = self._tokenize(transcript)
        base_score = 55.0 if len(tokens) >= 80 else len(tokens) / 80 * 55.0
        llm_payload = self._call_llm_for_topic(task_prompt, transcript, reading_text, listening_summary, task_type)

        strengths: List[str] = []
        improvements: List[str] = []
        task_fulfillment = None
        clarity = None
        support = None
        content_accuracy = None
        score = base_score
        rubric_evidence: List[str] = []

        if llm_payload:
            try:
                if llm_payload.get('score_5') is not None:
                    score = float(llm_payload.get('score_5'))
                else:
                    score = float(llm_payload.get('score', base_score))
            except (TypeError, ValueError):
                score = base_score
            task_fulfillment = llm_payload.get('task_fulfillment')
            clarity = llm_payload.get('clarity_coherence')
            support = llm_payload.get('support_sufficiency')
            content_accuracy = llm_payload.get('content_accuracy')
            strengths = llm_payload.get('strengths') or []
            improvements = llm_payload.get('improvements') or []
            rubric_evidence = llm_payload.get('rubric_evidence') or []

        if not strengths and transcript.strip():
            strengths.append('Addresses the prompt with a clear main idea.')
        if not improvements:
            improvements.append('Add specific supporting details and transitions between ideas.')
        if not rubric_evidence:
            rubric_evidence.append('Response is generally on topic with some development.')

        if isinstance(score, (int, float)) and score > 5:
            score = self._map_100_to_band(score)
        score = max(0.0, min(5.0, float(score))) if transcript.strip() else 0.0
        score = self._round_to_half(score)

        return TopicDevelopmentResult(
            score=score,
            task_fulfillment=task_fulfillment,
            clarity_coherence=clarity,
            support_sufficiency=support,
            content_accuracy=content_accuracy,
            strengths=strengths,
            improvements=improvements,
            rubric_evidence=rubric_evidence,
        )

    # ------------------------------------------------------------------
    # LLM helpers

    def _call_llm_for_language(self, transcript: str) -> Optional[Dict]:
        client = self.client
        if not client or not client.is_configured or not transcript.strip():
            return None

        prompt = f"""
You are an expert TOEFL Speaking rater focusing on Language Use for the Take an Interview task.

Rubric anchors (0-5, half steps allowed):
5: Range of accurate grammar and vocabulary allows clear, precise meaning; errors are rare.
4: Grammar/vocabulary are adequate; minor errors do not impede meaning.
3: Limited range and accuracy noticeably restrict clarity; errors sometimes interfere.
2: Very limited range; frequent errors make meaning difficult.
1: Mostly unintelligible or isolated words; severe errors.
0: No response / not English.

Analyze the transcript and return STRICT JSON:
{{
  "score_5": number (0-5, half steps),
  "rubric_evidence": ["Short rubric-matched evidence statements", ...],
  "grammar_issues": [{{"snippet": "string", "issue": "string", "suggestion": "string"}}],
  "vocabulary_suggestions": ["Specific word-choice upgrades", ...],
  "word_choice_issues": [{{"word_used": "string", "better_alternative": "string", "reason": "string"}}],
  "strengths": ["Specific language strengths", ...],
  "improvements": ["Specific language improvements", ...]
}}

Keep entries concise (under 140 characters each). Be strict and rubric-aligned.

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
        task_type: Optional[str],
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

        rubric_block = ""
        if task_type and "interview" in task_type:
            rubric_block = """
Take an Interview Rubric (0-5, half steps allowed):
5: Fully addresses the question; on topic; well elaborated; clear and fluent.
4: Addresses the question; generally clear; some elaboration; minor weaknesses.
3: Addresses the question but limited elaboration/clarity.
2: Minimally relevant; little support; hard to follow.
1: Mostly unintelligible or isolated words.
0: No response / off-topic / not English.
"""

        prompt = f"""
You are an expert TOEFL Speaking rater. Perform a HOLISTIC evaluation of how well the student's response addresses the task.

TOEFL Speaking Content Evaluation Criteria:
1. Task Fulfillment: Did the response fully address all parts of the question?
2. Content Development: Are ideas developed with sufficient detail and examples?
3. Clarity & Coherence: Is the response well-organized with clear progression of ideas?
4. Relevance: Are all points relevant to the task?
5. Use of Source Material (for integrated tasks): Are key points from reading/listening accurately incorporated?

{rubric_block}

Provide a comprehensive evaluation. Return STRICT JSON:
{{
  "score_5": number between 0 and 5 (half steps allowed),
  "rubric_evidence": ["Short rubric-matched evidence statements", ...],
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
