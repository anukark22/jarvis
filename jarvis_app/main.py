"""Jarvis \u2014 a small always-on-top floating desktop assistant widget.

Run with:  python main.py

First launch will ask for your Anthropic API key (also settable via the
tray icon menu, or the ANTHROPIC_API_KEY environment variable).
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

import config
from jarvis_window import JarvisWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # stay alive in the tray when the window is hidden

    window = JarvisWindow()
    window.show()

    if not config.get_api_key():
        window.prompt_api_key()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
