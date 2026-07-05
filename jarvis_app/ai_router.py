from __future__ import annotations

import claude_client
import gemini_client


class ProviderError(Exception):
    pass


def send_message(provider: str, api_key: str, model: str, history: list[dict]) -> str:
    if provider == "gemini":
        try:
            return gemini_client.send_message(api_key, model, history)
        except gemini_client.GeminiAPIError as exc:
            raise ProviderError(str(exc)) from exc
    try:
        return claude_client.send_message(api_key, model, history)
    except claude_client.ClaudeAPIError as exc:
        raise ProviderError(str(exc)) from exc
