# TOEFL Learning Application - Comprehensive Codebase Architecture Analysis

## Executive Summary

This is a sophisticated **Flask-based TOEFL preparation application** that integrates AI-powered learning features across vocabulary, reading, listening, speaking, and writing modules. The application uses a monolithic architecture with server-side rendering, SQLAlchemy ORM for database persistence, and multiple AI service integrations (primarily Google Gemini API).

**Key Characteristics:**
- 3979 lines in main app.py with 70+ routes
- SQLite database with 15+ models
- Heavy reliance on Gemini 2.5 Flash API for content generation and analysis
- Sophisticated audio processing for listening and speaking modules
- Multi-phase learning flows (deconstruction → drafting → feedback)

---

## 1. PROJECT STRUCTURE & ORGANIZATION

### Directory Layout
```
/workspace/TOEFL/
├── app/
│   └── flask_app/                  # Main Flask application
│       ├── app.py                  # 3979 lines - ALL routes & main logic
│       ├── config.py               # Flask configuration (development/production)
│       ├── models.py               # 15+ SQLAlchemy database models
│       ├── scheduler.py            # SM-2 spaced repetition algorithm
│       ├── utils.py                # Helper functions (auth, queries, progress tracking)
│       ├── requirements.txt        # Python dependencies
│       ├── services/               # AI & audio service modules
│       ├── static/                 # Assets (audio, uploads, CSS, JS)
│       ├── templates/              # Jinja2 HTML templates
│       ├── instance/               # SQLite database files (local)
│       └── tests/                  # Unit tests
├── data/seeds/                     # CSV vocabulary data
└── README.md, WRITING.md, LISTENING_IMPLEMENTATION.md, etc.
```

### Technology Stack
| Component | Technology |
|-----------|-----------|
| Backend Framework | Flask 3.0 (Python) |
| Database | SQLite with Flask-SQLAlchemy |
| Frontend | Jinja2 templates + Bootstrap 5.3 |
| Authentication | Flask sessions + bcrypt |
| Spaced Repetition | SM-2 algorithm (scheduler.py) |
| AI Services | Google Gemini 2.5 Flash API |
| Audio Processing | gTTS, OpenAI Whisper, Praat Parselmouth, librosa |
| Text-to-Speech | Kokoro (natural voice), gTTS |
| Deep Learning | PyTorch 2.8.0 + Transformers |
| HTTP Requests | requests, Flask-CORS |

---

## 2. EXISTING FEATURES BY MODULE

### A. VOCABULARY MODULE (Core Feature)
**Routes:** `/session`, `/session/<session_id>/grade`, `/vocab/*`, `/test/unfamiliar-words`

**Features:**
- Spaced repetition learning with SM-2 algorithm
- 3-response grading system: "Recognize" (complete mastery), "Barely" (partial recall), "Not Yet" (unfamiliar)
- Session management with in-memory queue deque structure
- Progress tracking: mastery breakdown, memorization curve, study streaks
- Pronunciation audio generation on-demand (cached in `/static/audio/`)
- Unfamiliar words tracking (separate learning list)
- Daily goal configuration (1-1000 words/day)

**Key Models:**
- `User` - Basic account with daily_goal, created_at
- `Word` - Vocabulary entries with definition, example, cn_gloss, pronunciation_audio_url
- `UserWord` - Spaced repetition state (easiness, interval, repetitions, next_due)
- `ReviewLog` - Each review attempt with grade, latency_ms, algorithm state

### B. READING MODULE
**Routes:** `/reading/*`, `/exercises/reading`, `/reading/question-types/*`

**Features:**
- 3 reading difficulty levels: sentence, paragraph, passage
- Question type library with learning & practice modes
- Paraphrase evaluation with Gemini
- Custom question generation based on selected topics
- Reading comprehension exercises with synonym support

**Key Models:**
- Implicit question storage (via drill_store service)

### C. LISTENING MODULE
**Routes:** `/listening/*`, `/listening/dictation`, `/listening/signpost`, `/listening/lecture`, `/listening/conversation`

**Features:**
- **Dictation training** - Single sentences with word-level timestamps
- **Signpost training** - 2-3 sentence segments with discourse markers (contrast, addition, example, etc.)
- **Lecture simulation** - Full 5-minute academic lectures with comprehension questions
- **Conversation simulation** - 3-minute student-professor dialogues
- All audio generated via Gemini + text-to-speech (Kokoro/gTTS)
- Word-level timestamp generation for precise answer location lookup

**Key Models:**
- `ListeningSentence` - Individual sentences with audio_url, word_timestamps, difficulty
- `ListeningSignpost` - 2-3 sentence segments with signpost_phrase (contrast/addition/etc), question, options, explanation_cn
- `ListeningLecture` - Full lectures with title, topic, transcript, questions, expert_notes
- `ListeningConversation` - Student-professor dialogues with situation context
- `ListeningQuestion` - Questions linked to lecture/conversation with question_type, options, correct_answer, explanation
- `ListeningUserProgress` - User progress tracking per listening item

### D. SPEAKING MODULE
**Routes:** `/speaking/*`, `/speaking/task/<int:task_number>/*`

**Features:**
- 6 independent speaking tasks
- Audio recording upload (WebM format saved to `/static/uploads/speaking/`)
- Speech transcription via OpenAI Whisper
- Comprehensive rating across multiple dimensions:
  - Delivery (fluency, rhythm, pronunciation, stress)
  - Vocabulary & grammar analysis
  - Topic development assessment
  - Academic word usage tracking
