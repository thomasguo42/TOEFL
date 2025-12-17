"""SQLAlchemy database models for TOEFL vocabulary app."""
from datetime import datetime, timezone
import sqlite3

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Configure SQLite connections for better concurrency."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout=15000;")
        cursor.close()


def utcnow():
    """Get current UTC time."""
    return datetime.now(timezone.utc)


class User(db.Model):
    """User account model."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, index=True)
    email = db.Column(db.String(255), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    daily_goal = db.Column(db.Integer, default=20, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    words = db.relationship('UserWord', back_populates='user', cascade='all, delete-orphan')
    reviews = db.relationship('ReviewLog', back_populates='user', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<User {self.email}>'


class Word(db.Model):
    """Vocabulary word model."""
    __tablename__ = 'words'

    id = db.Column(db.Integer, primary_key=True, index=True)
    lemma = db.Column(db.String(255), unique=True, index=True, nullable=False)
    definition = db.Column(db.Text, nullable=False)
    example = db.Column(db.Text, nullable=False)
    cn_gloss = db.Column(db.String(255), nullable=True)
    pronunciation_audio_url = db.Column(db.String(500), nullable=True)
    pronunciation_pitfall_cn = db.Column(db.Text, nullable=True)

    # Relationships
    user_words = db.relationship('UserWord', back_populates='word', cascade='all, delete-orphan')
    reviews = db.relationship('ReviewLog', back_populates='word', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Word {self.lemma}>'

    def to_dict(self):
        """Convert word to dictionary."""
        return {
            'id': self.id,
            'lemma': self.lemma,
            'definition': self.definition,
            'example': self.example,
            'cn_gloss': self.cn_gloss,
            'pronunciation_audio_url': self.pronunciation_audio_url,
            'pronunciation_pitfall_cn': self.pronunciation_pitfall_cn
        }


class UserWord(db.Model):
    """User's progress on a specific word (spaced repetition state)."""
    __tablename__ = 'user_words'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'word_id', name='uq_user_word'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    word_id = db.Column(db.Integer, db.ForeignKey('words.id', ondelete='CASCADE'), nullable=False)
    easiness = db.Column(db.Float, default=2.5)
    interval = db.Column(db.Float, default=0.0)
    repetitions = db.Column(db.Integer, default=0)
    next_due = db.Column(db.DateTime(timezone=True), default=utcnow)
    last_grade = db.Column(db.String(50), nullable=True)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    user = db.relationship('User', back_populates='words')
    word = db.relationship('Word', back_populates='user_words')

    def __repr__(self):
        return f'<UserWord user={self.user_id} word={self.word_id}>'


class ReviewLog(db.Model):
    """Log of each review attempt."""
    __tablename__ = 'review_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    word_id = db.Column(db.Integer, db.ForeignKey('words.id', ondelete='CASCADE'), nullable=False)
    grade = db.Column(db.String(50), nullable=False)
    latency_ms = db.Column(db.Integer, nullable=True)
    is_new = db.Column(db.Boolean, default=False, nullable=False)
    easiness = db.Column(db.Float, nullable=True)
    interval = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    word = db.relationship('Word', back_populates='reviews')
    user = db.relationship('User', back_populates='reviews')

    def __repr__(self):
        return f'<ReviewLog user={self.user_id} word={self.word_id} grade={self.grade}>'


class UnfamiliarWord(db.Model):
    """Words marked as unfamiliar by users for additional practice."""
    __tablename__ = 'unfamiliar_words'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'word_text', name='uq_user_unfamiliar_word'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    word_text = db.Column(db.String(255), nullable=False, index=True)
    context = db.Column(db.Text, nullable=True)  # The sentence/paragraph where the word was found
    source = db.Column(db.String(100), nullable=True)  # e.g., 'reading_passage', 'exercise', etc.
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    user = db.relationship('User', backref='unfamiliar_words')

    def __repr__(self):
        return f'<UnfamiliarWord user={self.user_id} word={self.word_text}>'


# ============================================================================
# LISTENING MODULE MODELS
# ============================================================================

