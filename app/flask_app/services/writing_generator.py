"""
Writing task generation service using Gemini AI.
Generates Integrated and Academic Discussion writing tasks for TOEFL practice.
"""
from __future__ import annotations

import random
from typing import Dict, Optional
from flask import current_app

from .gemini_client import get_gemini_client
from .tts_service import get_tts_service


# Topics for integrated tasks (academic subjects)
INTEGRATED_TOPICS = [
    "Environmental Science",
    "Psychology",
    "Sociology",
    "Business Management",
    "Education",
    "Technology",
    "Public Health",
    "Urban Planning",
    "History",
    "Economics"
]

# Topics for academic discussion tasks (seminar style prompts)
DISCUSSION_TOPICS = [
    "Freshman Seminar",
    "Business Ethics",
    "Environmental Policy",
    "Art History",
    "Psychology of Learning",
    "Sociology of Technology",
    "Public Health",
    "Cultural Studies",
    "Urban Planning",
    "Economics of Innovation"
]


def generate_integrated_task(topic: Optional[str] = None) -> Optional[Dict]:
    """
    Generate an Integrated Writing Task (Reading + Listening + Writing).

    The lecture typically refutes or challenges the reading passage.
    Student must summarize both sources and explain their relationship.

    Time: 3 minutes reading, ~2 minutes listening, 20 minutes writing (150-225 words)
    """
    client = get_gemini_client()
    if not client or not client.is_configured:
        current_app.logger.error("Gemini API not configured")
        return None

    chosen_topic = topic or random.choice(INTEGRATED_TOPICS)

    prompt = f"""Generate a TOEFL Integrated Writing Task on the topic: {chosen_topic}

OFFICIAL TOEFL FORMAT:
- Reading: 230-300 words (academic passage presenting a position with 3 supporting points)
- Listening: 230-300 words (lecture that refutes, challenges, or adds nuance to the reading)
- Writing prompt: Summarize the lecture and explain how it relates to the reading

Structure Requirements:
1. Reading passage should present a clear thesis with 3 distinct supporting points
2. Lecture should address each of the 3 points, usually with counterarguments or challenges
3. Both should be academic in tone but accessible

Return STRICT JSON:
{{
    "topic": "{chosen_topic}",
    "reading_text": "Academic passage (230-300 words) with clear thesis and 3 supporting points",
    "listening_transcript": "Professor's lecture (230-300 words) that addresses the reading's points",
    "prompt": "Summarize the points made in the lecture, being sure to explain how they cast doubt on / challenge / relate to specific points made in the reading passage.",
    "reading_main_point": "Brief summary of reading's main argument",
    "lecture_stance": "How the lecture relates to the reading (refutes/challenges/supports)",
    "point_pairs": [
        {{"reading_point": "First point from reading", "lecture_counter": "Lecture's response to this point"}},
        {{"reading_point": "Second point from reading", "lecture_counter": "Lecture's response to this point"}},
        {{"reading_point": "Third point from reading", "lecture_counter": "Lecture's response to this point"}}
    ]
}}

Make it authentic TOEFL style with academic vocabulary and clear structure."""

    try:
        result = client.generate_json(
            prompt,
            temperature=0.7,
            system_instruction="You are an expert TOEFL test designer creating authentic integrated writing tasks.",
            max_output_tokens=2048
        )

        if result and isinstance(result, dict):
            result['task_type'] = 'integrated'
            result['word_limit'] = 225
            result['time_limit_minutes'] = 20

            # Generate audio for the listening lecture (remove "Professor:" labels)
            if result.get('listening_transcript'):
                # Remove speaker labels if present
                clean_transcript = result['listening_transcript'].replace('Professor: ', '').replace('professor: ', '')

                tts = get_tts_service()
                audio_result = tts.generate_audio(
                    clean_transcript,
                    filename_prefix=f"writing_integrated_{chosen_topic.lower().replace(' ', '_')}",
                    voice="am_adam"  # Male professor voice
                )
                if audio_result:
                    result['listening_audio_url'] = f"/static/{audio_result.audio_path}"
                    current_app.logger.info(f"Generated audio for integrated writing task")
                else:
                    current_app.logger.warning(f"Failed to generate audio for integrated writing task")

            # Store deconstruction data
            if 'point_pairs' in result:
                result['deconstruction_data'] = {
                    'reading_main_point': result.get('reading_main_point'),
                    'lecture_stance': result.get('lecture_stance'),
                    'point_pairs': result.get('point_pairs')
                }

            current_app.logger.info(f"Generated integrated writing task on topic: {chosen_topic}")
            return result

    except Exception as e:
        current_app.logger.error(f"Error generating integrated writing task: {e}")

    return None


