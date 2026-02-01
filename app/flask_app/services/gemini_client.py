"""Client wrapper around LLM providers (DeepSeek REST or Google Gemini SDK)."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

import requests
from flask import current_app


class GeminiClient:
    """Lightweight client for structured content generation via DeepSeek or Gemini.

    Provider selection:
    - Set `LLM_PROVIDER=gemini` to use Google Gemini via `google.generativeai`.
    - Set `LLM_PROVIDER=deepseek` to use DeepSeek Chat Completions REST.
    - If unset, defaults to `gemini` when `GEMINI_API_KEY` is present and `DEEPSEEK_API_KEY` is not.
    """

    DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
    DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"
    DEFAULT_TIMEOUT = 40
    MAX_RETRIES = 5
    RETRY_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
    BACKOFF_INITIAL_SECONDS = 1.5
    BACKOFF_MAX_SECONDS = 30

    def __init__(self, api_key: Optional[str] = None):
        provider = os.getenv("LLM_PROVIDER", "").strip().lower()
        if provider not in {"gemini", "deepseek"}:
            provider = "gemini" if (os.getenv("GEMINI_API_KEY") and not os.getenv("DEEPSEEK_API_KEY")) else "deepseek"
        self.provider = provider

        if self.provider == "gemini":
            self.api_key = api_key or os.getenv("GEMINI_API_KEY")
            self.model = os.getenv("GEMINI_MODEL", self.DEFAULT_GEMINI_MODEL)
            self.fallback_model = os.getenv("GEMINI_FALLBACK_MODEL", "")
            self.api_root = ""
        else:
            self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("GEMINI_API_KEY")
            self.model = os.getenv("DEEPSEEK_MODEL", self.DEFAULT_DEEPSEEK_MODEL)
            self.api_root = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
            self.fallback_model = os.getenv("DEEPSEEK_FALLBACK_MODEL", "")

        try:
            self.timeout = int(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", str(self.DEFAULT_TIMEOUT)))
        except ValueError:
            self.timeout = self.DEFAULT_TIMEOUT
        self.enable_fallback_on_empty = (
            os.getenv("DEEPSEEK_FALLBACK_ON_EMPTY", "true").strip().lower() in {"1", "true", "yes", "y"}
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate_json(
        self,
        prompt: str,
        temperature: float = 0.8,
        system_instruction: Optional[str] = None,
        response_mime: str = "application/json",
        max_output_tokens: Optional[int] = None,
        model_override: Optional[str] = None,
        disable_retries: bool = False,
    ) -> Optional[Any]:
        """Send a prompt and attempt to parse JSON out of the response."""
        if not self.is_configured:
            current_app.logger.error("%s API not configured - API key missing", self.provider)
            return None

        if self.provider == "gemini":
            return self._generate_json_gemini(
                prompt=prompt,
                temperature=temperature,
                system_instruction=system_instruction,
                response_mime=response_mime,
                max_output_tokens=max_output_tokens,
                model_override=model_override,
                disable_retries=disable_retries,
            )

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        def _request(with_model: Optional[str]) -> Dict[str, Any]:
            attempt = 0
            backoff = self.BACKOFF_INITIAL_SECONDS
            max_attempts = 1 if disable_retries else self.MAX_RETRIES

            while attempt < max_attempts:
                payload = {
                    "model": with_model or self.model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if max_output_tokens is not None:
                    payload["max_tokens"] = max_output_tokens

                try:
                    response = requests.post(
                        self.api_root,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=self.timeout,
                    )
                    response.raise_for_status()
                    try:
                        return response.json()
                    except Exception as exc:
                        current_app.logger.error("Failed to parse DeepSeek response as JSON: %s", exc)
                        return {}
                except requests.exceptions.HTTPError as exc:
                    status_code = exc.response.status_code if exc.response is not None else None
                    if status_code in self.RETRY_STATUS_CODES and attempt < max_attempts - 1:
                        wait = min(backoff, self.BACKOFF_MAX_SECONDS)
                        current_app.logger.warning(
                            "DeepSeek HTTP %s for model %s. Retrying in %.1fs (attempt %s/%s).",
                            status_code,
                            with_model or self.model,
                            wait,
                            attempt + 1,
                            max_attempts,
                        )
                        time.sleep(wait)
                        attempt += 1
                        backoff *= 2
                        continue
                    current_app.logger.error("DeepSeek HTTP error: %s - %s", status_code, exc)
                    raise
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                    if attempt < max_attempts - 1:
                        wait = min(backoff, self.BACKOFF_MAX_SECONDS)
                        current_app.logger.warning(
                            "DeepSeek request timed out/connection error (%s). Retrying in %.1fs (attempt %s/%s).",
                            exc,
                            wait,
                            attempt + 1,
                            max_attempts,
                        )
                        time.sleep(wait)
                        attempt += 1
                        backoff *= 2
                        continue
                    current_app.logger.error(
                        "DeepSeek request failed after retries due to timeout/connection issue: %s",
                        exc,
                    )
                    raise
                except Exception as exc:
                    if attempt < max_attempts - 1:
                        wait = min(backoff, self.BACKOFF_MAX_SECONDS)
                        current_app.logger.warning(
                            "DeepSeek request unexpected error (%s). Retrying in %.1fs (attempt %s/%s).",
                            exc,
                            wait,
                            attempt + 1,
                            max_attempts,
                        )
                        time.sleep(wait)
                        attempt += 1
                        backoff *= 2
                        continue
                    current_app.logger.error("DeepSeek request failed with unexpected error: %s", exc)
                    raise

            return {}

        try:
            data = _request(model_override)
        except requests.exceptions.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            primary_model = model_override or self.model
            if status_code in {400, 404} and self.fallback_model and self.fallback_model != primary_model:
                current_app.logger.warning(
                    "DeepSeek model %s returned %s; retrying once with fallback model=%s",
                    primary_model,
                    status_code,
                    self.fallback_model,
                )
                data = _request(self.fallback_model)
            elif status_code in {401, 403, 429}:
                current_app.logger.warning(
                    "DeepSeek quota/permission error (%s) for model=%s; returning None.",
                    status_code,
                    primary_model,
                )
                return None
            else:
                raise

        text, finish_reason = self._extract_text_and_finish_reason(data)
        if not text and self.enable_fallback_on_empty:
            primary_model = model_override or self.model
            if self.fallback_model and self.fallback_model != primary_model:
                current_app.logger.warning(
                    "DeepSeek returned empty content (finish=%s); retrying with fallback model=%s",
                    finish_reason,
                    self.fallback_model,
                )
                data = _request(self.fallback_model)
                text, finish_reason = self._extract_text_and_finish_reason(data)

        if not text:
            current_app.logger.error(
                "DeepSeek response contained empty text. Finish reason: %s, Full response: %s",
                finish_reason,
                str(data)[:500],
            )
            return None

        parsed = self._robust_parse_json(text)
        if parsed is None:
            current_app.logger.error(
                "DeepSeek JSON parsing failed. Text length: %s, First 500 chars: %s",
                len(text),
                text[:500],
            )
        return parsed

    def generate_text(
        self,
        prompt: str,
        temperature: float = 0.7,
        system_instruction: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        model_override: Optional[str] = None,
        disable_retries: bool = False,
    ) -> Optional[str]:
        """Send a prompt and return raw text output."""
        if not self.is_configured:
            current_app.logger.error("%s API not configured - API key missing", self.provider)
            return None

        if self.provider == "gemini":
            return self._generate_text_gemini(
                prompt=prompt,
                temperature=temperature,
                system_instruction=system_instruction,
                max_output_tokens=max_output_tokens,
                model_override=model_override,
                disable_retries=disable_retries,
            )

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        def _request(with_model: Optional[str]) -> Dict[str, Any]:
            attempt = 0
            backoff = self.BACKOFF_INITIAL_SECONDS
            max_attempts = 1 if disable_retries else self.MAX_RETRIES

            while attempt < max_attempts:
                payload = {
                    "model": with_model or self.model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if max_output_tokens is not None:
                    payload["max_tokens"] = max_output_tokens

                try:
                    response = requests.post(
                        self.api_root,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=self.timeout,
                    )
                    response.raise_for_status()
                    try:
                        return response.json()
                    except Exception as exc:
                        current_app.logger.error("Failed to parse DeepSeek response as JSON: %s", exc)
                        return {}
                except requests.exceptions.HTTPError as exc:
                    status_code = exc.response.status_code if exc.response is not None else None
                    if status_code in self.RETRY_STATUS_CODES and attempt < max_attempts - 1:
                        wait = min(backoff, self.BACKOFF_MAX_SECONDS)
                        current_app.logger.warning(
                            "DeepSeek HTTP %s for model %s. Retrying in %.1fs (attempt %s/%s).",
                            status_code,
                            with_model or self.model,
                            wait,
                            attempt + 1,
                            max_attempts,
                        )
                        time.sleep(wait)
                        attempt += 1
                        backoff *= 2
                        continue
                    current_app.logger.error("DeepSeek HTTP error: %s - %s", status_code, exc)
                    raise
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                    if attempt < max_attempts - 1:
                        wait = min(backoff, self.BACKOFF_MAX_SECONDS)
                        current_app.logger.warning(
                            "DeepSeek request timed out/connection error (%s). Retrying in %.1fs (attempt %s/%s).",
                            exc,
                            wait,
                            attempt + 1,
                            max_attempts,
                        )
                        time.sleep(wait)
                        attempt += 1
                        backoff *= 2
                        continue
                    current_app.logger.error(
                        "DeepSeek request failed after retries due to timeout/connection issue: %s",
                        exc,
                    )
                    raise
                except Exception as exc:
                    if attempt < max_attempts - 1:
                        wait = min(backoff, self.BACKOFF_MAX_SECONDS)
                        current_app.logger.warning(
                            "DeepSeek request unexpected error (%s). Retrying in %.1fs (attempt %s/%s).",
                            exc,
                            wait,
                            attempt + 1,
                            max_attempts,
                        )
                        time.sleep(wait)
                        attempt += 1
                        backoff *= 2
                        continue
                    current_app.logger.error("DeepSeek request failed with unexpected error: %s", exc)
                    raise

            return {}

        try:
            data = _request(model_override)
        except requests.exceptions.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            primary_model = model_override or self.model
            if status_code in {400, 404} and self.fallback_model and self.fallback_model != primary_model:
                current_app.logger.warning(
                    "DeepSeek model %s returned %s; retrying once with fallback model=%s",
                    primary_model,
                    status_code,
                    self.fallback_model,
                )
                data = _request(self.fallback_model)
            elif status_code in {401, 403, 429}:
                current_app.logger.warning(
                    "DeepSeek quota/permission error (%s) for model=%s; returning None.",
                    status_code,
                    primary_model,
                )
                return None
            else:
                raise

        text, finish_reason = self._extract_text_and_finish_reason(data)
        if not text and self.enable_fallback_on_empty:
            primary_model = model_override or self.model
            if self.fallback_model and self.fallback_model != primary_model:
                current_app.logger.warning(
                    "DeepSeek returned empty content (finish=%s); retrying with fallback model=%s",
                    finish_reason,
                    self.fallback_model,
                )
                data = _request(self.fallback_model)
                text, finish_reason = self._extract_text_and_finish_reason(data)

        text = (text or "").strip()
        if not text:
            current_app.logger.error(
                "DeepSeek response contained empty text. Finish reason: %s, Full response: %s",
                finish_reason,
                str(data)[:500],
            )
            return None

        return text

    def _generate_json_gemini(
        self,
        *,
        prompt: str,
        temperature: float,
        system_instruction: Optional[str],
        response_mime: str,
        max_output_tokens: Optional[int],
        model_override: Optional[str],
        disable_retries: bool,
    ) -> Optional[Any]:
        """Gemini SDK path using google.generativeai."""
        try:
            import google.generativeai as genai
            from google.generativeai import types
        except Exception as exc:
            current_app.logger.error("Gemini SDK not available: %s", exc)
            return None

        genai.configure(api_key=self.api_key)

        def _call(model_name: str) -> Optional[str]:
            cfg = types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_mime_type=response_mime or "application/json",
            )
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_instruction,
                generation_config=cfg,
            )
            resp = model.generate_content(prompt)
            return getattr(resp, "text", None)

        attempt = 0
        backoff = self.BACKOFF_INITIAL_SECONDS
        max_attempts = 1 if disable_retries else self.MAX_RETRIES
        primary_model = model_override or self.model

        last_text: Optional[str] = None
        while attempt < max_attempts:
            try:
                last_text = _call(primary_model)
                break
            except Exception as exc:
                if attempt < max_attempts - 1:
                    wait = min(backoff, self.BACKOFF_MAX_SECONDS)
                    current_app.logger.warning(
                        "Gemini request failed (%s). Retrying in %.1fs (attempt %s/%s).",
                        str(exc)[:140],
                        wait,
                        attempt + 1,
                        max_attempts,
                    )
                    time.sleep(wait)
                    attempt += 1
                    backoff *= 2
                    continue
                current_app.logger.error("Gemini request failed: %s", exc)
                return None

        text = (last_text or "").strip()
        if not text and self.enable_fallback_on_empty and self.fallback_model and self.fallback_model != primary_model:
            current_app.logger.warning(
                "Gemini returned empty content; retrying with fallback model=%s",
                self.fallback_model,
            )
            try:
                text = (_call(self.fallback_model) or "").strip()
            except Exception as exc:
                current_app.logger.error("Gemini fallback request failed: %s", exc)
                return None

        if not text:
            current_app.logger.error("Gemini response contained empty text.")
            return None

        parsed = self._robust_parse_json(text)
        if parsed is None:
            current_app.logger.error(
                "Gemini JSON parsing failed. Text length: %s, First 500 chars: %s",
                len(text),
                text[:500],
            )
        return parsed

    def _generate_text_gemini(
        self,
        *,
        prompt: str,
        temperature: float,
        system_instruction: Optional[str],
        max_output_tokens: Optional[int],
        model_override: Optional[str],
        disable_retries: bool,
    ) -> Optional[str]:
        """Gemini SDK path using google.generativeai for plain text."""
        try:
            import google.generativeai as genai
            from google.generativeai import types
        except Exception as exc:
            current_app.logger.error("Gemini SDK not available: %s", exc)
            return None

        genai.configure(api_key=self.api_key)

        def _call(model_name: str) -> Optional[str]:
            cfg = types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_instruction,
                generation_config=cfg,
            )
            resp = model.generate_content(prompt)
            return getattr(resp, "text", None)

        attempt = 0
        backoff = self.BACKOFF_INITIAL_SECONDS
        max_attempts = 1 if disable_retries else self.MAX_RETRIES
        primary_model = model_override or self.model

        last_text: Optional[str] = None
        while attempt < max_attempts:
            try:
                last_text = _call(primary_model)
                break
            except Exception as exc:
                if attempt < max_attempts - 1:
                    wait = min(backoff, self.BACKOFF_MAX_SECONDS)
                    current_app.logger.warning(
                        "Gemini request failed (%s). Retrying in %.1fs (attempt %s/%s).",
                        str(exc)[:140],
                        wait,
                        attempt + 1,
                        max_attempts,
                    )
                    time.sleep(wait)
                    attempt += 1
                    backoff *= 2
                    continue
                current_app.logger.error("Gemini request failed: %s", exc)
                return None

        text = (last_text or "").strip()
        if not text and self.enable_fallback_on_empty and self.fallback_model and self.fallback_model != primary_model:
            current_app.logger.warning(
                "Gemini returned empty content; retrying with fallback model=%s",
                self.fallback_model,
            )
            try:
                text = (_call(self.fallback_model) or "").strip()
            except Exception as exc:
                current_app.logger.error("Gemini fallback request failed: %s", exc)
                return None

        if not text:
            current_app.logger.error("Gemini response contained empty text.")
            return None

        return text

    @staticmethod
    def _parse_json_response(text: str) -> Optional[Any]:
        """Attempt to parse JSON payload even if wrapped in fences."""
        if not text:
            return None

        text = text.strip()

        if text.startswith("```"):
            parts = text.split("```")
            if len(parts) >= 3:
                text = parts[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            else:
                text = parts[1] if len(parts) > 1 else text
                text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            current_app.logger.debug("JSON decode error at position %s: %s", e.pos, e.msg)
            return None

    @staticmethod
    def _robust_parse_json(text: str) -> Optional[Any]:
        """Parse JSON with additional heuristics for stray prose or truncated wrappers."""
        parsed = GeminiClient._parse_json_response(text)
        if parsed is not None:
            return parsed

        candidate = GeminiClient._extract_json_substring(text)
        if candidate:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        repaired = GeminiClient._repair_truncated_json(text)
        if repaired:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                return None
        return None

    @staticmethod
    def _extract_json_substring(text: str) -> Optional[str]:
        """Extract the largest plausible JSON object/array substring from text."""
        if not text:
            return None

        start_obj = text.find("{")
        end_obj = text.rfind("}")
        start_arr = text.find("[")
        end_arr = text.rfind("]")

        candidates = []
        if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
            json_str = text[start_obj : end_obj + 1]
            candidates.append(json_str)
            try:
                json.loads(json_str)
                return json_str
            except json.JSONDecodeError:
                brace_count = 0
                for i in range(start_obj, len(text)):
                    if text[i] == "{":
                        brace_count += 1
                    elif text[i] == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            better_json = text[start_obj : i + 1]
                            try:
                                json.loads(better_json)
                                return better_json
                            except json.JSONDecodeError:
                                pass

        if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
            candidates.append(text[start_arr : end_arr + 1])

        if not candidates:
            return None

        return candidates[0]

    @staticmethod
    def _repair_truncated_json(text: str) -> Optional[str]:
        """Attempt to repair truncated JSON by closing open strings/braces."""
        if not text:
            return None
        start_obj = text.find("{")
        start_arr = text.find("[")
        if start_obj == -1 and start_arr == -1:
            return None
        start = min([pos for pos in [start_obj, start_arr] if pos != -1])
        snippet = text[start:].strip()
        if not snippet:
            return None

        stack: list[str] = []
        in_string = False
        escape = False
        last_complete_index = None

        for idx, ch in enumerate(snippet):
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == "\"":
                    in_string = False
            else:
                if ch == "\"":
                    in_string = True
                elif ch in "{[":
                    stack.append(ch)
                elif ch in "]}":
                    if not stack:
                        continue
                    opener = stack[-1]
                    if (opener == "{" and ch == "}") or (opener == "[" and ch == "]"):
                        stack.pop()
                        if not stack:
                            last_complete_index = idx

        if last_complete_index is not None:
            return snippet[: last_complete_index + 1]

        repaired = snippet.rstrip()
        if repaired.endswith(","):
            repaired = repaired[:-1]
        if in_string:
            repaired += "\""
        closing = ""
        for opener in reversed(stack):
            closing += "}" if opener == "{" else "]"
        repaired += closing
        return repaired if repaired else None

    @staticmethod
    def _extract_text_and_finish_reason(data: Dict[str, Any]) -> tuple[str, Optional[str]]:
        choices = data.get("choices") or []
        if not choices:
            current_app.logger.warning("DeepSeek response missing choices. Full response: %s", data)
            return "", None
        first = choices[0] or {}
        finish_reason = first.get("finish_reason")
        message = first.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content, finish_reason
        return "", finish_reason


def get_gemini_client() -> GeminiClient:
    """Factory helper to allow lazy imports without circular references."""
    return GeminiClient()
