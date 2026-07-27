"""
AI CAM 4.0 Entry Point — sys.path cleanup, QApplication, MainWindow.

Strips the hermes venv from sys.path to avoid PySide6 conflicts.
Uses os._exit(0) for clean shutdown on NVIDIA GPU systems.
"""

from __future__ import annotations

import os
import sys


def _cleanup_sys_path() -> None:
    """
    Remove hermes virtual-environment paths from sys.path.

    Hermes runs inside its own venv which may ship a different PySide6/
    Qt version. Mixing two Qt installations causes crashes, especially
    on NVIDIA GPU systems. We strip them so the project's own deps are used.
    """
    venv_markers = ("hermes", ".venv", "venv", "env", "site-packages")
    cleaned: list[str] = []
    for p in sys.path:
        lower = p.lower().replace("\\", "/")
        # Keep paths that are clearly project-local or system
        if any(marker in lower for marker in venv_markers):
            if "ai cam" not in lower and "ai_cam" not in lower:
                continue
        cleaned.append(p)
    sys.path[:] = cleaned


def main() -> None:
    """Launch AI CAM 4.0."""
    _cleanup_sys_path()

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("AI CAM 4.0")
    app.setOrganizationName("AICAM")

    # Dark palette for consistent look
    from PySide6.QtGui import QPalette, QColor

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(40, 40, 45))
    palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.Base, QColor(30, 30, 35))
    palette.setColor(QPalette.AlternateBase, QColor(45, 45, 50))
    palette.setColor(QPalette.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.Button, QColor(50, 50, 55))
    palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    from app.main_window import MainWindow

    window = MainWindow()
    window.show()

    exit_code = app.exec()

    # os._exit(0) for NVIDIA GPU compatibility — bypasses Python cleanup
    # which can hang on some NVIDIA driver configurations
    os._exit(exit_code)


if __name__ == "__main__":
    main()
