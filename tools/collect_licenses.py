"""Collect upstream distribution notices alongside frozen applications."""

import shutil
from importlib.metadata import distribution
from pathlib import Path


def collect(destination: Path):
    for name in ("PySide6", "PySide6-Essentials", "shiboken6", "windows-capture", "numpy", "opencv-python"):
        dist = distribution(name)
        for file in dist.files or []:
            basename = Path(str(file)).name.lower()
            if any(word in basename for word in ("license", "licence", "copying", "notice")):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    relative = Path(str(file))
                    # Keep only the safe portion beneath the installed distribution.
                    relative = Path(*[part for part in relative.parts if part not in ("..", "/", "\\")])
                    target = destination / name / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)


if __name__ == "__main__":
    collect(Path(__file__).resolve().parents[1] / "assets" / "licenses" / "dependencies")
