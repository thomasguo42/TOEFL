"""Enhanced SM-2 spaced repetition scheduler for vocabulary learning."""
from datetime import datetime, timedelta, timezone
from typing import Tuple

GRADE_SCORES = {"recognize": 5, "barely": 3, "not": 1}


def compute_schedule(user_word, grade: str, user_id: int) -> Tuple[object, datetime]:
    """
    Apply enhanced SM-2 spaced repetition algorithm with adaptive scheduling.

    Enhanced features:
    - "recognize" words: Normal progression with gradually increasing intervals
    - "barely" words: Reappear multiple times within the same day for reinforcement
    - "not" words: Aggressive short-term repetition schedule (red button behavior)
    - Smart adjustment based on word history

    Args:
        user_word: UserWord instance or None for new words
        grade: 'recognize', 'barely', or 'not'
        user_id: User ID for creating new UserWord

    Returns:
        Tuple of (updated_user_word, next_due_datetime)
    """
    from models import UserWord  # Import here to avoid circular dependency

    score = GRADE_SCORES[grade]
    now = datetime.now(timezone.utc)

    if user_word is None:
        user_word = UserWord(
            user_id=user_id,
            easiness=2.5,
            interval=0.0,
            repetitions=0,
            next_due=now,
            last_grade=grade,
        )

    easiness = user_word.easiness
    repetitions = user_word.repetitions
    interval_days = user_word.interval
    last_grade = user_word.last_grade

    if score >= 4:  # Recognize - word is known well
        repetitions += 1

        # Check if this is a comeback from struggling
        if last_grade in ['barely', 'not'] and repetitions <= 3:
            # More conservative intervals for recovering words
            if repetitions == 1:
                interval_days = 0.5  # 12 hours
            elif repetitions == 2:
                interval_days = 1.5  # 1.5 days
            elif repetitions == 3:
                interval_days = 3.0  # 3 days
            else:
                interval_days = max(1.0, interval_days * (easiness * 0.8))
        else:
            # Normal progression for stable words
            if repetitions == 1:
                interval_days = 1.0  # 1 day
            elif repetitions == 2:
                interval_days = 3.0  # 3 days (reduced from 6)
            elif repetitions == 3:
                interval_days = 7.0  # 1 week
            else:
                interval_days = max(1.0, interval_days * easiness)

        # Gradually increase easiness for consistently recognized words
        easiness = max(1.3, easiness + (0.1 - (5 - score) * (0.08 + (5 - score) * 0.02)))
        next_due = now + timedelta(days=interval_days)

    elif score == 3:  # Barely - needs reinforcement within the same day
        # Don't reset repetitions completely, but don't advance either
        repetitions = max(1, repetitions)

        # Aggressive same-day repetition schedule
        # Check how many times we've seen "barely" in a row
        if last_grade == 'barely':
            # Second "barely" in a row - very short interval
            interval_days = 0.1  # ~2.4 hours
            next_due = now + timedelta(minutes=10)
        else:
            # First "barely" - give a bit more time
            interval_days = 0.2  # ~4.8 hours
            next_due = now + timedelta(minutes=30)

        # Reduce easiness to slow down future progression
        easiness = max(1.3, easiness - 0.15)

    else:  # Not - red button behavior: intensive short-term repetition
        # Reset repetitions to 0 to treat as new word
        repetitions = 0
        interval_days = 0.0

        # Check history to determine intensity
        if last_grade == 'not':
            # Multiple "not" in a row - very aggressive schedule
            next_due = now + timedelta(minutes=1)  # Immediate reappearance
        elif last_grade == 'barely':
            # Struggled then failed - still very short
            next_due = now + timedelta(minutes=2)
        else:
            # First time failing - slightly longer interval
            next_due = now + timedelta(minutes=3)

        # Significantly reduce easiness for failed words
        easiness = max(1.3, easiness - 0.25)

    user_word.easiness = round(easiness, 4)
    user_word.repetitions = repetitions
    user_word.interval = interval_days
    user_word.next_due = next_due
    user_word.last_grade = grade

    return user_word, next_due
