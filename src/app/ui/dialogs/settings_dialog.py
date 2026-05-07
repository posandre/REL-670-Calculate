from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
)

from app.localization.translator import Translator


class SettingsDialog(QDialog):
    def __init__(
        self,
        translator: Translator,
        parent: QDialog | None = None,
        *,
        show_point_labels: bool = True,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setWindowTitle(translator.text("menu.settings"))
        self.setMinimumWidth(460)
        self.language_combo = QComboBox()
        self.language_combo.addItems(translator.available_languages())
        self.language_combo.setCurrentText(translator.language)
        self.point_labels_checkbox = QCheckBox(translator.text("chart.show_point_labels"))
        self.point_labels_checkbox.setChecked(show_point_labels)

        intro = QLabel(translator.text("settings.description"))
        intro.setWordWrap(True)
        intro.setObjectName("infoSection")

        language_group = QGroupBox(translator.text("settings.language_group"))
        language_form = QFormLayout(language_group)
        language_form.addRow(translator.text("label.language"), self.language_combo)

        chart_group = QGroupBox(translator.text("settings.chart_group"))
        form = QFormLayout(chart_group)
        form.addRow("", self.point_labels_checkbox)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(translator.text("button.ok"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(translator.text("button.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        for button in buttons.buttons():
            button.setCursor(Qt.CursorShape.PointingHandCursor)  # type: ignore[name-defined]

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(language_group)
        layout.addWidget(chart_group)
        layout.addWidget(buttons)

    @property
    def selected_language(self) -> str:
        return self.language_combo.currentText()

    @property
    def show_point_labels(self) -> bool:
        return self.point_labels_checkbox.isChecked()
