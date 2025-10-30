from __future__ import annotations

import shelve
from pathlib import Path
from typing import Any, Optional

from flask import current_app


def _db_path() -> str:
    """Resolve persistent shelf file under Flask instance path."""
    instance_dir = Path(current_app.instance_path)
    instance_dir.mkdir(parents=True, exist_ok=True)
    return str(instance_dir / "question_drills.db")


def set_drill(drill_id: str, drill: dict) -> None:
    """Persist a drill by id."""
    try:
        db_path = _db_path()
        current_app.logger.info(f"Saving drill {drill_id} to {db_path}")
        with shelve.open(db_path, writeback=True) as db:
            db[drill_id] = drill
            db.sync()  # Force write to disk
        current_app.logger.info(f"Successfully saved drill {drill_id}, store now has {count()} items")
    except Exception as e:
        current_app.logger.error(f"Failed to save drill {drill_id}: {e}")
        raise


def get_drill(drill_id: str) -> Optional[dict]:
    """Retrieve a drill by id, or None if missing."""
    try:
        db_path = _db_path()
        with shelve.open(db_path, flag='r') as db:
            data: Any = db.get(drill_id)
            if data:
                current_app.logger.info(f"Retrieved drill {drill_id} from store")
            else:
                current_app.logger.warning(f"Drill {drill_id} not found in store at {db_path}, available keys: {list(db.keys())[:5]}")
            return data if isinstance(data, dict) else None
    except Exception as e:
        current_app.logger.error(f"Failed to retrieve drill {drill_id}: {e}")
        return None


def delete_drill(drill_id: str) -> None:
    """Delete a drill by id if present."""
    with shelve.open(_db_path()) as db:
        if drill_id in db:
            del db[drill_id]


def count() -> int:
    """Return number of stored drills (for diagnostics)."""
    try:
        with shelve.open(_db_path(), flag='r') as db:
            return len(db)
    except Exception as e:
        current_app.logger.error(f"Failed to count drills: {e}")
        return 0


def update_drill(drill_id: str, drill: dict) -> None:
    """Update an existing drill (same as set)."""
    set_drill(drill_id, drill)

