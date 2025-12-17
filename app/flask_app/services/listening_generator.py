"""
Listening content generator service using Gemini AI.

This service generates all content for the TOEFL Listening section:
- Feature 1: Dictation sentences (15-25 words, complex academic)
- Feature 2: Signpost phrase segments (2-3 sentences with transitional phrases)
- Feature 3: Full lectures (500 words) and conversations (300 words) with questions
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional
from flask import current_app

from services.gemini_client import GeminiClient


# Common signpost phrases organized by category
SIGNPOST_PHRASES = {
    'contrast': [
        'In contrast',
        'On the other hand',
        'However',
        'Nevertheless',
        'Conversely',
        'Despite this',
        'Yet'
    ],
    'addition': [
        'Furthermore',
        'Moreover',
        'In addition',
        'Additionally',
        'Besides that',
        'Whats more',
        'Also important'
    ],
    'example': [
        'For example',
        'For instance',
        'To illustrate this',
        'A good example of this is',
        'Consider the case of',
        'Let me give you an example'
    ],
    'sequence': [
        'First of all',
        'Secondly',
        'Next',
        'Then',
        'Finally',
        'To begin with',
        'Subsequently'
    ],
    'cause_effect': [
        'As a result',
        'Therefore',
        'Consequently',
        'This led to',
        'Because of this',
        'Thus',
        'Hence'
    ],
    'emphasis': [
        'It is important to note that',
        'Significantly',
        'Most importantly',
        'The key point is',
        'Notably',
        'Essentially'
    ],
    'conclusion': [
        'In conclusion',
        'To sum up',
        'In summary',
        'Overall',
        'To wrap up',
        'In short'
    ]
}

LECTURE_WORD_COUNT_MIN = 620
LECTURE_WORD_COUNT_MAX = 680
LECTURE_WORD_COUNT_RELAXED_MIN = 560
LECTURE_WORD_COUNT_RELAXED_MAX = 720


def generate_dictation_sentences_batch(
    client: GeminiClient,
    count: int = 5,
    topic: Optional[str] = None,
    difficulty: str = 'medium'
) -> Optional[List[Dict]]:
    """
    Generate multiple dictation sentences at once for better UX.

    Args:
        client: GeminiClient instance
        count: Number of sentences to generate (default 5)
        topic: Academic topic (e.g., "geology", "art history")
        difficulty: 'easy', 'medium', or 'hard'

    Returns:
        List of dicts with 'text', 'topic', 'difficulty' or None on failure
    """
    topics_pool = [
        'Biology', 'Astronomy', 'Geology', 'Art History', 'Psychology',
        'Economics', 'Anthropology', 'Environmental Science', 'Linguistics',
        'Sociology', 'Physics', 'History', 'Education Theory', 'Public Health'
    ]

    import random

    if topic:
        topic_instruction = (
            f"All sentences should remain within the broader topic of {topic}, "
            "but each must emphasize a different facet or subtopic so the practice set feels varied "
            "(for example: historical context, current research, notable figures, practical application, etc.). "
            "Keep the `topic` field concise (e.g., 'Economics - behavioral finance')."
        )
        selected_topics = [topic] * count
    else:
        if count <= len(topics_pool):
            selected_topics = random.sample(topics_pool, k=count)
        else:
            selected_topics = random.sample(topics_pool, k=len(topics_pool))
            while len(selected_topics) < count:
                selected_topics.append(random.choice(topics_pool))

        topic_instruction = (
            "Assign each sentence to the matching topic from the list below in order. "
            "Do not reuse topics; ensure the `topic` field exactly matches the assignment.\n"
            "Topic assignments (sentence order matters):\n"
        )
        topic_instruction += "\n".join(
            f"{idx + 1}. {topic_name}" for idx, topic_name in enumerate(selected_topics, start=1)
        )

    example_topic = selected_topics[0] if selected_topics else (topic or 'General Academic Topic')
    alt_example_topic = selected_topics[1] if len(selected_topics) > 1 else example_topic

    # Adjust complexity based on difficulty
    complexity_instructions = {
        'easy': 'Use simple sentence structure with common academic vocabulary.',
        'medium': 'Use moderate complexity with some specialized vocabulary and compound structure.',
        'hard': 'Use complex sentence structure with advanced vocabulary, subordinate clauses, and technical terms.'
    }

    prompt = f"""Generate {count} DIFFERENT academic sentences for university-level lectures.

