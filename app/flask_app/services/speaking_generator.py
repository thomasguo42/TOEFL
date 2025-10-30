"""
Speaking task generation service using Gemini AI.
Generates Independent and Integrated speaking tasks for TOEFL practice.
"""
from __future__ import annotations

import random
import re
from typing import Dict, Optional, List
from flask import current_app

from .gemini_client import get_gemini_client
from .tts_service import get_tts_service

# Task 1: Independent Speaking (Personal Preference)
INDEPENDENT_TOPICS = [
    "Education and Learning",
    "Technology and Society",
    "Work and Career",
    "Hobbies and Leisure",
    "Friends and Relationships",
    "Environment and Nature",
    "Health and Lifestyle",
    "Culture and Traditions",
    "Travel and Exploration",
    "Personal Growth"
]

# Task 2-4: Integrated Tasks Topics
INTEGRATED_TOPICS = [
    "University Policies",
    "Campus Life",
    "Academic Skills",
    "Student Services",
    "Environmental Issues",
    "Social Psychology",
    "Education Methods",
    "Technology in Education",
    "Cultural Studies",
    "Communication Skills"
]


def _parse_conversation(transcript: str) -> List[Dict[str, str]]:
    """
    Parse a conversation transcript with speaker labels into segments.

    Format: "Woman: Hello there\nMan: Hi, how are you?"
    Returns: [{'speaker': 'Woman', 'text': 'Hello there', 'voice': 'af_heart'}, ...]
    """
    segments = []

    # Voice mapping
    VOICE_MAP = {
        'Woman': 'af_heart',      # Female voice
        'Female': 'af_heart',
        'Girl': 'af_heart',
        'Man': 'am_adam',         # Male voice
        'Male': 'am_adam',
        'Boy': 'am_adam',
        'Professor': 'am_adam',   # Default to male for professor
        'Student': 'af_heart',    # Default to female for student
    }

    # Split by speaker labels (e.g., "Woman:", "Man:", "Professor:")
    pattern = r'(Woman|Man|Female|Male|Girl|Boy|Professor|Student):\s*'
    parts = re.split(pattern, transcript)

    # Process pairs of (speaker, text)
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            speaker = parts[i].strip()
            text = parts[i + 1].strip()

            if text:
                voice = VOICE_MAP.get(speaker, 'af_heart')
                segments.append({
                    'speaker': speaker,
                    'text': text,
                    'voice': voice
                })

    return segments


def _remove_speaker_labels(transcript: str) -> str:
    """Remove speaker labels from transcript (fallback for single-voice audio)."""
    # Remove patterns like "Woman: ", "Man: ", "Professor: ", etc.
    pattern = r'(Woman|Man|Female|Male|Girl|Boy|Professor|Student):\s*'
    return re.sub(pattern, '', transcript).strip()


def generate_independent_task(topic: Optional[str] = None) -> Optional[Dict]:
    """
    Generate Task 1: Independent Speaking (Personal Preference/Opinion)
    45 seconds response time, 15 seconds preparation
    """
    client = get_gemini_client()
    if not client or not client.is_configured:
        current_app.logger.error("Gemini API not configured")
        return None

    chosen_topic = topic or random.choice(INDEPENDENT_TOPICS)

    prompt = f"""Generate a TOEFL Independent Speaking Task (Task 1) on the topic: {chosen_topic}

Requirements:
1. Create a question that asks about personal preference, experience, or opinion
2. The question should be clear, relatable, and allow for 45 seconds of response
3. Provide a sample high-scoring response (approximately 100-120 words)
4. Provide a response template/structure that students can follow
5. All in English

Return STRICT JSON with these keys:
{{
    "topic": "{chosen_topic}",
    "prompt": "The question text",
    "preparation_time": 15,
    "response_time": 45,
    "sample_response": "A high-scoring sample answer",
    "response_template": "Suggested structure like: 1. State preference, 2. Give reason 1, 3. Give reason 2, 4. Conclude"
}}

Make it authentic TOEFL style."""

    try:
        result = client.generate_json(
            prompt,
            temperature=0.7,
            system_instruction="You are an expert TOEFL test designer creating authentic speaking tasks.",
            max_output_tokens=1024
        )

        if result and isinstance(result, dict):
            result['task_number'] = 1
            result['task_type'] = 'independent'
            result['reading_text'] = None
            result['listening_transcript'] = None
            current_app.logger.info(f"Generated independent speaking task on topic: {chosen_topic}")
            return result

    except Exception as e:
        current_app.logger.error(f"Error generating independent task: {e}")

    return None


