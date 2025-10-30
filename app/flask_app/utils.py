"""Utility functions for the Flask application."""
import bcrypt
from functools import wraps
from flask import session, redirect, url_for, flash
from datetime import datetime, timezone, date, timedelta
from sqlalchemy import func, case, and_, or_

from models import db, User, Word, UserWord, ReviewLog, UnfamiliarWord


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    password_bytes = password.encode('utf-8')
    hash_bytes = password_hash.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hash_bytes)


def login_required(f):
    """Decorator to require login for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    """Get the currently logged-in user."""
    user_id = session.get('user_id')
    if user_id:
        return User.query.get(user_id)
    return None


def get_due_words(user_id: int, limit: int = 20):
    """Get words that are due for review."""
    now = datetime.now(timezone.utc)

    # Get words that are due or have never been seen
    results = db.session.query(Word).join(
        UserWord,
        (UserWord.word_id == Word.id) & (UserWord.user_id == user_id),
        isouter=True
    ).filter(
        or_(
            UserWord.next_due.is_(None),
            UserWord.next_due <= now,
            UserWord.id.is_(None)
        )
    ).order_by(
        case((UserWord.next_due.is_(None), 0), else_=1),
        UserWord.next_due
    ).limit(limit).all()

    return results


def get_fallback_words(user_id: int, exclude_ids: list, limit: int):
    """Get new words that haven't been seen yet."""
    results = db.session.query(Word).join(
        UserWord,
        (UserWord.word_id == Word.id) & (UserWord.user_id == user_id),
        isouter=True
    ).filter(
        UserWord.id.is_(None),
        ~Word.id.in_(exclude_ids) if exclude_ids else True
    ).order_by(Word.id).limit(limit * 3).all()

    # Filter out excluded and return limited
    filtered = [w for w in results if w.id not in exclude_ids]
    return filtered[:limit]


def get_or_create_user_word(user_id: int, word_id: int):
    """Get or create a UserWord entry."""
    user_word = UserWord.query.filter_by(user_id=user_id, word_id=word_id).first()

    if user_word is None:
        word = Word.query.get(word_id)
        if word is None:
            return None
        user_word = UserWord(user_id=user_id, word_id=word_id)
        db.session.add(user_word)
        db.session.flush()

    return user_word


def log_review(user_id: int, word_id: int, grade: str, latency_ms: int,
               is_new: bool, easiness: float, interval: float):
    """Log a review attempt."""
    review = ReviewLog(
        user_id=user_id,
        word_id=word_id,
        grade=grade,
        latency_ms=latency_ms,
        is_new=is_new,
        easiness=easiness,
        interval=interval
    )
    db.session.add(review)


def get_todays_progress(user_id: int):
    """Get today's progress statistics."""
    today = datetime.now(timezone.utc).date()

    result = db.session.query(
        func.count(ReviewLog.id),
        func.sum(case((ReviewLog.is_new == True, 1), else_=0))
    ).filter(
        ReviewLog.user_id == user_id,
        func.date(ReviewLog.created_at) == today.isoformat()
    ).first()

    total = result[0] or 0
    new_cards = result[1] or 0
    review_cards = max(0, total - new_cards)

    return total, new_cards, review_cards


def get_mastery_breakdown(user_id: int):
    """Get mastery level breakdown."""
    total_words = db.session.query(func.count(Word.id)).scalar() or 0

    result = db.session.query(
        func.count(UserWord.id),
        func.sum(case(
            (and_(
                UserWord.repetitions >= 4,
                UserWord.interval >= 10.0,
                UserWord.easiness >= 2.3
            ), 1),
            else_=0
        )),
        func.sum(case(
            (or_(
                UserWord.last_grade == 'not',
                UserWord.easiness < 1.7,
                UserWord.interval < 1.0
            ), 1),
            else_=0
        )),
        func.sum(case((UserWord.repetitions == 0, 1), else_=0))
    ).filter(UserWord.user_id == user_id).first()

    engaged_count = result[0] or 0
    mastered = result[1] or 0
    struggling = result[2] or 0
    tracked_new = result[3] or 0

    learning = max(0, engaged_count - mastered - struggling)
    untouched = max(0, total_words - engaged_count)
    new_total = tracked_new + untouched

    def pct(value: int) -> float:
        if total_words <= 0:
            return 0.0
        return (value / total_words) * 100

    return {
        'mastered': mastered,
        'mastered_pct': pct(mastered),
        'learning': learning,
        'learning_pct': pct(learning),
        'struggling': struggling,
        'struggling_pct': pct(struggling),
        'new': new_total,
        'new_pct': pct(new_total),
        'total': total_words
    }