Requirements for EACH sentence:
- Length: 15-25 words
- Content: Factually accurate, academically appropriate, aligned with its assigned topic
- Style: NATURAL SPOKEN lecture style with proper pauses
  * Use commas for natural breathing pauses
  * Include transitional words (however, therefore, for example, etc.)
  * Sound like a real professor speaking clearly in a lecture
  * DO NOT use hesitations like "um", "uh", "you know" - speak clearly and professionally
  * Use natural academic pacing with pauses between clauses
- Complexity: {complexity_instructions.get(difficulty, complexity_instructions['medium'])}
- Topic distribution guidance:
  {topic_instruction}

CRITICAL: Make each sentence sound like natural, clear academic speech that would be heard in an actual TOEFL exam.
The voice will be synthesized, so proper punctuation creates natural pauses.
Example style: "The process of photosynthesis, which occurs in plant cells, converts light energy into chemical energy, thereby sustaining most life on Earth."

Return JSON format:
{{
    "sentences": [
        {{
            "text": "first sentence here with proper commas for pauses",
            "topic": "{example_topic}",
            "difficulty": "{difficulty}"
        }},
        {{
            "text": "second sentence here with proper commas for pauses",
            "topic": "{alt_example_topic}",
            "difficulty": "{difficulty}"
        }},
        ... ({count} total sentences)
    ]
}}"""

    try:
        result = client.generate_json(
            prompt,
            temperature=0.9,
            max_output_tokens=2048
        )
        if result and 'sentences' in result:
            return result['sentences']
    except Exception as e:
        current_app.logger.error(f"Failed to generate dictation sentences batch: {e}")

    return None


def generate_dictation_sentence(
    client: GeminiClient,
    topic: Optional[str] = None,
    difficulty: str = 'medium'
) -> Optional[Dict]:
    """
    Generate a single complex academic sentence for dictation practice.

    Args:
        client: GeminiClient instance
        topic: Academic topic (e.g., "geology", "art history")
        difficulty: 'easy', 'medium', or 'hard'

    Returns:
        Dict with 'text', 'topic', 'difficulty' or None on failure
    """
    topics_pool = [
        'Biology', 'Astronomy', 'Geology', 'Art History', 'Psychology',
        'Economics', 'Anthropology', 'Environmental Science', 'Linguistics'
    ]

    if not topic:
        import random
        topic = random.choice(topics_pool)

    # Adjust complexity based on difficulty
    complexity_instructions = {
        'easy': 'Use simple sentence structure with common academic vocabulary.',
        'medium': 'Use moderate complexity with some specialized vocabulary and compound structure.',
        'hard': 'Use complex sentence structure with advanced vocabulary, subordinate clauses, and technical terms.'
    }

    prompt = f"""Generate ONE academic sentence for a university-level lecture on {topic}.

Requirements:
- Length: 15-25 words
- Content: Factually accurate, academically appropriate
- Style: NATURAL SPOKEN lecture style with proper pauses
  * Use commas for natural breathing pauses
  * Include transitional words (however, therefore, for example, etc.)
  * Sound like a real professor speaking clearly in a lecture
  * DO NOT use hesitations like "um", "uh", "you know" - speak clearly and professionally
  * Use natural academic pacing with pauses between clauses
- Complexity: {complexity_instructions.get(difficulty, complexity_instructions['medium'])}

Return JSON format:
{{
    "text": "the sentence here with proper commas for pauses",
    "topic": "{topic}",
    "difficulty": "{difficulty}"
}}

