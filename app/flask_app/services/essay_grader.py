"""
Standalone essay grading service (not TOEFL-related).
Grades essays based on user-provided topics and provides detailed feedback.
"""
from __future__ import annotations

from typing import Dict, Optional
from flask import current_app

from .gemini_client import get_gemini_client


class EssayGrader:
    """Grade essays and provide comprehensive feedback."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_gemini_client()
        return self._client

    def grade_essay(self, essay_text: str, topic: str) -> Dict:
        """
        Grade an essay based on the provided topic.

        Args:
            essay_text: The essay text to grade
            topic: The essay topic/prompt

        Returns:
            Dictionary containing:
            - corrected_text: Grammar and spelling corrected version
            - corrections_made: List of corrections made
            - grammar_score: 0-10
            - vocabulary_score: 0-10
            - organization_score: 0-10
            - topic_relevance_score: 0-10
            - overall_score: 0-10
            - grammar_issues: List of specific issues
            - vocabulary_suggestions: List of suggestions
            - organization_feedback: Text feedback on structure
            - content_feedback: Text feedback on content
            - topic_coverage: How well the essay addresses the topic
            - missing_aspects: Aspects not covered
            - summary: Overall assessment
            - strengths: List of strengths
            - improvements: List of areas for improvement
        """
        if not self.client or not self.client.is_configured:
            return {
                'error': 'Gemini API not configured',
                'success': False
            }

        prompt = f"""You are an expert essay grader. Grade this essay based on the given topic.

**TOPIC:** {topic}

**ESSAY:**
{essay_text}

**INSTRUCTIONS:**
1. First, correct all grammar, spelling, and punctuation errors in the essay
2. Evaluate how well the essay addresses the topic
3. Assess grammar, vocabulary, organization, and content quality
4. Provide specific, actionable feedback

Provide a JSON response with the following structure:
{{
    "corrected_text": "The fully corrected version of the essay",
    "corrections_made": [
        "Changed 'there' to 'their' in paragraph 1",
        "Fixed comma splice in paragraph 2"
    ],
    "grammar_score": 8.5,
    "vocabulary_score": 7.0,
    "organization_score": 8.0,
    "topic_relevance_score": 9.0,
    "overall_score": 8.1,
    "grammar_issues": [
        {{
            "issue": "Subject-verb agreement error",
            "original": "The students was studying",
            "correction": "The students were studying",
            "explanation": "Plural subject requires plural verb"
        }}
    ],
    "vocabulary_suggestions": [
        {{
            "word": "good",
            "suggestion": "excellent, outstanding, remarkable",
            "context": "Consider using more specific words instead of generic 'good'"
        }}
    ],
    "organization_feedback": "The essay has a clear introduction and conclusion. However, the body paragraphs could be better structured with topic sentences.",
    "content_feedback": "The essay demonstrates a solid understanding of the topic. The arguments are well-supported with examples.",
    "topic_coverage": "The essay addresses all major aspects of the topic. It provides a balanced discussion of both advantages and disadvantages.",
    "missing_aspects": [
        "Could include more real-world examples",
        "Lacks discussion of counterarguments"
    ],
    "summary": "This is a well-written essay with clear arguments and good organization. The main areas for improvement are vocabulary variety and inclusion of counterarguments.",
    "strengths": [
        "Clear thesis statement",
        "Well-organized paragraphs",
        "Good use of transitions"
    ],
    "improvements": [
        "Vary vocabulary more",
        "Add counterarguments",
        "Include more specific examples"
    ]
}}

**SCORING GUIDELINES:**
- Grammar (0-10): Correctness of grammar, spelling, punctuation
- Vocabulary (0-10): Range, accuracy, and sophistication of word choice
- Organization (0-10): Structure, coherence, and logical flow
- Topic Relevance (0-10): How well the essay addresses the topic
- Overall Score: Average of the four scores
"""

        try:
            # Use generate_json which returns parsed JSON directly
            feedback = self.client.generate_json(
                prompt,
                temperature=0.2,
                response_mime='application/json'
            )

            if feedback:
                # generate_json returns the parsed JSON object directly
                feedback['success'] = True
                return feedback
            else:
                current_app.logger.error("Essay grading failed: No response from Gemini API")
                return {
                    'error': 'Failed to generate grading feedback',
                    'success': False
                }

        except Exception as e:
            current_app.logger.error(f"Exception during essay grading: {e}")
            return {
                'error': f'Grading exception: {str(e)}',
                'success': False
            }


def get_essay_grader() -> EssayGrader:
    """Singleton getter for essay grader."""
    if not hasattr(current_app, 'essay_grader'):
        current_app.essay_grader = EssayGrader()
    return current_app.essay_grader