def get_memorize_curve(user_id: int, days: int = 14):
    """Get memorization curve data for the last N days."""
    results = db.session.query(
        func.date(ReviewLog.created_at).label('day'),
        func.count(ReviewLog.id),
        func.sum(case((ReviewLog.is_new == True, 1), else_=0)),
        func.sum(case((ReviewLog.grade == 'recognize', 1), else_=0)),
        func.sum(case((ReviewLog.grade == 'barely', 1), else_=0)),
        func.sum(case((ReviewLog.grade == 'not', 1), else_=0))
    ).filter(
        ReviewLog.user_id == user_id
    ).group_by('day').order_by('day').all()

    # Convert to dictionary and fill in missing days
    today = datetime.now(timezone.utc).date()
    curve_dict = {
        date.fromisoformat(row[0]): {
            'total': row[1] or 0,
            'new_count': row[2] or 0,
            'review_count': (row[1] or 0) - (row[2] or 0),
            'recognize': row[3] or 0,
            'barely': row[4] or 0,
            'not_grade': row[5] or 0
        }
        for row in results
    }

    curve = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        data = curve_dict.get(day, {
            'total': 0, 'new_count': 0, 'review_count': 0,
            'recognize': 0, 'barely': 0, 'not_grade': 0
        })
        data['date'] = day.strftime('%m/%d')
        curve.append(data)

    return curve


def get_words_by_mastery(user_id: int, category: str, limit: int = 100, offset: int = 0):
    """
    Get words filtered by mastery level.

    Categories:
    - 'mastered': repetitions >= 4, interval >= 10, easiness >= 2.3
    - 'learning': engaged but not mastered or struggling
    - 'struggling': last_grade == 'not' OR easiness < 1.7 OR interval < 1.0
    - 'new': never reviewed
    """
    if category == 'new':
        # Words never reviewed by this user
        results = db.session.query(Word).outerjoin(
            UserWord,
            (UserWord.word_id == Word.id) & (UserWord.user_id == user_id)
        ).filter(
            UserWord.id.is_(None)
        ).order_by(Word.id).limit(limit).offset(offset).all()

        count = db.session.query(func.count(Word.id)).outerjoin(
            UserWord,
            (UserWord.word_id == Word.id) & (UserWord.user_id == user_id)
        ).filter(UserWord.id.is_(None)).scalar()

    elif category == 'mastered':
        # Well-learned words
        results = db.session.query(Word).join(
            UserWord,
            (UserWord.word_id == Word.id) & (UserWord.user_id == user_id)
        ).filter(
            and_(
                UserWord.repetitions >= 4,
                UserWord.interval >= 10.0,
                UserWord.easiness >= 2.3
            )
        ).order_by(UserWord.next_due).limit(limit).offset(offset).all()

        count = db.session.query(func.count(Word.id)).join(
            UserWord,
            (UserWord.word_id == Word.id) & (UserWord.user_id == user_id)
        ).filter(
            and_(
                UserWord.repetitions >= 4,
                UserWord.interval >= 10.0,
                UserWord.easiness >= 2.3
            )
        ).scalar()

    elif category == 'struggling':
        # Words user is having trouble with
        results = db.session.query(Word).join(
            UserWord,
            (UserWord.word_id == Word.id) & (UserWord.user_id == user_id)
        ).filter(
            or_(
                UserWord.last_grade == 'not',
                UserWord.easiness < 1.7,
                and_(UserWord.interval < 1.0, UserWord.repetitions > 0)
            )
        ).order_by(UserWord.next_due).limit(limit).offset(offset).all()

        count = db.session.query(func.count(Word.id)).join(
            UserWord,
            (UserWord.word_id == Word.id) & (UserWord.user_id == user_id)
        ).filter(
            or_(
                UserWord.last_grade == 'not',
                UserWord.easiness < 1.7,
                and_(UserWord.interval < 1.0, UserWord.repetitions > 0)
            )
        ).scalar()

    else:  # 'learning'
        # Words being learned (not new, not mastered, not struggling)
        subq_mastered = db.session.query(UserWord.word_id).filter(
            UserWord.user_id == user_id,
            UserWord.repetitions >= 4,
            UserWord.interval >= 10.0,
            UserWord.easiness >= 2.3
        ).subquery()

        subq_struggling = db.session.query(UserWord.word_id).filter(
            UserWord.user_id == user_id,
            or_(
                UserWord.last_grade == 'not',
                UserWord.easiness < 1.7,
                and_(UserWord.interval < 1.0, UserWord.repetitions > 0)
            )
        ).subquery()

        results = db.session.query(Word).join(
            UserWord,
            (UserWord.word_id == Word.id) & (UserWord.user_id == user_id)
        ).filter(
            ~Word.id.in_(subq_mastered),
            ~Word.id.in_(subq_struggling)
        ).order_by(UserWord.next_due).limit(limit).offset(offset).all()

        count = db.session.query(func.count(Word.id)).join(
            UserWord,
            (UserWord.word_id == Word.id) & (UserWord.user_id == user_id)
        ).filter(
            ~Word.id.in_(subq_mastered),
            ~Word.id.in_(subq_struggling)
        ).scalar()

    return results, count or 0