def generate_integrated_task_2(topic: Optional[str] = None) -> Optional[Dict]:
    """
    Generate Task 2: Campus Announcement + Opinion (Reading + Listening + Speaking)
    60 seconds response time, 30 seconds preparation
    Reading: 45-50 seconds, Listening: 60-80 seconds
    """
    client = get_gemini_client()
    if not client or not client.is_configured:
        current_app.logger.error("Gemini API not configured")
        return None

    chosen_topic = topic or random.choice(INTEGRATED_TOPICS)

    prompt = f"""Generate a TOEFL Integrated Speaking Task 2 (Campus Situation) on topic: {chosen_topic}

OFFICIAL TOEFL FORMAT:
- Reading: 75-100 words (displayed for 45-50 seconds)
- Listening: 60-80 seconds of audio (transcript should be 90-120 words to fill 60-80 seconds when spoken naturally at 120-130 WPM)
- Preparation: 30 seconds
- Response: 60 seconds

This task involves:
1. A short reading passage about a campus announcement or change
2. A listening part with TWO STUDENTS (one male, one female) having a conversation discussing the announcement
3. ONE student has a STRONGER, clearer opinion with detailed reasons; the other briefly responds or asks questions
4. The speaking prompt asks students to summarize the main student's opinion and reasons

Requirements:
- Reading: Clear announcement/policy with 2 specific points (75-100 words)
- Listening: Realistic conversation between two students (90-120 words total for 60-80s duration)
  * One student (randomly male or female) expresses a strong opinion (agree/disagree) with 2 detailed reasons
  * The other student responds briefly, asks clarifying questions, or makes short comments
  * Format as dialogue with speaker labels (e.g., "Woman: ...", "Man: ...")
- All in English

Return STRICT JSON:
{{
    "topic": "{chosen_topic}",
    "reading_text": "The announcement text (75-100 words)",
    "listening_transcript": "Conversation between two students with speaker labels (90-120 words for 60-80s audio)",
    "prompt": "The speaking question referencing the student with the main opinion (e.g., 'The woman expresses her opinion about the announcement. State her opinion and explain the reasons she gives for holding that opinion.')",
    "preparation_time": 30,
    "response_time": 60,
    "sample_response": "High-scoring response (90-110 words to fill 60s)",
    "response_template": "Template structure"
}}"""

    try:
        result = client.generate_json(
            prompt,
            temperature=0.7,
            system_instruction="You are an expert TOEFL test designer creating authentic integrated speaking tasks.",
            max_output_tokens=1536
        )

        if result and isinstance(result, dict):
            result['task_number'] = 2
            result['task_type'] = 'integrated_reading_listening_speaking'

            # Generate audio for listening part (conversation between two students)
            if result.get('listening_transcript'):
                tts = get_tts_service()

                # Parse conversation into segments
                segments = _parse_conversation(result['listening_transcript'])

                if segments and len(segments) > 1:
                    # Multi-speaker conversation
                    audio_result = tts.generate_multi_speaker_audio(
                        segments,
                        filename_prefix=f"speaking_task2_{chosen_topic.lower().replace(' ', '_')}"
                    )
                else:
                    # Fallback to single speaker if parsing failed
                    clean_text = _remove_speaker_labels(result['listening_transcript'])
                    audio_result = tts.generate_audio(
                        clean_text,
                        filename_prefix=f"speaking_task2_{chosen_topic.lower().replace(' ', '_')}",
                        voice="default"
                    )

                if audio_result:
                    result['listening_audio_url'] = f"/static/{audio_result.audio_path}"
                    current_app.logger.info(f"Generated audio for task 2")
                else:
                    current_app.logger.warning(f"Failed to generate audio for task 2")

            current_app.logger.info(f"Generated integrated task 2 on topic: {chosen_topic}")
            return result

    except Exception as e:
        current_app.logger.error(f"Error generating integrated task 2: {e}")

    return None


