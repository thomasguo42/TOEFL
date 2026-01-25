"""Helpers to enforce single-correct multiple choice questions.

We can't perfectly prove semantic unambiguity without a model, but we can:
- enforce strict schema (4 distinct options, answer ∈ options)
- ensure rationale coverage for each option when provided

Generators should use these checks to retry/regenerate when DeepSeek returns
ambiguous or malformed items.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_options(options: Any) -> List[str]:
    if not isinstance(options, list):
        return []
    cleaned: List[str] = []
    for opt in options:
        text = _clean_text(opt)
        if text:
            cleaned.append(text)
    return cleaned


def has_casefold_duplicates(values: Sequence[str]) -> bool:
    seen = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            return True
        seen.add(key)
    return False


def validate_four_option_mcq(
    *,
    options: Any,
    answer: Any,
    rationales: Optional[Any] = None,
) -> Tuple[bool, List[str]]:
    """Validate a standard 4-option MCQ with a single correct answer."""
    issues: List[str] = []

    normalized_options = normalize_options(options)
    if len(normalized_options) != 4:
        issues.append(f"expected 4 options, got {len(normalized_options)}")
        return False, issues

    if has_casefold_duplicates(normalized_options):
        issues.append("options contain duplicates (case-insensitive)")

    answer_text = _clean_text(answer)
    if not answer_text:
        issues.append("answer is empty")
    elif answer_text not in normalized_options:
        issues.append("answer does not exactly match any option")

    if rationales is not None:
        if not isinstance(rationales, dict):
            issues.append("rationales is not an object")
        else:
            # Accept exact-key match only; callers can remap if desired.
            for opt in normalized_options:
                rationale = _clean_text(rationales.get(opt))
                if not rationale:
                    issues.append(f"missing rationale for option: {opt}")

    return len(issues) == 0, issues


def validate_many_mcqs(
    items: Any,
    *,
    option_key: str = "options",
    answer_key: str = "answer",
    rationales_key: Optional[str] = "rationales",
) -> Tuple[bool, List[str]]:
    """Validate a list of MCQ dicts; returns (ok, issues)."""
    if not isinstance(items, list):
        return False, ["items is not a list"]

    issues: List[str] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            issues.append(f"item {idx} is not an object")
            continue
        ok, item_issues = validate_four_option_mcq(
            options=item.get(option_key),
            answer=item.get(answer_key),
            rationales=item.get(rationales_key) if rationales_key else None,
        )
        if not ok:
            issues.extend([f"item {idx}: {issue}" for issue in item_issues])

    return len(issues) == 0, issues


def llm_check_unambiguous_mcq(
    client: Any,
    *,
    context: str,
    question: str,
    options: Sequence[str],
    answer: str,
    strict: bool = True,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Ask an LLM to judge whether the MCQ is unambiguous (exactly one correct choice).

    This is best-effort and should be used as a gate before shipping generated items.
    Set `MCQ_RIGOR_LLM_CHECK=false` to disable.
    """
    enabled = os.getenv("MCQ_RIGOR_LLM_CHECK", "true").strip().lower() in {"1", "true", "yes", "y"}
    if not enabled:
        return True, None

    if not client:
        return True, None

    context_text = _clean_text(context)
    question_text = _clean_text(question)
    options_list = [str(opt) for opt in options]
    answer_text = _clean_text(answer)
    if not question_text or not options_list or not answer_text:
        return False, {"unambiguous": False, "issues": ["missing question/options/answer"]}

    prompt = (
        "You are validating a TOEFL-style multiple choice item for ambiguity.\n\n"
        "Decide if EXACTLY ONE option is correct given the context.\n"
        "Rules:\n"
        "- If more than one option could reasonably be correct, mark unambiguous=false.\n"
        "- If the correct answer is not uniquely supported, mark unambiguous=false.\n"
        "- If any distractor is also acceptable (even as a polite variant), mark unambiguous=false.\n"
        "- Be strict.\n\n"
        f"CONTEXT:\n{context_text}\n\n"
        f"QUESTION:\n{question_text}\n\n"
        "OPTIONS:\n"
        + "\n".join([f"- {opt}" for opt in options_list])
        + "\n\n"
        f"PROPOSED ANSWER:\n{answer_text}\n\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "unambiguous": boolean,\n'
        '  "other_plausible_options": [string],\n'
        '  "issues": [string]\n'
        "}\n"
    )

    try:
        result = client.generate_json(
            prompt,
            temperature=0.0 if strict else 0.2,
            system_instruction="You are a meticulous exam-item validator. Be strict and concise.",
            max_output_tokens=600,
        )
    except Exception as exc:
        return False, {"unambiguous": False, "issues": [f"validator error: {str(exc)[:120]}"]}

    if not isinstance(result, dict):
        return False, {"unambiguous": False, "issues": ["validator returned non-object"]}

    unambiguous = result.get("unambiguous")
    if unambiguous is True:
        return True, result
    return False, result