def get_words_reviewed_today(user_id: int):
    """Return distinct Word objects reviewed on the current day."""
    today_iso = datetime.now(timezone.utc).date().isoformat()
    subquery = db.session.query(ReviewLog.word_id).filter(
        ReviewLog.user_id == user_id,
        func.date(ReviewLog.created_at) == today_iso
    ).distinct()

    return Word.query.filter(Word.id.in_(subquery)).order_by(Word.lemma.asc()).all()


def get_words_in_stage_range(user_id: int, min_repetitions: int, max_repetitions: int, limit: int = 10):
    """Return words whose SRS repetitions fall between the provided bounds."""
    return db.session.query(Word).join(
        UserWord,
        (UserWord.word_id == Word.id) & (UserWord.user_id == user_id)
    ).filter(
        UserWord.repetitions >= min_repetitions,
        UserWord.repetitions <= max_repetitions
    ).order_by(UserWord.next_due.asc()).limit(limit).all()


def get_unfamiliar_words_for_study(user_id: int, limit: int = 20):
    """
    Get unfamiliar words that match vocabulary database for study.
    Returns Word objects that correspond to user's unfamiliar words.
    """
    # Get all unfamiliar word texts for this user
    unfamiliar_texts = db.session.query(UnfamiliarWord.word_text).filter(
        UnfamiliarWord.user_id == user_id
    ).all()

    if not unfamiliar_texts:
        return []

    # Extract just the text values
    word_texts = [uw[0] for uw in unfamiliar_texts]

    # Find matching words in vocabulary database
    matched_words = Word.query.filter(
        func.lower(Word.lemma).in_([w.lower() for w in word_texts])
    ).limit(limit).all()

    return matched_words


