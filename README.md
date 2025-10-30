# TOEFL Vocabulary Studio

A Flask-based vocabulary learning application with spaced repetition for TOEFL preparation.

## Architecture

This is a **monolithic Flask application** with Jinja2 server-side rendering, following a simplified architecture pattern.

### Technology Stack

- **Backend**: Flask 3.0 (Python)
- **Frontend**: Jinja2 templates with Bootstrap 5.3
- **Database**: SQLite with Flask-SQLAlchemy
- **Authentication**: Flask sessions with bcrypt password hashing
- **Scheduling**: SM-2 spaced repetition algorithm

### Project Structure

```
/workspace/TOEFL/
├── app/
│   └── flask_app/          # Main Flask application
│       ├── app.py          # Main application file (all routes)
│       ├── config.py       # Configuration
│       ├── models.py       # SQLAlchemy models
│       ├── scheduler.py    # SM-2 algorithm
│       ├── utils.py        # Helper functions
│       ├── requirements.txt # Python dependencies
│       ├── services/        # AI + audio helpers
│       ├── static/          # Generated/static assets
│       │   └── audio/       # On-demand pronunciation cache
│       └── templates/       # Jinja2 templates
│           ├── exercises/   # Post-session drills
│           ├── base.html
│           ├── login.html
│           ├── register.html
│           ├── session.html
│           ├── dashboard.html
│           ├── settings.html
│           └── errors/
│               ├── 404.html
│               └── 500.html
├── data/
│   └── seeds/             # CSV files with vocabulary words
│       ├── awl_list1_sample.csv
│       └── toefl_cn_core.csv
├── run_flask.sh           # Application starter script
└── README.md             # This file
```

## Features

### User Management
- User registration with email and password
- Secure password hashing with bcrypt
- Flask session-based authentication
- Configurable daily goal (1-1000 words/day)

### Vocabulary Learning
- Spaced repetition system based on SM-2 algorithm
- Three-grade response system:
  - **Recognize** (稳得住): Complete mastery
  - **Barely** (模糊记得): Partial recall
  - **Not Yet** (完全陌生): Unfamiliar
- Dynamic scheduling based on performance
- One-click pronunciation playback on every card
- In-memory session queue management

### Progress Tracking
- Daily goal tracking
- Mastery breakdown (mastered, learning, struggling, new)
- 14-day review activity curve
- Real-time progress updates

### Post-Session Exercises
- Dictation Challenge with auto-generated pronunciation audio
- Contextual Gap-Fill using Gemini for TOEFL-style sentences (option-by-option rationales)
- Synonym Showdown with Chinese nuance explanations and rationales for each choice
- Reading Immersion mode with highlighted study words and rationale-backed comprehension quiz

### Analytics Dashboard
- Today's progress (total reviewed, new words, reviews)
- Mastery level visualization
- Historical review data
- Settings management

## Getting Started

### Prerequisites

- Python 3.10+
- Virtual environment at `/venv/main` (or modify `run_flask.sh`)

### Installation & Running

1. **Start the application:**
   ```bash
   bash /workspace/TOEFL/run_flask.sh
   ```

   This script will:
   - Install Flask dependencies
   - Initialize the SQLite database
   - Seed vocabulary words from CSV files
   - Start Flask development server

2. **Access the application:**
   - **Local**: http://localhost:1111
   - **Public**: http://142.189.182.224:42990
   - **Internal VM**: http://172.17.0.3:1111

### Default Configuration

- **Port**: 1111
- **Database**: SQLite (`toefl_vocab.db`)
- **Debug Mode**: Enabled
- **Default Daily Goal**: 20 words

## API Endpoints

### Authentication
- `GET /` - Home page (redirects to login or session)
- `GET /login` - Login page
- `POST /login` - Login form submission
- `GET /register` - Registration page
- `POST /register` - Registration form submission
- `GET /logout` - Logout user

### Vocabulary Session
- `GET /session` - Main vocabulary learning interface
- `POST /session/<session_id>/grade` - Submit word grade
- `POST /api/daily-goal` - Update daily goal via JSON

### Exercises
- `GET /exercises/dictation` - Audio dictation drill
- `GET /exercises/gap-fill` - Contextual gap-fill multiple choice
- `GET /exercises/synonym-showdown` - Synonym nuance questions
- `GET /exercises/reading` - Reading immersion passage selector

### Dashboard & Analytics
- `GET /dashboard` - Analytics dashboard
- `GET /api/dashboard` - Dashboard data (JSON)
- `GET /settings` - User settings page
- `POST /settings` - Update settings

### System
- `GET /healthz` - Health check endpoint

## Database Models

### User
- `id`: Primary key
- `email`: Unique email address
- `password_hash`: Bcrypt hashed password
- `daily_goal`: Daily review goal (default: 20)
- `created_at`: Account creation timestamp

