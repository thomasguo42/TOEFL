"""Helpers for parsing full-length practice test PDFs (text-extracted)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import re


@dataclass(frozen=True)
class FullLengthTest:
    test_id: str
    title: str
    filename: str


_ROOT_DIR = Path(__file__).resolve().parents[3]
_CANDIDATE_DIRS = (
    _ROOT_DIR / "TOEFL_Practice_Test",
    _ROOT_DIR,
    _ROOT_DIR / "data" / "seeds",
)
_TESTS = [
    FullLengthTest(
        test_id="practice_test_1",
        title="Full-Length Practice Test 1",
        filename="toefl-ibt-full-length-practice-test-1.txt",
    ),
    FullLengthTest(
        test_id="practice_test_2",
        title="Full-Length Practice Test 2",
        filename="toefl-ibt-full-length-practice-test-2.txt",
    ),
    FullLengthTest(
        test_id="teachers_resources_test_1",
        title="Teacher Resources Practice Test 1",
        filename="toefl-ibt-teachers-resources-practice-test-1.txt",
    ),
    FullLengthTest(
        test_id="teachers_resources_test_2",
        title="Teacher Resources Practice Test 2",
        filename="toefl-ibt-teachers-resources-practice-test-2.txt",
    ),
    FullLengthTest(
        test_id="teachers_resources_test_3",
        title="Teacher Resources Practice Test 3",
        filename="toefl-ibt-teachers-resources-practice-test-3.txt",
    ),
    FullLengthTest(
        test_id="teachers_resources_test_4",
        title="Teacher Resources Practice Test 4",
        filename="toefl-ibt-teachers-resources-practice-test-4.txt",
    ),
    FullLengthTest(
        test_id="teachers_resources_test_5",
        title="Teacher Resources Practice Test 5",
        filename="toefl-ibt-teachers-resources-practice-test-5.txt",
    ),
]


def list_full_length_tests() -> List[Dict[str, str]]:
    return [{"id": test.test_id, "title": test.title} for test in _TESTS]

def _resolve_test_path(filename: str) -> Optional[Path]:
    for base in _CANDIDATE_DIRS:
        candidate = base / filename
        if candidate.exists():
            return candidate
    return None

def _load_text(test_id: str) -> Optional[str]:
    test = next((t for t in _TESTS if t.test_id == test_id), None)
    if not test:
        return None
    path = _resolve_test_path(test.filename)
    if not path:
        return None
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: Optional[str] = None, start_pos: int = 0) -> Optional[str]:
    if not text:
        return None
    start_idx = text.find(start, start_pos)
    if start_idx == -1:
        return None
    start_idx += len(start)
    if end:
        end_idx = text.find(end, start_idx)
        if end_idx == -1:
            end_idx = len(text)
    else:
        end_idx = len(text)
    return text[start_idx:end_idx].strip()


def get_reading_section(test_id: str) -> Optional[Dict[str, str]]:
    text = _load_text(test_id)
    if not text:
        return None

    module1_marker = "Reading Section, Module 1"
    module2_marker = "Reading Section, Module 2"
    listening_marker = "Listening Section"

    module1_start = text.find(module1_marker)
    if module1_start == -1:
        return None
    module2_start = text.find(module2_marker, module1_start + 1)
    if module2_start == -1:
        return None

    # Answer key headers appear after module content.
    answer1_start = text.find(module1_marker, module2_start + 1)
    answer2_start = text.find(module2_marker, answer1_start + 1) if answer1_start != -1 else -1
    listening_start = text.find(listening_marker, answer2_start + 1) if answer2_start != -1 else -1

    module1 = text[module1_start:module2_start].strip()
    if answer1_start != -1:
        module2 = text[module2_start:answer1_start].strip()
    else:
        module2 = text[module2_start:].strip()

    answer1 = text[answer1_start:answer2_start].strip() if answer1_start != -1 and answer2_start != -1 else ""
    answer2 = text[answer2_start:listening_start].strip() if answer2_start != -1 and listening_start != -1 else ""

    return {
        "module1": module1,
        "module2": module2,
        "answer_key_module1": answer1,
        "answer_key_module2": answer2,
    }


def get_listening_section(test_id: str) -> Optional[Dict[str, str]]:
    text = _load_text(test_id)
    if not text:
        return None

    module1_marker = "Listening Section, Module 1"
    module2_marker = "Listening Section, Module 2"
    writing_marker = "Writing Section"

    module1_start = text.find(module1_marker)
    if module1_start == -1:
        return None
    module2_start = text.find(module2_marker, module1_start + 1)
    if module2_start == -1:
        return None

    answer1_start = text.find(module1_marker, module2_start + 1)
    answer2_start = text.find(module2_marker, answer1_start + 1) if answer1_start != -1 else -1
    writing_start = text.find(writing_marker, answer2_start + 1) if answer2_start != -1 else -1

    module1 = text[module1_start:module2_start].strip()
    if answer1_start != -1:
        module2 = text[module2_start:answer1_start].strip()
    else:
        module2 = text[module2_start:].strip()

    answer1 = text[answer1_start:answer2_start].strip() if answer1_start != -1 and answer2_start != -1 else ""
    answer2 = text[answer2_start:writing_start].strip() if answer2_start != -1 and writing_start != -1 else ""

    return {
        "module1": module1,
        "module2": module2,
        "answer_key_module1": answer1,
        "answer_key_module2": answer2,
    }


def get_writing_section(test_id: str) -> Optional[Dict[str, str]]:
    text = _load_text(test_id)
    if not text:
        return None

    lines = text.splitlines()
    writing_indices = [idx for idx, line in enumerate(lines) if line.strip() == "Writing Section"]
    if not writing_indices:
        return None

    speaking_idx = next((idx for idx, line in enumerate(lines) if line.strip() == "Speaking Section"), len(lines))

    answer_key_idx = None
    for idx in range(writing_indices[0], speaking_idx):
        if lines[idx].strip() == "Answer Key":
            answer_key_idx = idx
            break

    start_idx = writing_indices[0]
    if answer_key_idx is None:
        content_lines = lines[start_idx:speaking_idx]
        answer_lines = []
    else:
        content_lines = lines[start_idx:answer_key_idx - 1]
        answer_lines = lines[answer_key_idx - 1:speaking_idx]

    content = "\n".join(content_lines).strip()
    answer_key = "\n".join(answer_lines).strip()

    return {
        "content": content,
        "answer_key": answer_key,
    }


def _should_skip_speaking_line(text: str) -> bool:
    if not text:
        return True
    if text.isdigit():
        return True
    if text.startswith("TOEFL iBT"):
        return True
    if text.startswith("Teacher Resources"):
        return True
    if text.startswith("Practice Test"):
        return True
    return False


def get_speaking_section(test_id: str) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    text = _load_text(test_id)
    if not text:
        return None

    lines = [line.strip() for line in text.splitlines()]
    start_idx = next((idx for idx, line in enumerate(lines) if line.strip() == "Speaking Section"), None)
    if start_idx is None:
        return None

    repeat_items: List[Dict[str, Any]] = []
    interview_items: List[Dict[str, Any]] = []
    current_prompt: List[str] = []
    current_mode: Optional[str] = None

    def flush_prompt() -> None:
        nonlocal current_prompt, current_mode
        if current_prompt and current_mode:
            prompt_text = re.sub(r"\s+", " ", " ".join(current_prompt)).strip()
            if prompt_text:
                if current_mode == "repeat":
                    repeat_items.append({"prompt": prompt_text, "response_time_seconds": 10})
                elif current_mode == "interview":
                    interview_items.append({"prompt": prompt_text, "response_time_seconds": 45, "focus_points": []})
        current_prompt = []

    for raw in lines[start_idx + 1:]:
        line = raw.strip()
        if not line:
            continue
        if line == "Listen and Repeat":
            flush_prompt()
            current_mode = "repeat"
            continue
        if line == "Take an Interview":
            flush_prompt()
            current_mode = "interview"
            continue
        if line.endswith("Section") and line != "Speaking Section":
            flush_prompt()
            break
        if line.startswith("Trainer:"):
            flush_prompt()
            current_mode = "repeat"
            remainder = line[len("Trainer:"):].strip()
            if remainder:
                current_prompt = [remainder]
            continue
        if line.startswith("Interviewer:"):
            flush_prompt()
            current_mode = "interview"
            remainder = line[len("Interviewer:"):].strip()
            if remainder:
                current_prompt = [remainder]
            continue
        if current_prompt:
            if _should_skip_speaking_line(line):
                continue
            current_prompt.append(line)

    flush_prompt()

    if not repeat_items and not interview_items:
        return None
    return {"repeat_items": repeat_items, "items": interview_items}