CRITICAL: Make the sentence sound like natural, clear academic speech that would be heard in an actual TOEFL exam.
The voice will be synthesized, so proper punctuation creates natural pauses.
Example style: "The process of photosynthesis, which occurs in plant cells, converts light energy into chemical energy, thereby sustaining most life on Earth."
"""

    try:
        result = client.generate_json(prompt, temperature=0.9)
        if result and 'text' in result:
            return result
    except Exception as e:
        current_app.logger.error(f"Failed to generate dictation sentence: {e}")

    return None


def generate_signpost_segments_batch(
    client: GeminiClient,
    count: int = 5,
    topic: Optional[str] = None
) -> Optional[List[Dict]]:
    """
    Generate multiple signpost exercises at once for better UX.

    Args:
        client: GeminiClient instance
        count: Number of signpost segments to generate (default 5)
        topic: Optional academic topic focus

    Returns:
        List of dicts with segment details or None on failure
    """
    import random

    # Select random signpost phrases from different categories
    selected_phrases = []
    categories_list = list(SIGNPOST_PHRASES.keys())

    for _ in range(count):
        category = random.choice(categories_list)
        phrase = random.choice(SIGNPOST_PHRASES[category])
        selected_phrases.append({'phrase': phrase, 'category': category})

    default_topics = [
        'Ancient Roman architecture',
        'Climate change effects',
        'Renaissance art',
        'Cognitive psychology',
        'Marine biology',
        'Economic theories',
        'Archaeological discoveries',
        'Quantum physics',
        'Literary movements',
        'Urban planning'
    ]

    phrases_list = ', '.join([f'"{p["phrase"]}" ({p["category"]})' for p in selected_phrases])

    if topic:
        topic_instruction = (
            f"All segments must relate to the broader academic area of {topic}. "
            "Vary the subtopics or contexts (for example: historical perspective, modern applications, key research, practical implications) "
            "so each exercise feels distinct while staying within this domain."
        )
        topics_line = ''
    else:
        topic_instruction = (
            "Choose a different academic topic for each segment from the curated list below."
        )
        topics_line = f"- Choose a unique academic topic from this list: {', '.join(default_topics)}\n"

    prompt = f"""Generate {count} DIFFERENT short segments (2-3 sentences each) from university lectures.

Each segment must include ONE of these signpost phrases naturally:
{phrases_list}

For EACH segment:
- {topic_instruction}
{topics_line}- Ensure the domain and examples feel authentic to the chosen topic
- Naturally include the assigned signpost phrase
- Make 2-3 clear, professional sentences with proper punctuation for pauses
- NO hesitations like "um", "uh" - speak clearly like real TOEFL audio
- Create a multiple-choice question about what the professor is about to do
- Provide 4 answer options (one correct, three distractors)
- Supply `explanation_cn` summarizing why the correct option matches (Simplified Chinese, ≤40 characters)
- Supply `option_explanations_cn` with EVERY option text as keys and ≤40 character Simplified Chinese rationales explaining why that option is correct or incorrect
- ALL other content (segment text, question, options) must remain in English. Chinese is ONLY allowed inside `explanation_cn` and `option_explanations_cn`.

Example: "Ancient civilizations developed complex irrigation systems. However, many of these techniques were lost over time. Today, archaeologists are rediscovering these methods."

