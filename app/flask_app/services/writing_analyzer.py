"""
Writing analysis and feedback service using Gemini AI.
Provides comprehensive feedback with scoring, annotations, and actionable suggestions.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List, Optional, Tuple
from flask import current_app

from .gemini_client import get_gemini_client


class WritingAnalyzer:
    """Comprehensive essay analyzer providing TOEFL-style feedback."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_gemini_client()
        return self._client

    def analyze_essay(
        self,
        essay_text: str,
        task_type: str,
        prompt: str,
        reading_text: Optional[str] = None,
        listening_transcript: Optional[str] = None,
        discussion_context: Optional[Dict[str, Any]] = None
    ) -> Dict:
        """
        Comprehensive analysis of an essay.

        Returns:
            Dict with scores, annotations, coach_summary, strengths, improvements
        """
        if not essay_text or not essay_text.strip():
            return self._empty_feedback()

        word_count = len(essay_text.split())

        # Get comprehensive LLM feedback
        llm_feedback = self._call_llm_for_analysis(
            essay_text=essay_text,
            task_type=task_type,
            prompt=prompt,
            reading_text=reading_text,
            listening_transcript=listening_transcript,
            discussion_context=discussion_context,
            word_count=word_count
        )

        if not llm_feedback:
            return self._empty_feedback()

        feedback = self._normalize_feedback(llm_feedback, task_type=task_type)
        if not feedback:
            current_app.logger.warning("Gemini feedback normalization failed; returning empty feedback object.")
            return self._empty_feedback()
        return feedback

    def generate_paraphrases(self, sentence: str, count: int = 3) -> List[str]:
        """
        Generate multiple paraphrased versions of a sentence.
        Used for the real-time paraphrasing assistant feature.
        """
        if not self.client or not self.client.is_configured:
            return []

        prompt = f"""Provide {count} different academic paraphrases of this sentence:

"{sentence}"

Requirements:
- Maintain the same meaning
- Use different vocabulary and sentence structure
- Keep academic tone
- Make each paraphrase distinctly different from the others

Return STRICT JSON:
{{
    "paraphrases": ["paraphrase 1", "paraphrase 2", "paraphrase 3"]
}}"""

        try:
            result = self.client.generate_json(
                prompt=prompt,
                temperature=0.8,
                system_instruction="You are an expert academic writing tutor helping with paraphrasing.",
                max_output_tokens=512
            )

            if isinstance(result, dict) and 'paraphrases' in result:
                return result['paraphrases'][:count]

        except Exception as e:
            current_app.logger.warning(f"Paraphrase generation failed: {e}")

        return []

    def _call_llm_for_analysis(
        self,
        essay_text: str,
        task_type: str,
        prompt: str,
        reading_text: Optional[str],
        listening_transcript: Optional[str],
        discussion_context: Optional[Dict[str, Any]],
        word_count: int
    ) -> Optional[Dict]:
        """Call LLM for comprehensive essay analysis."""
        if not self.client or not self.client.is_configured:
            return None

        # Build context - For integrated tasks, include FULL source materials for content checking
        context_parts = [f"Task Type: {task_type}", f"Prompt: {prompt}"]
        if task_type == 'integrated':
            # Include full reading and listening for content accuracy evaluation
            if reading_text:
                context_parts.append(f"Reading Passage (FULL):\n{reading_text}")
            if listening_transcript:
                context_parts.append(f"Listening Transcript (FULL - Professor's Lecture):\n{listening_transcript}")
        elif task_type == 'discussion':
            if discussion_context:
                professor_question = discussion_context.get('professor_question')
                if professor_question:
                    context_parts.append(f"Professor Question:\n{professor_question}")

                student_posts = discussion_context.get('student_posts') or []
                if student_posts:
                    formatted_posts = []
                    for post in student_posts:
                        if not isinstance(post, dict):
                            continue
                        name = post.get('name') or "Student"
                        stance = post.get('stance')
                        message = post.get('message') or ""
                        header = f"{name} ({stance})" if stance else name
                        formatted_posts.append(f"{header}:\n{message}")
                    if formatted_posts:
                        context_parts.append("Classmates' Posts:\n" + "\n\n".join(formatted_posts))

                highlights = discussion_context.get('discussion_highlights') or []
                if highlights:
                    highlight_lines = []
                    for highlight in highlights:
                        if not isinstance(highlight, dict):
                            continue
                        source = highlight.get('source') or "Classmate"
                        key_point = highlight.get('key_point') or ""
                        implication = highlight.get('implication')
                        if implication:
                            highlight_lines.append(f"{source}: {key_point} (Implication: {implication})")
                        else:
                            highlight_lines.append(f"{source}: {key_point}")
                    if highlight_lines:
                        context_parts.append("Key Discussion Highlights:\n" + "\n".join(highlight_lines))
        else:
            # For other tasks, include concise context if available
            if reading_text:
                context_parts.append(f"Reading Passage: {reading_text[:500]}...")
            if listening_transcript:
                context_parts.append(f"Listening Transcript: {listening_transcript[:500]}...")

        context = "\n\n".join(context_parts)

        # Task-specific instructions
        task_specific = ""
        if task_type == 'integrated':
            task_specific = """
For Integrated Task, CRITICALLY EVALUATE CONTENT ACCURACY:

Additional Fields (CONCISE):
- "content_accuracy": Did student address ALL professor's points? (2-3 sentences, under 300 chars)
- "point_coverage": Array of 3-4 strings, each stating one professor's point and coverage status (e.g., "Point 1: Digital divide worsens inequality - Accurately addressed") (each under 100 chars)
- "example_accuracy": Were professor's examples correctly referenced? (1-2 sentences, under 200 chars)
- "paraphrase_quality": Quality of paraphrasing vs copying (1-2 sentences, under 200 chars)
- "source_integration": How well reading/lecture connected (1-2 sentences, under 200 chars)

SCORING: Content score MUST reflect accuracy. Missing 1 major point = max 3/5, missing 2+ = max 2/5.

CONTENT VALIDATION:
- Cross-check every essay claim against the professor's lecture. Explicitly call out mismatches or omissions.
- Flag fabricated or imprecise examples in "example_accuracy".
- Note any stylistic drift (casual tone, repetitive phrasing, vague language) in "organization_notes" or "content_suggestions".
"""
        elif task_type == 'discussion':
            task_specific = """
For Academic Discussion Task, VERIFY RELEVANCE AND INTERACTION:

Discussion Expectations:
- Assess whether the response directly addresses the professor's question and references at least one classmate or the professor by name.
- Critique whether the writer adds a new idea, evidence, or perspective rather than repeating existing comments.
- Flag missing connections to classmates in "content_suggestions" or "organization_notes".
- Mention tone/formality issues appropriate for an academic forum.

Additional Fields (STRICT JSON):
- "thread_alignment": Does the reply answer the professor and stay on-topic? (2 sentences, <=260 chars)
- "participant_references": Array summarizing how the writer engages classmates/professor (3-4 items, <=110 chars each)
- "new_contribution": What fresh idea/evidence does the writer add? (1-2 sentences, <=220 chars)
- "tone_style": Academic tone & register feedback (<=200 chars)
- "evidence_precision": Comment on specificity/accuracy of support (<=220 chars)
"""

        strict_requirements = """
STRICTNESS EXPECTATIONS:
- Apply TOEFL criteria rigorously. Do not inflate scores; use half steps (e.g., 3.5) only when justified and explain shortcomings.
- Judge factual accuracy: if the essay misquotes, invents details, or contradicts the lecture/reading/discussion scenario, reflect this in scores and feedback text.
- For discussion tasks, highlight when the response fails to acknowledge classmates or omits a fresh contribution.
- Comment on precision of vocabulary, sentence variety, and academic tone.
- ALWAYS populate every field listed below with clear, specific text. Never return null, empty strings, or empty arrays. If a strength is minimal, still cite the best aspect. If a category is weak, provide a corrective action instead of leaving it blank.
- Provide 5-8 annotations. Cover task fulfillment, grammar, cohesion, and lexical issues where relevant.
- Strengths: 3-4 items highlighting any relatively solid elements (even if modest).
- Improvements: 4-5 precise actions tied to TOEFL rubric.
- Grammar/Vocabulary: give concrete corrections/substitutions.
- Organization/Content suggestions: focus on structure, logical flow, evidence accuracy, and alignment with sources.
- Ensure scores align with qualitative feedback; if coach_summary calls performance weak, overall_score_5 must be ≤3.
"""

        analysis_prompt = f"""You are an expert TOEFL Writing rater. Provide comprehensive, detailed feedback for this essay.

Context:
{context}

Student Essay ({word_count} words):
{essay_text}

Provide detailed analysis with:

1. SCORES (0-5 scale for subscores, overall will be converted to 0-30):
   - overall_score_5: Overall score 0-5
   - content_development: Ideas, examples, details (0-5)
   - organization: Structure, coherence, transitions (0-5)
   - vocabulary: Word choice, range, appropriateness (0-5)
   - grammar: Grammar accuracy, sentence variety (0-5)

2. ANNOTATIONS (In-line feedback - find 5-8 specific issues):
   Array of objects, each with:
   - type: "vague" / "lexical" / "grammar" / "cohesion" / "task"
   - text: The exact phrase from the essay (find it precisely)
   - comment: Actionable feedback (max 100 chars)
   - start_index: Character position where phrase starts
   - end_index: Character position where phrase ends

3. DETAILED FEEDBACK CATEGORIES (BE CONCISE):
   - coach_summary: 2-3 sentences of overall feedback
   - strengths: Array of 3-4 specific strengths (each under 120 chars)
   - improvements: Array of 4-5 actionable improvements (each under 120 chars)
   - grammar_issues: Array of 2-3 grammar problems with corrections (each under 100 chars)
   - vocabulary_suggestions: Array of 2-3 vocab suggestions (each under 100 chars)
   - organization_notes: Array of 2 organization notes (each under 120 chars)
   - content_suggestions: Array of 2 content suggestions (each under 120 chars)

{task_specific}
{strict_requirements}

Return STRICT JSON with ALL fields. Be CONCISE - respect character limits. Use clear, actionable language.
"""

        try:
            current_app.logger.info(f"Calling Gemini AI for essay analysis (task_type={task_type}, word_count={word_count})")
            result = self.client.generate_json(
                prompt=analysis_prompt,
                temperature=0.4,
                system_instruction="You are a meticulous TOEFL Writing evaluator who provides detailed, actionable feedback in compact JSON format.",
                max_output_tokens=4096  # Increased for comprehensive content evaluation
            )
            current_app.logger.info(f"Gemini AI response received. Type: {type(result)}")

            if isinstance(result, dict):
                current_app.logger.info(f"Gemini returned dict with keys: {list(result.keys())}")
                return result
            if isinstance(result, str):
                parsed = json.loads(result)
                current_app.logger.info(f"Gemini returned string, parsed to dict with keys: {list(parsed.keys())}")
                return parsed

        except Exception as e:
            current_app.logger.error(f"Essay analysis LLM call failed: {e}", exc_info=True)

        return None

    def _normalize_feedback(self, raw_feedback: Dict[str, Any], task_type: str) -> Optional[Dict[str, Any]]:
        """Normalize Gemini feedback into DB-safe structures with strict typing."""
        if not isinstance(raw_feedback, dict):
            current_app.logger.warning("Gemini feedback payload was not a dict: %s", type(raw_feedback))
            return None
        data = self._flatten_feedback(raw_feedback)

        normalized: Dict[str, Any] = {
            'overall_score': self._convert_to_30_scale(self._safe_float(data.get('overall_score_5', 0.0))),
            'content_development_score': self._safe_float(data.get('content_development', 0.0)),
            'organization_structure_score': self._safe_float(data.get('organization', 0.0)),
            'vocabulary_language_score': self._safe_float(data.get('vocabulary', 0.0)),
            'grammar_mechanics_score': self._safe_float(data.get('grammar', 0.0)),
            'annotations': self._normalize_annotations(data.get('annotations')),
            'coach_summary': self._normalize_text_field(data.get('coach_summary')) or '',
            'strengths': self._normalize_list_field(self._pick_field(data, ('strengths', 'positives', 'positive_points')), limit=4, max_len=120),
            'improvements': self._normalize_list_field(self._pick_field(data, ('improvements', 'areas_for_improvement', 'improvement_points')), limit=5, max_len=120),
            'grammar_issues': self._normalize_list_field(self._pick_field(data, ('grammar_issues', 'grammar_notes')), limit=3, max_len=100),
            'vocabulary_suggestions': self._normalize_list_field(self._pick_field(data, ('vocabulary_suggestions', 'lexical_suggestions', 'word_choice')), limit=3, max_len=100),
            'organization_notes': self._normalize_list_field(self._pick_field(data, ('organization_notes', 'structure_notes')), limit=2, max_len=120),
            'content_suggestions': self._normalize_list_field(self._pick_field(data, ('content_suggestions', 'content_notes', 'development_notes')), limit=2, max_len=120),
        }

        if task_type == 'integrated':
            normalized.update(self._normalize_integrated_feedback(data))
        elif task_type == 'discussion':
            normalized.update(self._normalize_discussion_feedback(data))
        else:
            normalized.update({
                'content_accuracy': None,
                'point_coverage': [],
                'example_accuracy': None,
                'paraphrase_quality': None,
                'source_integration': None,
            })

        self._apply_score_strictness(normalized, data, task_type)
        return normalized

    def _flatten_feedback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten common nested Gemini structures into a single dict."""
        flattened: Dict[str, Any] = {}
        for key, value in payload.items():
            flattened[key] = value

        containers = (
            'scores',
            'score_breakdown',
            'rubric_scores',
            'rubric',
            'overall_feedback',
            'feedback',
        )
        for container_key in containers:
            container = payload.get(container_key)
            if isinstance(container, dict):
                for sub_key, sub_value in container.items():
                    # Only promote missing or falsy values to avoid overwriting explicit top-level entries
                    if not flattened.get(sub_key):
                        flattened[sub_key] = sub_value

        return flattened

    @staticmethod
    def _pick_field(data: Dict[str, Any], candidate_keys: Tuple[str, ...]) -> Any:
        """Pick the first non-empty field from a list of candidate keys."""
        for key in candidate_keys:
            value = data.get(key)
            if value not in (None, '', [], {}):
                return value
        return None

    def _apply_score_strictness(self, feedback: Dict[str, Any], data: Dict[str, Any], task_type: str) -> None:
        """Apply defensive score downgrades when Gemini flags major issues."""
        if task_type == 'integrated':
            severity = 0
            keyword_flags = ('irrelevant', 'not address', 'fails to', 'missing', 'does not', 'misinterpret', 'inaccurate', 'fabricated', 'off-topic')

            content_accuracy_text = self._normalize_text_field(feedback.get('content_accuracy')) or ''
            if any(flag in content_accuracy_text.lower() for flag in keyword_flags):
                severity += 2

            point_coverage = feedback.get('point_coverage') or []
            if isinstance(point_coverage, list):
                for item in point_coverage:
                    if isinstance(item, str) and any(flag in item.lower() for flag in keyword_flags):
                        severity += 1
            task_annotations = [
                ann for ann in feedback.get('annotations', [])
                if isinstance(ann, dict) and ann.get('type') == 'task'
            ]
            if len(task_annotations) >= 2:
                severity += 1

            coach_summary = self._normalize_text_field(feedback.get('coach_summary')) or ''
            if 'off-topic' in coach_summary.lower() or 'not relevant' in coach_summary.lower():
                severity += 1

            improvements = feedback.get('improvements') or []
            for item in improvements:
                if isinstance(item, str) and any(flag in item.lower() for flag in keyword_flags):
                    severity += 1
                    break

            if severity <= 0:
                return

            if severity >= 3:
                cap_content = 1.0
            elif severity == 2:
                cap_content = 2.0
            else:
                cap_content = 3.0

            feedback['content_development_score'] = min(feedback.get('content_development_score', cap_content), cap_content)
            allowed_overall = self._convert_to_30_scale(cap_content)
            feedback['overall_score'] = min(feedback.get('overall_score', allowed_overall), allowed_overall)

            # Clamp organization and vocabulary slightly to avoid inflated totals on off-topic essays
            if cap_content <= 2.0:
                feedback['organization_structure_score'] = min(feedback.get('organization_structure_score', cap_content), cap_content)
                feedback['vocabulary_language_score'] = min(feedback.get('vocabulary_language_score', cap_content + 0.5), cap_content + 0.5)

        elif task_type == 'discussion':
            severity = 0
            keyword_flags = ('off-topic', 'irrelevant', 'does not address', 'fails to respond', 'ignores', 'no reference', 'does not mention', 'unrelated', 'missing new idea')

            coach_summary = self._normalize_text_field(feedback.get('coach_summary')) or ''
            if any(flag in coach_summary.lower() for flag in keyword_flags):
                severity += 2

            task_annotations = [
                ann for ann in feedback.get('annotations', [])
                if isinstance(ann, dict) and ann.get('type') == 'task'
            ]
            if len(task_annotations) >= 2:
                severity += 1

            for bucket in ('improvements', 'content_suggestions', 'organization_notes'):
                entries = feedback.get(bucket) or []
                for entry in entries:
                    if isinstance(entry, str) and any(flag in entry.lower() for flag in keyword_flags):
                        severity += 1
                        break

            strengths = feedback.get('strengths') or []
            if not strengths:
                severity += 1

            if severity <= 0:
                return

            if severity >= 3:
                cap_content = 1.5
            elif severity == 2:
                cap_content = 2.5
            else:
                cap_content = 3.0

            feedback['content_development_score'] = min(feedback.get('content_development_score', cap_content), cap_content)
            allowed_overall = self._convert_to_30_scale(cap_content)
            feedback['overall_score'] = min(feedback.get('overall_score', allowed_overall), allowed_overall)

            feedback['organization_structure_score'] = min(feedback.get('organization_structure_score', cap_content + 0.5), cap_content + 0.5)
            feedback['vocabulary_language_score'] = min(feedback.get('vocabulary_language_score', cap_content + 0.5), cap_content + 0.5)

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        """Safely coerce a value to float."""
        if value is None:
            return default
        if isinstance(value, (int, float)):
            result = float(value)
            if math.isnan(result) or math.isinf(result):
                return default
            return result
        try:
            result = float(str(value).strip())
            if math.isnan(result) or math.isinf(result):
                return default
            return result
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        """Safely coerce a value to int, returning None on failure."""
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_json_like(value: Any) -> Any:
        """Attempt to interpret stringified JSON structures."""
        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                return None
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                return candidate
        return value

    def _normalize_text_field(self, value: Any) -> Optional[str]:
        """Normalize free-text fields into concise strings."""
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            joined = "; ".join(
                filter(None, (self._normalize_text_field(item) for item in value))
            )
            return joined or None
        if isinstance(value, dict):
            for key in ('text', 'summary', 'value', 'message', 'content'):
                if key in value:
                    candidate = self._normalize_text_field(value[key])
                    if candidate:
                        return candidate
            # If single value dict, take first non-empty value
            for dict_value in value.values():
                candidate = self._normalize_text_field(dict_value)
                if candidate:
                    return candidate
            return None
        try:
            return str(value)
        except Exception:
            return None

    def _normalize_list_field(self, value: Any, limit: Optional[int] = None, max_len: Optional[int] = None) -> List[str]:
        """Normalize list-like feedback fields into bounded lists of concise strings."""
        parsed = self._parse_json_like(value)
        items: List[str] = []

        if isinstance(parsed, list):
            iterable = parsed
        elif isinstance(parsed, str):
            iterable = [seg.strip() for seg in re.split(r'[\n;]+', parsed) if seg.strip()]
        elif parsed is None:
            iterable = []
        else:
            iterable = [parsed]

        for entry in iterable:
            text = self._normalize_text_field(entry)
            if not text:
                continue
            if max_len:
                text = text[:max_len]
            items.append(text)

        if limit is not None:
            items = items[:limit]
        return items

    def _normalize_annotations(self, value: Any) -> List[Dict[str, Any]]:
        """Normalize annotation objects and discard malformed entries."""
        parsed = self._parse_json_like(value)
        if not isinstance(parsed, list):
            return []

        annotations: List[Dict[str, Any]] = []
        for raw in parsed:
            if not isinstance(raw, dict):
                continue

            text = self._normalize_text_field(raw.get('text'))
            comment = self._normalize_text_field(raw.get('comment'))
            start_index = self._safe_int(raw.get('start_index'))
            end_index = self._safe_int(raw.get('end_index'))
            issue_type = (self._normalize_text_field(raw.get('type')) or 'task').lower()

            if not text or not comment:
                continue
            if start_index is None or end_index is None or end_index <= start_index:
                continue

            annotations.append({
                'type': issue_type[:20],
                'text': text[:200],
                'comment': comment[:100],
                'start_index': start_index,
                'end_index': end_index,
            })

        return annotations[:8]

    def _normalize_integrated_feedback(self, raw_feedback: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize integrated-task specific feedback fields (content accuracy, coverage, etc.)."""
        integrated_defaults = {
            'content_accuracy': None,
            'point_coverage': [],
            'example_accuracy': None,
            'paraphrase_quality': None,
            'source_integration': None,
        }

        # Gemini sometimes nests all integrated feedback under content_accuracy
        nested_source = raw_feedback.get('content_accuracy')
        if isinstance(nested_source, dict):
            integrated_defaults['content_accuracy'] = self._normalize_text_field(nested_source.get('content_accuracy'))
            integrated_defaults['example_accuracy'] = self._normalize_text_field(
                nested_source.get('example_accuracy', raw_feedback.get('example_accuracy'))
            )
            integrated_defaults['paraphrase_quality'] = self._normalize_text_field(
                nested_source.get('paraphrase_quality', raw_feedback.get('paraphrase_quality'))
            )
            integrated_defaults['source_integration'] = self._normalize_text_field(
                nested_source.get('source_integration', raw_feedback.get('source_integration'))
            )
            integrated_defaults['point_coverage'] = self._normalize_point_coverage(
                nested_source.get('point_coverage', raw_feedback.get('point_coverage'))
            )
        else:
            integrated_defaults['content_accuracy'] = self._normalize_text_field(nested_source)
            integrated_defaults['example_accuracy'] = self._normalize_text_field(raw_feedback.get('example_accuracy'))
            integrated_defaults['paraphrase_quality'] = self._normalize_text_field(raw_feedback.get('paraphrase_quality'))
            integrated_defaults['source_integration'] = self._normalize_text_field(raw_feedback.get('source_integration'))
            integrated_defaults['point_coverage'] = self._normalize_point_coverage(raw_feedback.get('point_coverage'))

        return integrated_defaults

    def _normalize_point_coverage(self, value: Any) -> List[str]:
        """Normalize point coverage entries to concise strings."""
        parsed = self._parse_json_like(value)
        points: List[str] = []

        if isinstance(parsed, list):
            iterable = parsed
        elif isinstance(parsed, dict):
            iterable = [parsed]
        elif isinstance(parsed, str):
            iterable = [parsed]
        elif parsed is None:
            iterable = []
        else:
            iterable = [parsed]

        for entry in iterable:
            text = self._normalize_text_field(entry)
            if not text:
                continue
            points.append(text[:120])

        return points[:4]

    def _normalize_discussion_feedback(self, raw_feedback: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize academic discussion feedback fields."""
        alignment = self._normalize_text_field(
            self._pick_field(raw_feedback, ('thread_alignment', 'discussion_alignment', 'prompt_alignment', 'content_accuracy'))
        )
        references = self._normalize_point_coverage(
            self._pick_field(raw_feedback, ('participant_references', 'classmate_references', 'point_coverage'))
        )
        new_contribution = self._normalize_text_field(
            self._pick_field(raw_feedback, ('new_contribution', 'unique_perspective', 'example_accuracy'))
        )
        tone_style = self._normalize_text_field(
            self._pick_field(raw_feedback, ('tone_style', 'tone_and_register', 'paraphrase_quality'))
        )
        evidence_precision = self._normalize_text_field(
            self._pick_field(raw_feedback, ('evidence_precision', 'support_quality', 'source_integration'))
        )

        return {
            'content_accuracy': alignment,
            'point_coverage': references,
            'example_accuracy': new_contribution,
            'paraphrase_quality': tone_style,
            'source_integration': evidence_precision,
        }

    def _convert_to_30_scale(self, score_5: float) -> float:
        """Convert 0-5 scale score to 0-30 TOEFL scale."""
        # TOEFL uses 0-5 internally but reports as 0-30
        # 5 -> 30, 4 -> 24, 3 -> 18, 2 -> 12, 1 -> 6, 0 -> 0
        return round(score_5 * 6, 1)

    def _empty_feedback(self) -> Dict:
        """Return empty feedback structure."""
        return {
            'overall_score': 0.0,
            'content_development_score': 0.0,
            'organization_structure_score': 0.0,
            'vocabulary_language_score': 0.0,
            'grammar_mechanics_score': 0.0,
            'annotations': [],
            'coach_summary': 'No essay text provided.',
            'strengths': [],
            'improvements': [],
            'grammar_issues': [],
            'vocabulary_suggestions': [],
            'organization_notes': [],
            'content_suggestions': [],
            'content_accuracy': None,
            'point_coverage': [],
            'example_accuracy': None,
            'paraphrase_quality': None,
            'source_integration': None
        }


# Singleton instance
_analyzer: Optional[WritingAnalyzer] = None


def get_writing_analyzer() -> WritingAnalyzer:
    """Get or create the writing analyzer singleton."""
    global _analyzer
    if _analyzer is None:
        _analyzer = WritingAnalyzer()
    return _analyzer