- Real-time feedback generation via Gemini

**Key Models:**
- `SpeakingTask` - Task prompts with difficulty, time_limit
- `SpeakingResponse` - Audio submissions with transcription, attempt_number
- `SpeakingFeedback` - Detailed analysis with multiple score components

**Key Services:**
- `speech_rater.py` - Whisper transcription + speech metrics extraction
- `speaking_feedback_engine.py` - Language use and topic development analysis
- `speaking_generator.py` - Task prompt generation via Gemini
- `tts_service.py` - Text-to-speech via Kokoro/gTTS

### E. WRITING MODULE (Most Sophisticated)
**Routes:** `/writing/*`, `/writing/task/*`, `/writing/practice/*`, `/writing/feedback/*`, `/writing/api/paraphrase`

**Features - Two Task Types:**

**1. Integrated Writing Task (20 minutes)**
- Reading passage + listening audio → summarize & integrate
- AI deconstruction of reading/listening points
- Real-time paraphrasing assistant during drafting
- Point coverage evaluation

**2. Independent Writing Task (Academic Discussion)**
- Essay prompt with stance taking
- AI outline generation with thesis & supporting points
- Time-limited drafting environment

**Unified Feedback System (Both Tasks):**
- TOEFL-style scoring (0-30 scale):
  - Content & Development (0-5)
  - Organization & Structure (0-5)
  - Vocabulary & Language Use (0-5)
  - Grammar & Mechanics (0-5)
- In-line annotations with color-coded highlights:
  - Vague statements
  - Lexical issues
  - Grammar errors
  - Cohesion problems
- Categorized feedback:
  - Strengths & improvements
  - Grammar issues with corrections
  - Vocabulary enhancement suggestions
  - Organization notes
  - Content suggestions
- Revision tracking (multiple attempts with parent_response_id linking)

**Key Models:**
- `WritingTask` - Task definition with task_type (integrated/discussion), topic, prompt, reading_text, listening_audio_url, listening_transcript, deconstruction_data, outline_data, word_limit, time_limit_minutes
- `WritingResponse` - User essay submissions with essay_text, word_count, time_spent_seconds, attempt_number, is_revised, parent_response_id
- `WritingFeedback` - Comprehensive AI analysis with:
  - Rubric scores (overall_score, content_development_score, organization_structure_score, vocabulary_language_score, grammar_mechanics_score)
  - Annotations (JSON array of highlighted issues)
  - Coach summary, strengths, improvements
  - Grammar issues, vocabulary suggestions
  - Content accuracy, point coverage, example accuracy, paraphrase quality, source integration

**Key Services:**
- `writing_generator.py` - Task generation by type via Gemini
- `writing_analyzer.py` - Essay analysis with comprehensive feedback generation

### F. SUPPORTING FEATURES
- **Dashboard** - User progress overview across all modules
- **Word search** - Full-text vocabulary search
- **Exercise hub** - Centralized access to post-session drills
- **Settings** - Daily goal configuration, account management

---

## 3. DATABASE MODELS (Complete List)

### Authentication & Vocabulary
| Model | Purpose | Key Fields |
|-------|---------|-----------|
| `User` | User accounts | id, email, password_hash, daily_goal, created_at |
| `Word` | Vocabulary entries | id, lemma, definition, example, cn_gloss, pronunciation_audio_url, pronunciation_pitfall_cn |
| `UserWord` | Spaced repetition state | user_id, word_id, easiness, interval, repetitions, next_due, last_grade, updated_at |
| `ReviewLog` | Review history | user_id, word_id, grade, latency_ms, is_new, easiness, interval, created_at |
| `UnfamiliarWord` | User-marked unfamiliar words | user_id, word_text, context, source, created_at |

### Listening
| Model | Purpose | Key Fields |
|-------|---------|-----------|
| `ListeningSentence` | Single sentences | text, topic, difficulty, audio_url, audio_duration_seconds, word_timestamps |
| `ListeningSignpost` | Discourse marker segments | text, signpost_phrase, signpost_category, audio_url, question_text, options, correct_answer, explanation_cn, option_explanations_cn |
| `ListeningLecture` | Full lectures | title, topic, transcript, audio_url, audio_duration_seconds, word_timestamps, expert_notes |
| `ListeningConversation` | Student-professor dialogues | title, situation, transcript, audio_url, audio_duration_seconds, word_timestamps, expert_notes |
| `ListeningQuestion` | Comprehension questions | lecture_id/conversation_id, question_order, question_text, question_type, options, correct_answer, explanation, distractor_explanations, answer_start_time, answer_end_time |
| `ListeningUserProgress` | User listening progress | user_id, listening_type (sentence/signpost/lecture/conversation), listening_id, status, score, completed_at |

### Speaking
| Model | Purpose | Key Fields |
|-------|---------|-----------|
| `SpeakingTask` | Speaking prompts | task_number (1-6), prompt, difficulty, time_limit_minutes |
| `SpeakingResponse` | Audio submissions | user_id, task_id, audio_url, transcription, attempt_number, delivery_score, fluency_score, pronunciation_score, rhythm_score, grammar_score, vocabulary_score, topic_development_score, overall_score, word_count, created_at |
| `SpeakingFeedback` | Detailed analysis | response_id, overall_score, delivery_score, fluency_score, pronunciation_score, grammar_score, vocabulary_score, topic_development_score, delivery_strengths, delivery_improvements, grammar_issues, vocabulary_suggestions, topic_feedback, pronunciation_notes, specific_feedback |

