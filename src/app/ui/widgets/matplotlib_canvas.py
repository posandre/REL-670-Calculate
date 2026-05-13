from __future__ import annotations

import os
from typing import ClassVar

import matplotlib as mpl
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LocalizedNavigationToolbar(NavigationToolbar2QT):
    _TEXT: ClassVar[dict[str, str]] = {
        "Home": "Початковий вигляд",
        "Back": "Назад",
        "Forward": "Вперед",
        "Pan": "Перемістити",
        "Zoom": "Масштаб",
        "Subplots": "Поля графіка",
        "Save": "Зберегти",
        "Reset original view": "Початковий вигляд",
        "Back to previous view": "Назад до попереднього вигляду",
        "Forward to next view": "Вперед до наступного вигляду",
        "Left button pans, Right button zooms\nx/y fixes axis, CTRL fixes aspect": (
            "Ліва кнопка переміщує, права масштабує\n"
            "x/y фіксує вісь, Ctrl фіксує пропорції"
        ),
        "Zoom to rectangle\nx/y fixes axis": "Масштабувати прямокутник\nx/y фіксує вісь",
        "Configure subplots": "Налаштувати поля графіка",
        "Edit axis, curve and image parameters": "Редагувати параметри осей і графіка",
        "Save the figure": "Зберегти графік",
    }

    _SUBPLOT_TEXT: ClassVar[dict[str, str]] = {
        "Borders": "Межі",
        "Spacings": "Відступи",
        "top": "верх",
        "bottom": "низ",
        "left": "ліворуч",
        "right": "праворуч",
        "hspace": "горизонтальний",
        "wspace": "вертикальний",
        "Tight layout": "Стиснути поля",
        "Reset": "Скинути",
        "Export values": "Експорт значень",
        "Close": "Закрити",
    }

    def __init__(self, canvas: FigureCanvasQTAgg, parent: QWidget | None = None) -> None:
        super().__init__(canvas, parent)
        self._localize_actions()

    def _localize_actions(self) -> None:
        for action in self.actions():
            text = action.text()
            tooltip = action.toolTip()
            if text in self._TEXT:
                action.setText(self._TEXT[text])
            if tooltip in self._TEXT:
                action.setToolTip(self._TEXT[tooltip])

    def configure_subplots(self):  # type: ignore[no-untyped-def]
        dialog = super().configure_subplots()
        dialog.setWindowTitle("Налаштування полів графіка")
        for group_box in dialog.findChildren(QGroupBox):
            title = group_box.title()
            if title in self._SUBPLOT_TEXT:
                group_box.setTitle(self._SUBPLOT_TEXT[title])
        for label in dialog.findChildren(QLabel):
            text = label.text()
            if text in self._SUBPLOT_TEXT:
                label.setText(self._SUBPLOT_TEXT[text])
        for button in dialog.findChildren(QPushButton):
            text = button.text()
            if text in self._SUBPLOT_TEXT:
                button.setText(self._SUBPLOT_TEXT[text])
        return dialog

    def save_figure(self, *args):  # type: ignore[no-untyped-def]
        filetypes = self.canvas.get_supported_filetypes_grouped()
        sorted_filetypes = sorted(filetypes.items())
        default_filetype = self.canvas.get_default_filetype()
        startpath = os.path.expanduser(mpl.rcParams["savefig.directory"])
        start = os.path.join(startpath, self.canvas.get_default_filename())
        filters = []
        selected_filter = None
        for name, exts in sorted_filetypes:
            exts_list = " ".join(f"*.{ext}" for ext in exts)
            file_filter = f"{name} ({exts_list})"
            if default_filetype in exts:
                selected_filter = file_filter
            filters.append(file_filter)
        fname, _file_filter = QFileDialog.getSaveFileName(
            self.canvas.parent(),
            "Зберегти графік як",
            start,
            ";;".join(filters),
            selected_filter,
        )
        if fname:
            if startpath != "":
                mpl.rcParams["savefig.directory"] = os.path.dirname(fname)
            try:
                self.canvas.figure.savefig(fname)
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Помилка збереження",
                    str(exc),
                    QMessageBox.StandardButton.Ok,
                    QMessageBox.StandardButton.NoButton,
                )
        return fname


class MatplotlibPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.figure = Figure(figsize=(6.0, 4.0), constrained_layout=True)
        self.axis = self.figure.add_subplot(111)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = LocalizedNavigationToolbar(self.canvas, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    def redraw(self) -> None:
        self.canvas.draw_idle()
