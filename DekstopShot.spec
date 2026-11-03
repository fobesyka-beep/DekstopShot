# Build on Windows x64 using Python 3.10–3.13. Directory distribution keeps Qt DLLs replaceable.
from PyInstaller.utils.hooks import collect_all

capture_data, capture_binaries, capture_hidden = collect_all("windows_capture")
a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=capture_binaries,
    datas=capture_data + [("THIRD_PARTY_NOTICES.md", "."), ("README.md", "."),
                          ("LICENSE", "."), ("VALIDATION.md", "."), ("assets/licenses", "licenses"),
                          ("assets/dekstopshot.png", "assets"), ("docs", "docs")],
    hiddenimports=capture_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
              "PySide6.QtQuick", "PySide6.QtMultimedia", "tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="DekstopShot", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    disable_windowed_traceback=False, icon="assets/dekstopshot.ico", manifest="assets/app.manifest",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="DekstopShot")
