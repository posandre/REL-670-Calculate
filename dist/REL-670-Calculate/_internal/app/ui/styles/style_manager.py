from __future__ import annotations

from PySide6.QtWidgets import QApplication

from app.core.config import PACKAGE_ROOT


class StyleManager:
    @staticmethod
    def apply(app: QApplication) -> None:
        qss_path = PACKAGE_ROOT / "ui" / "styles" / "app.qss"
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