### Writing
| Model | Purpose | Key Fields |
|-------|---------|-----------|
| `WritingTask` | Writing task prompts | task_type (integrated/discussion), topic, prompt, reading_text, listening_audio_url, listening_transcript, deconstruction_data (JSON), outline_data (JSON), word_limit, time_limit_minutes |
| `WritingResponse` | Essay submissions | user_id, task_id, essay_text, word_count, time_spent_seconds, attempt_number, is_revised, parent_response_id |
| `WritingFeedback` | Essay analysis | response_id, overall_score, content_development_score, organization_structure_score, vocabulary_language_score, grammar_mechanics_score, annotations (JSON), coach_summary, strengths (JSON), improvements (JSON), grammar_issues (JSON), vocabulary_suggestions (JSON), organization_notes (JSON), content_suggestions (JSON), content_accuracy, point_coverage (JSON), example_accuracy, paraphrase_quality, source_integration |

---

## 4. ROUTE ORGANIZATION IN app.py

### Authentication Routes (3979 line file structure)
```python
GET/POST /                          # Index/home
GET/POST /register                  # User registration
GET/POST /login                     # User login
GET      /logout                    # Logout
```

### Dashboard Routes
```python
GET      /dashboard                 # Main dashboard (all modules overview)
GET      /vocab/dashboard           # Vocabulary dashboard
GET      /reading/dashboard         # Reading dashboard
GET      /listening/dashboard       # Listening dashboard
GET      /speaking/dashboard        # Speaking dashboard
GET      /writing/dashboard         # Writing dashboard
GET      /api/dashboard             # Dashboard data API
```

### Vocabulary Routes
```python
GET      /session                   # Start new spaced repetition session
POST     /session/<session_id>/grade # Submit card response
GET      /words                     # Browse all words
GET      /search                    # Search vocabulary
GET      /vocab/unfamiliar-words    # View unfamiliar words list
GET      /test/unfamiliar-words     # Practice unfamiliar words
GET      /api/unfamiliar-words      # Get unfamiliar words (API)
POST     /api/unfamiliar-words      # Add unfamiliar word (API)
DELETE   /api/unfamiliar-words/<int:word_id> # Remove unfamiliar word
```

### Reading Routes
```python
GET      /reading                   # Reading home page
GET      /reading/dashboard         # Reading dashboard
GET      /reading/practice/<practice_type> # Practice page (sentence/paragraph/passage)
POST     /reading/practice/<practice_type>/generate # Generate batch
POST     /reading/practice/<practice_type>/navigate # Navigate through batch
GET      /reading/api/sentence      # Get single sentence (API)
GET      /reading/api/paragraph     # Get paragraph (API)
GET      /reading/api/passage       # Get passage (API)
POST     /reading/api/paraphrase    # Evaluate paraphrase (API)
GET      /reading/api/bootstrap     # Initialize reading session (API)
POST     /exercises/api/reading/generate # Generate reading passage
GET      /reading/question-types    # Question types hub
GET      /reading/question-types/<question_type_id>/learn # Learn question type
GET      /reading/question-types/<question_type_id>/practice # Practice question type
POST     /reading/api/question-types/<question_type_id>/generate # Generate drill
POST     /reading/api/question-types/<question_type_id>/navigate # Navigate drill
POST     /reading/api/question-types/<question_type_id>/regenerate # Regenerate drill
GET      /exercises/gap-fill        # Gap-fill exercise page
POST     /exercises/api/gap-fill/generate # Generate gap-fill batch
GET      /exercises/synonym-showdown # Synonym exercise page
POST     /exercises/api/synonym/generate # Generate synonym batch
GET      /exercises/reading         # Reading immersion exercise page
```

### Listening Routes
```python
GET      /listening/dictation       # Dictation trainer page
POST     /listening/api/dictation/generate # Generate sentence batch
GET      /listening/api/dictation/<int:sentence_id> # Get sentence (API)
POST     /listening/api/dictation/<int:sentence_id>/submit # Submit answer
GET      /listening/signpost        # Signpost trainer page
POST     /listening/api/signpost/generate # Generate signpost batch
POST     /listening/api/signpost/next # Get next signpost
POST     /listening/api/signpost/<int:signpost_id>/submit # Submit signpost answer
GET      /listening/lecture         # Lecture simulator page
POST     /listening/api/lecture/generate # Generate lecture
POST     /listening/api/lecture/<int:lecture_id>/submit # Submit lecture answers
GET      /listening/conversation    # Conversation simulator page
POST     /listening/api/conversation/generate # Generate conversation
POST     /listening/api/conversation/<int:conversation_id>/submit # Submit conversation answers
```

### Speaking Routes
```python
GET      /speaking                  # Speaking dashboard
GET/POST /speaking/dashboard        # Speaking dashboard
GET      /speaking/task/<int:task_number>/start # Start task
GET      /speaking/task/<int:task_number>/regenerate # Regenerate task prompt
GET      /speaking/task/<int:task_number>/generate # Generate task
GET      /speaking/task/<int:task_number>/check # Get current task
POST     /speaking/task/<int:task_id>/submit # Submit audio response
GET      /speaking/task/<int:task_id>/feedback # View feedback
```

