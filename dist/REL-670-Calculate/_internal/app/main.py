from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen


def _resource_path(relative_path: str) -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / relative_path
    return Path(__file__).resolve().parents[2] / relative_path


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "REL.Engineering.REL670Calculate"
        )
    except (AttributeError, OSError):
        return


def _build_splash_pixmap(icon_path: Path) -> QPixmap:
    pixmap = QPixmap(640, 360)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    gradient = QLinearGradient(0, 0, 640, 360)
    gradient.setColorAt(0.0, QColor("#0f172a"))
    gradient.setColorAt(1.0, QColor("#155e75"))
    painter.fillRect(pixmap.rect(), gradient)

    painter.setPen(QColor("#e2e8f0"))
    title_font = QFont("Segoe UI", 24, QFont.Weight.Bold)
    painter.setFont(title_font)
    painter.drawText(185, 150, "REL-670-Calculate")

    subtitle_font = QFont("Segoe UI", 12, QFont.Weight.Medium)
    painter.setFont(subtitle_font)
    painter.setPen(QColor("#cbd5e1"))
    painter.drawText(185, 185, "Запуск інженерного модуля розрахунків")

    icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
    icon_pixmap = icon.pixmap(128, 128)
    if not icon_pixmap.isNull():
        painter.drawPixmap(40, 110, icon_pixmap)

    painter.end()
    return pixmap


def main() -> int:
    _set_windows_app_id()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("REL-670-Calculate")
    app.setOrganizationName("REL Engineering")
    icon_path = _resource_path("resources/app_icon.ico")
    if icon_path.exists():
        icon = QIcon(str(icon_path))
        app.setWindowIcon(icon)

    splash = QSplashScreen(_build_splash_pixmap(icon_path))
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    splash.show()
    splash.showMessage(
        "Ініціалізація компонентів...",
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
        QColor("#e2e8f0"),
    )
    app.processEvents()

    from app.ui.styles.style_manager import StyleManager
    from app.ui.windows.main_window import MainWindow

    StyleManager.apply(app)
    window = MainWindow()
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.resize(1280, 820)
    window.show()
    splash.finish(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