Return JSON format:
{{
    "segments": [
        {{
            "text": "segment text with signpost phrase and proper punctuation",
            "signpost_phrase": "the exact signpost phrase used",
            "category": "the category (contrast/addition/etc)",
            "question_text": "What is the professor about to do?",
            "options": ["option1", "option2", "option3", "option4"],
            "correct_answer": "the correct option text",
            "explanation_cn": "Correct option rationale in Simplified Chinese",
            "option_explanations_cn": {{
                "option1": "为什么此选项正确或错误（简洁中文）",
                "option2": "为什么此选项正确或错误（简洁中文）",
                "option3": "为什么此选项正确或错误（简洁中文）",
                "option4": "为什么此选项正确或错误（简洁中文）"
            }}
        }},
        ... ({count} total segments)
    ]
}}"""

    try:
        result = client.generate_json(prompt, temperature=0.85)
        if result and 'segments' in result:
            return result['segments']
    except Exception as e:
        current_app.logger.error(f"Failed to generate signpost segments batch: {e}")

    return None


def generate_signpost_segment(
    client: GeminiClient,
    signpost_phrase: Optional[str] = None,
    category: Optional[str] = None
) -> Optional[Dict]:
    """
    Generate a 2-3 sentence segment containing a signpost phrase.

    Args:
        client: GeminiClient instance
        signpost_phrase: Specific phrase to use (optional)
        category: Category of signpost phrase (optional)

    Returns:
        Dict with segment details or None on failure
    """
    import random

    # Select signpost phrase if not provided
    if not signpost_phrase:
        if category and category in SIGNPOST_PHRASES:
            signpost_phrase = random.choice(SIGNPOST_PHRASES[category])
        else:
            # Pick random category and phrase
            category = random.choice(list(SIGNPOST_PHRASES.keys()))
            signpost_phrase = random.choice(SIGNPOST_PHRASES[category])

    # Determine category if not provided
    if not category:
        for cat, phrases in SIGNPOST_PHRASES.items():
            if signpost_phrase in phrases:
                category = cat
                break

    topics = [
        'Ancient Roman architecture',
        'Climate change effects',
        'Renaissance art',
        'Cognitive psychology',
        'Marine biology',
        'Economic theories',
        'Archaeological discoveries'
    ]

    topic = random.choice(topics)

    prompt = f"""Generate a SHORT segment (2-3 sentences) from a university lecture on {topic}.

CRITICAL REQUIREMENT: The segment MUST naturally include this exact phrase: "{signpost_phrase}"

The phrase should:
- Appear naturally in the flow of the lecture
- Signal a transition in the lecture structure
- Be followed or preceded by relevant content
- Be spoken CLEARLY with proper pauses (use commas)

Example structure:
- Sentence 1: Introduce a concept
- Sentence 2: Use "{signpost_phrase}" to transition
- Sentence 3: Continue with the new point

Speech Style Requirements:
- Clear, professional academic speaking
- NO hesitations like "um", "uh", "you know"
- Use commas for natural pauses between clauses
- Sound like a real TOEFL exam lecture recording

Also create a multiple-choice question:
- Question: "What is the professor about to do?" or "What does this phrase signal?"
- 4 answer options (one correct, three distractors)
- Correct answer should reflect the signpost function
- Provide `explanation_cn` summarizing why the correct option is right (Simplified Chinese, ≤40 characters)
- Provide `option_explanations_cn` with EVERY option mapped to a ≤40 character Simplified Chinese rationale explaining why it is correct or incorrect
- ALL other text (segment, question, options) must stay in English. Chinese is ONLY allowed inside `explanation_cn` and `option_explanations_cn`.

Return JSON format:
{{
    "text": "the full segment with proper punctuation for natural pauses",
    "signpost_phrase": "{signpost_phrase}",
    "category": "{category}",
    "question_text": "What is the professor about to do?",
    "options": ["option1", "option2", "option3", "option4"],
    "correct_answer": "the correct option text",
    "explanation_cn": "简洁说明正确选项原因（中文）",
    "option_explanations_cn": {{
        "option1": "中文解析，说明选项正确或错误原因",
        "option2": "中文解析，说明选项正确或错误原因",
        "option3": "中文解析，说明选项正确或错误原因",
        "option4": "中文解析，说明选项正确或错误原因"
    }}
}}

Example of good style: "Ancient civilizations developed complex irrigation systems. However, many of these techniques were lost over time. Today, archaeologists are rediscovering these methods."
"""

    try:
        result = client.generate_json(prompt, temperature=0.85)
        if result and 'text' in result:
            return result
    except Exception as e:
        current_app.logger.error(f"Failed to generate signpost segment: {e}")

    return None


def generate_lecture(
    client: GeminiClient,
    topic: str,
    duration_target: str = '6 minutes'
) -> Optional[Dict]:
    """
    Generate a full 5-minute lecture (approximately 500 words).

    Args:
        client: GeminiClient instance
        topic: Academic topic for the lecture
        duration_target: Target duration (e.g., '5 minutes')

    Returns:
        Dict with lecture transcript, questions, and expert notes or None on failure
    """
    prompt = f"""Generate a complete {duration_target} university lecture on {topic}.