class ListeningSentence(db.Model):
    """Single sentence for dictation practice."""
    __tablename__ = 'listening_sentences'

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)  # The accurate transcript
    topic = db.Column(db.String(100), nullable=True)  # Academic topic
    difficulty = db.Column(db.String(20), default='medium')  # easy, medium, hard
    audio_url = db.Column(db.String(500), nullable=True)  # Path to audio file
    audio_duration_seconds = db.Column(db.Float, nullable=True)
    word_timestamps = db.Column(db.JSON, nullable=True)  # [{word, start, end}, ...]
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self):
        return f'<ListeningSentence id={self.id} topic={self.topic}>'

    def to_dict(self):
        return {
            'id': self.id,
            'text': self.text,
            'topic': self.topic,
            'difficulty': self.difficulty,
            'audio_url': self.audio_url,
            'audio_duration_seconds': self.audio_duration_seconds,
            'word_timestamps': self.word_timestamps,
        }


class ListeningSignpost(db.Model):
    """Short audio segment with signpost phrase for structure recognition training."""
    __tablename__ = 'listening_signposts'

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)  # The transcript (2-3 sentences)
    signpost_phrase = db.Column(db.String(100), nullable=False)  # e.g., "In contrast..."
    signpost_category = db.Column(db.String(50), nullable=False)  # e.g., "contrast", "addition", "example"
    audio_url = db.Column(db.String(500), nullable=True)
    audio_duration_seconds = db.Column(db.Float, nullable=True)
    question_text = db.Column(db.Text, nullable=False)  # "What is the professor about to do?"
    options = db.Column(db.JSON, nullable=False)  # List of answer options
    correct_answer = db.Column(db.String(255), nullable=False)
    explanation_cn = db.Column(db.Text, nullable=True)  # Chinese explanation
    option_explanations_cn = db.Column(db.JSON, nullable=True)  # Chinese rationale per option
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self):
        return f'<ListeningSignpost id={self.id} phrase="{self.signpost_phrase}">'

    def to_dict(self):
        return {
            'id': self.id,
            'text': self.text,
            'signpost_phrase': self.signpost_phrase,
            'signpost_category': self.signpost_category,
            'audio_url': self.audio_url,
            'audio_duration_seconds': self.audio_duration_seconds,
            'question_text': self.question_text,
            'options': self.options,
            'correct_answer': self.correct_answer,
            'explanation_cn': self.explanation_cn,
            'option_explanations_cn': self.option_explanations_cn or {},
        }


class ListeningLecture(db.Model):
    """Full 5-minute lecture for comprehensive listening practice."""
    __tablename__ = 'listening_lectures'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    topic = db.Column(db.String(100), nullable=False)  # e.g., "Biology", "Art History"
    transcript = db.Column(db.Text, nullable=False)  # Full transcript
    audio_url = db.Column(db.String(500), nullable=True)
    audio_duration_seconds = db.Column(db.Float, nullable=True)
    word_timestamps = db.Column(db.JSON, nullable=True)  # Full word-level timestamps
    expert_notes = db.Column(db.Text, nullable=True)  # AI-generated ideal notes
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    questions = db.relationship('ListeningQuestion', back_populates='lecture', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ListeningLecture id={self.id} title="{self.title}">'

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'topic': self.topic,
            'transcript': self.transcript,
            'audio_url': self.audio_url,
            'audio_duration_seconds': self.audio_duration_seconds,
            'word_timestamps': self.word_timestamps,
            'expert_notes': self.expert_notes,
            'questions': [q.to_dict() for q in self.questions],
        }


class ListeningConversation(db.Model):
    """3-minute conversation between student and professor."""
    __tablename__ = 'listening_conversations'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    situation = db.Column(db.String(255), nullable=False)  # e.g., "Office hours discussion"
    transcript = db.Column(db.Text, nullable=False)  # Full transcript with speaker labels
    audio_url = db.Column(db.String(500), nullable=True)
    audio_duration_seconds = db.Column(db.Float, nullable=True)
    word_timestamps = db.Column(db.JSON, nullable=True)
    expert_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    questions = db.relationship('ListeningQuestion', back_populates='conversation', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ListeningConversation id={self.id} title="{self.title}">'

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'situation': self.situation,
            'transcript': self.transcript,
            'audio_url': self.audio_url,
            'audio_duration_seconds': self.audio_duration_seconds,
            'word_timestamps': self.word_timestamps,
            'expert_notes': self.expert_notes,
            'questions': [q.to_dict() for q in self.questions],
        }


