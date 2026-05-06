from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
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
        self.language_combo = QComboBox()
        self.language_combo.addItems(translator.available_languages())
        self.language_combo.setCurrentText(translator.language)
        self.point_labels_checkbox = QCheckBox(translator.text("chart.show_point_labels"))
        self.point_labels_checkbox.setChecked(show_point_labels)

        form = QFormLayout()
        form.addRow(translator.text("label.language"), self.language_combo)
        form.addRow("", self.point_labels_checkbox)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @property
    def selected_language(self) -> str:
        return self.language_combo.currentText()

    @property
    def show_point_labels(self) -> bool:
        return self.point_labels_checkbox.isChecked()
