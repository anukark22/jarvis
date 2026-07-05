"""Minimal Google Gemini API client, mirroring claude_client's interface
so the rest of the app doesn't need to care which provider is active.
"""

from __future__ import annotations

import requests

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

SYSTEM_PROMPT = (
    "You are Jarvis, a calm, dry-witted AI assistant persona running as a small "
    "floating desktop companion. In this build you can hold a natural conversation "
    "by voice or text, but you do NOT have real tools wired up to control apps, "
    "files, or the operating system yet -- that's a deliberate, separate step so "
    "system-level actions can be added safely with proper confirmation prompts. "
    "If asked to do something requiring real system access, say so plainly and "
    "offer to talk through how it would be done instead. Keep replies concise "
    "(usually under 70 words) unless the user clearly wants detail."
)


class GeminiAPIError(Exception):
    pass


def _to_gemini_contents(history: list[dict]) -> list[dict]:
    """Claude-style {"role": "user"/"assistant", "content": str} ->
    Gemini-style {"role": "user"/"model", "parts": [{"text": str}]}"""
    out = []
    for msg in history:
        role = "model" if msg["role"] == "assistant" else "user"
        out.append({"role": role, "parts": [{"text": msg["content"]}]})
    return out


def send_message(api_key: str, model: str, history: list[dict]) -> str:
    if not api_key:
        raise GeminiAPIError(
            "No Gemini API key configured. Set one in Jarvis's settings "
            "or export GEMINI_API_KEY."
        )

    url = f"{API_BASE}/{model}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "contents": _to_gemini_contents(history),
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
    except requests.RequestException as exc:
        raise GeminiAPIError(f"Network error reaching the API: {exc}") from exc

    if resp.status_code != 200:
        detail = ""
        try:
            detail = resp.json().get("error", {}).get("message", "")
        except ValueError:
            detail = resp.text[:200]
        raise GeminiAPIError(f"API returned {resp.status_code}: {detail}")

    data = resp.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "\n".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError):
        text = ""
    return text or "(empty response)"
