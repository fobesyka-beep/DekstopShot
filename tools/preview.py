"""Render the actual widgets with clearly marked demo sources. Does not capture the desktop."""

import argparse
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path)
parser.add_argument("--mode", choices=("monitor", "window"), default="monitor")
parser.add_argument("--flat", action="store_true", help="Render the opaque fallback without a demonstration desktop")
parser.add_argument("--language", choices=("ru", "en"), default="ru")
args = parser.parse_args()
if args.output and sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QRegion  # noqa: E402
from PySide6.QtWidgets import QApplication, QGraphicsBlurEffect, QLabel, QWidget  # noqa: E402

from dekstopshot.core import Monitor, Settings, WindowTarget  # noqa: E402
from dekstopshot.ui import MainWindow  # noqa: E402

app = QApplication([])
app.setStyle("Fusion")


class DemoDesktop(QWidget):
    """Procedural desktop stand-in, never a capture of the user's real screen."""

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor("#195d87"))
        gradient.setColorAt(.4, QColor("#79a3b3"))
        gradient.setColorAt(1, QColor("#464956"))
        p.fillRect(self.rect(), gradient)
        p.setPen(Qt.PenStyle.NoPen)
        ribbon = QPainterPath(QPointF(-60, 540))
        ribbon.cubicTo(280, 280, 670, 850, 1320, 350)
        ribbon.lineTo(1320, 650)
        ribbon.cubicTo(700, 1120, 310, 530, -60, 820)
        ribbon.closeSubpath()
        wave = QLinearGradient(0, 300, 1100, 880)
        wave.setColorAt(0, QColor("#468ab4"))
        wave.setColorAt(.48, QColor("#b5b5b4"))
        wave.setColorAt(1, QColor("#5c7688"))
        p.fillPath(ribbon, wave)
        # One inactive example window makes the blur-through surface apparent.
        p.setBrush(QColor(220, 232, 236, 145))
        p.drawRoundedRect(QRectF(720, 125, 400, 500), 16, 16)
        p.setBrush(QColor(110, 141, 156, 120))
        p.drawRoundedRect(QRectF(745, 155, 230, 14), 7, 7)
        for y, width in ((215, 300), (252, 245), (289, 285), (386, 230), (423, 270), (460, 180)):
            p.drawRoundedRect(QRectF(745, y, width, 10), 5, 5)


scene = None
window = MainWindow(Settings(capture_mode=args.mode, language=args.language))
window.resize(*MainWindow.DEFAULT_SIZE)
width, height = window.width(), window.height()
if not args.flat:
    scene = QWidget()
    scene.setWindowTitle("DekstopShot — предпросмотр")
    scene.resize(width + 100, height + 110)
    desktop = DemoDesktop(scene)
    desktop.setGeometry(scene.rect())
    pane = QWidget(scene)
    pane.setGeometry(50, 50, width, height)
    outline = QPainterPath()
    outline.addRoundedRect(QRectF(pane.rect()), 24, 24)
    pane.setMask(QRegion(outline.toFillPolygon().toPolygon()))
    blurred_desktop = DemoDesktop(pane)
    blurred_desktop.resize(scene.size())
    blurred_desktop.move(-50, -50)
    blur = QGraphicsBlurEffect(blurred_desktop)
    blur.setBlurRadius(44)
    blur.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    blurred_desktop.setGraphicsEffect(blur)
    tint = QWidget(pane)
    tint.setGeometry(pane.rect())
    tint.setStyleSheet("background: rgba(32, 56, 73, 88);")
    window.setParent(scene, Qt.WindowType.Widget)
    window.move(50, 50)
    window.backdrop = True
    caption = QLabel("DEKSTOPSHOT  /  LIQUID GLASS", scene)
    caption.setGeometry(56, 14, width - 12, 22)
    caption.setStyleSheet("background: transparent; color: #ecf7ff; font-size: 12px; letter-spacing: 2px;")
    note = QLabel("Demonstration background · application interface with transparent glass controls"
                  if args.language == "en" else
                  "Демонстрационный фон · интерфейс приложения с прозрачными стеклянными кнопками", scene)
    note.setGeometry(56, height + 68, width - 12, 25)
    note.setStyleSheet("background: transparent; color: #d2e5f1; font-size: 12px;")
    scene.show()
window.update_monitors([
    Monitor("demo-dell", "DISPLAY1", "DELL U2723QE", 0, 0, 2560, 1440, True),
    Monitor("demo-lg", "DISPLAY2", "LG UltraGear", -1920, 0, 1920, 1080),
], "demo-dell")
target = WindowTarget(123, 456, 789, "Project — Visual Studio Code" if args.language == "en"
                      else "Проект — Visual Studio Code", "Code.exe")
window.update_windows([target], target if args.mode == "window" else None)
window.update_mode(args.mode)
window.show_message("Preview · demonstration monitors, application windows and background"
                    if args.language == "en" else
                    "Предпросмотр · демонстрационные мониторы, приложения и фон")
window.show()
app.processEvents()
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not (scene or window).grab().save(buffer, "PNG"):
        raise SystemExit("Could not save preview")
    buffer.close()
    args.output.write_bytes(bytes(data))
else:
    raise SystemExit(app.exec())
