"""The animated orb itself -- a small custom-painted QWidget.

No image assets: everything is drawn each frame with QPainter (glow, two
counter-rotating rings, a pulsing core). A QTimer elsewhere feeds it a phase
value; this widget just renders whatever phase/state it's given.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

STATE_COLORS = {
    "idle": "#00d4ff",
    "standby": "#8a6bff",
    "listening": "#ffcc33",
    "thinking": "#ff8a3d",
    "speaking": "#39ff9c",
}

# rough multipliers on the base rotation/pulse speed per state
SPEED = {
    "idle": 0.35,
    "standby": 0.7,
    "listening": 1.8,
    "thinking": 3.2,
    "speaking": 2.0,
}


class OrbGraphic(QWidget):
    """Emits `clicked` on a plain click, and `drag_delta` while being dragged
    so the parent window can move itself -- this widget has no window of its
    own, it's just the visual + input surface."""

    clicked = Signal()
    drag_started = Signal()
    drag_moved = Signal(QPointF)  # global-pixel delta since last move event
    drag_ended = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "idle"
        self.angle = 0.0
        self.phase = 0.0
        self._press_pos: QPointF | None = None
        self._dragging = False
        self.setMouseTracking(True)

    def set_state(self, state: str) -> None:
        self.state = state if state in STATE_COLORS else "idle"

    def tick(self, dt_ms: float) -> None:
        speed = SPEED.get(self.state, 1.0)
        self.angle = (self.angle + dt_ms * 0.06 * speed) % 360.0
        self.phase += dt_ms * 0.0035 * speed
        self.update()

    def paintEvent(self, event):  # noqa: N802 (Qt naming convention)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        radius = min(w, h) / 2.0 - 4
        color = QColor(STATE_COLORS.get(self.state, "#00d4ff"))

        # ambient glow
        glow = QRadialGradient(cx, cy, radius * 1.7)
        glow_c = QColor(color)
        glow_c.setAlpha(120)
        glow.setColorAt(0.0, glow_c)
        edge_c = QColor(color)
        edge_c.setAlpha(0)
        glow.setColorAt(1.0, edge_c)
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), radius * 1.7, radius * 1.7)

        # outer rotating ring
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.angle)
        pen = QPen(color)
        pen.setWidthF(1.4)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(0, 0), radius * 0.92, radius * 0.92)
        painter.restore()

        # inner counter-rotating dashed ring
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self.angle * 1.5)
        pen2 = QPen(color)
        pen2.setWidthF(1.1)
        pen2.setStyle(Qt.DashLine)
        painter.setPen(pen2)
        painter.drawEllipse(QPointF(0, 0), radius * 0.72, radius * 0.72)
        painter.restore()

        # breathing core
        pulse = 0.5 + 0.5 * abs(math.sin(self.phase))
        core_r = radius * 0.52 * (0.92 + 0.14 * pulse)
        core_grad = QRadialGradient(cx, cy, core_r)
        core_grad.setColorAt(0.0, QColor("#0b2e3d"))
        core_grad.setColorAt(1.0, QColor("#020a10"))
        painter.setBrush(core_grad)
        edge_pen = QPen(color)
        edge_pen.setWidthF(1.6)
        painter.setPen(edge_pen)
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

    # ---- input: click to expand/collapse, drag to move the window ----
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._press_pos = event.globalPosition()
        self._dragging = False

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._press_pos is None:
            return
        delta = event.globalPosition() - self._press_pos
        if not self._dragging and (abs(delta.x()) > 4 or abs(delta.y()) > 4):
            self._dragging = True
            self.drag_started.emit()
        if self._dragging:
            self.drag_moved.emit(delta)
            self._press_pos = event.globalPosition()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._dragging:
            self.drag_ended.emit()
        else:
            self.clicked.emit()
        self._press_pos = None
        self._dragging = False