def generate_integrated_task_3(topic: Optional[str] = None) -> Optional[Dict]:
    """
    Generate Task 3: Academic Concept + Example (Reading + Listening + Speaking)
    60 seconds response time, 30 seconds preparation
    Reading: 45-50 seconds, Listening: 1-2 minutes
    """
    client = get_gemini_client()
    if not client or not client.is_configured:
        current_app.logger.error("Gemini API not configured")
        return None

    academic_topics = [
        "Psychology", "Biology", "Business", "Sociology",
        "Economics", "Environmental Science", "Marketing", "Education"
    ]
    chosen_topic = topic if topic in academic_topics else random.choice(academic_topics)

    prompt = f"""Generate a TOEFL Integrated Speaking Task 3 (General/Specific) on: {chosen_topic}

OFFICIAL TOEFL FORMAT:
- Reading: 75-100 words (displayed for 45-50 seconds)
- Listening: 1-2 minutes of audio (transcript should be 150-240 words to fill 1-2 minutes when spoken naturally at 120-130 WPM)
- Preparation: 30 seconds
- Response: 60 seconds

This task involves:
1. Reading: A short passage defining an academic concept
2. Listening: A lecture excerpt giving specific examples to illustrate the concept
3. Speaking: Explain the concept and how the examples illustrate it

Requirements:
- Reading: Clear definition with key characteristics (75-100 words)
- Listening: 1-2 concrete examples that clearly illustrate the concept (150-240 words to ensure 1-2min duration)
- All in English

Return STRICT JSON:
{{
    "topic": "{chosen_topic}",
    "reading_text": "Academic concept definition (75-100 words)",
    "listening_transcript": "Professor's lecture with examples (150-240 words for 1-2min audio)",
    "prompt": "Using points and examples from the lecture, explain [concept] and how the examples illustrate it.",
    "preparation_time": 30,
    "response_time": 60,
    "sample_response": "High-scoring response (90-110 words to fill 60s)",
    "response_template": "Template structure"
}}"""

    try:
        result = client.generate_json(
            prompt,
            temperature=0.7,
            system_instruction="You are an expert TOEFL test designer creating authentic academic speaking tasks.",
            max_output_tokens=1536
        )

        if result and isinstance(result, dict):
            result['task_number'] = 3
            result['task_type'] = 'integrated_reading_listening_speaking'

            # Generate audio for listening part (remove "Professor:" label)
            if result.get('listening_transcript'):
                tts = get_tts_service()
                # Remove speaker labels like "Professor:" from the audio
                clean_text = _remove_speaker_labels(result['listening_transcript'])
                audio_result = tts.generate_audio(
                    clean_text,
                    filename_prefix=f"speaking_task3_{chosen_topic.lower().replace(' ', '_')}",
                    voice="am_adam"  # Use male professor voice
                )
                if audio_result:
                    result['listening_audio_url'] = f"/static/{audio_result.audio_path}"
                    current_app.logger.info(f"Generated audio for task 3")
                else:
                    current_app.logger.warning(f"Failed to generate audio for task 3")

            current_app.logger.info(f"Generated integrated task 3 on topic: {chosen_topic}")
            return result

    except Exception as e:
        current_app.logger.error(f"Error generating integrated task 3: {e}")

    return None