### Word
- `id`: Primary key
- `lemma`: Word lemma (unique)
- `definition`: English definition
- `example`: Example sentence (TOEFL context)
- `cn_gloss`: Chinese translation (optional)
- `pronunciation_audio_url`: Cached audio asset (optional, generated on demand)
- `pronunciation_pitfall_cn`: Chinese hint for pronunciation pitfalls (optional)

### UserWord
- Tracks spaced repetition state per user-word pair
- `easiness`: SM-2 easiness factor (default: 2.5)
- `interval`: Days until next review
- `repetitions`: Number of successful repetitions
- `next_due`: Next review due date
- `last_grade`: Most recent grade

### ReviewLog
- Logs every review attempt
- `grade`: User's response (recognize/barely/not)
- `latency_ms`: Response time in milliseconds
- `is_new`: Whether this was the first review
- `easiness`: Easiness factor at time of review
- `interval`: Interval at time of review
- `created_at`: Review timestamp

## Spaced Repetition Algorithm

The application uses the **SM-2 algorithm** with custom grade mappings:

### Grade Scoring
- **Recognize (稳得住)**: Score 5 - Perfect recall
- **Barely (模糊记得)**: Score 3 - Difficult recall
- **Not Yet (完全陌生)**: Score 1 - Failed recall

### Scheduling Rules
- **Recognize**: Interval increases by easiness factor (min 1 day)
  - First repetition: 1 day
  - Second repetition: 6 days
  - Subsequent: interval × easiness
- **Barely**: Resets to 5 minutes, reduces easiness by 0.15
- **Not Yet**: Resets to 1 minute, reduces easiness by 0.20

## Development

### Adding New Words

Add CSV files to `/workspace/TOEFL/data/seeds/` with columns:
- `lemma`: The word
- `definition`: English definition
- `example`: Example sentence
- `cn_gloss`: Chinese translation (optional)

The words will be automatically loaded on application startup.

### Modifying Templates

Templates are in `/workspace/TOEFL/app/flask_app/templates/` using:
- Bootstrap 5.3 for styling
- Font Awesome 6.4 for icons
- Custom dark theme with CSS variables

### Configuration

Edit `/workspace/TOEFL/app/flask_app/config.py`:
```python
class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///toefl_vocab.db'
    # ... other settings
```

### AI Exercise Configuration

Several post-session drills lean on AI services:
- **Gemini 2.5 Flash** powers contextual gap-fill, synonym nuance, and reading immersion.
- **gTTS** generates pronunciation audio on demand (cached under `app/flask_app/static/audio/`).

Set the Gemini API key as an environment variable before launching the app:

```bash
export GEMINI_API_KEY="your-gemini-api-key"
# optional overrides
export GEMINI_MODEL="gemini-2.5-pro"
export GEMINI_FALLBACK_MODEL="gemini-2.5-flash"   # used only when MAX_TOKENS yields empty content
export GEMINI_FALLBACK_ON_MAX_TOKENS=true          # enable automatic pro→flash retry once
export GEMINI_TIMEOUT_SECONDS=40                   # request timeout
```

If the key is missing, the app falls back to deterministic (non-AI) exercise variants.

When Gemini responses are malformed or rate-limited (HTTP 429), the generators perform limited retries with exponential backoff and, upon failure, serve high-quality seed fallbacks from `data/seeds/`. Reading, paragraph, and passage endpoints will transparently use these seeds to avoid 503 errors.

#### Important Note on Gemini 2.5 Pro Thinking Tokens

**Gemini 2.5 Pro uses "thinking tokens"** (extended reasoning) which are counted against `maxOutputTokens` *before* generating visible output. This means:
- The model may use 50-80% of token budget for internal reasoning
- If `maxOutputTokens` is too low, you'll get MAX_TOKENS with empty/truncated responses
- **Solution**: We've increased all `max_output_tokens` limits (4096-8192) to accommodate thinking + output
- **Alternative**: Switch to `gemini-2.5-flash` which has controllable `thinkingBudget` and lower thinking overhead

This is documented in [Google's forums](https://discuss.ai.google.dev/t/how-to-reduce-thought-reasoning-in-gemini-2-5-pro/82535) and affects all Pro API users.

## Production Deployment

For production use, consider:

1. **Use a production WSGI server:**
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:1111 app:app
   ```

2. **Set environment variables:**
   ```bash
   export FLASK_ENV=production
   export SECRET_KEY='your-secret-key-here'
   export DATABASE_URL='postgresql://...'  # Use PostgreSQL
   ```

3. **Use a reverse proxy** (nginx/Apache)

4. **Enable HTTPS**

5. **Configure proper CORS** (remove wildcard origins)

## Migration Notes

This application was migrated from a Next.js + FastAPI architecture to a Flask monolithic architecture. All functionality has been preserved:

- ✅ User authentication
- ✅ Vocabulary session management
- ✅ Spaced repetition scheduling
- ✅ Progress tracking
- ✅ Analytics dashboard
- ✅ Dark theme UI
- ✅ Responsive design

## Support

For issues or questions, refer to the inline documentation in the source code or check the error logs in the Flask console.

## License

Educational project for TOEFL vocabulary learning.