CRITICAL LENGTH REQUIREMENT: The transcript MUST be BETWEEN 620 and 680 words to ensure a full 6-minute lecture.
Do NOT include parenthetical word counts or any meta commentary (e.g., "(300 words)") anywhere in the transcript, questions, or notes.

Requirements:
- Length: 620-680 words (for a natural 6-minute lecture at ~105-115 words/minute)
- Style: NATURAL PROFESSIONAL LECTURE SPEECH (like actual TOEFL recordings):
  * Clear, well-paced academic speaking
  * Use commas and periods for natural pauses
  * Rhetorical questions for engagement
  * Transitions and signpost phrases (However, Therefore, For example, etc.)
  * Professor addressing students directly
  * NO hesitations like "um", "uh", "you know" - speak professionally
  * Sound like a real university professor in a recorded lecture
- Content: Well-structured with clear introduction, body, and conclusion
- Accuracy: Factually correct academic content

CRITICAL VOICE QUALITY: This will be converted to audio. Use proper punctuation (commas, periods)
to create natural pauses. The speech should sound like actual TOEFL exam audio - clear, professional,
well-paced academic English.

Also generate:
1. **5-6 TOEFL-style questions** (multiple choice):
   - Mix of question types: main idea, detail, inference, purpose, attitude
   - Each question should have 4 options
   - Include explanation for correct answer (Simplified Chinese, ≤70 characters)
   - Include explanations for why each distractor is wrong (Simplified Chinese, ≤70 characters each)
   - Provide `distractor_explanations` keyed by the EXACT option text
   - ALL question text, options, transcript quotes, and notes must remain in English. Chinese is ONLY allowed inside the explanation fields.
   - CRITICAL: For each question, identify the EXACT portion of the transcript that contains the answer
     and provide approximate timestamps (in seconds) where this information appears

2. **Expert Notes** (ideal note-taking):
   - Concise, well-organized notes
   - Key points only
   - Use abbreviations and symbols
   - Structured format (bullet points, indentation)

Return JSON format:
{{
    "title": "Clear lecture title",
    "topic": "{topic}",
    "transcript": "Full lecture transcript...",
    "questions": [
        {{
            "question_text": "What is the main topic of the lecture?",
            "question_type": "main_idea",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "A",
            "explanation": "Why A is correct",
            "distractor_explanations": {{
                "B": "Why B is wrong",
                "C": "Why C is wrong",
                "D": "Why D is wrong"
            }},
            "transcript_quote": "The exact portion of transcript containing the answer",
            "answer_time_range": {{
                "start": 45.0,
                "end": 60.0
            }}
        }}
    ],
    "expert_notes": "# Topic\\n- Main point 1\\n  - Detail\\n- Main point 2\\n..."
}}

IMPORTANT: Be precise with answer_time_range. Consider:
- Introduction typically: 0-45 seconds
- Main body: 45-320 seconds
- Conclusion: 320-360 seconds
Estimate based on position in the 500-word transcript."""

    def _word_count_distance(count: int) -> int:
        if LECTURE_WORD_COUNT_MIN <= count <= LECTURE_WORD_COUNT_MAX:
            return 0
        if count < LECTURE_WORD_COUNT_MIN:
            return LECTURE_WORD_COUNT_MIN - count
        return count - LECTURE_WORD_COUNT_MAX

    def _refine_length(initial_payload: Dict, word_count: int) -> Optional[Dict]:
        """Ask Gemini to expand or tighten the lecture to hit the target range."""
        try:
            refinement_prompt = f"""You generated a lecture on {topic}, but the transcript length was {word_count} words.
Revise the entire lecture package so the transcript is BETWEEN {LECTURE_WORD_COUNT_MIN} and {LECTURE_WORD_COUNT_MAX} words.
- Preserve academic accuracy and natural spoken lecture style.
- Update questions, transcript quotes, timestamps, and expert notes so they stay consistent with the revised transcript.
- Maintain the same JSON structure and field names as the ORIGINAL payload.

Return ONLY valid JSON.

