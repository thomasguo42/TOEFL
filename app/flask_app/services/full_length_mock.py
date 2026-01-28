"""Parse full-length practice tests into New TOEFL mock payloads."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from .gemini_client import get_gemini_client, GeminiClient
from .tts_service import TTSService
from .full_length_tests import get_reading_section, get_listening_section, get_writing_section


_QUESTION_RE = re.compile(r"^(\d+)\.\s*(.*)")
_OPTION_RE = re.compile(r"^\(([A-D])\)\s*(.*)")
_OCR_STOP_WORDS = {
    "a", "an", "the", "to", "of", "in", "on", "for", "or", "and", "is", "it", "as", "at", "by",
    "he", "she", "we", "they", "i", "you", "us", "our", "their", "this", "that", "these", "those",
    "be", "are", "was", "were", "but", "if", "so", "do", "did", "does", "not", "no", "yes",
}
_OCR_SUFFIXES = {
    "tion", "tions", "sion", "sions", "ing", "ings", "ed", "er", "ers", "est", "able", "ible",
    "al", "ally", "ly", "ment", "ments", "ness", "ity", "ities", "ive", "ives", "ous", "ogy",
    "ogies", "gies", "egies", "tion", "tions", "e", "y", "t", "s", "d", "r", "n",
}
_OCR_PHRASE_FIXES = {
    "strat egies": "strategies",
    "op tions": "options",
    "satisfac tion": "satisfaction",
    "passag e": "passage",
    "anxiet y": "anxiety",
    "t o ": "to ",
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
    "issueslike": "issues like",
    "problemsandweakened": "problems and weakened",
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
}


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
    cleaned = re.sub(r"\s+", " ", text).strip()

    def _should_merge(left: str, right: str) -> bool:
        left_lower = left.lower()
        right_lower = right.lower()
        if right_lower in _OCR_SUFFIXES and len(left) >= 2:
            return True
        if len(left) <= 2 and left_lower not in _OCR_STOP_WORDS:
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
                    line = f"{line}{next_line}"
                    idx += 1
        merged.append(line)
        idx += 1
    return merged


def _parse_answer_key(answer_text: str) -> Dict[int, str]:
    answers: Dict[int, str] = {}
    for line in _clean_lines(answer_text):
        match = re.match(r"^(\d+)\s+(.+)$", line)
        if match:
            answers[int(match.group(1))] = match.group(2).strip()
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
            idx += 1
            continue
        q_num = int(q_match.group(1))
        if stop_numbers and q_num in stop_numbers:
            break
        question_text = _fix_ocr_spacing(q_match.group(2).strip())
        idx += 1
        options: List[str] = []
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

        cloze_item, cursor = _parse_cloze(lines, answers)
        if cloze_item:
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
        questions, idx = _parse_questions(lines, idx, max_question=20)
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
                "title": title,
                "passage_lines": body_lines,
                "passage": passage,
                "questions": questions,
            })

    return {
        "cloze": cloze,
        "daily_life": daily,
        "academic": academics,
    }


def build_full_length_listening_mock(
    test_id: str,
    client: Optional[GeminiClient] = None,
    tts: Optional[TTSService] = None,
) -> Optional[Dict[str, Any]]:
    section = get_listening_section(test_id)
    if not section:
        return None

    client = client or get_gemini_client()
    tts = tts or TTSService()

    responses: List[Dict[str, Any]] = []
    conversations: List[Dict[str, Any]] = []
    talks: List[Dict[str, Any]] = []

    for module_idx, module_key in enumerate(("module1", "module2"), start=1):
        module_text = section.get(module_key, "")
        answer_text = section.get(f"answer_key_module{module_idx}", "")
        answers = _parse_answer_key(answer_text)
        lines = _merge_wrapped_lines(_clean_lines(module_text))

        # Responses (1-8)
        resp_questions, idx = _parse_questions(lines, 0)
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
                    "prompt": q.get("question"),
                    "options": q.get("options"),
                    "answer": q.get("answer"),
                    "rationales": q.get("rationales") or {},
                })
        # Parse conversations and talks
        idx = 0
        while idx < len(lines):
            line = lines[idx].lower()
            if line.startswith("listen to a conversation"):
                idx += 1
                segment_lines: List[str] = []
                while idx < len(lines) and not _QUESTION_RE.match(lines[idx]):
                    if lines[idx].lower().startswith("listen to"):
                        break
                    segment_lines.append(lines[idx])
                    idx += 1
                segments = []
                for seg in segment_lines:
                    if ":" in seg:
                        speaker, text = seg.split(":", 1)
                        segments.append({"speaker": speaker.strip(), "text": text.strip()})
                questions, idx = _parse_questions(lines, idx)
                for q in questions:
                    letter = answers.get(q.get("number"))
                    if letter:
                        opt_idx = ord(letter.upper()) - ord("A")
                        if 0 <= opt_idx < len(q["options"]):
                            q["answer"] = q["options"][opt_idx]
                            rationale = _generate_rationales(client, q, " ".join(segment_lines), include_evidence=False)
                            q["rationales"] = rationale["rationales"]
                conv = {"id": f"conv_{module_idx}_{len(conversations)}", "segments": segments, "questions": questions}
                audio = tts.generate_multi_speaker_audio(segments, filename_prefix="new_toefl_conversation")
                if audio:
                    conv["audio_url"] = f"/static/{audio.audio_path}"
                conversations.append(conv)
                continue
            if line.startswith("listen to an announcement") or line.startswith("listen to a talk"):
                idx += 1
                talk_lines: List[str] = []
                while idx < len(lines) and not _QUESTION_RE.match(lines[idx]):
                    if lines[idx].lower().startswith("listen to"):
                        break
                    talk_lines.append(lines[idx])
                    idx += 1
                talk_text = " ".join([seg.split(":", 1)[-1].strip() for seg in talk_lines]).strip()
                questions, idx = _parse_questions(lines, idx)
                for q in questions:
                    letter = answers.get(q.get("number"))
                    if letter:
                        opt_idx = ord(letter.upper()) - ord("A")
                        if 0 <= opt_idx < len(q["options"]):
                            q["answer"] = q["options"][opt_idx]
                            rationale = _generate_rationales(client, q, talk_text, include_evidence=False)
                            q["rationales"] = rationale["rationales"]
                talk = {"id": f"talk_{module_idx}_{len(talks)}", "talk": talk_text, "questions": questions}
                audio = tts.generate_audio(talk_text, filename_prefix="new_toefl_talk")
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
        audio = tts.generate_audio(prompt_text, filename_prefix="new_toefl_response")
        if audio:
            item["audio_url"] = f"/static/{audio.audio_path}"

    return {
        "responses": responses,
        "conversation": conversations,
        "talk": talks,
    }


def build_full_length_writing_mock(test_id: str) -> Optional[Dict[str, Any]]:
    section = get_writing_section(test_id)
    if not section:
        return None

    content = section.get("content", "")
    answer_key = section.get("answer_key", "")
    answer_map = _parse_answer_key(answer_key)
    lines = _merge_wrapped_lines(_clean_lines(content))

    sentence_build: List[Dict[str, Any]] = []
    idx = 0
    while idx < len(lines):
        match = _QUESTION_RE.match(lines[idx])
        if match and int(match.group(1)) <= 10:
            prompt = match.group(2).strip()
            idx += 1
            tokens = []
            scan_limit = min(idx + 3, len(lines))
            while idx < scan_limit:
                if "/" in lines[idx]:
                    tokens = [t.strip() for t in lines[idx].split("/") if t.strip()]
                    idx += 1
                    break
                idx += 1
            answer = answer_map.get(int(match.group(1)), "")
            sentence_build.append({"prompt": prompt, "tokens": tokens, "answer": answer})
            continue
        idx += 1

    email_idx = next((i for i, line in enumerate(lines) if line.lower().startswith("write an email")), None)
    discussion_idx = next((i for i, line in enumerate(lines) if line.lower().startswith("write for an academic discussion")), None)
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
            if line.lower().startswith("yes,") or line.lower().startswith("i don"):
                break
            professor_lines.append(line)
        remaining = discussion_block[len(professor_lines):]
        for idx, line in enumerate(remaining):
            if not line:
                continue
            if line.lower().startswith("yes"):
                student_posts.append({"name": "Student A", "stance": "Agree", "message": line})
            elif line.lower().startswith("i don"):
                student_posts.append({"name": "Student B", "stance": "Disagree", "message": line})
            if len(student_posts) >= 2:
                break

        discussion_task = {
            "id": f"discussion_{test_id}",
            "professor_prompt": " ".join(professor_lines).strip(),
            "student_posts": student_posts,
        }

    return {
        "sentence_build": sentence_build,
        "email": email_task,
        "discussion": discussion_task,
    }