def generate_integrated_task_4(topic: Optional[str] = None) -> Optional[Dict]:
    """
    Generate Task 4: Academic Lecture Summary (Listening + Speaking)
    60 seconds response time, 20 seconds preparation
    Listening: 1-1.5 minutes
    """
    client = get_gemini_client()
    if not client or not client.is_configured:
        current_app.logger.error("Gemini API not configured")
        return None

    academic_topics = [
        "Biology", "Psychology", "History", "Astronomy",
        "Geology", "Anthropology", "Economics", "Environmental Science"
    ]
    chosen_topic = topic if topic in academic_topics else random.choice(academic_topics)

    prompt = f"""Generate a TOEFL Integrated Speaking Task 4 (Academic Lecture) on: {chosen_topic}

OFFICIAL TOEFL FORMAT:
- Listening ONLY: 1-1.5 minutes of audio (transcript should be 150-195 words to fill 1-1.5 minutes when spoken naturally at 120-130 WPM)
- Preparation: 20 seconds
- Response: 60 seconds

This task involves:
1. Listening ONLY: A lecture excerpt presenting a main concept and 2 supporting examples/points
2. Speaking: Summarize the main concept and explain the 2 examples

Requirements:
- Lecture has clear structure: intro of concept + example 1 with details + example 2 with details
- Examples clearly support the main concept with specific details
- Total transcript: 150-195 words to ensure 1-1.5min duration
- All in English

Return STRICT JSON:
{{
    "topic": "{chosen_topic}",
    "listening_transcript": "Professor's lecture (150-195 words for 1-1.5min audio)",
    "prompt": "Using points and examples from the lecture, explain [the main concept discussed].",
    "preparation_time": 20,
    "response_time": 60,
    "sample_response": "High-scoring response (90-110 words to fill 60s)",
    "response_template": "Template structure"
}}"""

    try:
        result = client.generate_json(
            prompt,
            temperature=0.7,
            system_instruction="You are an expert TOEFL test designer creating authentic academic lecture tasks.",
            max_output_tokens=1536
        )

        if result and isinstance(result, dict):
            result['task_number'] = 4
            result['task_type'] = 'integrated_listening_speaking'
            result['reading_text'] = None  # Task 4 has no reading

            # Generate audio for listening part (remove "Professor:" label)
            if result.get('listening_transcript'):
                tts = get_tts_service()
                # Remove speaker labels like "Professor:" from the audio
                clean_text = _remove_speaker_labels(result['listening_transcript'])
                audio_result = tts.generate_audio(
                    clean_text,
                    filename_prefix=f"speaking_task4_{chosen_topic.lower().replace(' ', '_')}",
                    voice="am_adam"  # Use male professor voice
                )
                if audio_result:
                    result['listening_audio_url'] = f"/static/{audio_result.audio_path}"
                    current_app.logger.info(f"Generated audio for task 4")
                else:
                    current_app.logger.warning(f"Failed to generate audio for task 4")

            current_app.logger.info(f"Generated integrated task 4 on topic: {chosen_topic}")
            return result

    except Exception as e:
        current_app.logger.error(f"Error generating integrated task 4: {e}")

    return None


def generate_task_by_number(task_number: int, topic: Optional[str] = None) -> Optional[Dict]:
    """Generate a speaking task by task number (1-4)"""
    generators = {
        1: generate_independent_task,
        2: generate_integrated_task_2,
        3: generate_integrated_task_3,
        4: generate_integrated_task_4
    }

    generator = generators.get(task_number)
    if not generator:
        current_app.logger.error(f"Invalid task number: {task_number}")
        return None

    return generator(topic)


def generate_speaking_practice_set() -> List[Dict]:
    """Generate a complete set of 4 speaking tasks"""
    tasks = []
    for task_num in range(1, 5):
        task = generate_task_by_number(task_num)
        if task:
            tasks.append(task)
        else:
            current_app.logger.warning(f"Failed to generate task {task_num}")

    return tasks
