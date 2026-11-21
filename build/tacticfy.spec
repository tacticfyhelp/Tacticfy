# PyInstaller spec for Tacticfy: one-folder, windowed build with the app icon.
# Equivalent CLI: pyinstaller --onedir --windowed --icon=assets/Tacticfy.ico main.py (+ the data below).
# Build with build_installer.bat, or:
#   .venv\Scripts\python.exe -m PyInstaller build\tacticfy.spec --noconfirm --distpath dist --workpath build\pyinstaller-work

import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 - SPECPATH is injected by PyInstaller
ICON = os.path.join(ROOT, "assets", "Tacticfy.ico")

datas = [
    (os.path.join(ROOT, "config"), "config"),
    (ICON, "assets"),
]
# Drop developer-only files from the bundled config (a local calibration overlay must never ship).
datas_filter = {"offsets.user.json"}

hiddenimports = (
    collect_submodules("pymem")
    + ["scipy.optimize", "scipy.optimize._lsap", "psutil", "bs4"]
)

# Large Qt modules the app never uses; keeps the installer small.
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DExtras", "PySide6.QtQuick", "PySide6.QtQuick3D",
    "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSensors", "PySide6.QtSerialPort",
    "tkinter", "matplotlib", "pytest", "IPython",
]

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