class ListeningQuestion(db.Model):
    """Question associated with a lecture or conversation."""
    __tablename__ = 'listening_questions'

    id = db.Column(db.Integer, primary_key=True)
    lecture_id = db.Column(db.Integer, db.ForeignKey('listening_lectures.id', ondelete='CASCADE'), nullable=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('listening_conversations.id', ondelete='CASCADE'), nullable=True)
    question_order = db.Column(db.Integer, nullable=False)  # Order in the set (1-6)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(50), nullable=False)  # e.g., "main_idea", "detail", "inference"
    options = db.Column(db.JSON, nullable=False)  # List of answer options
    correct_answer = db.Column(db.String(255), nullable=False)
    explanation = db.Column(db.Text, nullable=False)  # Why correct answer is right
    distractor_explanations = db.Column(db.JSON, nullable=True)  # Why wrong answers are wrong
    answer_start_time = db.Column(db.Float, nullable=True)  # Timestamp where answer info starts
    answer_end_time = db.Column(db.Float, nullable=True)  # Timestamp where answer info ends

    # Relationships
    lecture = db.relationship('ListeningLecture', back_populates='questions')
    conversation = db.relationship('ListeningConversation', back_populates='questions')

    def __repr__(self):
        return f'<ListeningQuestion id={self.id} order={self.question_order}>'

    def to_dict(self):
        return {
            'id': self.id,
            'question_order': self.question_order,
            'question_text': self.question_text,
            'question_type': self.question_type,
            'options': self.options,
            'correct_answer': self.correct_answer,
            'explanation': self.explanation,
            'distractor_explanations': self.distractor_explanations,
            'answer_start_time': self.answer_start_time,
            'answer_end_time': self.answer_end_time,
        }


class ListeningUserProgress(db.Model):
    """Track user's progress on listening exercises."""
    __tablename__ = 'listening_user_progress'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    exercise_type = db.Column(db.String(50), nullable=False)  # 'dictation', 'signpost', 'lecture', 'conversation'
    exercise_id = db.Column(db.Integer, nullable=False)  # ID of the exercise
    score = db.Column(db.Float, nullable=True)  # 0-100 score
    completed = db.Column(db.Boolean, default=False)
    user_answer = db.Column(db.JSON, nullable=True)  # User's response
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    user = db.relationship('User', backref='listening_progress')

    def __repr__(self):
        return f'<ListeningUserProgress user={self.user_id} type={self.exercise_type} id={self.exercise_id}>'


# ============================================================================
# SPEAKING MODULE MODELS
# ============================================================================