### Writing Routes
```python
GET      /writing                   # Writing dashboard
GET/POST /writing/dashboard         # Writing dashboard
GET      /writing/task/<task_type>/generate # Generate new task (integrated/discussion)
GET      /writing/practice/<int:task_id> # Writing practice page (all phases)
POST     /writing/task/<int:task_id>/submit # Submit essay
GET      /writing/feedback/<int:response_id> # View feedback
POST     /writing/api/paraphrase    # Real-time paraphrasing assistant
```

### Utility Routes
```python
GET      /exercises                 # Exercise hub
GET      /loading                   # Loading page
GET      /settings                  # Settings page
POST     /settings                  # Update settings
POST     /api/daily-goal            # Update daily goal (API)
```

---

## 5. SERVICES DIRECTORY - AI & AUDIO INTEGRATION

### Core AI Service: `gemini_client.py`
**Purpose:** Centralized Gemini API wrapper

**Key Methods:**
- `generate_json(prompt, temperature, system_instruction, response_mime, max_output_tokens)` - Main method for structured content generation
- `generate(prompt, ...)` - Unstructured text generation
- Automatic retry logic with exponential backoff (5 retries, 1.5-30s delays)
- Error handling with fallback model support
- Configurable timeouts & model selection

**Configuration:**
```python
DEFAULT_MODEL = "gemini-2.5-flash-lite"
DEFAULT_API_KEY = "AIzaSyAJrbPs_fr5hUqt08qUAporCHztsoZgFzE"  # Public demo key
FALLBACK_MODEL = "gemini-2.5-flash"
DEFAULT_TIMEOUT = 40 seconds
```

**Usage Pattern:**
```python
client = get_gemini_client()
result = client.generate_json(
    prompt="Your prompt here",
    system_instruction="Optional system instruction",
    response_mime="application/json",  # For structured responses
    max_output_tokens=4096
)
```

### Content Generation Services

#### `listening_generator.py` (32KB)
**Functions:**
- `generate_dictation_sentence(topic, difficulty)` - Single sentence generation
- `generate_dictation_sentences_batch(topic, count, difficulty)` - Batch generation
- `generate_signpost_segment(category)` - 2-3 sentences with discourse marker
- `generate_signpost_segments_batch(categories, count)` - Batch signpost generation
- `generate_lecture(topic, duration)` - Full 5-minute lecture generation
- `generate_conversation(situation, num_turns)` - Student-professor dialogue generation
- `find_answer_timestamps(transcript, answer_text)` - Locate answer in transcript

**AI Integration:**
- All content generated via Gemini with JSON response parsing
- Audio generation via Kokoro TTS (natural voices)
- Word-level timestamp generation for precise answer location

#### `speaking_generator.py` (16KB)
**Functions:**
- `generate_task_by_number(task_number)` - Generate prompt for tasks 1-6
- `generate_task_batch(count)` - Batch task generation
- AI prompt generation via Gemini with structured output

#### `writing_generator.py` (9KB)
**Functions:**
- `generate_task_by_type(task_type)` - Generate integrated or discussion task
- Reading/listening content integration
- Deconstruction data generation (extracted key points)
- Outline data generation (thesis, supporting arguments)

#### `exercise_generator.py` (9KB)
**Functions:**
- `generate_gap_fill_single(topic, word)` - Single gap-fill exercise
- `generate_synonym_single(word)` - Synonym multiple choice
- `generate_reading_passage_single(topic)` - Reading comprehension passage
- All use Gemini for content with JSON response parsing

#### `question_types.py` (29KB)
**Functions:**
- `generate_question_type_drill(question_type_id, count)` - Generate questions for specific type
- `get_question_types_by_category(category)` - Get available question types
- `get_question_type_metadata(question_type_id)` - Get question type details
- Supports 10+ reading comprehension question types

#### `reading_content.py` (25KB)
**Functions:**
- `get_sentence(topic)` - Get reading sentence
- `get_paragraph(topic)` - Get reading paragraph
- `get_passage(topic)` - Get reading passage
- `evaluate_paraphrase(original, paraphrase)` - Compare paraphrase quality via Gemini

### Analysis & Feedback Services

#### `writing_analyzer.py` (31KB - Most Complex)
**Key Methods:**
- `analyze_essay(essay_text, task_type, prompt, reading_text, listening_transcript)` - Main analysis
- `generate_paraphrases(sentence, count)` - Real-time paraphrasing assistant
- `_call_llm_for_analysis()` - Calls Gemini with complex prompt
- `_normalize_feedback()` - Parses and normalizes LLM output

**Returns:**
```python
{
    'overall_score': float,  # 0-30
    'content_development_score': float,
    'organization_structure_score': float,
    'vocabulary_language_score': float,
    'grammar_mechanics_score': float,
    'annotations': [
        {
            'type': 'vague|lexical|grammar|cohesion',
            'text': 'highlighted text',
            'comment': 'feedback message',
            'start': int,
            'end': int
        }
    ],
    'coach_summary': str,
    'strengths': [str],
    'improvements': [str],
    'grammar_issues': [{'issue': str, 'correction': str}],
    'vocabulary_suggestions': [str],
    'organization_notes': [str],
    'content_suggestions': [str],
    'content_accuracy': str,
    'point_coverage': [{'point': str, 'status': 'covered|partially_covered|missing'}],
    'paraphrase_quality': str,
    'source_integration': str
}
```

