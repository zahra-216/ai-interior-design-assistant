"""
Resilient Gemini client shared by the agents.

Free-tier Gemini often fails with 503 (model overloaded) or 429 (rate limit /
quota). Each model has its own free quota, so instead of failing we:

  1. on 503 / 500 / timeout / 429, move straight on to the next model in
     GEMINI_MODELS (another model usually has capacity right now),
  2. put a model on a cooldown after a 429 (quota) or 404 (not available to
     this key) so later requests skip it instead of wasting time on it,
  3. if every model failed, wait briefly (backoff + jitter) and go round again.

Configure the fallback chain in .env (comma separated, first = preferred):
    GEMINI_MODELS=gemini-3.6-flash,gemini-3.8-flash,gemini-3.5-flash-lite
"""

import json
import os
import random
import re
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

load_dotenv()

DEFAULT_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
]

MODELS = [m.strip() for m in os.getenv("GEMINI_MODELS", "").split(",") if m.strip()] or DEFAULT_MODELS

REQUEST_TIMEOUT_MS = int(os.getenv("GEMINI_TIMEOUT_MS", "30000"))
TOTAL_TIME_BUDGET_S = float(os.getenv("GEMINI_TOTAL_BUDGET_S", "60"))
ROUNDS = 2
RATE_LIMIT_COOLDOWN_S = 60
NOT_FOUND_COOLDOWN_S = 24 * 3600

# Temporary problems: try the next model now, and this one again next round
RETRYABLE_CODES = {429, 500, 502, 503, 504}

_client = None
_cooldown_until = {}  # model name -> unix time it may be used again


class GeminiUnavailableError(Exception):
    """Raised when every model in the fallback chain failed."""


def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not configured in .env")
        _client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
        )
    return _client


def _status_code(exc):
    if isinstance(exc, errors.APIError):
        return exc.code
    return None


def generate(contents, system_instruction=None, response_schema=None, temperature=0.4):
    """
    Call Gemini with retries and model fallback.

    Returns the response text. If response_schema is given, Gemini is put in
    JSON mode and constrained to that schema (a Pydantic model class or a dict).
    """
    config_kwargs = {"temperature": temperature}
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    if response_schema is not None:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = response_schema
    config = types.GenerateContentConfig(**config_kwargs)

    client = get_client()
    started = time.time()
    last_error = None

    for round_number in range(ROUNDS):
        now = time.time()
        available = [m for m in MODELS if _cooldown_until.get(m, 0) <= now]
        # If everything is cooling down, try them all anyway rather than failing instantly
        for model in available or MODELS:
            if time.time() - started > TOTAL_TIME_BUDGET_S:
                raise GeminiUnavailableError(f"Gave up after {TOTAL_TIME_BUDGET_S}s. Last error: {last_error!r}")
            try:
                response = client.models.generate_content(model=model, contents=contents, config=config)
                text = (response.text or "").strip()
                if not text:
                    raise ValueError("Empty response from Gemini")
                return text
            except Exception as exc:  # noqa: BLE001 - we classify below
                last_error = exc
                code = _status_code(exc)
                print(f"[gemini] {model} failed ({code or type(exc).__name__}): {str(exc)[:160]}")

                if code == 429:
                    _cooldown_until[model] = time.time() + RATE_LIMIT_COOLDOWN_S
                elif code == 404:
                    _cooldown_until[model] = time.time() + NOT_FOUND_COOLDOWN_S
                elif code is not None and code not in RETRYABLE_CODES:
                    # 400 / 401 / 403: bad request or bad key - another model will not help
                    raise
                # otherwise (5xx, timeout, network error, empty reply): just try the next model

        if round_number < ROUNDS - 1:
            time.sleep(1.5 + random.uniform(0, 1.5))

    raise GeminiUnavailableError(f"All Gemini models failed. Last error: {last_error!r}")


def generate_json(contents, response_schema, system_instruction=None, temperature=0.4):
    """Like generate(), but returns parsed JSON (dict/list)."""
    text = generate(contents, system_instruction=system_instruction,
                    response_schema=response_schema, temperature=temperature)
    return parse_json(text)


def parse_json(text):
    """Parse JSON, tolerating ```json fences or stray text around the object."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group())