class SpeakingTask(db.Model):
    """Speaking practice task (Independent or Integrated)."""
    __tablename__ = 'speaking_tasks'

    id = db.Column(db.Integer, primary_key=True)
    task_number = db.Column(db.Integer, nullable=False)  # 1-4
    task_type = db.Column(db.String(50), nullable=False)  # 'integrated', 'discussion', legacy variants
    topic = db.Column(db.String(255), nullable=False)
    prompt = db.Column(db.Text, nullable=False)  # The main question/prompt

    # For integrated tasks
    reading_text = db.Column(db.Text, nullable=True)  # Reading passage (if applicable)
    listening_audio_url = db.Column(db.String(500), nullable=True)  # Listening audio (if applicable)
    listening_transcript = db.Column(db.Text, nullable=True)  # For reference

    # Task settings
    preparation_time = db.Column(db.Integer, default=15)  # Seconds
    response_time = db.Column(db.Integer, default=45)  # Seconds

    # Sample/template
    sample_response = db.Column(db.Text, nullable=True)  # High-scoring sample
    response_template = db.Column(db.Text, nullable=True)  # Suggested structure
    sample_audio_url = db.Column(db.String(500), nullable=True)  # Pre-recorded sample

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    responses = db.relationship('SpeakingResponse', back_populates='task', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<SpeakingTask id={self.id} task_number={self.task_number} type={self.task_type}>'

    def to_dict(self):
        return {
            'id': self.id,
            'task_number': self.task_number,
            'task_type': self.task_type,
            'topic': self.topic,
            'prompt': self.prompt,
            'reading_text': self.reading_text,
            'listening_audio_url': self.listening_audio_url,
            'listening_transcript': self.listening_transcript,
            'preparation_time': self.preparation_time,
            'response_time': self.response_time,
            'sample_response': self.sample_response,
            'response_template': self.response_template,
            'sample_audio_url': self.sample_audio_url,
        }


class SpeakingResponse(db.Model):
    """User's recorded response to a speaking task."""
    __tablename__ = 'speaking_responses'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('speaking_tasks.id', ondelete='CASCADE'), nullable=False)

    # Audio data
    audio_url = db.Column(db.String(500), nullable=False)  # Path to uploaded audio
    audio_duration_seconds = db.Column(db.Float, nullable=True)
    transcription = db.Column(db.Text, nullable=True)  # Whisper transcription

    # Metadata
    attempt_number = db.Column(db.Integer, default=1)  # Allow multiple attempts
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    user = db.relationship('User', backref='speaking_responses')
    task = db.relationship('SpeakingTask', back_populates='responses')
    feedback = db.relationship('SpeakingFeedback', back_populates='response', uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<SpeakingResponse id={self.id} user={self.user_id} task={self.task_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'task_id': self.task_id,
            'audio_url': self.audio_url,
            'audio_duration_seconds': self.audio_duration_seconds,
            'transcription': self.transcription,
            'attempt_number': self.attempt_number,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class SpeakingFeedback(db.Model):
    """Comprehensive feedback for a speaking response."""
    __tablename__ = 'speaking_feedback'

    id = db.Column(db.Integer, primary_key=True)
    response_id = db.Column(db.Integer, db.ForeignKey('speaking_responses.id', ondelete='CASCADE'), nullable=False, unique=True)

    # Overall scores
    overall_score = db.Column(db.Float, nullable=True)  # 0-100
    delivery_score = db.Column(db.Float, nullable=True)  # From SpeechRater
    language_use_score = db.Column(db.Float, nullable=True)  # From NLP/LLM
    topic_development_score = db.Column(db.Float, nullable=True)  # From LLM

    # Delivery sub-scores (from SpeechRater)
    fluency_score = db.Column(db.Float, nullable=True)
    pronunciation_score = db.Column(db.Float, nullable=True)
    rhythm_score = db.Column(db.Float, nullable=True)

    # Detailed metrics (JSON from SpeechRater)
    speech_metrics = db.Column(db.JSON, nullable=True)  # All the detailed metrics

    # Language use analysis
    lexical_diversity = db.Column(db.Float, nullable=True)  # Type-Token Ratio
    academic_word_count = db.Column(db.Integer, nullable=True)
    grammar_errors = db.Column(db.JSON, nullable=True)  # List of errors
    vocabulary_suggestions = db.Column(db.JSON, nullable=True)  # LLM suggestions

    # Topic development analysis (from LLM)
    task_fulfillment = db.Column(db.Text, nullable=True)  # LLM assessment
    clarity_coherence = db.Column(db.Text, nullable=True)  # LLM assessment
    support_sufficiency = db.Column(db.Text, nullable=True)  # LLM assessment

    # Actionable feedback
    strengths = db.Column(db.JSON, nullable=True)  # List of strengths
    areas_for_improvement = db.Column(db.JSON, nullable=True)  # List of improvements
    specific_feedback = db.Column(db.JSON, nullable=True)  # Detailed feedback points

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    response = db.relationship('SpeakingResponse', back_populates='feedback')

    def __repr__(self):
        return f'<SpeakingFeedback response_id={self.response_id} overall={self.overall_score}>'

    def to_dict(self):
        return {
            'id': self.id,
            'response_id': self.response_id,
            'overall_score': self.overall_score,
            'delivery_score': self.delivery_score,
            'language_use_score': self.language_use_score,
            'topic_development_score': self.topic_development_score,
            'fluency_score': self.fluency_score,
            'pronunciation_score': self.pronunciation_score,
            'rhythm_score': self.rhythm_score,
            'speech_metrics': self.speech_metrics,
            'lexical_diversity': self.lexical_diversity,
            'academic_word_count': self.academic_word_count,
            'grammar_errors': self.grammar_errors,
            'vocabulary_suggestions': self.vocabulary_suggestions,
            'task_fulfillment': self.task_fulfillment,
            'clarity_coherence': self.clarity_coherence,
            'support_sufficiency': self.support_sufficiency,
            'strengths': self.strengths,
            'areas_for_improvement': self.areas_for_improvement,
            'specific_feedback': self.specific_feedback,
        }

# ============================================================================
# WRITING MODULE MODELS
# ============================================================================

class WritingTask(db.Model):
    """Writing practice task (Integrated or Independent)."""
    __tablename__ = 'writing_tasks'

    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(50), nullable=False)  # 'integrated', 'discussion', or legacy 'independent'
    topic = db.Column(db.String(255), nullable=False)
    prompt = db.Column(db.Text, nullable=False)  # The main writing prompt

    # For integrated tasks
    reading_text = db.Column(db.Text, nullable=True)  # Reading passage
    listening_audio_url = db.Column(db.String(500), nullable=True)  # Listening audio
    listening_transcript = db.Column(db.Text, nullable=True)  # For reference and deconstruction

    # AI-generated deconstruction/planning aids (JSON)
    deconstruction_data = db.Column(db.JSON, nullable=True)  # For integrated: extracted points
    outline_data = db.Column(db.JSON, nullable=True)  # For discussion: checklist, legacy outlines

    # Task settings
    word_limit = db.Column(db.Integer, default=300)  # Typical TOEFL limit
    time_limit_minutes = db.Column(db.Integer, default=20)  # 20 for integrated, 10 for discussion (legacy: 30 independent)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    responses = db.relationship('WritingResponse', back_populates='task', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<WritingTask id={self.id} type={self.task_type} topic={self.topic}>'

    def to_dict(self):
        return {
            'id': self.id,
            'task_type': self.task_type,
            'topic': self.topic,
            'prompt': self.prompt,
            'reading_text': self.reading_text,
            'listening_audio_url': self.listening_audio_url,
            'listening_transcript': self.listening_transcript,
            'deconstruction_data': self.deconstruction_data,
            'outline_data': self.outline_data,
            'word_limit': self.word_limit,
            'time_limit_minutes': self.time_limit_minutes,
        }


class WritingResponse(db.Model):
    """User's essay submission for a writing task."""
    __tablename__ = 'writing_responses'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('writing_tasks.id', ondelete='CASCADE'), nullable=False)

    # Essay content
    essay_text = db.Column(db.Text, nullable=False)  # User's essay
    word_count = db.Column(db.Integer, nullable=True)
    time_spent_seconds = db.Column(db.Integer, nullable=True)  # Time spent writing

    # Image submission fields
    image_url = db.Column(db.String(500), nullable=True)  # Path to uploaded essay image
    is_image_submission = db.Column(db.Boolean, default=False)  # Distinguish image from text
    extracted_text = db.Column(db.Text, nullable=True)  # OCR-extracted text from image
    ocr_confidence = db.Column(db.Float, nullable=True)  # Confidence score of OCR (0-1)

    # Metadata
    attempt_number = db.Column(db.Integer, default=1)  # Allow multiple attempts/revisions
    is_revised = db.Column(db.Boolean, default=False)  # Is this a revision?
    parent_response_id = db.Column(db.Integer, db.ForeignKey('writing_responses.id'), nullable=True)  # If revision, link to original

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    user = db.relationship('User', backref='writing_responses')
    task = db.relationship('WritingTask', back_populates='responses')
    feedback = db.relationship('WritingFeedback', back_populates='response', uselist=False, cascade='all, delete-orphan')
    revisions = db.relationship('WritingResponse', backref=db.backref('parent_response', remote_side=[id]))

    def __repr__(self):
        return f'<WritingResponse id={self.id} user={self.user_id} task={self.task_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'task_id': self.task_id,
            'essay_text': self.essay_text,
            'word_count': self.word_count,
            'time_spent_seconds': self.time_spent_seconds,
            'image_url': self.image_url,
            'is_image_submission': self.is_image_submission,
            'extracted_text': self.extracted_text,
            'ocr_confidence': self.ocr_confidence,
            'attempt_number': self.attempt_number,
            'is_revised': self.is_revised,
            'parent_response_id': self.parent_response_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class WritingFeedback(db.Model):
    """Comprehensive AI feedback for a writing response."""
    __tablename__ = 'writing_feedback'

    id = db.Column(db.Integer, primary_key=True)
    response_id = db.Column(db.Integer, db.ForeignKey('writing_responses.id', ondelete='CASCADE'), nullable=False, unique=True)

    # Overall scores (TOEFL scale: 0-30)
    overall_score = db.Column(db.Float, nullable=True)  # 0-30 (converted from 0-5 scale internally)

    # Rubric breakdown (each 0-5)
    content_development_score = db.Column(db.Float, nullable=True)
    organization_structure_score = db.Column(db.Float, nullable=True)
    vocabulary_language_score = db.Column(db.Float, nullable=True)
    grammar_mechanics_score = db.Column(db.Float, nullable=True)

    # In-line annotations (JSON array of annotation objects)
    # Each: {type: 'vague'/'lexical'/'grammar'/'cohesion', text: 'highlighted text', comment: 'feedback', start: int, end: int}
    annotations = db.Column(db.JSON, nullable=True)

    # Holistic AI coach summary
    coach_summary = db.Column(db.Text, nullable=True)  # Overall encouraging feedback

    # Categorized feedback
    strengths = db.Column(db.JSON, nullable=True)  # List of specific strengths
    improvements = db.Column(db.JSON, nullable=True)  # List of specific improvements
    grammar_issues = db.Column(db.JSON, nullable=True)  # List of grammar problems with corrections
    vocabulary_suggestions = db.Column(db.JSON, nullable=True)  # Vocabulary enhancement suggestions
    organization_notes = db.Column(db.JSON, nullable=True)  # Essay structure notes
    content_suggestions = db.Column(db.JSON, nullable=True)  # Content depth suggestions

    # Task-specific feedback (for integrated tasks)
    content_accuracy = db.Column(db.Text, nullable=True)  # Assessment of content accuracy for integrated tasks
    point_coverage = db.Column(db.JSON, nullable=True)  # List of professor's points and coverage status
    example_accuracy = db.Column(db.Text, nullable=True)  # Assessment of example usage from sources
    paraphrase_quality = db.Column(db.Text, nullable=True)  # Assessment of paraphrasing
    source_integration = db.Column(db.Text, nullable=True)  # How well sources were integrated

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    response = db.relationship('WritingResponse', back_populates='feedback')

    def __repr__(self):
        return f'<WritingFeedback response_id={self.response_id} score={self.overall_score}>'

    def to_dict(self):
        return {
            'id': self.id,
            'response_id': self.response_id,
            'overall_score': self.overall_score,
            'content_development_score': self.content_development_score,
            'organization_structure_score': self.organization_structure_score,
            'vocabulary_language_score': self.vocabulary_language_score,
            'grammar_mechanics_score': self.grammar_mechanics_score,
            'annotations': self.annotations,
            'coach_summary': self.coach_summary,
            'strengths': self.strengths,
            'improvements': self.improvements,
            'grammar_issues': self.grammar_issues,
            'vocabulary_suggestions': self.vocabulary_suggestions,
            'organization_notes': self.organization_notes,
            'content_suggestions': self.content_suggestions,
            'content_accuracy': self.content_accuracy,
            'point_coverage': self.point_coverage,
            'example_accuracy': self.example_accuracy,
            'paraphrase_quality': self.paraphrase_quality,
            'source_integration': self.source_integration,
        }