#### `speech_rater.py` (25KB)
**Methods:**
- `rate_speech(audio_path)` - Rate speech with Whisper + analysis
- `_transcribe_with_whisper()` - OpenAI Whisper transcription
- `_extract_prosody_metrics()` - Extract fluency, rhythm, pronunciation using Praat Parselmouth
- `_analyze_grammar_and_vocabulary()` - Grammar analysis via Gemini
- `_analyze_topic_development()` - Topic quality via Gemini

**Returns:**
```python
{
    'transcription': str,
    'overall_score': float,
    'delivery_score': float,  # fluency + rhythm + pronunciation
    'grammar_score': float,
    'vocabulary_score': float,
    'topic_development_score': float,
    'metrics': {
        'fluency_rate': float,  # words per minute
        'rhythm_regularity': float,
        'pronunciation_accuracy': float,
        'stress_patterns': str,
        'total_duration': float
    },
    'strengths': [str],
    'improvements': [str],
    'specific_feedback': [str]
}
```

#### `speaking_feedback_engine.py` (12KB)
**Methods:**
- `analyze_language_use(transcription)` - Language complexity analysis
- `analyze_topic_development(transcription, prompt)` - Content quality analysis
- Uses Academic Word List (AWL) for lexical diversity scoring

### Supporting Services

#### `tts_service.py` (25KB)
**Methods:**
- `synthesize(text, speaker, lang)` - Text-to-speech generation
- Uses Kokoro (natural voices) as primary, gTTS as fallback
- Caches audio files for reuse

#### `audio.py` (1.6KB)
**Functions:**
- `ensure_pronunciation_audio(word)` - Generate/retrieve pronunciation audio

#### `drill_store.py` (2.2KB)
**Functions:**
- `set_drill(drill_id, drill_data)` - Store drill in-memory or database
- `get_drill(drill_id)` - Retrieve stored drill
- `update_drill(drill_id, drill_data)` - Update drill data
- `delete_drill(drill_id)` - Remove drill

#### `locale_loader.py` (799B)
**Functions:**
- `load_locale(locale_code)` - Load localization strings (Chinese support)

---

## 6. TEMPLATE STRUCTURE & UI PATTERNS

### Template Directory Organization
```
templates/
├── base.html                       # Master template (CSS variables, navbar, footer)
├── login.html                      # User authentication
├── register.html                   # User registration
├── main_dashboard.html             # Main landing dashboard
├── dashboard.html                  # User profile dashboard
├── settings.html                   # Account settings
├── loading.html                    # Loading spinner page
├── errors/                         # Error pages
│   ├── 404.html
│   └── 500.html
├── exercises/                      # Post-session exercise templates
│   ├── dictation.html
│   ├── gap_fill.html
│   ├── synonym.html
│   └── reading.html
├── reading/
│   ├── index.html                  # Reading home
│   ├── sentence_practice.html      # Sentence-level practice
│   ├── paragraph_practice.html     # Paragraph-level practice
│   ├── passage_practice.html       # Full passage practice
│   ├── question_types_hub.html     # Question type selector
│   ├── question_type_learn.html    # Question type learning page
│   ├── question_type_practice.html # Question type practice
│   └── generate.html               # Reading generation page
├── listening/
│   ├── dashboard.html              # Listening module home
│   ├── dictation.html              # Dictation trainer
│   ├── signpost.html               # Signpost (discourse markers) trainer
│   ├── lecture.html                # Lecture simulation
│   └── conversation.html           # Conversation simulation
├── speaking/
│   ├── dashboard.html              # Speaking home
│   ├── practice.html               # Speaking practice page
│   ├── feedback.html               # Speaking feedback review
│   └── generating.html             # Task generation status
├── writing/
│   ├── dashboard.html              # Writing home
│   ├── practice.html               # Writing practice (3-phase flow)
│   └── feedback.html               # Essay feedback review
├── search.html                     # Vocabulary search results
├── words.html                      # Browse all words
├── unfamiliar_words.html           # Unfamiliar words list
├── test_unfamiliar.html            # Test unfamiliar words
├── session.html                    # Main spaced repetition practice
├── exercises_hub.html              # Exercise selection page
├── vocab_dashboard.html            # Vocabulary statistics dashboard
└── reading_dashboard.html          # Reading progress dashboard
```

### UI Pattern: Bootstrap 5.3 + Custom CSS Variables
**Color Scheme (defined in base.html CSS variables):**
```css
--toefl-primary: #0066cc;           /* Main blue */
--toefl-success: #28a745;           /* Green for correct */
--toefl-danger: #dc3545;            /* Red for errors */
--toefl-warning: #ffc107;           /* Yellow for alerts */
--toefl-highlight: #fff6cc;         /* Soft highlight */
--toefl-highlight-blue: #e3f1ff;    /* Blue highlight */
--teal-400: #0ea5e9;                /* Accent teal */
--purple: #a855f7;                  /* Accent purple */
```

