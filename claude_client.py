"""Minimal Anthropic API client used by Jarvis's chat brain.

Kept dependency-light (just `requests`) and synchronous -- callers are
expected to run this inside a worker thread, never on the Qt UI thread.
"""

from __future__ import annotations

import requests

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

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


class ClaudeAPIError(Exception):
    pass


def send_message(api_key: str, model: str, history: list[dict]) -> str:
    """Send the full conversation history and return the assistant's reply text.

    `history` is a list of {"role": "user"|"assistant", "content": str} dicts.
    """
    if not api_key:
        raise ClaudeAPIError(
            "No Anthropic API key configured. Set one in Jarvis's settings "
            "or export ANTHROPIC_API_KEY."
        )

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 800,
        "system": SYSTEM_PROMPT,
        "messages": history,
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=30)
    except requests.RequestException as exc:
        raise ClaudeAPIError(f"Network error reaching the API: {exc}") from exc

    if resp.status_code != 200:
        detail = ""
        try:
            detail = resp.json().get("error", {}).get("message", "")
        except ValueError:
            detail = resp.text[:200]
        raise ClaudeAPIError(f"API returned {resp.status_code}: {detail}")

    data = resp.json()
    parts = [
        block.get("text", "")
        for block in data.get("content", [])
        if block.get("type") == "text"
    ]
    text = "\n".join(p for p in parts if p).strip()
    return text or "(empty response)"
