from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.localization.translator import Translator


class SettingsDialog(QDialog):
    def __init__(
        self,
        translator: Translator,
        parent: QWidget | None = None,
        *,
        show_point_labels: bool = True,
        zone_colors: Mapping[str, str] | None = None,
        zone_color_options: Sequence[tuple[str, str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._zone_colors = dict(zone_colors or {})
        self._zone_color_buttons: dict[str, QPushButton] = {}
        self.setWindowTitle(translator.text("menu.settings"))
        self.setMinimumSize(560, 520)
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

        color_group = QGroupBox(translator.text("settings.zone_colors_group"))
        color_form = QFormLayout(color_group)
        color_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        for key, title in zone_color_options or ():
            button = QPushButton()
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._zone_color_buttons[key] = button
            self._apply_color_to_button(button, self._zone_colors.get(key, "#2563eb"))
            button.clicked.connect(
                lambda _checked=False, color_key=key: self._choose_zone_color(color_key)
            )
            color_form.addRow(title, button)

        color_scroll_content = QWidget()
        color_scroll_layout = QVBoxLayout(color_scroll_content)
        color_scroll_layout.setContentsMargins(0, 0, 0, 0)
        color_scroll_layout.addWidget(chart_group)
        color_scroll_layout.addWidget(color_group)
        color_scroll_layout.addStretch()
        color_scroll = QScrollArea()
        color_scroll.setWidgetResizable(True)
        color_scroll.setWidget(color_scroll_content)

        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        general_layout.addWidget(language_group)
        general_layout.addStretch()

        graph_tab = QWidget()
        graph_layout = QVBoxLayout(graph_tab)
        graph_layout.addWidget(color_scroll)

        tabs = QTabWidget()
        tabs.addTab(general_tab, translator.text("settings.general_tab"))
        tabs.addTab(graph_tab, translator.text("settings.graphs_tab"))

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
        layout.addWidget(tabs, 1)
        layout.addWidget(buttons)

    def _choose_zone_color(self, key: str) -> None:
        current = QColor(self._zone_colors.get(key, "#2563eb"))
        color = QColorDialog.getColor(current, self, self._translator.text("settings.choose_color"))
        if not color.isValid():
            return
        value = color.name()
        self._zone_colors[key] = value
        button = self._zone_color_buttons.get(key)
        if button is not None:
            self._apply_color_to_button(button, value)

    @staticmethod
    def _apply_color_to_button(button: QPushButton, color_value: str) -> None:
        color = QColor(color_value)
        if not color.isValid():
            color = QColor("#2563eb")
            color_value = color.name()
        luminance = (
            0.299 * color.red()
            + 0.587 * color.green()
            + 0.114 * color.blue()
        )
        text_color = "#111827" if luminance > 150 else "#ffffff"
        button.setText(color_value.upper())
        button.setStyleSheet(
            "QPushButton {"
            f"background-color: {color_value};"
            f"color: {text_color};"
            "border: 1px solid #94a3b8;"
            "border-radius: 4px;"
            "padding: 4px 10px;"
            "}"
        )

    @property
    def selected_language(self) -> str:
        return self.language_combo.currentText()

    @property
    def show_point_labels(self) -> bool:
        return self.point_labels_checkbox.isChecked()

    @property
    def zone_colors(self) -> dict[str, str]:
        return dict(self._zone_colors)
