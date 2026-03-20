"""Parse full-length practice tests into New TOEFL mock payloads."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

import hashlib

from .gemini_client import get_gemini_client, GeminiClient
from .tts_service import TTSService
from .full_length_tests import get_reading_section, get_listening_section, get_writing_section

_PREBUILT_DIR = Path(__file__).resolve().parents[3] / "data" / "prebuilt" / "full_length_mocks"
_PREBUILT_ONLY = os.getenv("TOEFL_PREBUILT_ONLY", "false").lower() in {"1", "true", "yes"}


def _prebuilt_path(section: str, test_id: str) -> Path:
    return _PREBUILT_DIR / f"{section}_{test_id}.json"


def _load_prebuilt(section: str, test_id: str) -> Optional[Dict[str, Any]]:
    path = _prebuilt_path(section, test_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        current_app.logger.exception("Failed to read prebuilt mock %s", path)
        return None


def _save_prebuilt(section: str, test_id: str, payload: Dict[str, Any]) -> None:
    try:
        _PREBUILT_DIR.mkdir(parents=True, exist_ok=True)
        path = _prebuilt_path(section, test_id)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        current_app.logger.exception("Failed to save prebuilt mock %s/%s", section, test_id)


_QUESTION_RE = re.compile(r"^(\d+)\.\s*(.*)")
_OPTION_RE = re.compile(r"^\(([A-D])\)\s*(.*)")
_OCR_STOP_WORDS = {
    "a", "an", "the", "to", "of", "in", "on", "for", "or", "and", "is", "it", "as", "at", "by",
    "he", "she", "we", "they", "i", "you", "us", "our", "their", "this", "that", "these", "those",
    "be", "are", "was", "were", "but", "if", "so", "do", "did", "does", "not", "no", "yes",
    "up", "go", "am",
}
_OCR_SUFFIXES = {
    "tion", "tions", "sion", "sions", "ing", "ings", "ed", "er", "ers", "est", "able", "ible",
    "al", "ally", "ly", "ment", "ments", "ness", "ity", "ities", "ive", "ives", "ous", "ogy",
    "ogies", "gies", "egies", "tion", "tions",
}
_OCR_PHRASE_FIXES = {
    "strat egies": "strategies",
    "op tions": "options",
    "satisfac tion": "satisfaction",
    "passag e": "passage",
    "anxiet y": "anxiety",
    "t o ": "to ",
    "t omorrow": "tomorrow",
    "o f ": "of ",
    "me thodology": "methodology",
    "psy chology": "psychology",
    "suppor ting": "supporting",
    "wor d": "word",
    "closes t": "closest",
    "elimina ting": "eliminating",
    "incr easing": "increasing",
    "anenvironment": "an environment",
    "asdigestion": "as digestion",
    "andproduce": "and produce",
    "candisrupt": "can disrupt",
    "canlead": "can lead",
    "issueslike": "issues like ",
    "problemsandweakened": "problems and weakened",
    "r emind": "remind",
    "mentalhealth": "mental health",
    "Hum an": "Human",
    "h uman": "human",
    "mic robiome": "microbiome",
    "microb iome": "microbiome",
    "tr illions": "trillions",
    "mic roorganisms": "microorganisms",
    "mic robes": "microbes",
    "a nd": "and",
    "o ther": "other",
    "p lay": "play",
    "such a sdigestion": "such as digestion",
    "regulation .": "regulation.",
    "instan ce": "instance",
    "bacteri a": "bacteria",
    "an dproduce": "and produce",
    "medi cation": "medication",
    "cand isrupt": "can disrupt",
    "ca nlead": "can lead",
    "issu es": "issues",
    "lik e": "like",
    "proble ms": "problems",
    "p roble ms": "problems",
    "menta lhealth": "mental health",
    "depres sion": "depression",
    "anxie ty": "anxiety",
    "fiber ,": "fiber,",
    "stre ss": "stress",
    "avoi ding": "avoiding",
    "antibio tics": "antibiotics",
    "beneficial .": "beneficial.",
    "u nderstanding": "understanding",
    "o fthe": "of the",
    "gro ws": "grows",
    "hea lth": "health",
    "P articipation": "Participation",
    "g roups": "groups",
    "a nenvironment": "an environment",
    "i nitiative": "initiative",
    "team -building": "team-building",
    "mic robi ome": "microbiome",
    "viruse s": "viruses",
    "beable": "be able",
    "inwarm": "in warm",
    "upyesterday": "up yesterday",
    "die t": "diet",
    "b y": "by",
    "whil e": "while",
    "a gainst": "against",
    "can d isrupt": "can disrupt",
    "b alance o f": "balance of",
    "microbe s": "microbes",
    "ca n lead": "can lead",
    "h ealth": "health",
    "Researcher s": "Researchers",
    "b rain": "brain",
    "ma y": "may",
    "dig estion": "digestion",
    "digest ion": "digestion",
    "tr eating": "treating",
    "di seases": "diseases",
    "a nd medi cation": "and medication",
    "o f the": "of the",
    "you r": "your",
    "one’sown": "one’s own",
    "one'sown": "one's own",
    "Earth’sphysical": "Earth’s physical",
    "Earth'sphysical": "Earth's physical",
    "its elf": "itself",
    "it self": "itself",
}

_BAD_CONTRACTION_RE = re.compile(r"[A-Za-z]+(?:'|’)(?:re|ve|d|ll|m|t|s)[A-Za-z]+")
_BAD_SPACED_CONTRACTION_RE = re.compile(r"\b[A-Za-z]+\s+[’'](?:re|ve|d|ll|m|t)\b", re.IGNORECASE)
_BAD_PRONOUN_RE = re.compile(r"\b(my|your|our|their|his|her|its|you)([A-Za-z]{3,})\b", re.IGNORECASE)
_INLINE_OPTION_RE = re.compile(r"^\s*(\(?[A-D]\)?[).])\s+(.+)")


def _clean_lines(text: str) -> List[str]:
    lines = [line.strip() for line in (text or "").splitlines()]
    cleaned: List[str] = []
    for line in lines:
        if not line:
            continue
        if line.startswith("TOEFL iBT"):
            continue
        if line.startswith("Practice Test"):
            continue
        cleaned.append(line)
    return cleaned


def _fix_ocr_spacing(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\b([A-Za-z]+)\s+([’'])(re|ve|d|ll|m|t)\b", r"\1\2\3", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", text).strip()

    def _should_merge(left: str, right: str) -> bool:
        left_lower = left.lower()
        right_lower = right.lower()
        if right_lower in _OCR_SUFFIXES and len(left) >= 2:
            return True
        return False

    def _merge(match: re.Match[str]) -> str:
        left = match.group(1)
        right = match.group(2)
        if _should_merge(left, right):
            return f"{left}{right}"
        return match.group(0)

    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = re.sub(r"([A-Za-z]{1,})\s+([A-Za-z]{1,})", _merge, cleaned)
        def _merge_punct(match: re.Match[str]) -> str:
            left = match.group(1)
            right = match.group(2)
            punct = match.group(3)
            if _should_merge(left, right):
                return f"{left}{right}{punct}"
            return match.group(0)

        cleaned = re.sub(r"([A-Za-z]{1,})\s+([A-Za-z]{1,})([.,;:!?])", _merge_punct, cleaned)
    for bad, good in _OCR_PHRASE_FIXES.items():
        cleaned = re.sub(re.escape(bad), good, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[’']s(?=[A-Za-z])", lambda m: f"{m.group(0)} ", cleaned)
    cleaned = re.sub(r"('m)([A-Za-z])", r"\1 \2", cleaned)
    cleaned = re.sub(r"([’']ll)([A-Za-z])", r"\1 \2", cleaned)
    cleaned = re.sub(r"([’']re)([A-Za-z])", r"\1 \2", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"([’']ve)([A-Za-z])", r"\1 \2", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"([’']d)([A-Za-z])", r"\1 \2", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"([nN][’']t)([A-Za-z])", r"\1 \2", cleaned)
    cleaned = re.sub(r"([’']m)([A-Za-z])", r"\1 \2", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b([A-Za-z]+)\s+([’'])(re|ve|d|ll|m|t)\b", r"\1\2\3", cleaned, flags=re.IGNORECASE)
    for contraction in ("re", "ve", "d", "ll", "m", "t"):
        cleaned = re.sub(rf"\s+([’']{contraction})\b", r"\1", cleaned, flags=re.IGNORECASE)
    for contraction in ("'re", "’re", "'ve", "’ve", "'d", "’d", "'ll", "’ll", "'m", "’m", "'t", "’t"):
        cleaned = cleaned.replace(f" {contraction}", contraction)
    cleaned = re.sub(r"\s+([’'][A-Za-z]{1,2})\b", r"\1", cleaned)
    if "@" not in cleaned:
        def _split_pronoun(match: re.Match[str]) -> str:
            suffix = match.group(2)
            if suffix.lower().startswith("self"):
                return match.group(0)
            return f"{match.group(1)} {suffix}"
        cleaned = re.sub(r"\b(my|your|our|their|his|her|its|you)([A-Za-z’']{3,})\b", _split_pronoun, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\s*-\s*", "-", cleaned)
    return cleaned


def _repair_line_breaks(lines: List[str]) -> List[str]:
    merged: List[str] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if idx + 1 < len(lines):
            next_line = lines[idx + 1].strip()
            if line and next_line:
                last_word = line.split()[-1]
                if len(last_word) <= 2 and next_line[:1].islower():
                    if last_word.lower() in _OCR_STOP_WORDS:
                        line = f"{line} {next_line}"
                    else:
                        line = f"{line}{next_line}"
                    idx += 1
        merged.append(line)
        idx += 1
    return merged


def _has_pronoun_merge(text: str) -> bool:
    for match in _BAD_PRONOUN_RE.finditer(text):
        if not match.group(2).lower().startswith("self"):
            return True
    return False


def _payload_has_spacing_issues(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    blob = json.dumps(payload, ensure_ascii=False)
    if _BAD_CONTRACTION_RE.search(blob):
        return True
    if _BAD_SPACED_CONTRACTION_RE.search(blob):
        return True
    if _has_pronoun_merge(blob):
        return True
    lower_blob = blob.lower()
    for bad in _OCR_PHRASE_FIXES:
        if bad.lower() in lower_blob:
            return True
    return False


def _questions_have_inline_options(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    for daily in payload.get("daily_life", []) or []:
        for q in daily.get("questions", []) or []:
            if _INLINE_OPTION_RE.search(q.get("question", "")):
                return True
    for acad in payload.get("academic", []) or []:
        for q in acad.get("questions", []) or []:
            if _INLINE_OPTION_RE.search(q.get("question", "")):
                return True
    for item in payload.get("responses", []) or []:
        for q in item.get("questions", []) or []:
            if _INLINE_OPTION_RE.search(q.get("question", "")):
                return True
    for group in payload.get("conversation", []) or []:
        for q in group.get("questions", []) or []:
            if _INLINE_OPTION_RE.search(q.get("question", "")):
                return True
    for group in payload.get("talk", []) or []:
        for q in group.get("questions", []) or []:
            if _INLINE_OPTION_RE.search(q.get("question", "")):
                return True
    return False


def _reading_answers_missing(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    for daily in payload.get("daily_life", []) or []:
        for q in daily.get("questions", []) or []:
            if q.get("options") and not q.get("answer"):
                return True
    for acad in payload.get("academic", []) or []:
        for q in acad.get("questions", []) or []:
            if q.get("options") and not q.get("answer"):
                return True
    return False


def _reading_modules_missing(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    for cloze in payload.get("cloze", []) or []:
        if isinstance(cloze, dict) and cloze.get("module") is None:
            return True
    for daily in payload.get("daily_life", []) or []:
        if isinstance(daily, dict) and daily.get("module") is None:
            return True
    for acad in payload.get("academic", []) or []:
        if isinstance(acad, dict) and acad.get("module") is None:
            return True
    return False


def _reading_options_invalid(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    for daily in payload.get("daily_life", []) or []:
        for q in daily.get("questions", []) or []:
            opts = q.get("options") or []
            if opts and len(opts) != 4:
                return True
    for acad in payload.get("academic", []) or []:
        for q in acad.get("questions", []) or []:
            opts = q.get("options") or []
            if opts and len(opts) != 4:
                return True
    return False


def _listening_answers_missing(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    for item in payload.get("responses", []) or []:
        if item.get("options") and not item.get("answer"):
            return True
    for group in payload.get("conversation", []) or []:
        for q in group.get("questions", []) or []:
            if q.get("options") and not q.get("answer"):
                return True
    for group in payload.get("talk", []) or []:
        for q in group.get("questions", []) or []:
            if q.get("options") and not q.get("answer"):
                return True
    return False


def _listening_modules_missing(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    for item in payload.get("responses", []) or []:
        if isinstance(item, dict) and item.get("module") is None:
            return True
    for group in payload.get("conversation", []) or []:
        if isinstance(group, dict) and group.get("module") is None:
            return True
    for group in payload.get("talk", []) or []:
        if isinstance(group, dict) and group.get("module") is None:
            return True
    return False


def _writing_answers_missing(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    for item in payload.get("sentence_build", []) or []:
        if isinstance(item, dict) and not item.get("answer"):
            return True
    return False


def _normalize_text_spacing(text: str) -> str:
    if not text:
        return ""
    cleaned = text
    cleaned = re.sub(r"\b([A-Za-z]+)\s+([’'])(re|ve|d|ll|m|t)\b", r"\1\2\3", cleaned, flags=re.IGNORECASE)
    for contraction in ("'re", "’re", "'ve", "’ve", "'d", "’d", "'ll", "’ll", "'m", "’m", "'t", "’t"):
        cleaned = cleaned.replace(f" {contraction}", contraction)
    return cleaned


def _normalize_payload_text(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {key: _normalize_payload_text(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_normalize_payload_text(item) for item in payload]
    if isinstance(payload, str):
        return _normalize_text_spacing(payload)
    return payload


def _strip_repeated_section_headers(lines: List[str], prefix: str) -> List[str]:
    cleaned: List[str] = []
    seen = False
    for line in lines:
        if line.lower().startswith(prefix):
            if seen:
                continue
            seen = True
        cleaned.append(line)
    return cleaned


def _audio_file_exists(audio_url: Optional[str]) -> bool:
    if not audio_url:
        return False
    prefix = "/static/"
    if audio_url.startswith(prefix):
        rel_path = audio_url[len(prefix):]
    else:
        rel_path = audio_url.lstrip("/")
    audio_path = Path(current_app.root_path) / "static" / rel_path
    return audio_path.exists()


def _listening_audio_missing(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    for item in payload.get("responses", []) or []:
        prompt = (item.get("prompt") or "").strip()
        if prompt and not _audio_file_exists(item.get("audio_url")):
            return True
    for group in payload.get("conversation", []) or []:
        segments = group.get("segments") or []
        if segments and not _audio_file_exists(group.get("audio_url")):
            return True
    for group in payload.get("talk", []) or []:
        segments = group.get("segments") or []
        talk_text = (group.get("talk") or "").strip()
        if (segments or talk_text) and not _audio_file_exists(group.get("audio_url")):
            return True
    return False


def _parse_answer_key(answer_text: str) -> Dict[int, str]:
    answers: Dict[int, str] = {}
    lines = [line.strip() for line in _clean_lines(answer_text) if line.strip()]
    idx = 0
    headers = {"question", "number", "answer", "question number"}
    stop_prefixes = ("reading section", "listening section", "writing section", "speaking section", "answer key")
    while idx < len(lines):
        line = lines[idx].strip()
        lower = line.lower()
        if lower in headers:
            idx += 1
            continue
        if lower.startswith(stop_prefixes):
            idx += 1
            continue
        inline_match = re.match(r"^(\d+)\s+(.+)$", line)
        if inline_match:
            answers[int(inline_match.group(1))] = inline_match.group(2).strip()
            idx += 1
            continue
        if re.match(r"^\d+$", line):
            num = int(line)
            idx += 1
            while idx < len(lines) and lines[idx].strip().lower() in headers:
                idx += 1
            answer_parts = []
            while idx < len(lines):
                candidate = lines[idx].strip()
                if not candidate:
                    idx += 1
                    continue
                lower_candidate = candidate.lower()
                if lower_candidate.startswith(stop_prefixes):
                    break
                if re.match(r"^\d+$", candidate):
                    break
                if lower_candidate in headers:
                    idx += 1
                    continue
                answer_parts.append(candidate)
                idx += 1
            if answer_parts:
                answers[num] = " ".join(answer_parts).strip()
            continue
        idx += 1

    if len(answers) <= 1:
        tokens = []
        for line in lines:
            lower = line.lower()
            if lower in headers or lower.startswith(stop_prefixes):
                continue
            tokens.append(line)
        numbers = [int(tok) for tok in tokens if re.match(r"^\d+$", tok)]
        non_numbers = [tok for tok in tokens if not re.match(r"^\d+$", tok)]
        if numbers and non_numbers:
            seq: List[int] = []
            started = False
            for num in numbers:
                if not started:
                    if num == 1:
                        seq.append(num)
                        started = True
                    continue
                if num == seq[-1] + 1:
                    seq.append(num)
                else:
                    break
            if seq and len(non_numbers) >= len(seq):
                answers = {seq[idx]: non_numbers[idx] for idx in range(len(seq))}
    return answers


def _merge_wrapped_lines(lines: List[str]) -> List[str]:
    merged: List[str] = []
    buffer = ""
    for line in lines:
        if _QUESTION_RE.match(line) or _OPTION_RE.match(line) or line.lower().startswith("read "):
            if buffer:
                merged.append(buffer.strip())
                buffer = ""
            merged.append(line)
            continue
        if buffer:
            buffer = f"{buffer} {line}"
        else:
            buffer = line
    if buffer:
        merged.append(buffer.strip())
    return merged


def _normalize_cloze_paragraph(text: str) -> str:
    cleaned = text.replace("\n", " ")
    cleaned = re.sub(r"\((\d+)\s+blank lines?\)", lambda m: "_" * int(m.group(1)), cleaned, flags=re.IGNORECASE)
    cleaned = _fix_ocr_spacing(cleaned)
    cleaned = re.sub(r"[–—-]", "_", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\b([A-Za-z]+)\s+(_+)\s*([A-Za-z])", r"\1\2 \3", cleaned)
    def _join_single(match: re.Match[str]) -> str:
        left = match.group(1)
        right = match.group(2)
        if left.lower() in {"a", "i"}:
            return match.group(0)
        return f"{left}{right}"
    cleaned = re.sub(r"\b([A-Za-z])\s+([a-z])", _join_single, cleaned)
    cleaned = re.sub(r"([A-Za-z])\s+(_(?:\s*_)+)", lambda m: m.group(1) + m.group(2).replace(" ", ""), cleaned)
    while re.search(r"_\s+_", cleaned):
        cleaned = re.sub(r"_\s+_", "__", cleaned)
    cleaned = re.sub(r"(_{2,})([A-Za-z])", r"\1 \2", cleaned)
    cleaned = re.sub(r"one’sown", "one’s own", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"one'sown", "one's own", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bandable\b", "and able", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Earth’sphysical", "Earth’s physical", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Earth'sphysical", "Earth's physical", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _parse_cloze(module_lines: List[str], answers: Dict[int, str]) -> Tuple[Optional[Dict[str, Any]], int]:
    if "Fill in the missing letters in the paragraph." not in module_lines:
        return None, 0
    start = module_lines.index("Fill in the missing letters in the paragraph.") + 1
    end = start
    while end < len(module_lines) and not module_lines[end].lower().startswith("read "):
        end += 1
    paragraph_lines = [line for line in module_lines[start:end] if not line.lower().startswith("(questions")]
    paragraph = _normalize_cloze_paragraph(" ".join(paragraph_lines))
    if not paragraph:
        return None, end

    tokens = re.findall(r"\b[A-Za-z]+_+\b", paragraph)
    blanks = []
    for idx, token in enumerate(tokens, start=1):
        missing = answers.get(idx, "")
        prefix = token.rstrip("_")
        answer = f"{prefix}{missing}"
        blanks.append({
            "token": token,
            "answer": answer,
            "part_of_speech": "unknown",
            "hint": "Complete the word using context.",
        })
    return {"id": f"cloze_full_{hash(paragraph) & 0xffff}", "paragraph": paragraph, "blanks": blanks}, end


def _is_title_line(line: str) -> bool:
    if not line or len(line) > 80:
        return False
    lower = line.lower()
    if lower.startswith(("read ", "to:", "from:", "date:", "subject:")):
        return False
    if _OPTION_RE.match(line):
        return False
    if line.endswith((".", "?", "!", ":")):
        return False
    words = [w for w in re.split(r"\s+", line) if w]
    if not words:
        return False
    cap_count = sum(1 for w in words if w[:1].isupper())
    return cap_count / len(words) >= 0.6


def _split_title_line(lines: List[str]) -> Tuple[str, List[str]]:
    if not lines:
        return "", []
    first = lines[0].strip()
    if _is_title_line(first):
        return first, lines[1:]
    return "", lines


def _parse_questions(
    lines: List[str],
    start_idx: int,
    stop_numbers: Optional[set[int]] = None,
    stop_prefixes: Optional[List[str]] = None,
    max_question: Optional[int] = None,
    min_question: Optional[int] = None,
    allow_unnumbered: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    questions: List[Dict[str, Any]] = []
    idx = start_idx
    stop_prefixes = [p.lower() for p in (stop_prefixes or [])]
    while idx < len(lines):
        line = lines[idx]
        lower = line.lower()
        if any(lower.startswith(prefix) for prefix in stop_prefixes):
            break
        q_match = _QUESTION_RE.match(line)
        if not q_match:
            if allow_unnumbered:
                peek_idx = idx
                question_parts: List[str] = []
                option_found = False
                while peek_idx < len(lines):
                    candidate = lines[peek_idx].strip()
                    lower_candidate = candidate.lower()
                    if any(lower_candidate.startswith(prefix) for prefix in stop_prefixes):
                        break
                    if _QUESTION_RE.match(candidate):
                        break
                    if _OPTION_RE.match(candidate):
                        option_found = True
                        break
                    if candidate:
                        question_parts.append(candidate)
                    peek_idx += 1
                if option_found and question_parts:
                    q_num = None
                    question_text = _fix_ocr_spacing(" ".join(question_parts).strip())
                    idx = peek_idx
                else:
                    idx += 1
                    continue
            else:
                idx += 1
                continue
        else:
            q_num = int(q_match.group(1))
            if min_question is not None and q_num < min_question:
                idx += 1
                continue
            if stop_numbers and q_num in stop_numbers:
                break
            question_text = _fix_ocr_spacing(q_match.group(2).strip())
            idx += 1
        options: List[str] = []
        inline_match = _INLINE_OPTION_RE.search(question_text)
        if inline_match:
            question_text = question_text[:inline_match.start()].strip()
            options.append(_fix_ocr_spacing(inline_match.group(2).strip()))
        stop_reached = False
        while idx < len(lines):
            line = lines[idx]
            lower = line.lower()
            if any(lower.startswith(prefix) for prefix in stop_prefixes):
                stop_reached = True
                break
            if _is_title_line(line) and options:
                stop_reached = True
                break
            if allow_unnumbered and options and not _OPTION_RE.match(line) and not _QUESTION_RE.match(line):
                peek_idx = idx
                saw_question_mark = False
                option_ahead = False
                while peek_idx < len(lines) and peek_idx < idx + 3:
                    candidate = lines[peek_idx].strip()
                    if candidate.endswith("?"):
                        saw_question_mark = True
                    if _OPTION_RE.match(candidate):
                        option_ahead = True
                        break
                    peek_idx += 1
                if saw_question_mark and option_ahead:
                    break
            opt_match = _OPTION_RE.match(line)
            if opt_match:
                options.append(_fix_ocr_spacing(opt_match.group(2).strip()))
                idx += 1
                continue
            if _QUESTION_RE.match(line):
                break
            if options:
                options[-1] = _fix_ocr_spacing(f"{options[-1]} {line}".strip())
            else:
                question_text = _fix_ocr_spacing(f"{question_text} {line}".strip())
            idx += 1
        questions.append({"number": q_num, "question": question_text, "options": options})
        if max_question is not None and q_num >= max_question:
            break
        if stop_reached:
            break
    return questions, idx


def _parse_daily_content(
    caption: str,
    content_lines: List[str],
) -> Dict[str, Any]:
    caption_clean = caption.strip()
    lower_caption = caption_clean.lower()
    result: Dict[str, Any] = {
        "caption": caption_clean,
        "format": "notice",
        "title": "",
        "author": "",
        "headers": {},
        "body_lines": [],
        "footer_lines": [],
        "source_lines": content_lines,
    }

    if "social media post" in lower_caption:
        result["format"] = "social"
        if content_lines:
            result["author"] = content_lines[0].strip()
            body_lines = content_lines[1:]
        else:
            body_lines = []
        footer_lines = []
        if body_lines and body_lines[-1].strip().lower() == "like comment":
            footer_lines = [body_lines[-1]]
            body_lines = body_lines[:-1]
        result["body_lines"] = body_lines
        result["footer_lines"] = footer_lines
        result["title"] = result["author"]
        return result

    if "read an email" in lower_caption or "read a email" in lower_caption or "read an e-mail" in lower_caption:
        result["format"] = "email"
        headers: Dict[str, str] = {}
        body_lines: List[str] = []
        idx = 0
        while idx < len(content_lines):
            line = content_lines[idx].strip()
            lower = line.lower()
            if lower.startswith("to:"):
                headers["to"] = line.split(":", 1)[-1].strip()
            elif lower.startswith("from:"):
                headers["from"] = line.split(":", 1)[-1].strip()
            elif lower.startswith("date:"):
                headers["date"] = line.split(":", 1)[-1].strip()
            elif lower.startswith("subject:"):
                headers["subject"] = line.split(":", 1)[-1].strip()
            else:
                body_lines = content_lines[idx:]
                break
            idx += 1
        result["headers"] = headers
        result["body_lines"] = body_lines
        result["title"] = headers.get("subject", "")
        return result

    # Default: notice-style
    if content_lines:
        result["title"] = content_lines[0].strip()
        result["body_lines"] = content_lines[1:]
    else:
        result["body_lines"] = []
    return result


def _generate_rationales(
    client: GeminiClient,
    question: Dict[str, Any],
    source_text: str,
    include_evidence: bool = False,
) -> Dict[str, Any]:
    if not client or not client.is_configured:
        return {"rationales": {}, "evidence_quote": None}

    options = question.get("options") or []
    prompt = f"""