# ============================================
# STANDALONE ESSAY GRADING MODELS
# (Not related to TOEFL - separate feature)
# ============================================

class EssaySubmission(db.Model):
    """Standalone essay submission for grading (not TOEFL-related)."""
    __tablename__ = 'essay_submissions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    # Essay details
    topic = db.Column(db.Text, nullable=True)  # User-provided topic
    image_url = db.Column(db.String(500), nullable=False)  # Path to uploaded image
    extracted_text = db.Column(db.Text, nullable=False)  # OCR-extracted text
    ocr_confidence = db.Column(db.Float, nullable=True)  # OCR confidence score (0-1)
    word_count = db.Column(db.Integer, nullable=True)

    # Image quality info
    image_quality = db.Column(db.String(50), nullable=True)  # 'excellent', 'good', 'fair', 'poor'
    legibility_score = db.Column(db.Float, nullable=True)  # 0-1

    # Metadata
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    user = db.relationship('User', backref='essay_submissions')
    grading = db.relationship('EssayGrading', back_populates='submission', uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<EssaySubmission id={self.id} user={self.user_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'topic': self.topic,
            'image_url': self.image_url,
            'extracted_text': self.extracted_text,
            'ocr_confidence': self.ocr_confidence,
            'word_count': self.word_count,
            'image_quality': self.image_quality,
            'legibility_score': self.legibility_score,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class EssayGrading(db.Model):
    """AI grading and feedback for standalone essay submission."""
    __tablename__ = 'essay_gradings'

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('essay_submissions.id', ondelete='CASCADE'), nullable=False, unique=True)

    # Corrected version
    corrected_text = db.Column(db.Text, nullable=True)  # Grammar and spelling corrected version
    corrections_made = db.Column(db.JSON, nullable=True)  # List of corrections made

    # Evaluation based on topic
    topic_relevance_score = db.Column(db.Float, nullable=True)  # 0-10
    topic_coverage = db.Column(db.Text, nullable=True)  # How well the essay addresses the topic
    missing_aspects = db.Column(db.JSON, nullable=True)  # List of aspects not covered

    # Overall quality scores
    grammar_score = db.Column(db.Float, nullable=True)  # 0-10
    vocabulary_score = db.Column(db.Float, nullable=True)  # 0-10
    organization_score = db.Column(db.Float, nullable=True)  # 0-10
    overall_score = db.Column(db.Float, nullable=True)  # 0-10

    # Detailed feedback
    grammar_issues = db.Column(db.JSON, nullable=True)  # List of grammar issues with corrections
    vocabulary_suggestions = db.Column(db.JSON, nullable=True)  # Vocabulary improvements
    organization_feedback = db.Column(db.Text, nullable=True)  # Structure and organization feedback
    content_feedback = db.Column(db.Text, nullable=True)  # Content quality feedback

    # Summary
    summary = db.Column(db.Text, nullable=True)  # Overall assessment
    strengths = db.Column(db.JSON, nullable=True)  # List of strengths
    improvements = db.Column(db.JSON, nullable=True)  # List of areas for improvement

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    submission = db.relationship('EssaySubmission', back_populates='grading')

    def __repr__(self):
        return f'<EssayGrading submission_id={self.submission_id} score={self.overall_score}>'

    def to_dict(self):
        return {
            'id': self.id,
            'submission_id': self.submission_id,
            'corrected_text': self.corrected_text,
            'corrections_made': self.corrections_made,
            'topic_relevance_score': self.topic_relevance_score,
            'topic_coverage': self.topic_coverage,
            'missing_aspects': self.missing_aspects,
            'grammar_score': self.grammar_score,
            'vocabulary_score': self.vocabulary_score,
            'organization_score': self.organization_score,
            'overall_score': self.overall_score,
            'grammar_issues': self.grammar_issues,
            'vocabulary_suggestions': self.vocabulary_suggestions,
            'organization_feedback': self.organization_feedback,
            'content_feedback': self.content_feedback,
            'summary': self.summary,
            'strengths': self.strengths,
            'improvements': self.improvements,
        }