Original JSON (for reference):
{json.dumps(initial_payload)}
"""
            refined = client.generate_json(
                refinement_prompt,
                temperature=0.7,
                max_output_tokens=8192
            )
            return refined
        except Exception as exc:
            current_app.logger.error(f"Failed to refine lecture length: {exc}")
            return None

    best_result: Optional[Dict] = None
    best_distance = float("inf")

    try:
        for attempt in range(3):
            result = client.generate_json(
                prompt,
                temperature=0.85,
                max_output_tokens=8192  # Increased to accommodate full 600+ word lectures
            )

            if result and 'transcript' in result:
                transcript = result.get('transcript', '')
                word_count = len(transcript.split())

                questions = result.get('questions', [])
                if len(questions) < 5:
                    current_app.logger.warning(
                        f"Generated only {len(questions)} questions, expected 5-6 (attempt {attempt + 1})"
                    )
                    continue

                distance = _word_count_distance(word_count)
                if distance == 0:
                    return result

                current_app.logger.warning(
                    f"Lecture transcript length {word_count} outside target range (attempt {attempt + 1})"
                )

                refined = _refine_length(result, word_count)
                if refined and 'transcript' in refined:
                    refined_transcript = refined.get('transcript', '')
                    refined_count = len(refined_transcript.split())
                    refined_questions = refined.get('questions', [])
                    if len(refined_questions) >= 5 and _word_count_distance(refined_count) == 0:
                        current_app.logger.info(
                            f"Lecture refined to {refined_count} words after attempt {attempt + 1}"
                        )
                        return refined

                    # Track refined candidate if it improved the distance
                    refined_distance = _word_count_distance(refined_count)
                    if refined_distance < distance and len(refined_questions) >= 5:
                        best_result = refined
                        best_distance = refined_distance

                if distance < best_distance:
                    best_result = result
                    best_distance = distance

                if LECTURE_WORD_COUNT_RELAXED_MIN <= word_count <= LECTURE_WORD_COUNT_RELAXED_MAX:
                    current_app.logger.warning(
                        "Using lecture outside strict range but within relaxed bounds after %s attempts.",
                        attempt + 1
                    )
                    return result
    except Exception as e:
        current_app.logger.error(f"Failed to generate lecture: {e}")

    if best_result:
        best_transcript = best_result.get('transcript', '') if isinstance(best_result, dict) else ''
        best_word_count = len(best_transcript.split()) if best_transcript else 0
        if LECTURE_WORD_COUNT_RELAXED_MIN <= best_word_count <= LECTURE_WORD_COUNT_RELAXED_MAX:
            current_app.logger.warning(
                "Falling back to best lecture candidate (%s words) after refinement attempts.",
                best_word_count
            )
            return best_result

    return None


def generate_conversation(
    client: GeminiClient,
    situation: str = "office hours"
) -> Optional[Dict]:
    """
    Generate a 3-minute conversation between student and professor.

    Args:
        client: GeminiClient instance
        situation: Type of conversation (e.g., "office hours", "advising session")

    Returns:
        Dict with conversation transcript, questions, and expert notes or None on failure
    """
    situations_map = {
        'office hours': 'Student visits professor during office hours to discuss course content',
        'advising session': 'Student meets with advisor to discuss academic plans',
        'research discussion': 'Student discusses research project with professor',
        'assignment help': 'Student asks for clarification about an assignment'
    }

    situation_description = situations_map.get(situation, situations_map['office hours'])

    prompt = f"""Generate a complete 2-minute conversation between a university student and professor.

CRITICAL LENGTH REQUIREMENT: The transcript MUST be BETWEEN 230 and 270 words to ensure a natural 2-minute conversation.
Do NOT include parenthetical word counts or meta notes like "(300 words)" anywhere in the transcript, questions, or notes.

Situation: {situation_description}

Requirements:
- Length: 230-270 words (for ~2-minute conversation at 115-130 words/minute)
- Format: Clear speaker labels [Professor] and [Student]
- Style: NATURAL PROFESSIONAL CONVERSATION (like actual TOEFL recordings):
  * Clear, realistic academic dialogue
  * Back-and-forth exchange (not monologues)
  * Student asks questions, expresses concerns
  * Professor explains clearly and checks understanding
  * Use commas and periods for natural speech pauses
  * NO filler words like "um", "uh", "you know" - speak clearly
  * Sound like a real recorded university office hours conversation