**Common Component Patterns:**
1. **Progress Cards** - Mastery breakdown with color gradients
2. **Timer Displays** - Font-weight 700, color changes (normal → warning → danger)
3. **Audio Players** - HTML5 `<audio>` with custom controls
4. **Answer Feedback** - Color-coded with explanation modals
5. **Drag-and-drop** - For gap-fill exercises
6. **Audio Recording** - WebM format via MediaRecorder API
7. **Modal Dialogs** - Bootstrap modals for feedback, explanations, paraphrasing

### Writing Practice Template - 3-Phase Flow Example
The writing/practice.html implements a sophisticated three-phase interface:
```html
<!-- Phase 1: DECONSTRUCTION -->
<div class="phase-deconstruction">
    <div class="reference-panel">
        <!-- Reading passage or discussion context -->
        <!-- AI-extracted key points or outline -->
    </div>
</div>

<!-- Phase 2: DRAFTING -->
<div class="phase-drafting">
    <textarea class="essay-editor">User drafts essay here</textarea>
    <!-- Real-time word count -->
    <!-- Timer -->
    <!-- Paraphrasing assistant modal -->
</div>

<!-- Phase 3: FEEDBACK -->
<div class="phase-feedback">
    <!-- Overall score -->
    <!-- Rubric breakdown -->
    <!-- In-line annotations -->
    <!-- Categorized feedback -->
    <!-- Revision option -->
</div>
```

---

## 7. API INTEGRATIONS & EXTERNAL SERVICE USAGE

### 1. Google Gemini 2.5 Flash API
**Primary Integration Point:** `services/gemini_client.py`

**Usage Across Modules:**
| Service | Endpoint | Use Case | Response Type |
|---------|----------|----------|----------------|
| Listening | `generateContent` | Dictation sentence, signpost, lecture, conversation generation | JSON with text, transcript, questions |
| Reading | `generateContent` | Passage/paragraph/sentence generation, paraphrase evaluation, question type generation | JSON with content, options, answers |
| Speaking | `generateContent` | Task prompt generation, grammar/vocabulary/topic analysis | JSON with prompts, feedback |
| Writing | `generateContent` | Task generation, essay analysis, feedback generation, paraphrase suggestions | JSON with detailed feedback |

**API Configuration:**
- **Base URL:** `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
- **Default Model:** `gemini-2.5-flash-lite`
- **Fallback Model:** `gemini-2.5-flash`
- **Auth:** Query parameter `?key={api_key}`
- **Timeout:** 40 seconds (configurable)
- **Retries:** Up to 5 with exponential backoff (1.5s → 30s max)

**Request Structure:**
```json
{
    "contents": [
        {
            "parts": [{"text": "prompt_string"}]
        }
    ],
    "generationConfig": {
        "temperature": 0.8,
        "responseMimeType": "application/json",
        "maxOutputTokens": 4096
    },
    "systemInstruction": {
        "parts": [{"text": "system_instruction_string"}]
    }
}
```

**Error Handling:**
- Status codes 408, 409, 429, 500, 502, 503, 504 trigger retries
- Max output token errors trigger fallback model
- All failures logged to Flask logger

### 2. OpenAI Whisper (Speech-to-Text)
**Integration Point:** `services/speech_rater.py`

**Usage:**
- Transcribe uploaded speaking audio files
- Returns word-level timestamps (for potential future use)
- Model: `base` or `small` (configurable via environment)

**Features:**
- Automatic language detection
- High accuracy on academic English
- Fast processing (< 30s for typical speech)

### 3. Text-to-Speech Services
**Integration Points:** `services/tts_service.py`, `services/audio.py`

**Services:**
1. **Kokoro TTS** (Primary)
   - Natural-sounding voices
   - Multiple speakers available
   - Fast generation (~1s per sentence)

2. **gTTS (Google Text-to-Speech)** (Fallback)
   - Reliable, free service
   - Slight robotic quality
   - Used when Kokoro unavailable

**Usage:**
- Generate pronunciation audio for vocabulary words
- Generate audio for listening exercises (dictation, lectures, conversations)
- Cache generated audio in `/static/audio/` and `/static/listening_audio/`

### 4. Praat Parselmouth (Acoustic Analysis)
**Integration Point:** `services/speech_rater.py`

**Features:**
- Extract prosodic metrics from audio
- Fluency rate calculation (words per minute)
- Rhythm regularity measurement
- Stress pattern detection
- Formant analysis for pronunciation assessment

---

## 8. FILE UPLOAD HANDLING

### Upload Locations & Naming

**Speaking Audio Upload:**
- **Directory:** `/workspace/TOEFL/app/flask_app/static/uploads/speaking/`
- **Filename Format:** `{user_id}_{task_id}_{uuid_hex}.webm`
- **Example:** `4_12_adf7f571017e4c23a1d1e7815c3f23c4.webm`
- **Route Handler:** `POST /speaking/task/<int:task_id>/submit` (line 3515 in app.py)

**Upload Process:**
```python
# From app.py lines 3527-3538
audio_file = request.files.get('audio')
if not audio_file or audio_file.filename == '':
    return jsonify({'success': False, 'message': 'No audio file provided'}), 400

upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'speaking')
os.makedirs(upload_dir, exist_ok=True)

filename = f"{user.id}_{task_id}_{uuid.uuid4().hex}.webm"
audio_path = os.path.join(upload_dir, filename)
audio_file.save(audio_path)