def generate_discussion_task(topic: Optional[str] = None) -> Optional[Dict]:
    """
    Generate a Writing for an Academic Discussion task.

    Student must join a class discussion by responding to professor and classmates.

    Time: 10 minutes writing (minimum 100 words)
    """
    client = get_gemini_client()
    if not client or not client.is_configured:
        current_app.logger.error("Gemini API not configured")
        return None

    chosen_topic = topic or random.choice(DISCUSSION_TOPICS)

    prompt = f"""Generate a TOEFL "Writing for an Academic Discussion" task for a university course on: {chosen_topic}

Scenario format:
- Provide a short professor question (2-3 sentences) inviting opinions or solutions.
- Include two distinct student posts (80-120 words each) with different stances and specific supporting details.
- Posts should reference course concepts or real examples to feel authentic.

Return STRICT JSON:
{{
    "topic": "{chosen_topic}",
    "professor_question": "Professor's discussion prompt (2-3 sentences).",
    "student_posts": [
        {{"name": "Student 1 first name", "stance": "brief stance summary", "message": "Full discussion post (80-120 words) referencing the prompt."}},
        {{"name": "Student 2 first name", "stance": "contrasting or complementary stance summary", "message": "Full discussion post (80-120 words) with specific support."}}
    ],
    "prompt": "Instructions to the test taker (mention 10 minutes, 100+ words, respond to classmates and add new idea).",
    "response_guidance": {{
        "goals": [
            "First objective for the student response (<=110 chars)",
            "Second objective (<=110 chars)"
        ],
        "language_expectations": [
            "Academic tone reminder (<=110 chars)",
            "Precision/clarity reminder (<=110 chars)"
        ],
        "new_perspective_prompts": [
            "Suggestion for adding a new perspective (<=110 chars)",
            "Another angle to consider (<=110 chars)"
        ]
    }},
    "discussion_highlights": [
        {{"source": "Professor or student name", "key_point": "Concise paraphrase of a major idea (<=120 chars)", "implication": "Why it matters (<=120 chars)"}},
        {{"source": "Professor or student name", "key_point": "Another idea to react to", "implication": "Follow-up insight"}}
    ]
}}

Ensure names are realistic and content is academically appropriate."""

    try:
        result = client.generate_json(
            prompt,
            temperature=0.7,
            system_instruction="You are an expert TOEFL test designer creating authentic Writing for an Academic Discussion tasks.",
            max_output_tokens=2048
        )

        if result and isinstance(result, dict):
            result['task_type'] = 'discussion'
            result['word_limit'] = 120  # Target response length
            result['time_limit_minutes'] = 10
            result['discussion_context'] = {
                'professor_question': result.get('professor_question'),
                'student_posts': result.get('student_posts', []),
                'discussion_highlights': result.get('discussion_highlights', [])
            }
            if 'response_guidance' in result:
                result['outline_data'] = result['response_guidance']
            current_app.logger.info(f"Generated academic discussion writing task on topic: {chosen_topic}")
            return result

    except Exception as e:
        current_app.logger.error(f"Error generating academic discussion writing task: {e}")

    return None


def generate_task_by_type(task_type: str, topic: Optional[str] = None) -> Optional[Dict]:
    """Generate a writing task by type ('integrated' or 'discussion')."""
    if task_type == 'integrated':
        return generate_integrated_task(topic)
    elif task_type == 'discussion':
        return generate_discussion_task(topic)
    else:
        current_app.logger.error(f"Invalid task type: {task_type}")
        return None