- Content: Academically relevant topic

CRITICAL VOICE QUALITY: This will be converted to audio. Use proper punctuation for natural pauses.
The dialogue should sound like actual TOEFL exam conversation audio - clear, professional exchanges
between professor and student.

Also generate:
1. **5-6 TOEFL-style questions**:
   - Focus on: main purpose, details, speaker attitude, implied meaning
   - Each with 4 options
   - Include explanation for correct answer (Simplified Chinese, ≤70 characters)
   - Include explanations for each distractor (Simplified Chinese, ≤70 characters each)
   - Provide `distractor_explanations` keyed by the EXACT option text
   - ALL transcript text, questions, options, and notes must remain in English. Chinese is ONLY allowed inside the explanation fields.
   - Provide approximate timestamps for where answer appears

2. **Expert Notes**:
   - Capture key points from the conversation
   - Note student main concern/question
   - Note professor main advice/explanation

Return JSON format:
{{
    "title": "Conversation title",
    "situation": "{situation}",
    "transcript": "[Professor] Welcome! What can I help you with?\\n[Student] Hi, I was wondering...",
    "questions": [
        {{
            "question_text": "Why does the student visit the professor?",
            "question_type": "purpose",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "A",
            "explanation": "Why A is correct",
            "distractor_explanations": {{
                "B": "Why B is wrong",
                "C": "Why C is wrong",
                "D": "Why D is wrong"
            }},
            "transcript_quote": "Relevant portion from transcript",
            "answer_time_range": {{
                "start": 5.0,
                "end": 15.0
            }}
        }}
    ],
    "expert_notes": "Student issue: ...\\nProfessor advice: ..."
}}

Estimate timestamps based on ~300 words in 180 seconds.
"""

    try:
        for attempt in range(3):
            result = client.generate_json(
                prompt,
                temperature=0.85,
                max_output_tokens=6144
            )

            if result and 'transcript' in result:
                transcript = result.get('transcript', '')
                word_count = len(transcript.split())
                if word_count < 220 or word_count > 300:
                    current_app.logger.warning(
                        f"Conversation transcript length {word_count} outside target range (attempt {attempt + 1})"
                    )
                    continue

                questions = result.get('questions', [])
                if len(questions) < 5:
                    current_app.logger.warning(
                        f"Generated only {len(questions)} questions, expected 5-6 (attempt {attempt + 1})"
                    )
                    continue

                return result
    except Exception as e:
        current_app.logger.error(f"Failed to generate conversation: {e}")

    return None


def find_answer_timestamps(
    transcript: str,
    word_timestamps: List[Dict],
    answer_quote: str
) -> Optional[Dict[str, float]]:
    """
    Find the exact timestamps for a portion of text in the transcript.

    Args:
        transcript: Full transcript
        word_timestamps: List of {word, start, end} dicts
        answer_quote: The text quote to find

    Returns:
        Dict with 'start' and 'end' timestamps, or None if not found
    """
    if not word_timestamps or not answer_quote:
        return None

    # Normalize texts for comparison
    transcript_lower = transcript.lower()
    quote_lower = answer_quote.lower()

    # Find quote in transcript
    pos = transcript_lower.find(quote_lower)
    if pos == -1:
        current_app.logger.warning(f"Could not find answer quote in transcript")
        return None

    # Count words before the quote to find starting word index
    words_before = transcript[:pos].split()
    start_word_index = len(words_before)

    # Count words in the quote
    quote_words = answer_quote.split()
    end_word_index = start_word_index + len(quote_words)

    # Get timestamps from word_timestamps
    if start_word_index < len(word_timestamps) and end_word_index <= len(word_timestamps):
        start_time = word_timestamps[start_word_index]['start']
        end_time = word_timestamps[end_word_index - 1]['end']

        return {
            'start': start_time,
            'end': end_time
        }

    return None
