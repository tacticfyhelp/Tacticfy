"""Entry point for Tacticfy - FM27 Scout & Dual-Phase Tactical Synergy Optimizer."""

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from src import app_paths
from src.app_logging import setup_logging


def _set_windows_app_id() -> None:
    """Give the process its own taskbar identity so Windows shows Tacticfy.ico, not python.exe's icon."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_paths.APP_ID)
    except (AttributeError, OSError):
        pass


def main() -> int:
    """Launch the standalone PySide6 desktop application."""
    setup_logging()
    _set_windows_app_id()

    from src.ui.main_window import MainWindow  # after logging, so import errors reach app.log

    app = QApplication(sys.argv)
    app.setApplicationName(app_paths.APP_NAME)
    app.setApplicationVersion(app_paths.APP_VERSION)
    icon = app_paths.icon_path()
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    window = MainWindow(app_paths.bundle_root())
    window.show()
    # Auto-load sample squad quietly on startup without blocking popups
    window.on_load_clicked(interactive=False)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