audio_url = f"/static/uploads/speaking/{filename}"
```

**Post-Upload Processing:**
1. Save file to disk
2. Transcribe via Whisper
3. Extract audio metrics via Praat Parselmouth
4. Analyze grammar/vocabulary/topic via Gemini
5. Generate comprehensive feedback
6. Store in SpeakingResponse and SpeakingFeedback models

### Vocabulary Audio (Generated, Not Uploaded)
- **Directory:** `/workspace/TOEFL/app/flask_app/static/audio/`
- **Naming:** `{word_id}_{word_lemma}.mp3` or `.wav`
- **Generation:** On-demand via gTTS/Kokoro, cached for reuse
- **URL:** Stored in `Word.pronunciation_audio_url` field

### Listening Audio (Generated)
- **Directory:** `/workspace/TOEFL/app/flask_app/static/listening_audio/`
- **Naming:** `{exercise_type}_{category/type}_{timestamp}.mp3`
- **Example:** `signpost_contrast_1762061169953.mp3`, `dictation_academic_1762061174086.mp3`
- **Storage:** URL stored in model (ListeningSentence.audio_url, ListeningSignpost.audio_url, etc.)

### Static File Serving
- **Route Handling:** Flask serves `/static/*` directly from `/workspace/TOEFL/app/flask_app/static/`
- **CORS Enabled:** All origins allowed for development (configurable via config.py)
- **No User Authentication:** Static files served without auth checks

---

## 9. KEY ARCHITECTURAL PATTERNS & DESIGN DECISIONS

### 1. Monolithic Architecture
- **Single app.py file** with all routes (3979 lines)
- **Advantages:** Easy to understand, fast development, simple deployment
- **Disadvantages:** File size, potential for tangled dependencies, harder to test
- **Rationale:** Appropriate for single-developer project or rapid prototyping

### 2. Service Layer Pattern
**Separation of Concerns:**
- `app.py` - Route handling only
- `services/*` - Business logic (AI, audio, analysis)
- `models.py` - Data layer
- `utils.py` - Helper functions
- `scheduler.py` - Algorithm implementation

**Benefits:**
- Reusable components across routes
- Testable units (services tested independently)
- AI service abstraction (could swap Gemini for other LLM)

### 3. Lazy Initialization of Services
```python
# Pattern used across services
def get_gemini_client():
    """Singleton-like getter for Gemini client."""
    if not hasattr(current_app, 'gemini_client'):
        current_app.gemini_client = GeminiClient()
    return current_app.gemini_client
```

**Benefit:** Services only initialized when used, reduces startup time

### 4. Session Management for Vocabulary
```python
# In-memory session queue management
sessions = {}  # {session_id: {'user_id': int, 'queue': deque, 'seen': set}}
```

**Reason:** Vocabulary sessions are short-lived (minutes), in-memory storage is optimal
**Limitation:** Sessions lost on server restart (acceptable for learning app)

### 5. Spaced Repetition Algorithm
**Located:** `scheduler.py`
**Algorithm:** SM-2 (SuperMemo 2)
**Parameters:** Easiness (EF), Interval (I), Repetitions (n)

**Key Features:**
- Dynamic difficulty adjustment
- Exponential interval growth
- Three-grade response system
- Based on 25+ years of academic research

### 6. Error Handling Patterns
**API Errors:**
```python
# Gemini API failures
if not self.is_configured:
    current_app.logger.error("API not configured")
    return None

# Whisper failures
try:
    transcription = whisper.transcribe(audio_path)
except Exception as e:
    current_app.logger.error(f"Transcription failed: {e}")
    return default_response
```

**Database Errors:**
```python
try:
    db.session.add(record)
    db.session.commit()
except SQLAlchemy.exc.IntegrityError as e:
    db.session.rollback()
    current_app.logger.error(f"DB error: {e}")
    return error_response
```

### 7. JSON Response Format (Consistent)
```python
# Success response
return jsonify({'success': True, 'data': {...}})

# Error response
return jsonify({'error': 'message'}), 400

# API response
return jsonify({
    'task_id': 1,
    'redirect': '/path/to/resource'
})
```

---

## 10. DATABASE CONFIGURATION & PERSISTENCE

### SQLite Configuration
**Location:** `/workspace/TOEFL/app/flask_app/instance/toefl_vocab.db`

**Pragmas (from models.py):**
```python
PRAGMA journal_mode=WAL;        # Write-ahead logging for concurrency
PRAGMA synchronous=NORMAL;      # Balance between safety and speed
PRAGMA foreign_keys=ON;         # Enforce referential integrity
PRAGMA busy_timeout=15000;      # 15s timeout for locked database
```

**Connection Pooling:**
- Pool size: 10 (default)
- Pool recycle: 300s
- Pre-ping enabled (test connections before use)

**Why SQLite?**
- Zero configuration
- File-based (easy to backup)
- Sufficient for single/small team usage
- Can migrate to PostgreSQL later if needed

---

## 11. AUTHENTICATION & SECURITY

### Authentication Flow
1. **Registration:** POST `/register`
   - Email validation
   - Password hashing with bcrypt (salt rounds: configurable)
   - User created in database

2. **Login:** POST `/login`
   - Email lookup
   - Password verification against bcrypt hash
   - Session creation (`session['user_id'] = user.id`)

3. **Route Protection:** `@login_required` decorator
   - Checks `session['user_id']`
   - Redirects to login if missing
   - Flashes warning message

4. **Logout:** GET `/logout`
   - Clear session
   - Redirect to home

### Password Security
- **Algorithm:** bcrypt with salt
- **Hash Function:** `bcrypt.hashpw(password.encode(), bcrypt.gensalt())`
- **Verification:** `bcrypt.checkpw(password.encode(), hash.encode())`
- **Strength:** bcrypt automatically handles salt generation and key stretching

### Session Configuration
```python
SESSION_TYPE = 'filesystem'              # Store sessions on disk
PERMANENT_SESSION_LIFETIME = timedelta(days=7)
SESSION_COOKIE_SECURE = False            # Set True in production with HTTPS
SESSION_COOKIE_HTTPONLY = True           # Prevent JavaScript access
SESSION_COOKIE_SAMESITE = 'Lax'          # CSRF protection
```

### API Key Management
**Gemini API Key:**
- Default key hardcoded (demo purposes)
- Overridable via `GEMINI_API_KEY` environment variable
- Should use secrets management in production

---

## 12. RECOMMENDATIONS FOR ESSAY GRADING FEATURE (Your Use Case)

### Existing Foundation
The codebase already has:
1. **Writing infrastructure** - WritingTask, WritingResponse, WritingFeedback models
2. **Gemini integration** - gemini_client.py with proven error handling
3. **File upload patterns** - Speaking module uploads audio successfully
4. **Analysis patterns** - writing_analyzer.py shows complex feedback generation
5. **Database schema** - WritingFeedback model ready for score storage

### Architectural Fit for Handwritten Essay Image Grading
**Proposed Flow:**
```
User uploads essay image
    ↓
OCR processing (extract text from image)
    ↓
Optional: Gemini Vision API for additional analysis
    ↓
Call existing writing_analyzer.analyze_essay()
    ↓
Store results in WritingFeedback
    ↓
Display feedback to user
```

### Integration Points
1. **New Route:** `POST /writing/task/<int:task_id>/submit-image`
   - Accept file upload (PNG, JPG, PDF)
   - Similar structure to speaking audio upload

2. **Image Processing Service:** `services/ocr_service.py` (NEW)
   - Extract text from image
   - Could use Gemini Vision API or pytesseract

3. **Extend WritingResponse:** Add `image_url` field
   - Store uploaded image path
   - Reference in WritingFeedback

4. **Use Existing:** `writing_analyzer.py`
   - analyze_essay() works with extracted text
   - All scoring, annotations, feedback already implemented

---

## 13. TECHNOLOGY DEPENDENCIES SUMMARY

**Core Web Framework:**
- Flask 3.0.0, Flask-SQLAlchemy 3.1.1, Flask-CORS 4.0.0

**Database & ORM:**
- SQLAlchemy (via Flask-SQLAlchemy)
- SQLite 3

**Audio Processing:**
- gTTS 2.5.1 (text-to-speech)
- openai-whisper 20250625 (speech recognition)
- librosa 0.10.1 (audio analysis)
- praat-parselmouth 0.4.3 (acoustic analysis)
- pydub 0.25.1 (audio manipulation)
- soundfile 0.12.1 (audio I/O)
- kokoro 0.9.4 (TTS)

**Deep Learning:**
- torch 2.8.0, torchvision 0.23.0, torchaudio 2.8.0
- transformers 4.48.1 (Hugging Face models)
- xformers 0.0.32.post2 (optimized attention)

**Security & Utilities:**
- bcrypt 4.1.2 (password hashing)
- python-dotenv 1.0.0 (environment variables)
- requests 2.31.0 (HTTP requests)
- numpy 1.26.4 (numerical computing)

---

## 14. POTENTIAL AREAS FOR IMPROVEMENT

1. **Code Organization:** Consider breaking app.py into blueprints
   - `app/blueprints/vocabulary.py`, `app/blueprints/writing.py`, etc.
   - Would make file more manageable and routes clearer

2. **Testing:** Currently minimal test coverage
   - Add tests for services (especially AI integrations)
   - Mock Gemini API for reliable testing
   - Test database models and relationships

3. **Error Handling:** More specific error messages
   - User-facing errors could be more helpful
   - API errors could include suggested actions

4. **Configuration:** Hardcoded values should be configurable
   - Word limits, time limits, score scales
   - Model selection, temperatures, max tokens

5. **Documentation:** In-code comments could be more detailed
   - Complex algorithms (SM-2) need explanation
   - API request structures not always obvious

6. **Performance:** Some potential optimizations
   - Database query optimization (add indexes)
   - Caching strategies for frequently-accessed data
   - Batch processing for AI API calls

7. **Scalability:** Current architecture limitations
   - In-memory vocabulary sessions won't work with multiple servers
   - Consider Redis for session storage if needed
   - Database may need optimization for high user counts

---

## CONCLUSION

This is a **well-structured, feature-rich TOEFL learning platform** with:
- Sophisticated AI integration via Gemini API
- Comprehensive learning modules (vocabulary, reading, listening, speaking, writing)
- Strong foundation for essay grading with existing WritingFeedback model
- Proven file upload and audio processing patterns
- Consistent error handling and service architecture

The codebase is ready to extend with your handwritten essay grading feature using Gemini 2.5 Flash (for OCR + vision analysis) or pytesseract + existing writing_analyzer.

