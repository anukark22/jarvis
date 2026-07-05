from __future__ import annotations

import html as html_lib

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QSequentialAnimationGroup,
    Qt,
    QTimer,
)
from PySide6.QtGui import QAction, QColor, QPainter, QPixmap, QTextOption
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QLineEdit as QLE,
)

import config
from api_worker import ChatWorker
from orb_graphic import OrbGraphic
from voice_worker import ListenOnceWorker, SpeakWorker, WakeWordWorker

ORB_SIZE = 92
PANEL_W, PANEL_H = 360, 520
ANIM_MS = 300

GLASS_COLLAPSED = f"""
QFrame#glass {{
    background: rgba(8, 22, 34, 190);
    border: 1px solid rgba(0, 212, 255, 70);
    border-radius: {ORB_SIZE // 2}px;
}}
"""
GLASS_EXPANDED = """
QFrame#glass {
    background: rgba(6, 18, 28, 225);
    border: 1px solid rgba(0, 212, 255, 70);
    border-radius: 24px;
}
"""
GLASS_FULLSCREEN = """
QFrame#glass {
    background: rgba(6, 18, 28, 235);
    border: none;
    border-radius: 0px;
}
"""

ICON_BTN_STYLE = """
QPushButton {
    background: rgba(0, 212, 255, 18);
    border: 1px solid rgba(0, 212, 255, 70);
    border-radius: 15px;
    color: #00d4ff;
    font-size: 13px;
}
QPushButton:hover { background: rgba(0, 212, 255, 40); }
QPushButton[active="true"] {
    background: #8a6bff;
    border-color: #8a6bff;
    color: #040609;
}
QPushButton[muted="true"] {
    background: #ff3355;
    border-color: #ff3355;
    color: #040609;
}
"""


def _make_tray_icon() -> QPixmap:
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#00d4ff"))
    p.drawEllipse(8, 8, 48, 48)
    p.setBrush(QColor("#020a10"))
    p.drawEllipse(20, 20, 24, 24)
    p.end()
    return pix


