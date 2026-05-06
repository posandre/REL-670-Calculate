from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QTableWidget, QTableWidgetItem

from app.localization.translator import Translator
from app.models.electrical import ImpedancePoint, Phasor
from app.models.protection import DistanceZoneSettings


class BaseInputTable(QTableWidget):
    def __init__(self, translator: Translator, parent: QTableWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)

    def append_row(self, values: list[object]) -> None:
        row = self.rowCount()
        self.insertRow(row)
        for column, value in enumerate(values):
            self.setItem(row, column, QTableWidgetItem(str(value)))

    def remove_selected_rows(self) -> None:
        for index in sorted({item.row() for item in self.selectedItems()}, reverse=True):
            self.removeRow(index)

    def _text(self, row: int, column: int) -> str:
        item = self.item(row, column)
        return item.text().strip() if item is not None else ""


class ImpedanceTable(BaseInputTable):
    def __init__(self, translator: Translator) -> None:
        super().__init__(translator)
        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(
            [
                translator.text("table.name"),
                translator.text("table.r"),
                translator.text("table.x"),
            ]
        )

    def retranslate(self) -> None:
        self.setHorizontalHeaderLabels(
            [
                self._translator.text("table.name"),
                self._translator.text("table.r"),
                self._translator.text("table.x"),
            ]
        )

    def values(self) -> list[ImpedancePoint]:
        return [
            ImpedancePoint(
                name=self._text(row, 0) or f"Z{row + 1}",
                resistance=float(self._text(row, 1) or 0.0),
                reactance=float(self._text(row, 2) or 0.0),
            )
            for row in range(self.rowCount())
        ]


class ZoneTable(BaseInputTable):
    def __init__(self, translator: Translator) -> None:
        super().__init__(translator)
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(
            [
                translator.text("table.name"),
                translator.text("table.reach"),
                translator.text("table.angle"),
                translator.text("table.resistive"),
            ]
        )

    def retranslate(self) -> None:
        self.setHorizontalHeaderLabels(
            [
                self._translator.text("table.name"),
                self._translator.text("table.reach"),
                self._translator.text("table.angle"),
                self._translator.text("table.resistive"),
            ]
        )

    def values(self) -> list[DistanceZoneSettings]:
        return [
            DistanceZoneSettings(
                name=self._text(row, 0) or f"Z{row + 1}",
                reach_ohm=float(self._text(row, 1) or 0.0),
                angle_deg=float(self._text(row, 2) or 0.0),
                resistive_reach_ohm=float(self._text(row, 3) or 0.0),
            )
            for row in range(self.rowCount())
        ]


class PhasorTable(BaseInputTable):
    def __init__(self, translator: Translator) -> None:
        super().__init__(translator)
        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(
            [
                translator.text("table.name"),
                translator.text("table.magnitude"),
                translator.text("table.angle"),
            ]
        )

    def retranslate(self) -> None:
        self.setHorizontalHeaderLabels(
            [
                self._translator.text("table.name"),
                self._translator.text("table.magnitude"),
                self._translator.text("table.angle"),
            ]
        )

    def values(self) -> list[Phasor]:
        return [
            Phasor(
                name=self._text(row, 0) or f"P{row + 1}",
                magnitude=float(self._text(row, 1) or 0.0),
                angle_deg=float(self._text(row, 2) or 0.0),
            )
            for row in range(self.rowCount())
        ]
