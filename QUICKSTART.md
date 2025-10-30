# TOEFL Vocabulary Studio - Quick Start Guide

## 🚀 Start the Application

```bash
bash /workspace/TOEFL/run_flask.sh
```

## 🌐 Access URLs

### Local Development
- **Local**: http://localhost:1111
- **VM Internal**: http://172.17.0.3:1111

### Public Access (Your VM)
- **Public URL**: http://142.189.182.224:42990
- **Instance Port Range**: 41808-42990
- **Machine Port**: 1111 → Public Port 42990

## 📊 Current Status

✅ **Database**: SQLite initialized
✅ **Vocabulary Words**: 73 words loaded
✅ **Users**: Multiple users registered
✅ **Application**: Running on port 1111

## 🎯 Features Available

### Authentication
- Register new account: http://localhost:1111/register
- Login: http://localhost:1111/login
- Logout: http://localhost:1111/logout

### Learning
- Vocabulary Session: http://localhost:1111/session
  - Grade words: Recognize (稳得住), Barely (模糊记得), Not Yet (完全陌生)
  - Spaced repetition scheduling
  - Daily goal tracking

### Analytics
- Dashboard: http://localhost:1111/dashboard
  - Progress tracking
  - Mastery breakdown
  - 14-day review curve

### Settings
- User Settings: http://localhost:1111/settings
  - Adjust daily goal (1-1000 words)

## 🧪 Test the Application

### Quick Health Check
```bash
curl http://localhost:1111/healthz
```
Expected: `{"status": "ok"}`

### Test Registration (via command line)
```bash
curl -X POST http://localhost:1111/register \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "email=yourname@example.com&password=yourpass123&daily_goal=50"
```

### Check Database
```bash
cd /workspace/TOEFL/app/flask_app
python -c "
from app import app
from models import db, Word, User
with app.app_context():
    print(f'Words: {Word.query.count()}')
    print(f'Users: {User.query.count()}')
"
```

## 📁 Project Structure

```
/workspace/TOEFL/
├── app/flask_app/          ← Main application directory
│   ├── app.py              ← All routes and logic
│   ├── models.py           ← Database models
│   ├── scheduler.py        ← SM-2 algorithm
│   ├── utils.py            ← Helper functions
│   ├── config.py           ← Configuration
│   ├── requirements.txt    ← Python dependencies
│   └── templates/          ← Jinja2 HTML templates
├── data/seeds/             ← Vocabulary CSV files
├── run_flask.sh            ← Start script
├── README.md               ← Full documentation
└── QUICKSTART.md           ← This file
```

## 🛠️ Common Commands

### Stop the Application
```bash
# Find Flask process
lsof -ti:1111

# Kill the process
kill -9 $(lsof -ti:1111)
```

### View Logs
Flask logs are displayed in the terminal where you ran `run_flask.sh`

### Restart Application
```bash
kill -9 $(lsof -ti:1111)
bash /workspace/TOEFL/run_flask.sh
```

### Add New Vocabulary
1. Add CSV file to `/workspace/TOEFL/data/seeds/`
2. CSV format: `lemma,definition,example,cn_gloss`
3. Restart the application

## 🔑 Default Settings

- **Port**: 1111
- **Database**: SQLite at `/workspace/TOEFL/app/flask_app/toefl_vocab.db`
- **Debug Mode**: Enabled
- **Default Daily Goal**: 20 words
- **Session Cookie Lifetime**: 7 days

## 📝 Notes

- **Old Setup Removed**: Next.js + FastAPI architecture has been completely removed
- **Architecture**: Monolithic Flask application with server-side rendering
- **Templates**: Jinja2 with Bootstrap 5.3 and Font Awesome 6.4
- **Theme**: Dark theme with custom CSS variables

## 🐛 Troubleshooting

### Port Already in Use
```bash
lsof -ti:1111 | xargs kill -9
```

### Database Issues
```bash
rm /workspace/TOEFL/app/flask_app/toefl_vocab.db
bash /workspace/TOEFL/run_flask.sh  # Reinitialize
```

### No Words Loading
```bash
cd /workspace/TOEFL/app/flask_app
python -c "from app import app, seed_words_from_file; from pathlib import Path; [seed_words_from_file(Path(f)) for f in Path('/workspace/TOEFL/data/seeds').glob('*.csv')]"
```

## 📚 Next Steps

1. **Access the application** at http://142.189.182.224:42990
2. **Register a new account**
3. **Start learning vocabulary** with spaced repetition
4. **Track your progress** on the dashboard
5. **Adjust your daily goal** in settings

Enjoy your TOEFL vocabulary learning! 🎓