class JarvisWindow(QWidget):
    def __init__(self):
        super().__init__()
        # Qt.Tool is deliberately NOT used here: combined with FramelessWindowHint +
        # WindowStaysOnTopHint on Windows, it's a known source of the window
        # silently vanishing the moment it gets clicked/activated (Tool windows
        # aren't meant to become "active" the normal way Windows expects on click).
        # Trade-off: this means Jarvis shows a taskbar icon, which is a reasonable
        # price for the window actually staying visible and clickable reliably.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.cfg = config.load_config()
        self.history: list[dict] = []
        self.expanded = False
        self.busy = False
        self._animating = False
        self.is_fullscreen = False
        self._pre_fullscreen_geom: QRect | None = None
        self.always_listening = False
        self.armed_followup = False

        self._geom_anim: QPropertyAnimation | None = None
        self._wake_worker: WakeWordWorker | None = None
        self._listen_worker: ListenOnceWorker | None = None
        self._speak_worker: SpeakWorker | None = None
        self._api_worker: ClaudeWorker | None = None

        self._build_ui()
        self._build_tray()
        self._place_bottom_right()
        self._start_anim_loop()

        self._append("JARVIS", 'Online. Click the orb, or enable wake mode and say "Jarvis".')

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.frame = QFrame(self)
        self.frame.setObjectName("glass")
        self.frame.setStyleSheet(GLASS_COLLAPSED)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.frame)

        root = QVBoxLayout(self.frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- header: orb + meta only (kept small so it never gets squeezed) ----
        header = QHBoxLayout()
        header.setContentsMargins(14, 14, 14, 8)
        header.setSpacing(10)

        self.orb = OrbGraphic(self.frame)
        self.orb.setFixedSize(64, 64)
        self.orb.clicked.connect(self._on_orb_clicked)
        self.orb.drag_started.connect(self._on_drag_start)
        self.orb.drag_moved.connect(self._on_drag_move)
        header.addWidget(self.orb)

        meta = QVBoxLayout()
        meta.setSpacing(2)
        self.name_label = QLabel("JARVIS")
        self.name_label.setStyleSheet(
            "color:#00d4ff; font-weight:bold; font-size:13px; letter-spacing:3px; background:transparent;"
        )
        self.status_label = QLabel("idle")
        self.status_label.setStyleSheet(
            "color:#6fa8bb; font-size:10px; letter-spacing:1px; background:transparent;"
        )
        meta.addWidget(self.name_label)
        meta.addWidget(self.status_label)
        self.meta_widget = QWidget()
        self.meta_widget.setLayout(meta)
        self.meta_widget.setStyleSheet("background:transparent;")
        header.addWidget(self.meta_widget)
        header.addStretch(1)

        header_widget = QWidget()
        header_widget.setLayout(header)
        header_widget.setStyleSheet("background:transparent;")
        root.addWidget(header_widget)

        # ---- toolbar: its own full-width row, so the buttons are ALWAYS
        # visible regardless of how much horizontal space the header text
        # takes up (this used to live crammed into the header and could get
        # squeezed out) ----
        self.wake_btn = QPushButton("\U0001F399")  # microphone glyph
        self.mute_btn = QPushButton("\U0001F50A")  # speaker glyph
        self.fullscreen_btn = QPushButton("\u26F6")  # expand-to-fullscreen glyph
        self.min_btn = QPushButton("\u2212")
        for b in (self.wake_btn, self.mute_btn, self.fullscreen_btn, self.min_btn):
            b.setFixedSize(32, 32)
            b.setStyleSheet(ICON_BTN_STYLE)
            b.setCursor(Qt.PointingHandCursor)
        self.wake_btn.setToolTip("Wake word (always-listen)")
        self.mute_btn.setToolTip("Mute voice output")
        self.fullscreen_btn.setToolTip("Fullscreen")
        self.min_btn.setToolTip("Collapse")
        self.wake_btn.clicked.connect(self.toggle_wake_mode)
        self.mute_btn.clicked.connect(self.toggle_mute)
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        self.min_btn.clicked.connect(self.collapse)

        self.actions_widget = QWidget()
        actions_row = QHBoxLayout(self.actions_widget)
        actions_row.setContentsMargins(14, 0, 14, 10)
        actions_row.setSpacing(8)
        actions_row.addWidget(self.wake_btn)
        actions_row.addWidget(self.mute_btn)
        actions_row.addStretch(1)
        actions_row.addWidget(self.fullscreen_btn)
        actions_row.addWidget(self.min_btn)
        self.actions_widget.setStyleSheet("background:transparent;")
        root.addWidget(self.actions_widget)

        # ---- body: chat log + input (hidden while collapsed) ----
        self.body_widget = QWidget()
        body = QVBoxLayout(self.body_widget)
        body.setContentsMargins(14, 0, 14, 12)
        body.setSpacing(8)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QTextEdit.WidgetWidth)
        self.log.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.log.setStyleSheet(
            "QTextEdit { background: transparent; border: none; color: #d8f6ff; "
            "font-family: Consolas, monospace; font-size: 12px; }"
        )
        body.addWidget(self.log, 1)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("Ask Jarvis anything...")
        self.input_line.setStyleSheet(
            "QLineEdit { background: rgba(0,212,255,15); border: 1px solid rgba(0,212,255,70); "
            "border-radius: 16px; padding: 8px 12px; color: #d8f6ff; font-family: Consolas, monospace; }"
        )
        self.input_line.returnPressed.connect(self.send_text)
        self.send_btn = QPushButton("\u27A4")
        self.send_btn.setFixedSize(32, 32)
        self.send_btn.setStyleSheet(ICON_BTN_STYLE)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self.send_text)
        self.mic_btn = QPushButton("\U0001F399")
        self.mic_btn.setFixedSize(32, 32)
        self.mic_btn.setStyleSheet(ICON_BTN_STYLE)
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.clicked.connect(self.listen_once)
        input_row.addWidget(self.input_line, 1)
        input_row.addWidget(self.mic_btn)
        input_row.addWidget(self.send_btn)
        body.addLayout(input_row)

        hint = QLabel("chat-only for now \u00b7 no real OS/file/app control wired up yet")
        hint.setStyleSheet("color:#6fa8bb; font-size:9px; background:transparent;")
        hint.setWordWrap(True)
        body.addWidget(hint)

        self.body_widget.setStyleSheet("background:transparent;")
        self.body_widget.setVisible(False)
        root.addWidget(self.body_widget, 1)

        self.setGeometry(0, 0, ORB_SIZE, ORB_SIZE)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(_make_tray_icon().scaled(32, 32), self)
        menu = QMenu()
        show_action = QAction("Show Jarvis", self)
        show_action.triggered.connect(self._tray_show)
        settings_action = QAction("AI Provider Settings...", self)
        settings_action.triggered.connect(self.prompt_api_key)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(show_action)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("Jarvis")
        self.tray.activated.connect(lambda reason: self._tray_show())
        self.tray.show()

    def _tray_show(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit(self) -> None:
        if self._wake_worker:
            self._wake_worker.stop()
        from PySide6.QtWidgets import QApplication

        QApplication.instance().quit()

    def closeEvent(self, event) -> None:  # noqa: N802
        # closing the window just hides it to the tray, rather than quitting
        event.ignore()
        self.hide()

    def _place_bottom_right(self) -> None:
        from PySide6.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = screen.right() - ORB_SIZE - 32
        y = screen.bottom() - ORB_SIZE - 32
        self.setGeometry(x, y, ORB_SIZE, ORB_SIZE)

    # ------------------------------------------------------------ animation
    def _start_anim_loop(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(lambda: self.orb.tick(33))
        self._timer.start()

    def _on_orb_clicked(self) -> None:
        # Defensive: force the window visible/on-top before toggling, in case
        # anything (OS quirk, focus event) hid it out from under us.
        self.show()
        self.raise_()
        self.toggle_expand()

    def set_state(self, state: str, label: str | None = None) -> None:
        self.orb.set_state(state)
        self.status_label.setText(label or state)

    # ---------------------------------------------------------------- drag
    def _on_drag_start(self) -> None:
        pass

    def _on_drag_move(self, delta: QPointF) -> None:
        pos = self.pos()
        self.move(int(pos.x() + delta.x()), int(pos.y() + delta.y()))

    # ------------------------------------------------------------ expand UI
    def toggle_expand(self) -> None:
        if self._animating:
            return
        self.collapse() if self.expanded else self.expand()

    def expand(self) -> None:
        if self.expanded or self._animating:
            return
        self.expanded = True
        self._animating = True
        rect = self.geometry()
        target = QRect(rect.right() - PANEL_W, rect.bottom() - PANEL_H, PANEL_W, PANEL_H)
        self.frame.setStyleSheet(GLASS_EXPANDED)

        def _done():
            self._animating = False
            self.body_widget.setVisible(True)
            self.show()
            self.raise_()

        self._animate_geometry(target, on_finished=_done)
        self.meta_widget.setVisible(True)
        self.actions_widget.setVisible(True)

    def collapse(self) -> None:
        if not self.expanded or self._animating:
            return
        if self.is_fullscreen:
            self._exit_fullscreen(restore_geometry=False)
        self.expanded = False
        self._animating = True
        self.body_widget.setVisible(False)
        self.meta_widget.setVisible(False)
        self.actions_widget.setVisible(False)
        rect = self.geometry()
        target = QRect(rect.right() - ORB_SIZE, rect.bottom() - ORB_SIZE, ORB_SIZE, ORB_SIZE)

        def _done():
            self._animating = False
            self.frame.setStyleSheet(GLASS_COLLAPSED)
            self.show()
            self.raise_()

        self._animate_geometry(target, on_finished=_done)

    def toggle_fullscreen(self) -> None:
        if not self.expanded:
            return
        if self.is_fullscreen:
            self._exit_fullscreen(restore_geometry=True)
        else:
            self._pre_fullscreen_geom = self.geometry()
            self.is_fullscreen = True
            self.frame.setStyleSheet(GLASS_FULLSCREEN)
            self.showFullScreen()
            self.raise_()
            self.fullscreen_btn.setProperty("active", "true")
        self.fullscreen_btn.style().unpolish(self.fullscreen_btn)
        self.fullscreen_btn.style().polish(self.fullscreen_btn)

    def _exit_fullscreen(self, restore_geometry: bool) -> None:
        self.is_fullscreen = False
        self.showNormal()
        self.frame.setStyleSheet(GLASS_EXPANDED)
        if restore_geometry and self._pre_fullscreen_geom is not None:
            self.setGeometry(self._pre_fullscreen_geom)
        self.fullscreen_btn.setProperty("active", "false")
        self.fullscreen_btn.style().unpolish(self.fullscreen_btn)
        self.fullscreen_btn.style().polish(self.fullscreen_btn)

    def _animate_geometry(self, target: QRect, on_finished=None) -> None:
        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(ANIM_MS)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(self.geometry())
        anim.setEndValue(target)
        if on_finished:
            anim.finished.connect(on_finished)
        anim.start()
        self._geom_anim = anim  # keep a reference so it isn't garbage-collected

    # -------------------------------------------------------------- chat
    def _append(self, who: str, text: str) -> None:
        color = "#ffcc33" if who == "YOU" else "#39ff9c"
        safe = html_lib.escape(text).replace("\n", "<br>")
        self.log.append(
            f'<div style="margin-bottom:8px;">'
            f'<span style="color:{color}; font-size:9px; letter-spacing:2px;">{who}</span><br>'
            f'<span style="color:#d8f6ff;">{safe}</span></div>'
        )
        if who == "JARVIS" and self.expanded:
            self._pop()

    def _pop(self) -> None:
        """A small outward bounce on the panel so a new reply is noticeable
        even if you're not looking right at the chat log."""
        if self._animating or self.is_fullscreen:
            return
        base = self.geometry()
        bump = QRect(base.x() - 8, base.y() - 8, base.width() + 16, base.height() + 16)

        out_anim = QPropertyAnimation(self, b"geometry", self)
        out_anim.setDuration(110)
        out_anim.setEasingCurve(QEasingCurve.OutQuad)
        out_anim.setStartValue(base)
        out_anim.setEndValue(bump)

        back_anim = QPropertyAnimation(self, b"geometry", self)
        back_anim.setDuration(150)
        back_anim.setEasingCurve(QEasingCurve.OutBack)
        back_anim.setStartValue(bump)
        back_anim.setEndValue(base)

        group = QSequentialAnimationGroup(self)
        group.addAnimation(out_anim)
        group.addAnimation(back_anim)
        group.start()
        self._pop_anim = group  # keep a reference so it isn't garbage-collected

    def send_text(self) -> None:
        text = self.input_line.text().strip()
        if not text or self.busy:
            return
        self.input_line.clear()
        self._dispatch(text)

    def _dispatch(self, text: str) -> None:
        if not self.expanded:
            self.expand()
        self.busy = True
        self._append("YOU", text)
        self.set_state("thinking", "thinking")

        provider = self.cfg.get("provider", "anthropic")
        api_key = config.get_api_key(provider)
        if not api_key:
            self.busy = False
            self.set_state("idle", "idle")
            self._append("JARVIS", f"No {provider.title()} API key set yet. Right-click the tray icon and choose 'AI Provider Settings...'.")
            self.prompt_api_key()
            return

        self.history.append({"role": "user", "content": text})
        model = config.get_model(provider)
        self._api_worker = ChatWorker(provider, api_key, model, self.history, self)
        self._api_worker.result.connect(self._on_reply)
        self._api_worker.error.connect(self._on_reply_error)
        self._api_worker.start()

    def _on_reply(self, text: str) -> None:
        self.history.append({"role": "assistant", "content": text})
        self._append("JARVIS", text)
        self.busy = False
        self.speak(text)

    def _on_reply_error(self, msg: str) -> None:
        self.history.pop()  # drop the user turn that failed to get a reply
        self._append("JARVIS", f"[error] {msg}")
        self.busy = False
        self.set_state("idle", "idle")

    # -------------------------------------------------------------- voice
    def listen_once(self) -> None:
        if self.busy:
            return
        self._listen_worker = ListenOnceWorker(self)
        self._listen_worker.started_listening.connect(lambda: self.set_state("listening", "listening..."))
        self._listen_worker.result.connect(self._on_heard)
        self._listen_worker.error.connect(self._on_hear_error)
        self._listen_worker.start()

    def _on_heard(self, text: str) -> None:
        self.set_state("thinking", "thinking")
        self._dispatch(text)

    def _on_hear_error(self, msg: str) -> None:
        self.set_state("idle", "idle")
        self._append("JARVIS", f"[voice] {msg}")

    def speak(self, text: str) -> None:
        if self.cfg.get("muted"):
            self.set_state("standby" if self.always_listening else "idle")
            return
        self.set_state("speaking", "speaking")
        self._speak_worker = SpeakWorker(text, self)
        self._speak_worker.finished.connect(self._on_speak_done)
        self._speak_worker.error.connect(self._on_speak_error)
        self._speak_worker.start()

    def _on_speak_done(self) -> None:
        self.set_state("standby" if self.always_listening else "idle")

    def _on_speak_error(self, msg: str) -> None:
        self._append("JARVIS", f"[voice output] {msg}")
        self.set_state("standby" if self.always_listening else "idle")

    def toggle_mute(self) -> None:
        muted = not self.cfg.get("muted", False)
        self.cfg["muted"] = muted
        config.save_config(self.cfg)
        self.mute_btn.setProperty("muted", "true" if muted else "false")
        self.mute_btn.setStyleSheet(ICON_BTN_STYLE)  # re-polish
        self.mute_btn.style().unpolish(self.mute_btn)
        self.mute_btn.style().polish(self.mute_btn)

    def toggle_wake_mode(self) -> None:
        if self.always_listening:
            self.always_listening = False
            if self._wake_worker:
                self._wake_worker.stop()
            self.wake_btn.setProperty("active", "false")
            self.set_state("idle", "idle")
        else:
            self.always_listening = True
            self.wake_btn.setProperty("active", "true")
            self.set_state("standby", 'standby \u2014 say "Jarvis"')
            word = self.cfg.get("wake_word", "jarvis")
            self._wake_worker = WakeWordWorker(word, self)
            self._wake_worker.wake_detected.connect(self._on_wake)
            self._wake_worker.error.connect(self._on_wake_error)
            self._wake_worker.start()
        self.wake_btn.style().unpolish(self.wake_btn)
        self.wake_btn.style().polish(self.wake_btn)

    def _on_wake(self, remainder: str) -> None:
        if not self.expanded:
            self.expand()
        if remainder:
            self._dispatch(remainder)
        else:
            self.set_state("listening", "listening...")
            self.listen_once()

    def _on_wake_error(self, msg: str) -> None:
        self.always_listening = False
        self.wake_btn.setProperty("active", "false")
        self.wake_btn.style().unpolish(self.wake_btn)
        self.wake_btn.style().polish(self.wake_btn)
        self.set_state("idle", "idle")
        self._append("JARVIS", f"[wake mode] {msg}")

    # -------------------------------------------------------------- setup
    def prompt_api_key(self) -> None:
        providers = ["anthropic", "gemini"]
        current_provider = self.cfg.get("provider", "anthropic")
        idx = providers.index(current_provider) if current_provider in providers else 0
        provider, ok = QInputDialog.getItem(
            self, "Jarvis \u2014 AI Provider", "Choose provider:",
            ["Anthropic (Claude)", "Google (Gemini)"], idx, editable=False,
        )
        if not ok:
            return
        provider = "gemini" if provider.startswith("Google") else "anthropic"
        self.cfg["provider"] = provider
        config.save_config(self.cfg)

        current_key = config.get_api_key(provider)
        text, ok = QInputDialog.getText(
            self, "Jarvis \u2014 API Key", f"Enter your {provider.title()} API key:", QLE.Password, current_key
        )
        if ok and text.strip():
            config.set_api_key(text.strip(), provider)
            self._append("JARVIS", f"{provider.title()} API key saved. Using {provider.title()} now.")
        self.cfg = config.load_config()
