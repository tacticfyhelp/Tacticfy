# PyInstaller spec for Tacticfy: one-folder, windowed build with the app icon.
# Equivalent CLI: pyinstaller --onedir --windowed --icon=assets/Tacticfy.ico main.py (+ the data below).
# The .exe starts the local Tacticfy server and opens the UI in the default browser.
# Build with build_installer.bat, or:
#   .venv\Scripts\python.exe -m PyInstaller build\tacticfy.spec --noconfirm --distpath dist --workpath build\pyinstaller-work

import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 - SPECPATH is injected by PyInstaller
ICON = os.path.join(ROOT, "assets", "Tacticfy.ico")

datas = [
    (os.path.join(ROOT, "config"), "config"),
    (os.path.join(ROOT, "web"), "web"),  # index.html, app.js, compiled Tailwind CSS, icons
    (ICON, "assets"),
]
# Drop developer-only files from the bundled config (a local calibration overlay must never ship).
datas_filter = {"offsets.user.json"}

hiddenimports = (
    collect_submodules("pymem")
    + ["scipy.optimize", "scipy.optimize._lsap", "psutil", "bs4"]
)

# The UI is a web page served by the stdlib HTTP server: no GUI toolkit is bundled.
excludes = ["PySide6", "shiboken6", "tkinter", "matplotlib", "pytest", "IPython"]

a = Analysis(  # noqa: F821
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
a.datas = [d for d in a.datas if os.path.basename(d[0]) not in datas_filter]

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # --onedir
    name="Tacticfy",
    icon=ICON,
    console=False,  # --windowed
    debug=False,
    strip=False,
    upx=False,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Tacticfy",
)
