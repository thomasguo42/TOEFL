"""Client wrapper around the Google Gemini Generative Language API."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

import requests
from flask import current_app


class GeminiClient:
    """Lightweight client for structured content generation via Gemini."""

    DEFAULT_MODEL = "gemini-2.5-flash-lite"
    DEFAULT_API_KEY = "AIzaSyAJrbPs_fr5hUqt08qUAporCHztsoZgFzE"
    DEFAULT_TIMEOUT = 40
    MAX_RETRIES = 5
    RETRY_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
    BACKOFF_INITIAL_SECONDS = 1.5
    BACKOFF_MAX_SECONDS = 30

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or self.DEFAULT_API_KEY
        self.model = os.getenv("GEMINI_MODEL", self.DEFAULT_MODEL)
        self.api_root = os.getenv(
            "GEMINI_API_URL",
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
        )
        # Configurable timeout and model fallback behavior
        try:
            self.timeout = int(os.getenv("GEMINI_TIMEOUT_SECONDS", str(self.DEFAULT_TIMEOUT)))
        except ValueError:
            self.timeout = self.DEFAULT_TIMEOUT
        self.fallback_model = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
        self.enable_fallback_on_max_tokens = (
            os.getenv("GEMINI_FALLBACK_ON_MAX_TOKENS", "true").strip().lower() in {"1", "true", "yes", "y"}
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
        """Send a prompt and attempt to parse JSON out of the response.

        Args:
            prompt: The prompt to send to Gemini
            temperature: Temperature for generation (0.0-1.0)
            system_instruction: Optional system instruction
            response_mime: MIME type for response (default: application/json)
            max_output_tokens: Optional max output tokens

        Returns:
            Parsed JSON response, or None on failure
        """
        if not self.is_configured:
            current_app.logger.error("Gemini API not configured - API key missing")
            return None

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": response_mime,
            },
        }
        if max_output_tokens is not None:
            payload["generationConfig"]["maxOutputTokens"] = max_output_tokens
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        def _request(with_model: Optional[str]) -> Dict[str, Any]:
            """Perform a single HTTP request to Gemini using the provided model with retries."""
            api_root = (
                self.api_root
                if not with_model or with_model == self.model
                else f"https://generativelanguage.googleapis.com/v1beta/models/{with_model}:generateContent"
            )

            attempt = 0
            backoff = self.BACKOFF_INITIAL_SECONDS
            max_attempts = 1 if disable_retries else self.MAX_RETRIES

            while attempt < max_attempts:
                try:
                    response = requests.post(
                        f"{api_root}?key={self.api_key}",
                        json=payload,
                        timeout=self.timeout,
                    )
                    response.raise_for_status()
                    try:
                        return response.json()
                    except Exception as exc:
                        current_app.logger.error("Failed to parse Gemini response as JSON: %s", exc)
                        return {}

                except requests.exceptions.HTTPError as exc:
                    status_code = exc.response.status_code if exc.response is not None else None
                    if (
                        status_code in self.RETRY_STATUS_CODES
                        and attempt < max_attempts - 1
                    ):
                        wait = min(backoff, self.BACKOFF_MAX_SECONDS)
                        current_app.logger.warning(
                            "Gemini HTTP %s for model %s. Retrying in %.1fs (attempt %s/%s).",
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
                    current_app.logger.error("Gemini HTTP error: %s - %s", status_code, exc)
                    raise

                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                    if attempt < max_attempts - 1:
                        wait = min(backoff, self.BACKOFF_MAX_SECONDS)
                        current_app.logger.warning(
                            "Gemini request timed out/connection error (%s). Retrying in %.1fs (attempt %s/%s).",
                            exc,
                            wait,
                            attempt + 1,
                            max_attempts,
                        )
                        time.sleep(wait)
                        attempt += 1
                        backoff *= 2
                        continue
                    current_app.logger.error("Gemini request failed after retries due to timeout/connection issue: %s", exc)
                    raise

                except Exception as exc:
                    if attempt < max_attempts - 1:
                        wait = min(backoff, self.BACKOFF_MAX_SECONDS)
                        current_app.logger.warning(
                            "Gemini request unexpected error (%s). Retrying in %.1fs (attempt %s/%s).",
                            exc,
                            wait,
                            attempt + 1,
                            max_attempts,
                        )
                        time.sleep(wait)
                        attempt += 1
                        backoff *= 2
                        continue
                    current_app.logger.error("Gemini request failed with unexpected error: %s", exc)
                    raise

            # If we exit loop without returning or raising, return empty dict as failure.
            return {}

        # Primary request
        data = _request(model_override)

        # Extract best available text and finish reason
        text, finish_reason = self._extract_text_and_finish_reason(data)

        # If MAX_TOKENS occurred with empty text, optionally retry with a fallback model
        if (
            not text
            and finish_reason == "MAX_TOKENS"
            and self.enable_fallback_on_max_tokens
        ):
            # Avoid retrying with the same model
            primary_model = model_override or self.model
            if self.fallback_model and self.fallback_model != primary_model:
                current_app.logger.warning(
                    "Gemini returned MAX_TOKENS with empty content on model=%s; retrying once with fallback model=%s",
                    primary_model,
                    self.fallback_model,
                )
                data = _request(self.fallback_model)
                text, finish_reason = self._extract_text_and_finish_reason(data)

        if not text:
            # If still no text, surface diagnostics
            candidates = data.get("candidates") or []
            current_app.logger.error(
                "Gemini response contained empty text. Finish reason: %s, Candidates count: %s, Full response: %s",
                finish_reason,
                len(candidates),
                str(data)[:500]  # Log first 500 chars of response
            )
            return None

        parsed = self._robust_parse_json(text)
        if parsed is None:
            current_app.logger.error(
                "Gemini JSON parsing failed. Text length: %s, First 500 chars: %s",
                len(text),
                text[:500]
            )
        return parsed

    @staticmethod
    def _parse_json_response(text: str) -> Optional[Any]:
        """Attempt to parse JSON payload even if wrapped in fences."""
        if not text:
            return None

        text = text.strip()
        
        # Handle markdown code fences
        if text.startswith("```"):
            # Split by ``` and get content between first two fences
            parts = text.split("```")
            if len(parts) >= 3:
                # Get the middle part (between first ``` and second ```)
                text = parts[1]
                # Remove language identifier if present (e.g., "json")
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            else:
                # Malformed fence, try to extract anyway
                text = parts[1] if len(parts) > 1 else text
                text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            current_app.logger.debug(f"JSON decode error at position {e.pos}: {e.msg}")
            return None

    @staticmethod
    def _robust_parse_json(text: str) -> Optional[Any]:
        """Parse JSON with additional heuristics for stray prose or truncated wrappers."""
        # First, try the simple parser (handles code fences too)
        parsed = GeminiClient._parse_json_response(text)
        if parsed is not None:
            return parsed

        # Try to extract a JSON object or array substring
        candidate = GeminiClient._extract_json_substring(text)
        if candidate:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                return None
        return None

    @staticmethod
    def _extract_json_substring(text: str) -> Optional[str]:
        """Extract the largest plausible JSON object/array substring from text."""
        if not text:
            return None
        
        # Find first { and last }
        start_obj = text.find("{")
        end_obj = text.rfind("}")
        start_arr = text.find("[")
        end_arr = text.rfind("]")

        candidates = []
        if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
            json_str = text[start_obj : end_obj + 1]
            candidates.append(json_str)
            
            # Try to validate it's parseable
            try:
                json.loads(json_str)
                # If it parses, return it immediately (it's valid)
                return json_str
            except json.JSONDecodeError:
                # Try to find a better ending brace by counting
                brace_count = 0
                for i in range(start_obj, len(text)):
                    if text[i] == '{':
                        brace_count += 1
                    elif text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            # Found matching closing brace
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

        # Return first candidate (object preferred over array)
        return candidates[0]

    @staticmethod
    def _extract_text_and_finish_reason(data: Dict[str, Any]) -> tuple[str, Optional[str]]:
        """Extract the first non-empty text from candidates and return with finish reason.

        Handles cases where parts may include functionCall/functionResponse instead of text.
        """
        candidates = data.get("candidates") or []
        if not candidates:
            # Check for safety filters or other blocking reasons
            prompt_feedback = data.get("promptFeedback", {})
            block_reason = prompt_feedback.get("blockReason")
            safety_ratings = prompt_feedback.get("safetyRatings", [])
            if block_reason:
                current_app.logger.error(
                    "Gemini blocked request. Reason: %s, Safety ratings: %s",
                    block_reason,
                    safety_ratings,
                )
            else:
                current_app.logger.warning("Gemini response missing candidates. Full response: %s", data)
            return "", None

        # Iterate through candidates to find usable text
        fallback_finish: Optional[str] = None
        for cand in candidates:
            finish_reason = cand.get("finishReason")
            if not fallback_finish:
                fallback_finish = finish_reason
            parts = (cand.get("content") or {}).get("parts", [])
            collected = []
            for part in parts:
                # Primary: text content
                txt = part.get("text")
                if isinstance(txt, str) and txt.strip():
                    collected.append(txt)
                    continue
                # Secondary: functionCall with argsJson
                func = part.get("functionCall") if isinstance(part, dict) else None
                if isinstance(func, dict):
                    args_json = func.get("argsJson")
                    if isinstance(args_json, str) and args_json.strip():
                        collected.append(args_json)
                        continue
                # Tertiary: functionResponse with JSON
                func_resp = part.get("functionResponse") if isinstance(part, dict) else None
                if isinstance(func_resp, dict):
                    resp = func_resp.get("response")
                    if isinstance(resp, str) and resp.strip():
                        collected.append(resp)
                        continue
            if collected:
                return "".join(collected), finish_reason

        return "", fallback_finish


def get_gemini_client() -> GeminiClient:
    """Factory helper to allow lazy imports without circular references."""
    return GeminiClient()