You are a TOEFL test explainer. Provide concise rationales for every option,
explicitly stating why each wrong option is incorrect or unsupported.

Source:
{source_text}

Question:
{question.get('question')}

Options:
{chr(10).join([f"{idx+1}. {opt}" for idx, opt in enumerate(options)])}

Correct option (verbatim):
{question.get('answer')}

Return strict JSON:
{{
  "rationales": ["<=18 words each, in the same order as options"],
  "evidence_quote": "{'short quote from source supporting the correct answer' if include_evidence else ''}"
}}
"""
    try:
        result = client.generate_json(
            prompt=prompt,
            temperature=0.2,
            system_instruction="You are a concise TOEFL explainer. Output JSON only.",
            max_output_tokens=600,
        )
    except Exception as exc:
        current_app.logger.warning("Rationale generation failed: %s", exc)
        return {"rationales": {}, "evidence_quote": None}

    payload = result if isinstance(result, dict) else {}
    rationales_list = payload.get("rationales") if isinstance(payload, dict) else None
    if not isinstance(rationales_list, list) or len(rationales_list) != len(options):
        return {"rationales": {}, "evidence_quote": None}

    rationales = {opt: str(rationales_list[idx]) for idx, opt in enumerate(options)}
    evidence = payload.get("evidence_quote") if include_evidence else None
    return {"rationales": rationales, "evidence_quote": evidence}


def build_full_length_reading_mock(test_id: str, client: Optional[GeminiClient] = None) -> Optional[Dict[str, Any]]:
    prebuilt = _load_prebuilt("reading", test_id)
    if (
        prebuilt
        and not _payload_has_spacing_issues(prebuilt)
        and not _questions_have_inline_options(prebuilt)
        and not _reading_answers_missing(prebuilt)
        and not _reading_options_invalid(prebuilt)
        and not _reading_modules_missing(prebuilt)
    ):
        return prebuilt
    if _PREBUILT_ONLY:
        current_app.logger.warning("Prebuilt reading mock missing for %s (TOEFL_PREBUILT_ONLY enabled).", test_id)
        return None

    section = get_reading_section(test_id)
    if not section:
        return None

    client = client or get_gemini_client()
    cloze: List[Dict[str, Any]] = []
    daily: List[Dict[str, Any]] = []
    academics: List[Dict[str, Any]] = []

    for module_idx, module_key in enumerate(("module1", "module2"), start=1):
        module_text = section.get(module_key, "")
        answer_text = section.get(f"answer_key_module{module_idx}", "")
        answers = _parse_answer_key(answer_text)
        lines = _clean_lines(module_text)
        lines = _strip_repeated_section_headers(lines, "reading section")

        cloze_item, cursor = _parse_cloze(lines, answers)
        if cloze_item:
            cloze_item["module"] = module_idx
            cloze.append(cloze_item)

        # Daily life blocks (questions 11-15)
        idx = cursor
        while idx < len(lines):
            line = lines[idx]
            if line.lower().startswith(("read a ", "read an ")):
                caption = line.strip()
                source_type = caption.split(" ", 1)[1].replace(".", "").strip().lower()
                idx += 1
                content_lines: List[str] = []
                while idx < len(lines) and not _QUESTION_RE.match(lines[idx]):
                    if lines[idx].lower().startswith(("read a ", "read an ")):
                        break
                    content_lines.append(lines[idx])
                    idx += 1
                # If the daily content includes numbered rules (e.g., 1. 2. 3.), keep them as content
                while idx < len(lines) and _QUESTION_RE.match(lines[idx]):
                    q_match = _QUESTION_RE.match(lines[idx])
                    q_num = int(q_match.group(1)) if q_match else None
                    if q_num is not None and q_num >= 11:
                        break
                    content_lines.append(lines[idx])
                    idx += 1
                content_lines = _repair_line_breaks(content_lines)
                content_lines = [_fix_ocr_spacing(line) for line in content_lines if line]
                content = _parse_daily_content(caption, content_lines)
                source_text = " ".join(content_lines).strip()
                questions, idx = _parse_questions(
                    lines,
                    idx,
                    stop_numbers={16},
                    stop_prefixes=["read a", "read an"],
                    max_question=15,
                    min_question=11,
                )
                for q in questions:
                    if q.get("number") in answers and q.get("options"):
                        letter = answers[q["number"]]
                        index = ord(letter.upper()) - ord("A")
                        if 0 <= index < len(q["options"]):
                            q["answer"] = q["options"][index]
                            rationale = _generate_rationales(client, q, source_text, include_evidence=True)
                            q["rationales"] = rationale["rationales"]
                            q["evidence_quote"] = rationale["evidence_quote"]
                daily.append({
                    "id": f"daily_{module_idx}_{len(daily)}",
                    "module": module_idx,
                    "caption": content.get("caption", caption),
                    "format": content.get("format"),
                    "title": content.get("title", ""),
                    "author": content.get("author", ""),
                    "headers": content.get("headers", {}),
                    "body_lines": content.get("body_lines", []),
                    "footer_lines": content.get("footer_lines", []),
                    "source_lines": content.get("source_lines", content_lines),
                    "source_text": source_text,
                    "source_type": source_type,
                    "questions": [q for q in questions if q.get("number") and q.get("number") <= 15],
                })
                continue
            if line.lower().startswith("reading section"):
                break
            if _is_title_line(line):
                break
            if _QUESTION_RE.match(line):
                break
            idx += 1

        # Academic passage (questions 16-20)
        passage_lines: List[str] = []
        while idx < len(lines) and not _QUESTION_RE.match(lines[idx]):
            passage_lines.append(lines[idx])
            idx += 1
        passage_lines = _repair_line_breaks(passage_lines)
        passage_lines = [_fix_ocr_spacing(line) for line in passage_lines if line]
        title = ""
        body_lines = passage_lines
        if passage_lines:
            possible_title, remainder = _split_title_line(passage_lines)
            if possible_title:
                title = _fix_ocr_spacing(possible_title)
                body_lines = remainder
        passage = " ".join(passage_lines).strip()
        questions, idx = _parse_questions(lines, idx, max_question=20, min_question=16)
        for q in questions:
            if q.get("number") in answers and q.get("options"):
                letter = answers[q["number"]]
                index = ord(letter.upper()) - ord("A")
                if 0 <= index < len(q["options"]):
                    q["answer"] = q["options"][index]
                    rationale = _generate_rationales(client, q, passage, include_evidence=True)
                    q["rationales"] = rationale["rationales"]
                    q["evidence_quote"] = rationale["evidence_quote"]
        if passage and questions:
            academics.append({
                "id": f"academic_{module_idx}",
                "module": module_idx,
                "title": title,
                "passage_lines": body_lines,
                "passage": passage,
                "questions": questions,
            })

    payload = {
        "cloze": cloze,
        "daily_life": daily,
        "academic": academics,
    }
    payload = _normalize_payload_text(payload)
    _save_prebuilt("reading", test_id, payload)
    return payload


def build_full_length_listening_mock(
    test_id: str,
    client: Optional[GeminiClient] = None,
    tts: Optional[TTSService] = None,
) -> Optional[Dict[str, Any]]:
    prebuilt = _load_prebuilt("listening", test_id)
    if (
        prebuilt
        and not _payload_has_spacing_issues(prebuilt)
        and not _questions_have_inline_options(prebuilt)
        and not _listening_audio_missing(prebuilt)
        and not _listening_answers_missing(prebuilt)
        and not _listening_modules_missing(prebuilt)
    ):
        return prebuilt
    if _PREBUILT_ONLY:
        current_app.logger.warning("Prebuilt listening mock missing for %s (TOEFL_PREBUILT_ONLY enabled).", test_id)
        return None

    section = get_listening_section(test_id)
    if not section:
        return None

    client = client or get_gemini_client()
    tts = tts or TTSService()

    responses: List[Dict[str, Any]] = []
    conversations: List[Dict[str, Any]] = []
    talks: List[Dict[str, Any]] = []

    def _strip_speaker_prefix(text: str) -> str:
        if not text:
            return ""
        match = re.match(r"^\s*(?:Man|Woman|Professor|Podcast Host|Host|Interviewer|Speaker|Trainer):\s*(.+)$", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _cache_key(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]

    def _collect_speaker_segments(lines: List[str], start_idx: int) -> Tuple[List[Dict[str, str]], int]:
        segments: List[Dict[str, str]] = []
        idx = start_idx
        while idx < len(lines):
            line = lines[idx].strip()
            lower = line.lower()
            if _QUESTION_RE.match(line) or lower.startswith("listen to"):
                break
            if line.endswith("?"):
                peek_idx = idx + 1
                while peek_idx < len(lines) and not lines[peek_idx].strip():
                    peek_idx += 1
                if peek_idx < len(lines) and _OPTION_RE.match(lines[peek_idx].strip()):
                    break
            if ":" in line:
                speaker, text = line.split(":", 1)
                segments.append({"speaker": speaker.strip(), "text": _fix_ocr_spacing(text.strip())})
            else:
                if segments:
                    segments[-1]["text"] = _fix_ocr_spacing(f"{segments[-1]['text']} {line}".strip())
            idx += 1
        return segments, idx

    for module_idx, module_key in enumerate(("module1", "module2"), start=1):
        module_text = section.get(module_key, "")
        answer_text = section.get(f"answer_key_module{module_idx}", "")
        answers = _parse_answer_key(answer_text)
        lines = _clean_lines(module_text)
        lines = _strip_repeated_section_headers(lines, "listening section")

        # Responses (1-8)
        resp_questions, idx = _parse_questions(
            lines,
            0,
            stop_prefixes=["listen to a conversation", "listen to an announcement", "listen to a talk"],
            max_question=8,
        )
        next_question_number = 1
        if resp_questions:
            max_resp = max((q.get("number") or 0) for q in resp_questions)
            next_question_number = max_resp + 1
        for q in resp_questions:
            if q.get("number") and q.get("number") <= 8:
                letter = answers.get(q["number"])
                if letter:
                    index = ord(letter.upper()) - ord("A")
                    if 0 <= index < len(q["options"]):
                        q["answer"] = q["options"][index]
                        rationale = _generate_rationales(client, q, q.get("question") or "", include_evidence=False)
                        q["rationales"] = rationale["rationales"]
                responses.append({
                    "prompt": _strip_speaker_prefix(q.get("question") or ""),
                    "options": q.get("options"),
                    "answer": q.get("answer"),
                    "rationales": q.get("rationales") or {},
                    "module": module_idx,
                })
        # Parse conversations and talks
        idx = 0
        while idx < len(lines):
            line = lines[idx].lower()
            if line.startswith("listen to a conversation"):
                idx += 1
                segments, idx = _collect_speaker_segments(lines, idx)
                segment_text = " ".join([seg.get("text", "") for seg in segments]).strip()
                questions, idx = _parse_questions(
                    lines,
                    idx,
                    stop_prefixes=["listen to"],
                    max_question=None,
                    allow_unnumbered=True,
                )
                for q in questions:
                    if q.get("number") is None:
                        q["number"] = next_question_number
                        next_question_number += 1
                    else:
                        if q["number"] >= next_question_number:
                            next_question_number = q["number"] + 1
                    letter = answers.get(q.get("number"))
                    if letter:
                        opt_idx = ord(letter.upper()) - ord("A")
                        if 0 <= opt_idx < len(q["options"]):
                            q["answer"] = q["options"][opt_idx]
                            rationale = _generate_rationales(client, q, segment_text, include_evidence=False)
                            q["rationales"] = rationale["rationales"]
                conv = {
                    "id": f"conv_{module_idx}_{len(conversations)}",
                    "segments": segments,
                    "questions": questions,
                    "module": module_idx,
                }
                segment_text = " ".join([f"{seg.get('speaker', '')}:{seg.get('text', '')}" for seg in segments]).strip()
                audio = tts.generate_multi_speaker_audio_cached(
                    segments,
                    filename_prefix="new_toefl_conversation",
                    cache_key=_cache_key(segment_text),
                )
                if audio:
                    conv["audio_url"] = f"/static/{audio.audio_path}"
                conversations.append(conv)
                continue
            if line.startswith("listen to an announcement") or line.startswith("listen to a talk"):
                idx += 1
                segments, idx = _collect_speaker_segments(lines, idx)
                talk_text = " ".join([seg.get("text", "") for seg in segments]).strip()
                questions, idx = _parse_questions(
                    lines,
                    idx,
                    stop_prefixes=["listen to"],
                    max_question=None,
                    allow_unnumbered=True,
                )
                for q in questions:
                    if q.get("number") is None:
                        q["number"] = next_question_number
                        next_question_number += 1
                    else:
                        if q["number"] >= next_question_number:
                            next_question_number = q["number"] + 1
                    letter = answers.get(q.get("number"))
                    if letter:
                        opt_idx = ord(letter.upper()) - ord("A")
                        if 0 <= opt_idx < len(q["options"]):
                            q["answer"] = q["options"][opt_idx]
                            rationale = _generate_rationales(client, q, talk_text, include_evidence=False)
                            q["rationales"] = rationale["rationales"]
                talk = {
                    "id": f"talk_{module_idx}_{len(talks)}",
                    "talk": talk_text,
                    "questions": questions,
                    "module": module_idx,
                }
                audio = tts.generate_audio_cached(
                    talk_text,
                    filename_prefix="new_toefl_talk",
                    cache_key=_cache_key(talk_text),
                )
                if audio:
                    talk["audio_url"] = f"/static/{audio.audio_path}"
                talks.append(talk)
                continue
            idx += 1

    # Add audio for response prompts
    for item in responses:
        prompt_text = str(item.get("prompt") or "")
        if not prompt_text:
            continue
        audio = tts.generate_audio_cached(
            prompt_text,
            filename_prefix="new_toefl_response",
            cache_key=_cache_key(prompt_text),
        )
        if audio:
            item["audio_url"] = f"/static/{audio.audio_path}"

    payload = {
        "responses": responses,
        "conversation": conversations,
        "talk": talks,
    }
    payload = _normalize_payload_text(payload)
    _save_prebuilt("listening", test_id, payload)
    return payload


def build_full_length_writing_mock(test_id: str) -> Optional[Dict[str, Any]]:
    prebuilt = _load_prebuilt("writing", test_id)
    if prebuilt:
        sentence_build = prebuilt.get("sentence_build", [])
        missing_context = any(isinstance(item, dict) and not item.get("context") for item in sentence_build)
        if not missing_context and not _payload_has_spacing_issues(prebuilt) and not _writing_answers_missing(prebuilt):
            return prebuilt
    if _PREBUILT_ONLY:
        current_app.logger.warning("Prebuilt writing mock missing for %s (TOEFL_PREBUILT_ONLY enabled).", test_id)
        return None

    section = get_writing_section(test_id)
    if not section:
        return None

    content = section.get("content", "")
    answer_key = section.get("answer_key", "")
    answer_map = _parse_answer_key(answer_key)
    lines = _clean_lines(content)
    lines = _repair_line_breaks(lines)
    lines = [_fix_ocr_spacing(line) for line in lines if line]

    sentence_build: List[Dict[str, Any]] = []
    blank_re = re.compile(r"_{2,}")
    idx = 0
    while idx < len(lines):
        match = _QUESTION_RE.match(lines[idx])
        if match and int(match.group(1)) <= 10:
            prompt = _fix_ocr_spacing(match.group(2).strip())
            idx += 1
            tokens = []
            context_line = ""
            if idx < len(lines):
                candidate = lines[idx]
                if blank_re.search(candidate) and "/" in candidate and "?" in candidate:
                    context_part, token_part = candidate.split("?", 1)
                    if blank_re.search(context_part):
                        context_line = _fix_ocr_spacing(context_part.strip())
                    tokens = [_fix_ocr_spacing(t.strip()) for t in token_part.split("/") if t.strip()]
                    idx += 1
                elif blank_re.search(candidate) and "/" not in candidate:
                    context_line = _fix_ocr_spacing(candidate.strip())
                    idx += 1
            if not tokens and idx < len(lines) and "/" in lines[idx]:
                token_line = lines[idx]
                if "?" in token_line:
                    before, after = token_line.split("?", 1)
                    if not context_line and blank_re.search(before):
                        context_line = _fix_ocr_spacing(before.strip())
                    token_line = after
                tokens = [_fix_ocr_spacing(t.strip()) for t in token_line.split("/") if t.strip()]
                idx += 1
            elif not tokens:
                scan_limit = min(idx + 4, len(lines))
                while idx < scan_limit:
                    if "/" in lines[idx]:
                        token_line = lines[idx]
                        if "?" in token_line:
                            before, after = token_line.split("?", 1)
                            if not context_line and blank_re.search(before):
                                context_line = _fix_ocr_spacing(before.strip())
                            token_line = after
                        tokens = [_fix_ocr_spacing(t.strip()) for t in token_line.split("/") if t.strip()]
                        idx += 1
                        break
                    idx += 1
            if tokens and not context_line:
                first = tokens[0]
                if "_" in first:
                    split_match = re.match(r"^(.*[.!?])\s*([A-Za-z']+)$", first)
                    if split_match and blank_re.search(split_match.group(1)):
                        context_line = _fix_ocr_spacing(split_match.group(1).strip())
                        tokens[0] = _fix_ocr_spacing(split_match.group(2).strip())
            answer = answer_map.get(int(match.group(1)), "")
            item = {"prompt": prompt, "tokens": tokens, "answer": answer}
            if context_line:
                item["context"] = context_line
            sentence_build.append(item)
            continue
        idx += 1

    email_idx = next((i for i, line in enumerate(lines) if line.strip().lower() == "write an email"), None)
    discussion_idx = next((i for i, line in enumerate(lines) if line.strip().lower() == "write for an academic discussion"), None)
    email_task = None
    discussion_task = None

    if email_idx is not None:
        end_idx = discussion_idx if discussion_idx is not None else len(lines)
        email_block = lines[email_idx + 1:end_idx]
        scenario_lines = []
        instructions = []
        to_name = "Student"
        subject = "Request"
        for line in email_block:
            if line.startswith("•"):
                instructions.append(line.replace("•", "").strip())
            elif line.lower().startswith("to:"):
                to_name = line.split(":", 1)[-1].strip()
            elif line.lower().startswith("subject:"):
                subject = line.split(":", 1)[-1].strip()
            elif line.lower().startswith("write an email"):
                continue
            elif line.lower().startswith("you will"):
                continue
            elif line.lower().startswith("write as much"):
                continue
            elif "Your Response" in line:
                continue
            else:
                scenario_lines.append(line)
        email_task = {
            "id": f"email_{test_id}",
            "scenario": " ".join(scenario_lines).strip(),
            "instructions": instructions[:3],
            "to_name": to_name,
            "subject": subject,
        }

    if discussion_idx is not None:
        discussion_block = lines[discussion_idx + 1:]
        professor_lines = []
        student_posts: List[Dict[str, str]] = []
        for line in discussion_block:
            lower = line.lower()
            if lower.startswith("yes,") or lower.startswith("i don") or lower.startswith("i think") or lower.startswith("i believe"):
                break
            if lower.startswith("a professor has posted"):
                continue
            if lower.startswith("you will"):
                continue
            if lower.startswith("your professor"):
                continue
            if lower.startswith("an effective response"):
                continue
            if "make a contribution" in lower:
                continue
            if line.startswith("•"):
                continue
            professor_lines.append(line)
        remaining = discussion_block[len(professor_lines):]
        idx = 0
        while idx < len(remaining):
            line = remaining[idx]
            if not line:
                idx += 1
                continue
            lower = line.lower()
            if lower.startswith("yes") or lower.startswith("i don") or lower.startswith("i think") or lower.startswith("i believe"):
                message_lines = [line]
                idx += 1
                while idx < len(remaining):
                    next_line = remaining[idx]
                    next_lower = next_line.lower()
                    if not next_line:
                        idx += 1
                        continue
                    if next_lower.startswith(("yes", "i don", "i think", "i believe")):
                        break
                    if next_lower.startswith(("a professor has posted", "you will", "your professor", "an effective response")):
                        idx += 1
                        continue
                    message_lines.append(next_line)
                    idx += 1
                message = " ".join(message_lines).strip()
                if lower.startswith("yes") or lower.startswith("i think"):
                    student_posts.append({"name": "Student A", "stance": "Agree", "message": message})
                else:
                    student_posts.append({"name": "Student B", "stance": "Disagree", "message": message})
                if len(student_posts) >= 2:
                    break
            else:
                idx += 1

        discussion_task = {
            "id": f"discussion_{test_id}",
            "professor_prompt": " ".join(professor_lines).strip(),
            "student_posts": student_posts,
        }

    payload = {
        "sentence_build": sentence_build,
        "email": email_task,
        "discussion": discussion_task,
    }
    payload = _normalize_payload_text(payload)
    _save_prebuilt("writing", test_id, payload)
    return payload
