"""Painted glass surfaces, a screen map and accessible Qt controls."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QIcon,
    QKeyEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QRegion,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .core import Hotkey, Monitor, Settings, WindowTarget, choose_monitor
from .i18n import canonical_source, get_language, set_language, system_language, t
from .services import QUICK_LINKS
from .version import DISPLAY_VERSION

INK = "#f6fbff"
MUTED = "#c0d2df"
ACCENT = "#8bd8ff"

STYLE = """
QWidget { color: #f3f7ff; font-family: 'Segoe UI', 'DejaVu Sans'; font-size: 13px; }
QLabel { background: transparent; }
QLabel[role='muted'] { color: #c0d2df; }
QLabel[role='eyebrow'] { color: #bdd9e9; font-size: 10px; font-weight: 600; letter-spacing: 1.5px; }
QLabel[role='title'] { font-size: 25px; font-weight: 600; }
QLabel[role='panelTitle'] { font-size: 14px; font-weight: 600; }
QPushButton { border: 0; background: transparent; padding: 10px 16px; font-weight: 500; }
QPushButton[role='primary'] { font-weight: 600; padding: 15px 20px; }
QPushButton[role='icon'] { padding: 0; }
QPushButton[role='nav'], QPushButton[role='navActive'] { text-align: left; padding: 12px; }
QComboBox { background: rgba(26,60,81,35); border: 1px solid rgba(163,222,255,100);
    border-radius: 17px; padding: 9px 14px; padding-right: 29px; min-height: 18px; }
QComboBox:hover { border-color: rgba(190,236,255,185); background: rgba(112,192,230,25); }
QComboBox:focus { border-color: #b8e9ff; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: none; width: 0; height: 0; border: none; }
QComboBox QAbstractItemView { background: #355365; color: #f3f7ff; padding: 6px;
    selection-background-color: #4e8099; border: 1px solid #8abbce; outline: none; }
QCheckBox { color: #d0e0eb; spacing: 8px; background: transparent; font-size: 11px; }
QCheckBox::indicator { width: 14px; height: 14px; border-radius: 7px;
    border: 1px solid #9ac7db; background: rgba(132,198,228,12); }
QCheckBox::indicator:checked { background: #c6eeff; border: 3px solid #659eb7; }
QCheckBox::indicator:focus { border-color: white; }
QScrollArea { border: 0; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { width: 6px; background: transparent; margin: 4px 0; }
QScrollBar::handle:vertical { background: rgba(180,210,230,65); border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QMenu { color: #edf8ff; background: #314d60; border: 1px solid #81b8d3; padding: 6px; }
QMenu::item { padding: 9px 24px; border-radius: 6px; }
QMenu::item:selected { background: #517d96; }
QMenu::separator { height: 1px; background: #3c4b60; margin: 5px; }
QToolTip { color: #f3f7ff; background: #24364a; border: 1px solid #4b6278; padding: 7px; }
"""


def font(size: int, weight=QFont.Weight.Normal) -> QFont:
    result = QFont("Segoe UI")
    result.setPixelSize(size)
    result.setWeight(weight)
    return result


def icon(name: str, color: str = INK, size: int = 24) -> QIcon:
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 24, size / 24)
    draw_icon(painter, name, QColor(color))
    painter.end()
    return QIcon(pixmap)


def gemini_path() -> QPainterPath:
    """Four inward-curved sides with the gently rounded tips from the reference mark."""
    path = QPainterPath(QPointF(11.15, 1.9))
    path.quadTo(QPointF(12, -.1), QPointF(12.85, 1.9))
    path.cubicTo(14.2, 7.3, 16.7, 9.8, 22.1, 11.15)
    path.quadTo(QPointF(24.1, 12), QPointF(22.1, 12.85))
    path.cubicTo(16.7, 14.2, 14.2, 16.7, 12.85, 22.1)
    path.quadTo(QPointF(12, 24.1), QPointF(11.15, 22.1))
    path.cubicTo(9.8, 16.7, 7.3, 14.2, 1.9, 12.85)
    path.quadTo(QPointF(-.1, 12), QPointF(1.9, 11.15))
    path.cubicTo(7.3, 9.8, 9.8, 7.3, 11.15, 1.9)
    path.closeSubpath()
    return path


def draw_icon(p: QPainter, name: str, color: QColor):
    p.setPen(QPen(color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name in ("capture", "logo"):
        for x, y, sx, sy in ((4, 4, 1, 1), (20, 4, -1, 1), (4, 20, 1, -1), (20, 20, -1, -1)):
            p.drawLine(QPointF(x, y + sy * 5), QPointF(x, y))
            p.drawLine(QPointF(x, y), QPointF(x + sx * 5, y))
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(12, 12), 2.5, 2.5)
    elif name == "monitor":
        p.drawRoundedRect(QRectF(3, 4, 18, 13), 2, 2)
        p.drawLine(12, 17, 12, 21)
        p.drawLine(8, 21, 16, 21)
    elif name == "keyboard":
        p.drawRoundedRect(QRectF(2, 5, 20, 14), 3, 3)
        for y in (9, 12):
            for x in (6, 10, 14, 18):
                p.drawPoint(x, y)
        p.drawLine(8, 16, 16, 16)
    elif name == "external":
        p.drawLine(8, 16, 18, 6)
        p.drawLine(10, 6, 18, 6)
        p.drawLine(18, 6, 18, 14)
    elif name == "close":
        p.drawLine(7, 7, 17, 17)
        p.drawLine(7, 17, 17, 7)
    elif name == "hide":
        p.drawLine(6, 12, 18, 12)
    elif name == "refresh":
        p.drawArc(QRectF(5, 5, 14, 14), 35 * 16, 290 * 16)
        p.drawLine(19, 4, 19, 10)
        p.drawLine(14, 10, 19, 10)
    elif name == "pause":
        p.drawLine(8, 6, 8, 18)
        p.drawLine(16, 6, 16, 18)
    elif name == "play":
        path = QPainterPath(QPointF(8, 5))
        path.lineTo(19, 12)
        path.lineTo(8, 19)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "help":
        p.drawEllipse(QRectF(3, 3, 18, 18))
        p.drawArc(QRectF(9, 7, 6, 6), -90 * 16, 270 * 16)
        p.drawPoint(12, 17)
    elif name == "gemini":
        p.fillPath(gemini_path(), color)
    elif name == "chatgpt":
        for angle in range(0, 360, 60):
            p.save()
            p.translate(12, 12)
            p.rotate(angle)
            p.drawRoundedRect(QRectF(-3.5, -9, 7, 11), 3.3, 3.3)
            p.restore()
    elif name == "google":
        p.setFont(font(23, QFont.Weight.DemiBold))
        p.drawText(QRectF(1, -1, 24, 26), Qt.AlignmentFlag.AlignCenter, "G")


def app_icon() -> QIcon:
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, 128, 128)
    gradient.setColorAt(0, QColor("#8abed5"))
    gradient.setColorAt(.5, QColor("#4b7489"))
    gradient.setColorAt(1, QColor("#304f65"))
    p.setBrush(gradient)
    p.setPen(QPen(QColor("#c3ecff"), 2))
    p.drawRoundedRect(QRectF(3, 3, 122, 122), 31, 31)
    p.translate(23, 23)
    p.scale(3.4, 3.4)
    draw_icon(p, "capture", QColor("#f2fbff"))
    p.end()
    return QIcon(pixmap)


def draw_service_icon(p: QPainter, name: str):
    """Small local vector marks; no network downloads are needed to render icons."""
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    if name == "chatgpt":
        p.setBrush(QColor("#10a37f"))
        p.drawRoundedRect(QRectF(.5, .5, 23, 23), 6, 6)
        p.translate(3, 3)
        p.scale(.75, .75)
        draw_icon(p, "chatgpt", QColor("#ffffff"))
    elif name == "gemini":
        path = gemini_path()
        p.fillPath(path, QColor("#4285f4"))
        p.save()
        p.setClipPath(path, Qt.ClipOperation.IntersectClip)
        # Soft overlapping color fields reproduce the supplied four-color gradient:
        # red at the top, yellow on the left, green below, blue at the right/center.
        for center, radius, color in ((QPointF(9.5, 1), 12, "#ea4335"),
                                      (QPointF(1, 12), 11, "#fbbc05"),
                                      (QPointF(9.5, 23), 11.5, "#34a853")):
            gradient = QRadialGradient(center, radius)
            opaque = QColor(color)
            middle = QColor(color)
            middle.setAlpha(190)
            clear = QColor(color)
            clear.setAlpha(0)
            gradient.setColorAt(0, opaque)
            gradient.setColorAt(.25, opaque)
            gradient.setColorAt(.6, middle)
            gradient.setColorAt(1, clear)
            p.fillRect(QRectF(0, 0, 24, 24), gradient)
        p.restore()
    elif name == "claude":
        p.setPen(QPen(QColor("#e89573"), 2.35, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for index in range(12):
            angle = math.radians(index * 30 + 7)
            length = (9.2, 8.2, 9.6, 8.7)[index % 4]
            start = QPointF(12 + math.cos(angle) * 2.2, 12 + math.sin(angle) * 2.2)
            end = QPointF(12 + math.cos(angle) * length, 12 + math.sin(angle) * length)
            p.drawLine(start, end)
        p.setBrush(QColor("#e89573"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(12, 12), 2.7, 2.7)
    elif name == "google":
        ring = QRectF(3.4, 3.4, 17.2, 17.2)
        for start, sweep, color in ((45, 90, "#ea4335"), (135, 60, "#fbbc05"),
                                    (195, 105, "#34a853"), (300, 61, "#4285f4")):
            p.setPen(QPen(QColor(color), 4.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawArc(ring, start * 16, sweep * 16)
        p.setPen(QPen(QColor("#4285f4"), 4.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawLine(QPointF(12, 12), QPointF(22.7, 12))
    p.restore()


def service_icon(name: str, size=24) -> QIcon:
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 24, size / 24)
    draw_service_icon(painter, name)
    painter.end()
    return QIcon(pixmap)


def translated(widget, source: str, setter="setText", **values):
    specs = getattr(widget, "_translation_specs", {})
    specs[setter] = (canonical_source(source), values)
    widget._translation_specs = specs
    getattr(widget, setter)(t(source, **values))
    return widget


def label(text: str, role: str = "", wrap=False) -> QLabel:
    result = translated(QLabel(), text)
    if role:
        result.setProperty("role", role)
    result.setWordWrap(wrap)
    return result


def button(text: str, name: str = "", role: str = "") -> QPushButton:
    result = translated(GlassButton(), text)
    if name:
        result.setIcon(icon(name, INK if role == "primary" else MUTED, 18))
    if role:
        result.setProperty("role", role)
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    return result


def paint_lens(p: QPainter, rect: QRectF, radius: float, *, emphasized=False, hover=0.0,
               pressed=False, focus=False, cursor: QPointF | None = None):
    """A clear lens with a curved bezel and opposing specular edge reflections.

    Qt paints the material and rim lighting; DWM supplies the live desktop blur.
    This does not sample or displace desktop pixels like a browser SVG filter.
    """
    p.save()
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(5, 18, 31, 38))
    p.drawRoundedRect(rect.translated(0, 2.2), radius, radius)
    surface = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    extra = 6 if emphasized else 0
    surface.setColorAt(0, QColor(234, 250, 255, int(33 + extra + hover * 13)))
    surface.setColorAt(.18, QColor(202, 238, 255, 12 + extra))
    surface.setColorAt(.48, QColor(97, 165, 196, 4 + extra))
    surface.setColorAt(.72, QColor(19, 46, 66, 20 if pressed else 7))
    surface.setColorAt(1, QColor(207, 242, 255, int(26 + hover * 15)))
    p.fillPath(path, surface)
    p.setClipPath(path)
    shine = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + rect.height() * .44))
    shine.setColorAt(0, QColor(255, 255, 255, 22))
    shine.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillPath(path, shine)
    # A thin raised bezel, fading smoothly into the flat centre. Opposing
    # highlights convey the curved edge without filling the lens with white.
    for index in range(7):
        inset_amount = .6 + index * .55
        rim = rect.adjusted(inset_amount, inset_amount, -inset_amount, -inset_amount)
        strength = (1 - index / 7) ** 2
        sheen = QConicalGradient(rect.center(), 55)
        sheen.setColorAt(0, QColor(244, 253, 255, int((100 + hover * 35) * strength)))
        sheen.setColorAt(.20, QColor(154, 222, 255, int(20 * strength)))
        sheen.setColorAt(.43, QColor(10, 32, 50, int(55 * strength)))
        sheen.setColorAt(.57, QColor(216, 246, 255, int(80 * strength)))
        sheen.setColorAt(.78, QColor(114, 198, 242, int(12 * strength)))
        sheen.setColorAt(1, QColor(244, 253, 255, int((100 + hover * 35) * strength)))
        p.setPen(QPen(QBrush(sheen), .8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rim, max(1, radius - inset_amount), max(1, radius - inset_amount))
    if cursor is not None and hover > 0:
        glow = QRadialGradient(cursor, max(70, rect.height() * 1.5))
        glow.setColorAt(0, QColor(211, 245, 255, int(40 * hover)))
        glow.setColorAt(1, QColor(211, 245, 255, 0))
        p.fillPath(path, glow)
    p.setClipping(False)
    edge = QLinearGradient(rect.topLeft(), rect.bottomRight())
    edge.setColorAt(0, QColor(230, 252, 255, int(191 + hover * 40)))
    edge.setColorAt(.25, QColor(129, 211, 255, 170 if emphasized else 128))
    edge.setColorAt(.6, QColor(139, 213, 255, 72 if emphasized else 40))
    edge.setColorAt(1, QColor(190, 237, 255, int(162 + hover * 45)))
    p.setPen(QPen(QBrush(edge), 1.25 if emphasized else 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(rect, radius, radius)
    inset = rect.adjusted(1.8, 1.8, -1.8, -1.8)
    reflection = QLinearGradient(inset.topLeft(), inset.bottomLeft())
    reflection.setColorAt(0, QColor(237, 253, 255, 48))
    reflection.setColorAt(.36, QColor(237, 253, 255, 0))
    reflection.setColorAt(1, QColor(156, 217, 249, 28))
    p.setPen(QPen(QBrush(reflection), .7))
    p.drawRoundedRect(inset, max(1, radius - 1.8), max(1, radius - 1.8))
    if focus:
        p.setPen(QPen(QColor(223, 249, 255, 230), 1.1, Qt.PenStyle.DotLine))
        p.drawRoundedRect(rect.adjusted(4, 4, -4, -4), max(1, radius - 4), max(1, radius - 4))
    p.restore()


class GlassButton(QPushButton):
    """A capsule (or a circle for icon controls), keeping QPushButton keyboard semantics."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._hover = 0.0
        self._keyboard_focus = False
        self._cursor = QPointF(20, 10)
        self.setMouseTracking(True)
        self.setMinimumHeight(42)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._set_hover)

    def _set_hover(self, value):
        self._hover = float(value)
        self.update()

    def _animate(self, target):
        self._animation.stop()
        self._animation.setStartValue(self._hover)
        self._animation.setEndValue(target)
        self._animation.start()

    def enterEvent(self, event):
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(0.0)
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        self._cursor = event.position()
        self.update()
        super().mouseMoveEvent(event)

    def focusInEvent(self, event):
        self._keyboard_focus = event.reason() in (Qt.FocusReason.TabFocusReason,
                                                 Qt.FocusReason.BacktabFocusReason,
                                                 Qt.FocusReason.ShortcutFocusReason)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._keyboard_focus = False
        super().focusOutEvent(event)

    def paint_surface(self, p: QPainter) -> QRectF:
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -4)
        if self.isDown():
            rect.translate(0, 1)
        if not self.isEnabled():
            p.setOpacity(.4)
        role = self.property("role")
        paint_lens(p, rect, min(rect.height(), rect.width()) / 2,
                   emphasized=role in ("primary", "navActive"), hover=self._hover,
                   pressed=self.isDown(), focus=self.hasFocus() and self._keyboard_focus, cursor=self._cursor)
        return rect

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.paint_surface(p)
        role = self.property("role")
        p.setFont(self.font())
        p.setPen(QColor(INK))
        text = self.text().strip()
        icon_size = 18 if rect.height() < 48 else 21
        spacing = 8 if text and not self.icon().isNull() else 0
        icon_width = icon_size if not self.icon().isNull() else 0
        available = max(0, int(rect.width() - 22 - icon_width - spacing))
        text = p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, available)
        text_width = p.fontMetrics().horizontalAdvance(text)
        total = icon_width + spacing + text_width
        left = rect.left() + 13 if role in ("nav", "navActive") else rect.center().x() - total / 2
        if icon_width:
            self.icon().paint(p, int(left), int(rect.center().y() - icon_size / 2), icon_size, icon_size)
        if text:
            p.drawText(QRectF(left + icon_width + spacing, rect.top(), text_width + 2, rect.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)


class GlassKeyLabel(QLabel):
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        diameter = min(82, self.height() - 5)
        rect = (QRectF((self.width() - diameter) / 2, 2, diameter, diameter)
                if len(self.text()) <= 3 else QRectF(self.rect()).adjusted(4, 4, -4, -4))
        paint_lens(p, rect, rect.height() / 2, emphasized=True)
        p.end()
        super().paintEvent(event)


GLASS_RADIUS = 24


def update_glass_mask(widget):
    """Clip the native backdrop too: transparent paint alone leaves DWM corners square."""
    if widget.isWindow():
        path = QPainterPath()
        path.addRoundedRect(QRectF(widget.rect()), GLASS_RADIUS, GLASS_RADIUS)
        widget.setMask(QRegion(path.toFillPolygon().toPolygon()))


def paint_window_glass(widget):
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(widget.rect()).adjusted(.7, .7, -.7, -.7)
    path = QPainterPath()
    path.addRoundedRect(rect, GLASS_RADIUS, GLASS_RADIUS)
    p.setClipPath(path)
    gradient = QLinearGradient(0, 0, widget.width(), widget.height())
    # The compositor supplies the blur; this layer only adds a translucent tint.
    alpha = 38 if widget.backdrop else 248
    gradient.setColorAt(0, QColor(48, 76, 96, alpha))
    gradient.setColorAt(.48, QColor(39, 58, 73, alpha))
    gradient.setColorAt(1, QColor(24, 36, 48, alpha))
    p.fillPath(path, gradient)
    for center, radius, color in (
        (QPointF(widget.width() * .78, 20), 480, QColor(107, 189, 228, 17)),
        (QPointF(widget.width() * .42, widget.height()), 420, QColor(141, 170, 193, 9)),
        (QPointF(-25, 50), 310, QColor(145, 209, 241, 14)),
    ):
        glow = QRadialGradient(center, radius)
        glow.setColorAt(0, color)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillPath(path, glow)
    p.setClipping(False)
    edge = QLinearGradient(rect.topLeft(), rect.bottomRight())
    edge.setColorAt(0, QColor(235, 252, 255, 188))
    edge.setColorAt(.34, QColor(163, 221, 249, 48))
    edge.setColorAt(.68, QColor(178, 222, 245, 22))
    edge.setColorAt(1, QColor(219, 247, 255, 126))
    p.setPen(QPen(QBrush(edge), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(rect, GLASS_RADIUS, GLASS_RADIUS)
    inset = rect.adjusted(1.6, 1.6, -1.6, -1.6)
    p.setPen(QPen(QColor(235, 250, 255, 20), .7))
    p.drawRoundedRect(inset, GLASS_RADIUS - 1.6, GLASS_RADIUS - 1.6)
    p.end()


class GlassDialog(QDialog):
    surface_shown = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.backdrop = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)

    def paintEvent(self, event):
        paint_window_glass(self)

    def showEvent(self, event):
        super().showEvent(event)
        update_glass_mask(self)
        self.surface_shown.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        update_glass_mask(self)


class GlassPanel(QWidget):
    def __init__(self, parent=None, hero=False):
        super().__init__(parent)
        self.hero = hero

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        gradient = QLinearGradient(r.topLeft(), r.bottomRight())
        gradient.setColorAt(0, QColor(232, 249, 255, 19 if self.hero else 15))
        gradient.setColorAt(.42, QColor(160, 210, 237, 5))
        gradient.setColorAt(1, QColor(17, 39, 57, 13))
        p.setBrush(gradient)
        border = QLinearGradient(r.topLeft(), r.bottomRight())
        border.setColorAt(0, QColor(236, 252, 255, 88))
        border.setColorAt(.34, QColor(187, 231, 255, 21))
        border.setColorAt(.65, QColor(220, 242, 255, 10))
        border.setColorAt(1, QColor(218, 252, 255, 49))
        p.setPen(QPen(QBrush(border), 1))
        p.drawRoundedRect(r, 19, 19)

    @staticmethod
    def clip_path(rect: QRectF):
        path = QPainterPath()
        path.addRoundedRect(rect, 19, 19)
        return path


class DisplayMap(QWidget):
    selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.monitors: list[Monitor] = []
        self.selected_id = ""
        self.hitboxes: list[tuple[QRectF, Monitor]] = []
        self.setMinimumHeight(108)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        translated(self, "Расположение мониторов; выбор также доступен в списке ниже", "setAccessibleName")

    def set_monitors(self, monitors, selected_id):
        self.monitors, self.selected_id = monitors, selected_id
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.hitboxes.clear()
        if not self.monitors:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, t("Мониторы не найдены"))
            return
        left = min(m.left for m in self.monitors)
        top = min(m.top for m in self.monitors)
        right = max(m.left + m.width for m in self.monitors)
        bottom = max(m.top + m.height for m in self.monitors)
        scale = min((self.width() - 36) / (right - left), (self.height() - 30) / (bottom - top))
        x0 = (self.width() - (right - left) * scale) / 2
        y0 = (self.height() - (bottom - top) * scale) / 2 - 3
        for index, m in enumerate(self.monitors, 1):
            r = QRectF(x0 + (m.left - left) * scale + 3, y0 + (m.top - top) * scale + 3,
                       max(12, m.width * scale - 6), max(12, m.height * scale - 6))
            selected = m.id == self.selected_id
            gradient = QLinearGradient(r.topLeft(), r.bottomRight())
            gradient.setColorAt(0, QColor(139, 211, 249, 43 if selected else 13))
            gradient.setColorAt(1, QColor(45, 87, 116, 28 if selected else 13))
            p.setBrush(gradient)
            p.setPen(QPen(QColor(ACCENT if selected else "#8faebb"), 1.5 if selected else 1))
            p.drawRoundedRect(r, 7, 7)
            p.setFont(font(24 if r.height() > 50 else 16, QFont.Weight.DemiBold))
            p.setPen(QColor("#f0fbff" if selected else "#bed7e3"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(index))
            p.setPen(QPen(QColor("#afdff4" if selected else "#8aabba"), 2))
            if r.height() > 28:
                p.drawLine(QPointF(r.center().x(), r.bottom() + 2), QPointF(r.center().x(), r.bottom() + 7))
                p.drawLine(QPointF(r.center().x() - 12, r.bottom() + 7), QPointF(r.center().x() + 12, r.bottom() + 7))
            self.hitboxes.append((r, m))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            for rect, monitor in self.hitboxes:
                if rect.contains(event.position()):
                    self.selected.emit(monitor.id)
                    break


class LinkButton(GlassButton):
    def __init__(self, title: str, subtitle: str, name: str):
        super().__init__()
        self.title, self.subtitle, self.name = title, subtitle, name
        self.setObjectName(f"link_{name}")
        self.setMinimumHeight(70)
        self.setMinimumWidth(156)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        translated(self, "Открыть {title} в браузере", "setAccessibleName", title=title)
        translated(self, "Открыть {title} в браузере по умолчанию", "setToolTip", title=title)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.paint_surface(p)
        p.save()
        p.translate(19, 20)
        p.scale(1.25, 1.25)
        draw_service_icon(p, self.name)
        p.restore()
        p.setFont(font(14, QFont.Weight.DemiBold))
        p.setPen(QColor(INK))
        p.drawText(QRectF(62, 13, self.width() - 72, 24), Qt.AlignmentFlag.AlignVCenter, self.title)
        p.setFont(font(10))
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(62, 37, self.width() - 72, 19), Qt.AlignmentFlag.AlignVCenter, t(self.subtitle))


class QuickLinks(QWidget):
    open_link = Signal(str)

    def __init__(self):
        super().__init__()
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(10)
        self._columns = 0
        self.buttons = []
        for title, subtitle, name, url in QUICK_LINKS:
            link = LinkButton(title, subtitle, name)
            link.clicked.connect(lambda checked=False, u=url: self.open_link.emit(u))
            self.buttons.append(link)
        self._arrange(4)

    def _arrange(self, columns):
        if self._columns == columns:
            return
        self._columns = columns
        for link in self.buttons:
            self._grid.removeWidget(link)
        for index, link in enumerate(self.buttons):
            self._grid.addWidget(link, index // columns, index % columns)
        for index in range(4):
            self._grid.setColumnStretch(index, 1 if index < columns else 0)
            self._grid.setColumnMinimumWidth(index, 0)
        rows = (len(self.buttons) + columns - 1) // columns
        self.setFixedHeight(rows * 70 + (rows - 1) * 10)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange(4 if event.size().width() >= 666 else 2)


class DragHeader(QWidget):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()


class GlassComboBox(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(MUTED), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        x, y = self.width() - 17, self.height() / 2
        painter.drawLine(QPointF(x - 3, y - 1), QPointF(x, y + 2))
        painter.drawLine(QPointF(x, y + 2), QPointF(x + 3, y - 1))


class MainWindow(QWidget):
    DEFAULT_SIZE = (940, 620)
    MINIMUM_SIZE = (800, 520)
    READY_CLIPBOARD = "Готово к работе. Снимок — в буфере обмена."
    READY_SAVING = "Готово к работе. Снимок — в буфер и папку «Изображения»."

    surface_shown = Signal()
    capture_requested = Signal()
    monitor_requested = Signal(str)
    window_requested = Signal(object)
    mode_requested = Signal(str)
    refresh_requested = Signal()
    hotkey_requested = Signal()
    pause_requested = Signal()
    settings_requested = Signal(str, bool)
    open_link = Signal(str)
    help_requested = Signal()
    language_requested = Signal(str)

    def __init__(self, settings: Settings):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        set_language(getattr(settings, "language", system_language()))
        self.setWindowTitle("DekstopShot")
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)
        self.setMinimumSize(*self.MINIMUM_SIZE)
        self.resize(*self.DEFAULT_SIZE)
        self.backdrop = False
        self.monitors: list[Monitor] = []
        self._update_url = ""
        self._build(settings)

    def _build(self, settings):
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)
        sidebar = QWidget()
        sidebar.setFixedWidth(158)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(5, 5, 0, 4)
        logo_row = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(38, 38))
        logo_row.addWidget(logo)
        brand = label("DekstopShot")
        brand.setStyleSheet("font-size: 18px; font-weight: 600;")
        logo_row.addWidget(brand)
        logo_row.addStretch()
        side.addLayout(logo_row)
        side.addSpacing(3)
        tagline = label("СНИМОК В БУФЕР ОБМЕНА", "eyebrow")
        tagline.setStyleSheet("font-size: 9px; letter-spacing: 1px; color: #c3deeb;")
        side.addWidget(tagline)
        side.addSpacing(18)
        help_button = button("  Инструкция", "help", "nav")
        help_button.clicked.connect(self.help_requested)
        side.addWidget(help_button)
        side.addStretch()
        status = GlassPanel()
        status_layout = QVBoxLayout(status)
        status_layout.setContentsMargins(12, 14, 12, 12)
        status_layout.setSpacing(8)
        general_heading = label("ОБЩЕЕ", "eyebrow")
        general_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(general_heading)
        self.language_combo = GlassComboBox()
        self.language_combo.setMinimumContentsLength(5)
        self.language_combo.addItem("Русский", "ru")
        self.language_combo.addItem("English", "en")
        self.language_combo.setCurrentIndex(self.language_combo.findData(get_language()))
        translated(self.language_combo, "Язык", "setAccessibleName")
        translated(self.language_combo, "Язык", "setToolTip")
        self.language_combo.activated.connect(
            lambda index: self.language_requested.emit(self.language_combo.itemData(index)))
        status_layout.addWidget(self.language_combo)
        self.pause_button = button("  Пауза", "pause", "nav")
        self.pause_button.clicked.connect(self.pause_requested)
        status_layout.addWidget(self.pause_button)
        hide_button = button("  Скрыть в трей", role="nav")
        hide_button.clicked.connect(self.close)
        status_layout.addWidget(hide_button)
        self.update_button = button("")
        self.update_button.setStyleSheet("font-size: 11px;")
        self.update_button.clicked.connect(lambda: self.open_link.emit(self._update_url) if self._update_url else None)
        self.update_button.hide()
        status_layout.addWidget(self.update_button)
        side.addWidget(status)
        side.addSpacing(8)
        side.addWidget(label(f"WINDOWS  ·  {DISPLAY_VERSION}", "eyebrow"))
        root.addWidget(sidebar)
        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet("background: rgba(213,239,255,20);")
        root.addWidget(divider)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(1, 0, 6, 0)
        main.setSpacing(12)
        header = DragHeader()
        header.setFixedHeight(28)
        translated(header, "Перетащить окно настроек", "setAccessibleName")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addStretch()
        close = button("", "close", "icon")
        close.setFixedSize(28, 28)
        translated(close, "Скрыть в трей; DekstopShot продолжит работать", "setToolTip")
        translated(close, "Скрыть в трей", "setAccessibleName")
        close.clicked.connect(self.close)
        header_layout.addWidget(close)
        main.addWidget(header)

        middle = QHBoxLayout()
        middle.setSpacing(14)
        screen_panel = GlassPanel()
        screen_layout = QVBoxLayout(screen_panel)
        screen_layout.setContentsMargins(19, 17, 19, 17)
        screen_layout.setSpacing(8)
        panel_head = QHBoxLayout()
        panel_head.addWidget(label("Источник снимка", "panelTitle"))
        panel_head.addStretch()
        refresh = button("", "refresh", "icon")
        refresh.setFixedSize(26, 26)
        translated(refresh, "Обновить список мониторов", "setAccessibleName")
        translated(refresh, "Обновить мониторы", "setToolTip")
        refresh.clicked.connect(self.refresh_requested)
        panel_head.addWidget(refresh)
        screen_layout.addLayout(panel_head)
        self.mode_combo = GlassComboBox()
        self.mode_combo.addItem(t("Весь выбранный монитор"), "monitor")
        self.mode_combo.addItem(t("Окно приложения"), "window")
        translated(self.mode_combo, "Режим захвата: монитор или приложение", "setAccessibleName")
        self.mode_combo.setCurrentIndex(1 if settings.capture_mode == "window" else 0)
        self.mode_combo.activated.connect(lambda index: self.mode_requested.emit(self.mode_combo.itemData(index)))
        screen_layout.addWidget(self.mode_combo)
        self.source_stack = QStackedWidget()
        monitor_page = QWidget()
        monitor_page_layout = QVBoxLayout(monitor_page)
        monitor_page_layout.setContentsMargins(0, 0, 0, 0)
        monitor_page_layout.setSpacing(8)
        self.display_map = DisplayMap()
        self.display_map.selected.connect(self.monitor_requested)
        monitor_page_layout.addWidget(self.display_map, 1)
        self.monitor_combo = GlassComboBox()
        translated(self.monitor_combo, "Закреплённый монитор для скриншотов", "setAccessibleName")
        self.monitor_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.monitor_combo.setMinimumContentsLength(12)
        self.monitor_combo.activated.connect(self._monitor_changed)
        monitor_page_layout.addWidget(self.monitor_combo)
        self.monitor_detail = label("Выберите монитор", "muted", True)
        self.monitor_detail.setStyleSheet("font-size: 10px; color: #bed4e0;")
        monitor_page_layout.addWidget(self.monitor_detail)
        self.source_stack.addWidget(monitor_page)
        window_page = QWidget()
        window_page_layout = QVBoxLayout(window_page)
        window_page_layout.setContentsMargins(0, 0, 0, 0)
        window_page_layout.setSpacing(8)
        self.window_title = label("Выберите окно приложения", "panelTitle", True)
        self.window_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.window_title.setMinimumHeight(55)
        self.window_title.setMaximumHeight(80)
        window_page_layout.addWidget(self.window_title, 1)
        self.window_combo = GlassComboBox()
        translated(self.window_combo, "Открытые окна приложений", "setAccessibleName")
        self.window_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.window_combo.setMinimumContentsLength(12)
        self.window_combo.activated.connect(lambda index: self.window_requested.emit(self.window_combo.itemData(index)))
        window_page_layout.addWidget(self.window_combo)
        window_page_layout.addWidget(label("Только выбранное окно. Перед снимком разверните его.", "muted", True))
        self.source_stack.addWidget(window_page)
        self.source_stack.setCurrentIndex(1 if settings.capture_mode == "window" else 0)
        screen_layout.addWidget(self.source_stack)
        middle.addWidget(screen_panel, 3)

        key_panel = GlassPanel()
        key_layout = QVBoxLayout(key_panel)
        key_layout.setContentsMargins(19, 20, 19, 17)
        key_layout.setSpacing(10)
        key_layout.addWidget(label("Горячая клавиша", "panelTitle"))
        self.hotkey_label = GlassKeyLabel(settings.hotkey.label)
        self.hotkey_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hotkey_label.setMinimumHeight(86)
        self.hotkey_label.setStyleSheet("font-size: 28px; font-weight: 600; color: #f6fcff; background: transparent;")
        key_layout.addWidget(self.hotkey_label)
        change_key = button("Изменить клавишу", "keyboard")
        change_key.clicked.connect(self.hotkey_requested)
        key_layout.addWidget(change_key)
        self.hotkey_passthrough = translated(QCheckBox(), "Не блокировать клавишу")
        translated(self.hotkey_passthrough, "Передавать нажатие активному приложению", "setToolTip")
        self.hotkey_passthrough.setChecked(getattr(settings, "hotkey_passthrough", True))
        self.hotkey_passthrough.setStyleSheet("font-size: 10px; spacing: 6px;")
        self.hotkey_passthrough.toggled.connect(
            lambda value: self.settings_requested.emit("hotkey_passthrough", value))
        key_layout.addWidget(self.hotkey_passthrough)
        self.capture_status = label(self.READY_SAVING if getattr(settings, "save_screenshots", False)
                                    else self.READY_CLIPBOARD, "muted", True)
        self.capture_status.setMinimumHeight(42)
        self.capture_status.setStyleSheet("font-size: 10px; color: #c3dbe7; padding: 2px 0;")
        self.message = self.capture_status
        key_layout.addWidget(self.capture_status)
        middle.addWidget(key_panel, 2)
        main.addLayout(middle)

        link_title = QHBoxLayout()
        link_title.addWidget(label("Продолжи с AI", "panelTitle"))
        link_title.addStretch()
        main.addLayout(link_title)
        self.quick_links = QuickLinks()
        self.quick_links.open_link.connect(self.open_link)
        main.addWidget(self.quick_links)
        options = QHBoxLayout()
        self.start_hidden = translated(QCheckBox(), "При запуске — сразу в трей")
        self.start_hidden.setChecked(settings.start_hidden)
        self.start_hidden.toggled.connect(lambda value: self.settings_requested.emit("start_hidden", value))
        options.addWidget(self.start_hidden)
        self.save_screenshots = translated(QCheckBox(), "Сохранять в «Изображения»")
        translated(self.save_screenshots,
                   "Сохранять PNG в подпапке DekstopShot системной папки «Изображения».", "setToolTip")
        self.save_screenshots.setChecked(getattr(settings, "save_screenshots", False))
        self.save_screenshots.toggled.connect(
            lambda value: self.settings_requested.emit("save_screenshots", value))
        options.addWidget(self.save_screenshots)
        options.addStretch()
        main.addLayout(options)
        main.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def retranslate(self, settings: Settings):
        """Update the existing window without changing its HWND or signal connections."""
        set_language(settings.language)
        for widget in [self, *self.findChildren(QWidget)]:
            for setter, (source, values) in getattr(widget, "_translation_specs", {}).items():
                getattr(widget, setter)(t(source, **values))
            QWidget.update(widget)
        self.mode_combo.setItemText(0, t("Весь выбранный монитор"))
        self.mode_combo.setItemText(1, t("Окно приложения"))
        self.language_combo.setCurrentIndex(self.language_combo.findData(settings.language))
        self.sync_settings(settings)
        self.update_mode(settings.capture_mode)
        self.update_hotkey(settings.hotkey)

    def sync_settings(self, settings: Settings):
        for widget, value in ((self.start_hidden, settings.start_hidden),
                              (self.hotkey_passthrough, settings.hotkey_passthrough),
                              (self.save_screenshots, getattr(settings, "save_screenshots", False))):
            previous = widget.blockSignals(True)
            widget.setChecked(value)
            widget.blockSignals(previous)
        self.set_saving_status(getattr(settings, "save_screenshots", False))

    def set_saving_status(self, enabled: bool):
        source, _ = getattr(self.capture_status, "_translation_specs", {}).get("setText", ("", {}))
        if source in (self.READY_CLIPBOARD, self.READY_SAVING):
            translated(self.capture_status, self.READY_SAVING if enabled else self.READY_CLIPBOARD)

    def update_available(self, version: str, url: str):
        self._update_url = url
        translated(self.update_button, "Обновление {version}", version=version)
        translated(self.update_button, "Открыть страницу релиза {version}", "setToolTip", version=version)
        self.update_button.show()

    def _monitor_changed(self, index):
        identity = self.monitor_combo.itemData(index)
        if identity:
            self.monitor_requested.emit(identity)

    def update_monitors(self, monitors: list[Monitor], selected_id: str):
        self.monitors = monitors
        self.monitor_combo.blockSignals(True)
        self.monitor_combo.clear()
        try:
            selected = choose_monitor(monitors, selected_id)
            current_id = selected.id
            self.monitor_detail.setText(t("Закреплён · {resolution} px", resolution=selected.resolution) +
                                        (t(" · основной экран") if selected.primary else ""))
        except ValueError as error:
            selected, current_id = None, selected_id
            self.monitor_detail.setText(t(str(error)))
            self.monitor_combo.addItem(t("Закреплённый монитор недоступен"), None)
        for index, monitor in enumerate(monitors, 1):
            self.monitor_combo.addItem(f"{index}. {monitor.name}", monitor.id)
            item = self.monitor_combo.count() - 1
            self.monitor_combo.setItemData(item, f"{monitor.device} · {monitor.resolution}", Qt.ItemDataRole.ToolTipRole)
        selected_index = self.monitor_combo.findData(current_id)
        self.monitor_combo.setCurrentIndex(max(0, selected_index))
        self.monitor_combo.blockSignals(False)
        self.display_map.set_monitors(monitors, current_id)

    def update_windows(self, windows: list[WindowTarget], selected: WindowTarget | None):
        self.window_combo.blockSignals(True)
        self.window_combo.clear()
        self.window_combo.addItem(t("Выберите открытое окно…"), None)
        selected_index = 0
        for target in windows:
            self.window_combo.addItem(target.label, target)
            self.window_combo.setItemData(self.window_combo.count() - 1, target.label, Qt.ItemDataRole.ToolTipRole)
            if selected and (target.hwnd, target.pid, target.process_start) == (selected.hwnd, selected.pid, selected.process_start):
                selected_index = self.window_combo.count() - 1
        self.window_combo.setCurrentIndex(selected_index)
        if selected_index:
            target = self.window_combo.currentData()
            self.window_title.setText(target.title[:110])
        else:
            self.window_title.setText(t("Окно закрыто — выберите другое" if selected else "Выберите окно приложения"))
        self.window_combo.blockSignals(False)

    def update_mode(self, mode: str):
        index = 1 if mode == "window" else 0
        self.mode_combo.setCurrentIndex(index)
        self.source_stack.setCurrentIndex(index)

    def update_hotkey(self, hotkey: Hotkey):
        self.hotkey_label.setText(hotkey.label)
        self.hotkey_label.setStyleSheet("font-size: " + ("19px" if len(hotkey.label) > 12 else "28px") +
                                       "; font-weight: 600; color: #f6fcff; background: transparent;")

    def set_state(self, paused=False, busy=False, unavailable=False):
        text = "На паузе" if paused else "Делаю снимок…" if busy else "Выберите источник" if unavailable else "Готов к работе"
        self.setAccessibleDescription(t(text))
        self.hotkey_label.setToolTip(t(text))
        translated(self.pause_button, "  Продолжить" if paused else "  Пауза")
        self.pause_button.setIcon(icon("play" if paused else "pause", MUTED, 18))

    def show_message(self, text: str, error=False):
        translated(self.message, text)
        self.message.setStyleSheet(f"font-size: 11px; color: {'#ffe1c5' if error else '#d0eaf8'}; padding: 2px 0;")

    def paintEvent(self, event):
        paint_window_glass(self)

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def showEvent(self, event):
        super().showEvent(event)
        update_glass_mask(self)
        self.surface_shown.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        update_glass_mask(self)


class KeyRecorder(GlassButton):
    changed = Signal(object)
    begun = Signal()
    cancelled = Signal()

    def __init__(self, hotkey: Hotkey):
        super().__init__(hotkey.label)
        self.candidate = hotkey
        self.recording = False
        self.setMinimumHeight(88)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("font-size: 25px; font-weight: 600; color: #f2fbff;")
        self.clicked.connect(self.begin)

    def begin(self):
        self.recording = True
        self.setText(t("Нажмите сочетание…"))
        self.setFocus()
        self.grabKeyboard()
        self.begun.emit()

    def stop(self):
        if self.recording:
            self.releaseKeyboard()
            self.recording = False

    def event(self, event):
        # Handle Tab as a possible binding before QWidget turns it into focus traversal.
        if getattr(self, "recording", False):
            if event.type() == QEvent.Type.ShortcutOverride:
                event.accept()
                return True
            if event.type() == QEvent.Type.KeyPress:
                self.keyPressEvent(event)
                return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent):
        if not self.recording:
            return super().keyPressEvent(event)
        if event.isAutoRepeat():
            return
        if event.key() == Qt.Key.Key_Escape:
            self.stop()
            self.cancelled.emit()
            return
        if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr):
            return
        if event.modifiers() & Qt.KeyboardModifier.MetaModifier:
            self.setText(t("Выберите без Win"))
            return
        flags = 0
        for qt_flag, flag in ((Qt.KeyboardModifier.ControlModifier, 2),
                              (Qt.KeyboardModifier.AltModifier, 1),
                              (Qt.KeyboardModifier.ShiftModifier, 4)):
            if event.modifiers() & qt_flag:
                flags |= flag
        try:
            candidate = Hotkey(int(event.nativeVirtualKey()), flags)
        except ValueError:
            self.setText(t("Другая клавиша…"))
            return
        self.candidate = candidate
        self.stop()
        self.setText(candidate.label)
        self.changed.emit(candidate)
        event.accept()


class HotkeyDialog(GlassDialog):
    save_requested = Signal(object)

    def __init__(self, parent, hotkey: Hotkey):
        super().__init__(parent)
        self.setWindowTitle(t("Горячая клавиша"))
        self.setFixedWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(15)
        layout.addWidget(label("Твоя горячая клавиша", "title"))
        layout.addWidget(label("Нажмите клавишу или сочетание с Ctrl, Alt и Shift.\nEsc — отмена. Клавиша Win не поддерживается.", "muted", True))
        self.recorder = KeyRecorder(hotkey)
        self.recorder.cancelled.connect(self.reject)
        layout.addWidget(self.recorder)
        self.error = label("Минус над буквами и Num − — разные клавиши.", "muted", True)
        self.error.setMinimumHeight(42)
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        cancel = button("Отмена")
        cancel.clicked.connect(self.reject)
        self.save_button = button("Сохранить", role="primary")
        self.save_button.setEnabled(False)
        self.recorder.begun.connect(lambda: self.save_button.setEnabled(False))
        self.recorder.changed.connect(lambda _: self.save_button.setEnabled(True))
        self.save_button.clicked.connect(lambda: self.save_requested.emit(self.recorder.candidate))
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        QTimer.singleShot(0, self.recorder.begin)

    def show_error(self, text: str):
        self.error.setText(t(text))
        self.error.setStyleSheet("color: #ffd3b6;")

    def done(self, result):
        self.recorder.stop()
        super().done(result)


def save_icon(path: Path):
    app_icon().pixmap(256, 256).save(str(path))