def get_smart_session_composition(user_id: int, daily_goal: int):
    """
    Calculate optimal composition of new vs review words.

    Enhanced Strategy:
    - Prioritize unfamiliar words (highest priority, 25% if available)
    - Prioritize struggling words (30% if available)
    - Prioritize due review words (25-35%)
    - Add new words (15-20%)
    - Adjust based on user's performance
    """
    now = datetime.now(timezone.utc)

    # Get counts of unfamiliar words that match vocabulary
    unfamiliar_words = get_unfamiliar_words_for_study(user_id, limit=1000)
    unfamiliar_count = len(unfamiliar_words)

    # Get counts of different word types
    struggling_count = db.session.query(func.count(UserWord.id)).filter(
        UserWord.user_id == user_id,
        or_(
            UserWord.last_grade == 'not',
            UserWord.easiness < 1.7,
            and_(UserWord.interval < 1.0, UserWord.repetitions > 0)
        )
    ).scalar() or 0

    due_count = db.session.query(func.count(UserWord.id)).filter(
        UserWord.user_id == user_id,
        UserWord.next_due <= now,
        UserWord.repetitions > 0
    ).scalar() or 0

    total_words = Word.query.count()
    seen_count = db.session.query(func.count(UserWord.id)).filter(
        UserWord.user_id == user_id
    ).scalar() or 0
    unseen_count = total_words - seen_count

    # Calculate composition with unfamiliar words as highest priority
    unfamiliar_target = min(int(daily_goal * 0.25), unfamiliar_count)
    struggling_target = min(int(daily_goal * 0.30), struggling_count)
    due_target = min(int(daily_goal * 0.30), due_count)
    new_target = min(int(daily_goal * 0.15), unseen_count)

    # Adjust if we have capacity
    remaining = daily_goal - (unfamiliar_target + struggling_target + due_target + new_target)
    if remaining > 0:
        # Prioritize filling up unfamiliar words first
        if unfamiliar_count > unfamiliar_target:
            extra_unfamiliar = min(remaining, unfamiliar_count - unfamiliar_target)
            unfamiliar_target += extra_unfamiliar
            remaining -= extra_unfamiliar

        # Then struggling words
        if remaining > 0 and struggling_count > struggling_target:
            extra_struggling = min(remaining, struggling_count - struggling_target)
            struggling_target += extra_struggling
            remaining -= extra_struggling

        # Then due reviews
        if remaining > 0 and due_count > due_target:
            extra_due = min(remaining, due_count - due_target)
            due_target += extra_due
            remaining -= extra_due

        # Finally new words
        if remaining > 0 and unseen_count > new_target:
            extra_new = min(remaining, unseen_count - new_target)
            new_target += extra_new
            remaining -= extra_new

        # Any still remaining goes to due reviews
        if remaining > 0:
            due_target += remaining

    return {
        'unfamiliar': unfamiliar_target,
        'struggling': struggling_target,
        'due_review': due_target,
        'new': new_target,
        'total': unfamiliar_target + struggling_target + due_target + new_target,
        'stats': {
            'unfamiliar_available': unfamiliar_count,
            'struggling_available': struggling_count,
            'due_available': due_count,
            'unseen_available': unseen_count
        }
    }


def get_learning_velocity(user_id: int, days: int = 30):
    """Get learning velocity (new words learned per day)."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    results = db.session.query(
        func.date(ReviewLog.created_at).label('day'),
        func.count(func.distinct(case((ReviewLog.is_new == True, ReviewLog.word_id), else_=None)))
    ).filter(
        ReviewLog.user_id == user_id,
        ReviewLog.created_at >= cutoff_date
    ).group_by('day').order_by('day').all()

    velocity_data = []
    for row in results:
        velocity_data.append({
            'date': row[0],
            'new_words': row[1]
        })

    # Calculate average
    total_new = sum(d['new_words'] for d in velocity_data)
    avg_velocity = total_new / days if days > 0 else 0

    return velocity_data, avg_velocity


def get_study_streak(user_id: int):
    """Get current study streak (consecutive days with reviews)."""
    results = db.session.query(
        func.date(ReviewLog.created_at).label('day')
    ).filter(
        ReviewLog.user_id == user_id
    ).group_by('day').order_by(func.date(ReviewLog.created_at).desc()).all()

    if not results:
        return 0

    today = datetime.now(timezone.utc).date()
    streak = 0
    expected_date = today

    for row in results:
        review_date = date.fromisoformat(row[0])
        if review_date == expected_date:
            streak += 1
            expected_date = expected_date - timedelta(days=1)
        elif review_date < expected_date:
            break

    return streak


def search_words(query: str, limit: int = 50):
    """Search words by lemma or definition."""
    query = f"%{query}%"
    results = Word.query.filter(
        or_(
            Word.lemma.ilike(query),
            Word.definition.ilike(query),
            Word.cn_gloss.ilike(query)
        )
    ).limit(limit).all()

    return results
