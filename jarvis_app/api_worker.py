from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ai_router import ProviderError, send_message


class ChatWorker(QThread):
    result = Signal(str)
    error = Signal(str)

    def __init__(self, provider: str, api_key: str, model: str, history: list[dict], parent=None):
        super().__init__(parent)
        self.provider = provider
        self.api_key = api_key
        self.model = model
        # copy so the UI thread mutating `history` later can't race us
        self.history = [dict(m) for m in history]

    def run(self) -> None:
        try:
            reply = send_message(self.provider, self.api_key, self.model, self.history)
            self.result.emit(reply)
        except ProviderError as exc:
            self.error.emit(str(exc))
        except Exception as exc:  # last-resort guard so the thread never dies silently
            self.error.emit(f"Unexpected error: {exc}")
