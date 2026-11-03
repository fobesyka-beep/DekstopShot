import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dekstopshot.ui import app_icon  # noqa: E402

if __name__ == "__main__":
    app = QApplication([])
    assets = Path(__file__).resolve().parents[1] / "assets"
    pixmap = app_icon().pixmap(256, 256)
    for extension in ("ico", "png"):
        path = assets / f"dekstopshot.{extension}"
        if not pixmap.save(str(path), extension.upper()):
            raise SystemExit(f"Could not create application icon: {path}")
        print(path)
