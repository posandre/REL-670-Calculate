from __future__ import annotations

from math import cos, radians, sin, sqrt

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.localization.translator import Translator
from app.services.calculations.distance_stage_rules import (
    arg_dir_default,
    arg_neg_res_by_direction,
    compensated_load_angle_deg,
    load_angle_deg,
)


LOCKED_BACKGROUND = QColor("#e5e7eb")
EDITABLE_BACKGROUND = QColor("#ffffff")
SENSITIVE_STAGE_BACKGROUND = QColor("#fff2b8")

SETTINGS_ROW_KEYS = [
    "direction",
    "X1",
    "R1",
    "X0",
    "R0",
    "RPFF",
    "RFPE",
    "TPP",
    "TPE",
    "ArgNegRes",
    "ArgDir",
    "Фл",
    "Флк",
]


class StageHeaderView(QHeaderView):
    add_requested = Signal(int)
    remove_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._active_section = -1
        self.setMouseTracking(True)
        self._add_button = self._header_button("+")
        self._remove_button = self._header_button("-")
        self._add_button.clicked.connect(self._emit_add)
        self._remove_button.clicked.connect(self._emit_remove)
        self.sectionResized.connect(lambda *_: self._position_buttons())
        self.sectionMoved.connect(lambda *_: self._position_buttons())

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().mouseMoveEvent(event)
        section = self.logicalIndexAt(event.position().toPoint())
        self._active_section = section if section > 0 else -1
        self._position_buttons()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().leaveEvent(event)
        self._active_section = -1
        self._position_buttons()

    def _header_button(self, text: str) -> QToolButton:
        button = QToolButton(self)
        button.setText(text)
        button.setObjectName("stageHeaderButton")
        button.setFixedSize(20, 20)
        button.hide()
        return button

    def _position_buttons(self) -> None:
        visible = self._active_section > 0 and not self.isSectionHidden(
            self._active_section
        )
        self._add_button.setVisible(visible)
        self._remove_button.setVisible(visible)
        if not visible:
            return

        x = self.sectionViewportPosition(self._active_section)
        width = self.sectionSize(self._active_section)
        y = max((self.height() - self._add_button.height()) // 2, 0)
        self._remove_button.move(x + width - 44, y)
        self._add_button.move(x + width - 22, y)
        self._remove_button.raise_()
        self._add_button.raise_()

    def _emit_add(self) -> None:
        if self._active_section > 0:
            self.add_requested.emit(self._active_section)

    def _emit_remove(self) -> None:
        if self._active_section > 0:
            self.remove_requested.emit(self._active_section)


class SourceDataWidget(QWidget):
    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._settings_rows: dict[str, int] = {}
        self._settings_row_keys: dict[str, int] = {}
        self._syncing_fault_mode = False
        self._syncing_calculated_rows = False
        self._pending_sensitive_stage_column = 0
        self._build_ui()
        self.retranslate()

    def _build_ui(self) -> None:
        self.protection_type_combo = QComboBox()
        self.sensitive_stage_combo = QComboBox()
        self.ktc_primary = QLineEdit()
        self.ktc_secondary = QLineEdit()
        self.ktn_primary = QLineEdit()
        self.ktn_secondary = QLineEdit()
        self.sensitivity_factor = QLineEdit("1,10")
        self.phs_sensitivity_factor = QLineEdit("1,20")
        self.delta_phi = QLineEdit("4")
        self.rejection_factor = QLineEdit("0,85")
        self.delta_r_fw_rv = QLineEdit()
        self.delta_r_fw_rv.setReadOnly(True)

        self.settings_table = QTableWidget()
        self.settings_table.setRowCount(len(SETTINGS_ROW_KEYS))
        self.settings_table.setColumnCount(6)
        self.settings_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.settings_table.setAlternatingRowColors(False)
        self.settings_header = StageHeaderView(self.settings_table)
        self.settings_table.setHorizontalHeader(self.settings_header)
        self.settings_header.add_requested.connect(self._add_stage_after)
        self.settings_header.remove_requested.connect(self._remove_stage)
        self._disable_table_scroll(self.settings_table)

        self.load_table = QTableWidget()
        self.load_table.setRowCount(2)
        self.load_table.setColumnCount(5)
        self.load_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.load_table.setAlternatingRowColors(False)
        self._disable_table_scroll(self.load_table)

        self.controls_panel = QWidget()
        controls_layout = QVBoxLayout(self.controls_panel)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(self._engineering_settings_group())

        root = QVBoxLayout(self)
        root.addWidget(self._settings_group())
        root.addWidget(self._load_group())
        self.protection_type_combo.currentIndexChanged.connect(
            self._apply_protection_type_rules
        )
        self.sensitive_stage_combo.currentIndexChanged.connect(
            self._highlight_sensitive_stage
        )
        self.ktc_secondary.textChanged.connect(self._update_delta_r_fw_rv)
        self.settings_table.itemChanged.connect(self._on_settings_item_changed)

    def _engineering_settings_group(self) -> QGroupBox:
        self.engineering_settings_group = QGroupBox()
        layout = QGridLayout(self.engineering_settings_group)
        self.protection_type_label = QLabel()
        self.sensitive_stage_label = QLabel()
        self.sensitive_stage_error = QLabel()
        self.sensitive_stage_error.setObjectName("validationMessage")
        self.sensitive_stage_error.setWordWrap(True)
        self.sensitive_stage_error.hide()
        self.sensitivity_factor_label = QLabel()
        self.delta_phi_label = QLabel()
        self.rejection_factor_label = QLabel()
        self.delta_r_fw_rv_label = QLabel()
        self.sensitivity_factor_unit = QLabel()
        self.delta_phi_unit = QLabel()
        self.rejection_factor_unit = QLabel()
        self.delta_r_fw_rv_unit = QLabel()
        self.ktc_primary_unit = QLabel()
        self.ktc_secondary_unit = QLabel()
        self.ktn_primary_unit = QLabel()
        self.ktn_secondary_unit = QLabel()
        self.ktc_primary_label = QLabel()
        self.ktc_secondary_label = QLabel()
        self.ktn_primary_label = QLabel()
        self.ktn_secondary_label = QLabel()
        for editor in (
            self.ktc_primary,
            self.ktc_secondary,
            self.ktn_primary,
            self.ktn_secondary,
            self.sensitivity_factor,
            self.phs_sensitivity_factor,
            self.delta_phi,
            self.rejection_factor,
            self.delta_r_fw_rv,
        ):
            editor.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.protection_type_label, 0, 0)
        layout.addWidget(self.protection_type_combo, 0, 1, 1, 5)
        layout.addWidget(self.sensitive_stage_label, 1, 0)
        layout.addWidget(self.sensitive_stage_combo, 1, 1, 1, 5)
        layout.addWidget(self.sensitive_stage_error, 2, 1, 1, 5)
        layout.addWidget(self.ktc_primary_label, 3, 0)
        layout.addWidget(self.ktc_primary, 3, 1)
        layout.addWidget(self.ktc_primary_unit, 3, 2)
        layout.addWidget(self.ktc_secondary_label, 3, 3)
        layout.addWidget(self.ktc_secondary, 3, 4)
        layout.addWidget(self.ktc_secondary_unit, 3, 5)
        layout.addWidget(self.ktn_primary_label, 4, 0)
        layout.addWidget(self.ktn_primary, 4, 1)
        layout.addWidget(self.ktn_primary_unit, 4, 2)
        layout.addWidget(self.ktn_secondary_label, 4, 3)
        layout.addWidget(self.ktn_secondary, 4, 4)
        layout.addWidget(self.ktn_secondary_unit, 4, 5)
        self.phs_sensitivity_factor_label = QLabel()
        self.phs_sensitivity_factor_unit = QLabel()
        layout.addWidget(self.sensitivity_factor_label, 5, 0)
        layout.addWidget(self.sensitivity_factor, 5, 1, 1, 4)
        layout.addWidget(self.sensitivity_factor_unit, 5, 5)
        layout.addWidget(self.phs_sensitivity_factor_label, 6, 0)
        layout.addWidget(self.phs_sensitivity_factor, 6, 1, 1, 4)
        layout.addWidget(self.phs_sensitivity_factor_unit, 6, 5)
        layout.addWidget(self.delta_phi_label, 7, 0)
        layout.addWidget(self.delta_phi, 7, 1, 1, 4)
        layout.addWidget(self.delta_phi_unit, 7, 5)
        layout.addWidget(self.rejection_factor_label, 8, 0)
        layout.addWidget(self.rejection_factor, 8, 1, 1, 4)
        layout.addWidget(self.rejection_factor_unit, 8, 5)
        layout.addWidget(self.delta_r_fw_rv_label, 9, 0)
        layout.addWidget(self.delta_r_fw_rv, 9, 1, 1, 4)
        layout.addWidget(self.delta_r_fw_rv_unit, 9, 5)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(4, 1)
        return self.engineering_settings_group

    def _settings_group(self) -> QGroupBox:
        self.settings_group = QGroupBox()
        layout = QVBoxLayout(self.settings_group)
        layout.addWidget(self.settings_table)
        return self.settings_group

    def _load_group(self) -> QGroupBox:
        self.load_group = QGroupBox()
        layout = QVBoxLayout(self.load_group)
        layout.addWidget(self.load_table)
        return self.load_group

    def retranslate(self) -> None:
        t = self._translator.text
        protection_index = self.protection_type_combo.currentIndex()
        self.engineering_settings_group.setTitle(t("source.engineering_settings"))
        self.protection_type_label.setText(t("source.protection_type"))
        self.sensitive_stage_label.setText(t("source.sensitive_stage"))
        with QSignalBlocker(self.protection_type_combo):
            self.protection_type_combo.clear()
            self.protection_type_combo.addItems(
                [
                    t("source.protection_all_faults"),
                    t("source.protection_phase_faults"),
                ]
            )
            self.protection_type_combo.setCurrentIndex(max(protection_index, 0))
        self.settings_group.setTitle(t("source.settings"))
        self.load_group.setTitle(t("source.load_modes"))
        self.ktc_primary_label.setText(t("source.ktc_primary"))
        self.ktc_secondary_label.setText(t("source.ktc_secondary"))
        self.ktn_primary_label.setText(t("source.ktn_primary"))
        self.ktn_secondary_label.setText(t("source.ktn_secondary"))
        self.ktc_primary.setPlaceholderText(t("source.placeholder_primary"))
        self.ktc_secondary.setPlaceholderText(t("source.placeholder_secondary"))
        self.ktn_primary.setPlaceholderText(t("source.placeholder_primary"))
        self.ktn_secondary.setPlaceholderText(t("source.placeholder_secondary"))
        self.ktc_primary_unit.setText(t("unit.ampere"))
        self.ktc_secondary_unit.setText(t("unit.ampere"))
        self.ktn_primary_unit.setText(t("unit.volt"))
        self.ktn_secondary_unit.setText(t("unit.volt"))
        self.sensitivity_factor_label.setText(t("source.sensitivity_factor_psd"))
        self.phs_sensitivity_factor_label.setText(t("source.sensitivity_factor_phs"))
        self.delta_phi_label.setText(t("source.delta_phi"))
        self.rejection_factor_label.setText(t("source.rejection_factor"))
        self.delta_r_fw_rv_label.setText(t("source.delta_r_fw_rv"))
        self.sensitivity_factor_unit.setText(t("unit.relative"))
        self.phs_sensitivity_factor_unit.setText(t("unit.relative"))
        self.delta_phi_unit.setText(t("unit.degree"))
        self.rejection_factor_unit.setText(t("unit.relative"))
        self.delta_r_fw_rv_unit.setText(t("unit.ohm"))
        self._configure_settings_table()
        self._configure_load_table()
        self._apply_protection_type_rules()
        self._update_delta_r_fw_rv()
        self._update_sensitive_stage_options()

    def reset(self) -> None:
        self.set_inputs_locked(False)
        self.clear_validation_errors()
        for editor in (
            self.ktc_primary,
            self.ktc_secondary,
            self.ktn_primary,
            self.ktn_secondary,
        ):
            editor.clear()
        self.sensitivity_factor.setText("1,10")
        self.phs_sensitivity_factor.setText("1,20")
        self.delta_phi.setText("4")
        self.rejection_factor.setText("0,85")
        self._update_delta_r_fw_rv()
        self._configure_settings_table()
        self._configure_load_table()
        self._set_sensitive_stage_column(0)

    def set_inputs_locked(self, locked: bool) -> None:
        for widget in (
            self.protection_type_combo,
            self.sensitive_stage_combo,
            self.ktc_primary,
            self.ktc_secondary,
            self.ktn_primary,
            self.ktn_secondary,
            self.sensitivity_factor,
            self.phs_sensitivity_factor,
            self.delta_phi,
            self.rejection_factor,
            self.settings_table,
            self.load_table,
        ):
            widget.setEnabled(not locked)

    def clear_validation_errors(self) -> None:
        for editor in (
            self.ktc_primary,
            self.ktc_secondary,
            self.ktn_primary,
            self.ktn_secondary,
            self.sensitivity_factor,
            self.phs_sensitivity_factor,
            self.delta_phi,
            self.rejection_factor,
        ):
            editor.setProperty("invalid", False)
            editor.setToolTip("")
            editor.style().unpolish(editor)
            editor.style().polish(editor)
        self.sensitive_stage_combo.setProperty("invalid", False)
        self.sensitive_stage_combo.setToolTip("")
        self.sensitive_stage_combo.style().unpolish(self.sensitive_stage_combo)
        self.sensitive_stage_combo.style().polish(self.sensitive_stage_combo)
        if hasattr(self, "sensitive_stage_error"):
            self.sensitive_stage_error.clear()
            self.sensitive_stage_error.hide()
        for table in (self.settings_table, self.load_table):
            for row in range(table.rowCount()):
                for column in range(table.columnCount()):
                    item = table.item(row, column)
                    if item is not None:
                        editable = bool(item.flags() & Qt.ItemFlag.ItemIsEditable)
                        item.setBackground(EDITABLE_BACKGROUND if editable else LOCKED_BACKGROUND)
                        item.setToolTip("")
        self._highlight_sensitive_stage()

    def validate_for_calculation(self, mode: str) -> list[str]:
        self.clear_validation_errors()
        errors: list[str] = []
        required_fields = [
            (self._translator.text("source.delta_phi"), self.delta_phi),
            (self._translator.text("source.rejection_factor"), self.rejection_factor),
        ]
        if mode in {"all", "psd"}:
            required_fields.append(
                (
                    self._translator.text("source.sensitivity_factor_psd"),
                    self.sensitivity_factor,
                )
            )
        if mode in {"all", "phs"}:
            required_fields.append(
                (
                    self._translator.text("source.sensitivity_factor_phs"),
                    self.phs_sensitivity_factor,
                )
            )

        for label, editor in required_fields:
            if self._line_number(editor) is None:
                self._mark_line_invalid(editor, self._translator.text("validation.required"))
                errors.append(f"{label}: {self._translator.text('validation.required')}")

        stage_errors = self._validate_stage_tables(mode)
        errors.extend(stage_errors)
        if mode == "phs" and not self.sensitive_stage_combo.currentData():
            message = self._translator.text("validation.sensitive_stage_required")
            self._mark_combo_invalid(self.sensitive_stage_combo, message)
            errors.append(f"{self._translator.text('source.sensitive_stage')}: {message}")
        return errors

    def _validate_stage_tables(self, mode: str) -> list[str]:
        required_rows = ["X1", "R1", "RPFF"]
        if self.protection_type_combo.currentIndex() == 0:
            required_rows.extend(["X0", "R0", "RFPE"])
        complete_stage_found = False
        errors: list[str] = []
        missing_cells: list[str] = []
        for column in range(1, self.settings_table.columnCount()):
            missing_for_stage = [
                row_name
                for row_name in required_rows
                if self._setting_number(row_name, column) is None
            ]
            if not missing_for_stage:
                complete_stage_found = True
                continue
            if any(
                self._setting_number(row_name, column) is not None
                for row_name in required_rows
            ):
                for row_name in missing_for_stage:
                    self._mark_table_invalid(
                        self.settings_table,
                        self._settings_rows[row_name],
                        column,
                        self._translator.text("validation.required"),
                    )
                    missing_cells.append(
                        f"{self._translator.text('source.step_template', number=column)}: {row_name}"
                    )
        if missing_cells:
            errors.append(
                self._translator.text("validation.missing_stage_values")
                + " "
                + "; ".join(missing_cells)
            )
        if not complete_stage_found:
            errors.append(self._translator.text("validation.no_complete_stage"))
        return errors

    def _mark_line_invalid(self, editor: QLineEdit, message: str) -> None:
        editor.setProperty("invalid", True)
        editor.setToolTip(message)
        editor.style().unpolish(editor)
        editor.style().polish(editor)

    def _mark_combo_invalid(self, editor: QComboBox, message: str) -> None:
        editor.setProperty("invalid", True)
        editor.setToolTip(message)
        editor.style().unpolish(editor)
        editor.style().polish(editor)
        if editor is self.sensitive_stage_combo and hasattr(self, "sensitive_stage_error"):
            self.sensitive_stage_error.setText(message)
            self.sensitive_stage_error.show()

    def _mark_table_invalid(
        self,
        table: QTableWidget,
        row: int,
        column: int,
        message: str,
    ) -> None:
        item = table.item(row, column)
        if item is not None:
            item.setBackground(QColor("#fee2e2"))
            item.setToolTip(message)

    def to_dict(self) -> dict[str, object]:
        return {
            "protection_type": self.protection_type_combo.currentIndex(),
            "transformers": {
                "ktc_primary": self.ktc_primary.text(),
                "ktc_secondary": self.ktc_secondary.text(),
                "ktn_primary": self.ktn_primary.text(),
                "ktn_secondary": self.ktn_secondary.text(),
            },
            "sensitivity_factor": self.sensitivity_factor.text(),
            "psd_sensitivity_factor": self.sensitivity_factor.text(),
            "phs_sensitivity_factor": self.phs_sensitivity_factor.text(),
            "engineering_settings": {
                "delta_phi_deg": self.delta_phi.text(),
                "rejection_factor": self.rejection_factor.text(),
                "delta_r_fw_rv": self.delta_r_fw_rv.text(),
                "sensitive_stage": self.sensitive_stage_combo.currentData() or 0,
            },
            "settings": self._settings_to_dict(),
            "load_modes": self._table_items_to_dict(self.load_table),
        }

    def phase_phase_stage_inputs(self) -> list[dict[str, float | bool | str]]:
        stages: list[dict[str, float | bool | str]] = []
        for column in range(1, self.settings_table.columnCount()):
            values = {
                "x1": self._setting_number("X1", column),
                "r1": self._setting_number("R1", column),
                "rpff": self._setting_number("RPFF", column),
                "arg_neg_res_deg": self._setting_number("ArgNegRes", column),
                "arg_dir_deg": self._setting_number("ArgDir", column),
            }
            if any(value is None for value in values.values()):
                continue
            stages.append(
                {
                    "name": self._translator.text("source.step_template", number=column),
                    "is_forward": self._is_forward_stage(column),
                    "x1": float(values["x1"]),
                    "r1": float(values["r1"]),
                    "rpff": float(values["rpff"]),
                    "arg_neg_res_deg": float(values["arg_neg_res_deg"]),
                    "arg_dir_deg": float(values["arg_dir_deg"]),
                }
            )
        return stages

    def phase_ground_stage_inputs(self) -> list[dict[str, float | bool | str]]:
        stages: list[dict[str, float | bool | str]] = []
        for column in range(1, self.settings_table.columnCount()):
            values = {
                "x1": self._setting_number("X1", column),
                "r1": self._setting_number("R1", column),
                "x0": self._setting_number("X0", column),
                "r0": self._setting_number("R0", column),
                "rpff": self._setting_number("RPFF", column),
                "rfpe": self._setting_number("RFPE", column),
                "arg_neg_res_deg": self._setting_number("ArgNegRes", column),
                "arg_dir_deg": self._setting_number("ArgDir", column),
            }
            if any(value is None for value in values.values()):
                continue
            stages.append(
                {
                    "name": self._translator.text("source.step_template", number=column),
                    "is_forward": self._is_forward_stage(column),
                    "x1": float(values["x1"]),
                    "r1": float(values["r1"]),
                    "x0": float(values["x0"]),
                    "r0": float(values["r0"]),
                    "rpff": float(values["rpff"]),
                    "rfpe": float(values["rfpe"]),
                    "arg_neg_res_deg": float(values["arg_neg_res_deg"]),
                    "arg_dir_deg": float(values["arg_dir_deg"]),
                }
            )
        return stages

    def psb_stage_setting_inputs(self) -> list[dict[str, float | bool | str | None]]:
        stages: list[dict[str, float | bool | str | None]] = []
        for column in range(1, self.settings_table.columnCount()):
            values = {
                "x1": self._setting_number("X1", column),
                "r1": self._setting_number("R1", column),
                "x0": self._setting_number("X0", column),
                "r0": self._setting_number("R0", column),
                "rfpp": self._setting_number("RPFF", column),
                "rfpe": self._setting_number("RFPE", column),
                "arg_neg_res_deg": self._setting_number("ArgNegRes", column),
                "arg_dir_deg": self._setting_number("ArgDir", column),
            }
            if any(value is None for value in values.values()):
                continue
            stages.append(
                {
                    "name": self._translator.text("source.step_template", number=column),
                    "is_forward": self._is_forward_stage(column),
                    "x1": float(values["x1"]),
                    "r1": float(values["r1"]),
                    "x0": float(values["x0"]),
                    "r0": float(values["r0"]),
                    "rfpp": float(values["rfpp"]),
                    "rfpe": float(values["rfpe"]),
                    "arg_neg_res_deg": float(values["arg_neg_res_deg"]),
                    "arg_dir_deg": float(values["arg_dir_deg"]),
                    "load_angle_deg": load_angle_deg(
                        float(values["r1"]),
                        float(values["x1"]),
                    ),
                    "compensated_load_angle_deg": compensated_load_angle_deg(
                        float(values["r1"]),
                        float(values["x1"]),
                        float(values["r0"]),
                        float(values["x0"]),
                    ),
                    "time_sec": self._stage_time_seconds(column),
                }
            )
        return stages

    def sensitivity_factor_value(self) -> float | None:
        return self._line_number(self.sensitivity_factor)

    def psd_sensitivity_factor_value(self) -> float | None:
        return self._line_number(self.sensitivity_factor)

    def phs_sensitivity_factor_value(self) -> float | None:
        return self._line_number(self.phs_sensitivity_factor)

    def rejection_factor_value(self) -> float | None:
        return self._line_number(self.rejection_factor)

    def delta_phi_value(self) -> float | None:
        return self._line_number(self.delta_phi)

    def delta_r_secondary_value(self) -> float | None:
        return self._line_number(self.delta_r_fw_rv)

    def delta_r_primary_value(self) -> float | None:
        delta_r_secondary = self.delta_r_secondary_value()
        current_primary = self._line_number(self.ktc_primary)
        current_secondary = self._line_number(self.ktc_secondary)
        voltage_primary = self._line_number(self.ktn_primary)
        voltage_secondary = self._line_number(self.ktn_secondary)
        if None in (
            delta_r_secondary,
            current_primary,
            current_secondary,
            voltage_primary,
            voltage_secondary,
        ):
            return None
        if current_primary == 0 or current_secondary == 0 or voltage_secondary == 0:
            return None
        return float(delta_r_secondary) * (
            float(voltage_primary) / float(voltage_secondary)
        ) / (float(current_primary) / float(current_secondary))

    def load_cut_inputs(self) -> dict[str, float | None]:
        forward_r, forward_x = self._load_impedance_components(0)
        reverse_r, reverse_x = self._load_impedance_components(1)
        return {
            "r_load_fw": forward_r,
            "x_load_fw": forward_x,
            "r_load_rv": reverse_r,
            "x_load_rv": reverse_x,
            "rejection_factor": self.rejection_factor_value(),
            "delta_phi_deg": self.delta_phi_value(),
            "delta_r_secondary": self.delta_r_secondary_value(),
            "delta_r_primary": self.delta_r_primary_value(),
        }

    def _line_number(self, editor: QLineEdit) -> float | None:
        text = editor.text().strip().replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _load_impedance_components(self, row: int) -> tuple[float | None, float | None]:
        current = self._table_number(self.load_table, row, 1)
        voltage_kv = self._table_number(self.load_table, row, 2)
        angle_deg = self._table_number(self.load_table, row, 3)
        if current in (None, 0.0) or voltage_kv is None or angle_deg is None:
            return None, None
        # TODO: Verify load impedance convention against RET670 documentation.
        impedance_ohm = voltage_kv * 1000.0 / (sqrt(3.0) * current)
        angle_rad = radians(angle_deg)
        return impedance_ohm * cos(angle_rad), impedance_ohm * sin(angle_rad)

    def _table_number(self, table: QTableWidget, row: int, column: int) -> float | None:
        item = table.item(row, column)
        if item is None:
            return None
        text = item.text().strip().replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def from_dict(self, data: dict[str, object]) -> None:
        if not data:
            return

        transformers = data.get("transformers", {})
        if isinstance(transformers, dict):
            self.ktc_primary.setText(str(transformers.get("ktc_primary", "")))
            self.ktc_secondary.setText(str(transformers.get("ktc_secondary", "")))
            self.ktn_primary.setText(str(transformers.get("ktn_primary", "")))
            self.ktn_secondary.setText(str(transformers.get("ktn_secondary", "")))
        self.sensitivity_factor.setText(
            str(data.get("psd_sensitivity_factor", data.get("sensitivity_factor", "1,10")))
        )
        self.phs_sensitivity_factor.setText(
            str(data.get("phs_sensitivity_factor", "1,20"))
        )
        engineering_settings = data.get("engineering_settings", {})
        if isinstance(engineering_settings, dict):
            self.delta_phi.setText(str(engineering_settings.get("delta_phi_deg", "4")))
            self.rejection_factor.setText(
                str(engineering_settings.get("rejection_factor", "0,85"))
            )
            self.delta_r_fw_rv.setText(
                str(engineering_settings.get("delta_r_fw_rv", ""))
            )
            self._pending_sensitive_stage_column = int(
                engineering_settings.get("sensitive_stage", 0) or 0
            )

        with QSignalBlocker(self.protection_type_combo):
            self.protection_type_combo.setCurrentIndex(int(data.get("protection_type", 0)))

        settings = data.get("settings", {})
        if isinstance(settings, dict):
            self._settings_from_dict(settings)
        load_modes = data.get("load_modes", [])
        if isinstance(load_modes, list):
            self._table_items_from_dict(self.load_table, load_modes)
        self._update_delta_r_fw_rv()
        self._apply_protection_type_rules()
        self._set_sensitive_stage_column(self._pending_sensitive_stage_column)

    def _update_delta_r_fw_rv(self) -> None:
        value = self.ktc_secondary.text().strip().replace(",", ".")
        if value == "5":
            self.delta_r_fw_rv.setText("1")
        elif value == "1":
            self.delta_r_fw_rv.setText("5")
        else:
            self.delta_r_fw_rv.clear()

    def _configure_settings_table(self) -> None:
        with QSignalBlocker(self.settings_table):
            self._fill_settings_table()
        self._apply_protection_type_rules()

    def _fill_settings_table(self) -> None:
        t = self._translator.text
        rows = [
            t("source.direction"),
            "X1",
            "R1",
            "X0",
            "R0",
            "RPFF",
            "RFPE",
            "TPP",
            "TPE",
            "ArgNegRes",
            "ArgDir",
            "Фл",
            "Флк",
        ]
        self._settings_rows = {row_name: row for row, row_name in enumerate(rows)}
        self._settings_row_keys = {
            row_key: row for row, row_key in enumerate(SETTINGS_ROW_KEYS)
        }
        self.settings_table.verticalHeader().setVisible(False)
        for row, row_name in enumerate(rows):
            self.settings_table.setItem(row, 0, self._locked_item(row_name))
            for column in range(1, self.settings_table.columnCount()):
                self._initialize_settings_cell(row, column)
        self._renumber_settings_headers()
        self.settings_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._fit_table_height(self.settings_table)
        self._update_calculated_rows()
        self._update_sensitive_stage_options()

    def _initialize_settings_cell(self, row: int, column: int) -> None:
        t = self._translator.text
        if row == self._settings_row_keys["direction"]:
            widget = self._combo(
                [t("source.direction_forward"), t("source.direction_reverse")]
            )
            widget.currentIndexChanged.connect(self._update_calculated_rows)
            widget.currentIndexChanged.connect(self._update_sensitive_stage_options)
            self.settings_table.setCellWidget(row, column, widget)
            return
        self.settings_table.setItem(row, column, self._editable_item(""))

    def _renumber_settings_headers(self) -> None:
        self.settings_table.setHorizontalHeaderItem(
            0,
            QTableWidgetItem(self._translator.text("source.setting_name")),
        )
        for column in range(1, self.settings_table.columnCount()):
            label = self._translator.text("source.step_template", number=column)
            self.settings_table.setHorizontalHeaderItem(column, QTableWidgetItem(label))

    def _add_stage_after(self, column: int) -> None:
        insert_at = column + 1
        self.settings_table.insertColumn(insert_at)
        for row in range(self.settings_table.rowCount()):
            self._initialize_settings_cell(row, insert_at)
        self._renumber_settings_headers()
        self._apply_protection_type_rules()
        self._update_sensitive_stage_options()
        self.settings_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

    def _remove_stage(self, column: int) -> None:
        if column <= 0 or self.settings_table.columnCount() <= 2:
            return
        self.settings_table.removeColumn(column)
        self._renumber_settings_headers()
        self._apply_protection_type_rules()
        self._update_sensitive_stage_options()
        self.settings_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

    def _apply_protection_type_rules(self) -> None:
        if not self._settings_rows:
            return

        phase_faults_only = self.protection_type_combo.currentIndex() == 1
        if phase_faults_only:
            self._copy_setting_row("X1", "X0")
            self._copy_setting_row("R1", "R0")
            self._copy_setting_row("TPP", "TPE")

        for row_name in ("TPE", "X0", "R0"):
            self._set_setting_row_locked(row_name, phase_faults_only)
        for row_name in ("ArgNegRes", "ArgDir", "Фл", "Флк"):
            self._set_setting_row_locked(row_name, True)
        self._update_calculated_rows()

        self._update_sensitive_stage_options()

    def _on_settings_item_changed(self, item: QTableWidgetItem) -> None:
        if self._syncing_fault_mode or self._syncing_calculated_rows:
            return
        if self.protection_type_combo.currentIndex() == 1:
            if item.row() == self._settings_rows.get("X1"):
                self._copy_setting_row("X1", "X0")
            elif item.row() == self._settings_rows.get("R1"):
                self._copy_setting_row("R1", "R0")
            elif item.row() == self._settings_rows.get("TPP"):
                self._copy_setting_row("TPP", "TPE")
        if item.row() in {
            self._settings_rows.get("X1"),
            self._settings_rows.get("R1"),
            self._settings_rows.get("X0"),
            self._settings_rows.get("R0"),
        }:
            self._update_calculated_rows()

    def _update_calculated_rows(self) -> None:
        if not self._settings_rows:
            return

        self._syncing_calculated_rows = True
        try:
            for column in range(1, self.settings_table.columnCount()):
                self._set_setting_text(
                    "ArgNegRes",
                    column,
                    self._format_number(
                        arg_neg_res_by_direction(self._is_forward_stage(column))
                    ),
                )
                self._set_setting_text(
                    "ArgDir",
                    column,
                    self._format_number(arg_dir_default()),
                )

                r1 = self._setting_number("R1", column)
                x1 = self._setting_number("X1", column)
                r0 = self._setting_number("R0", column)
                x0 = self._setting_number("X0", column)
                self._set_setting_text("Фл", column, self._format_optional_angle(
                    load_angle_deg(r1, x1) if r1 is not None and x1 is not None else None
                ))
                self._set_setting_text("Флк", column, self._format_optional_angle(
                    compensated_load_angle_deg(r1, x1, r0, x0)
                    if None not in (r1, x1, r0, x0)
                    else None
                ))
        finally:
            self._syncing_calculated_rows = False

    def _is_forward_stage(self, column: int) -> bool:
        direction_row = self._settings_row_keys["direction"]
        widget = self.settings_table.cellWidget(direction_row, column)
        return not isinstance(widget, QComboBox) or widget.currentIndex() == 0

    def _setting_number(self, row_name: str, column: int) -> float | None:
        item = self.settings_table.item(self._settings_rows[row_name], column)
        if item is None:
            return None
        text = item.text().strip().replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _stage_time_seconds(self, column: int) -> float | None:
        times = [
            value
            for value in (
                self._setting_number("TPP", column),
                self._setting_number("TPE", column),
            )
            if value is not None
        ]
        return min(times) if times else 0.0

    def _set_setting_text(self, row_name: str, column: int, text: str) -> None:
        item = self.settings_table.item(self._settings_rows[row_name], column)
        if item is not None and item.text() != text:
            item.setText(text)

    def _format_number(self, value: float) -> str:
        return f"{value:g}".replace(".", ",")

    def _format_optional_angle(self, value: float | None) -> str:
        if value is None:
            return ""
        return f"{value:.2f}".replace(".", ",")

    def _settings_to_dict(self) -> dict[str, list[object]]:
        values: dict[str, list[object]] = {}
        for row_key, row in self._settings_row_keys.items():
            row_values: list[object] = []
            for column in range(1, self.settings_table.columnCount()):
                widget = self.settings_table.cellWidget(row, column)
                if isinstance(widget, QComboBox):
                    row_values.append(widget.currentIndex())
                    continue
                item = self.settings_table.item(row, column)
                row_values.append(item.text() if item is not None else "")
            values[row_key] = row_values
        return values

    def _settings_from_dict(self, values: dict[str, object]) -> None:
        stage_count = max(
            (
                len(row_values)
                for row_key, row_values in values.items()
                if row_key in self._settings_row_keys and isinstance(row_values, list)
            ),
            default=self.settings_table.columnCount() - 1,
        )
        if stage_count + 1 != self.settings_table.columnCount():
            self._set_stage_count(stage_count)
        with QSignalBlocker(self.settings_table):
            for row_key, row_values in values.items():
                if row_key not in self._settings_row_keys or not isinstance(row_values, list):
                    continue
                row = self._settings_row_keys[row_key]
                for offset, value in enumerate(row_values):
                    column = offset + 1
                    if column >= self.settings_table.columnCount():
                        continue
                    widget = self.settings_table.cellWidget(row, column)
                    if isinstance(widget, QComboBox):
                        widget.setCurrentIndex(int(value))
                        continue
                    item = self.settings_table.item(row, column)
                    if item is not None:
                        item.setText(str(value))

    def _set_stage_count(self, stage_count: int) -> None:
        self.settings_table.setColumnCount(max(stage_count + 1, 2))
        for row in range(self.settings_table.rowCount()):
            for column in range(1, self.settings_table.columnCount()):
                if (
                    self.settings_table.item(row, column) is None
                    and self.settings_table.cellWidget(row, column) is None
                ):
                    self._initialize_settings_cell(row, column)
        self._renumber_settings_headers()
        self.settings_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._update_sensitive_stage_options()

    def _set_sensitive_stage_column(self, column: int) -> None:
        self._update_sensitive_stage_options()
        index = self.sensitive_stage_combo.findData(column)
        with QSignalBlocker(self.sensitive_stage_combo):
            self.sensitive_stage_combo.setCurrentIndex(index if index >= 0 else 0)
        self._highlight_sensitive_stage()

    def _update_sensitive_stage_options(self, *_: object) -> None:
        if not hasattr(self, "sensitive_stage_combo") or not self._settings_rows:
            return

        current_data = self.sensitive_stage_combo.currentData()
        current_column = int(current_data or 0)
        with QSignalBlocker(self.sensitive_stage_combo):
            self.sensitive_stage_combo.clear()
            self.sensitive_stage_combo.addItem(
                self._translator.text("source.not_selected"),
                0,
            )
            for column in range(1, self.settings_table.columnCount()):
                if self._is_forward_stage(column):
                    self.sensitive_stage_combo.addItem(
                        self._translator.text("source.step_template", number=column),
                        column,
                    )
            index = self.sensitive_stage_combo.findData(current_column)
            self.sensitive_stage_combo.setCurrentIndex(index if index >= 0 else 0)
        self._highlight_sensitive_stage()

    def _highlight_sensitive_stage(self, *_: object) -> None:
        if not self._settings_rows:
            return

        selected_data = self.sensitive_stage_combo.currentData()
        selected_column = int(selected_data or 0)
        for column in range(1, self.settings_table.columnCount()):
            selected = column == selected_column
            header = self.settings_table.horizontalHeaderItem(column)
            if header is not None:
                header.setBackground(
                    SENSITIVE_STAGE_BACKGROUND if selected else EDITABLE_BACKGROUND
                )
            for row in range(self.settings_table.rowCount()):
                item = self.settings_table.item(row, column)
                if item is not None:
                    editable = bool(item.flags() & Qt.ItemFlag.ItemIsEditable)
                    base_background = EDITABLE_BACKGROUND if editable else LOCKED_BACKGROUND
                    item.setBackground(
                        SENSITIVE_STAGE_BACKGROUND if selected else base_background
                    )
            direction_row = self._settings_row_keys.get("direction")
            if direction_row is None:
                continue
            widget = self.settings_table.cellWidget(direction_row, column)
            if widget is not None:
                widget.setStyleSheet(
                    "background-color: #fff2b8;" if selected else ""
                )

    def _table_items_to_dict(self, table: QTableWidget) -> list[list[str]]:
        return [
            [
                table.item(row, column).text()
                if table.item(row, column) is not None
                else ""
                for column in range(table.columnCount())
            ]
            for row in range(table.rowCount())
        ]

    def _table_items_from_dict(self, table: QTableWidget, values: list[object]) -> None:
        for row, row_values in enumerate(values):
            if not isinstance(row_values, list) or row >= table.rowCount():
                continue
            for column, value in enumerate(row_values):
                if column >= table.columnCount():
                    continue
                item = table.item(row, column)
                if item is not None:
                    item.setText(str(value))

    def _copy_setting_row(self, source_name: str, target_name: str) -> None:
        source_row = self._settings_rows[source_name]
        target_row = self._settings_rows[target_name]
        self._syncing_fault_mode = True
        try:
            for column in range(1, self.settings_table.columnCount()):
                source = self.settings_table.item(source_row, column)
                target = self.settings_table.item(target_row, column)
                if target is not None:
                    target.setText(source.text() if source is not None else "")
        finally:
            self._syncing_fault_mode = False

    def _set_setting_row_locked(self, row_name: str, locked: bool) -> None:
        row = self._settings_rows[row_name]
        for column in range(1, self.settings_table.columnCount()):
            item = self.settings_table.item(row, column)
            if item is None:
                continue
            flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            if not locked:
                flags |= Qt.ItemFlag.ItemIsEditable
            item.setFlags(flags)
            item.setBackground(LOCKED_BACKGROUND if locked else EDITABLE_BACKGROUND)

    def _configure_load_table(self) -> None:
        t = self._translator.text
        self.load_table.setHorizontalHeaderLabels(
            [
                t("source.direction"),
                t("source.load_current"),
                t("source.load_voltage"),
                t("source.load_angle"),
                t("source.mode_description"),
            ]
        )
        self.load_table.verticalHeader().setVisible(False)
        directions = [t("source.forward"), t("source.reverse")]
        for row, direction in enumerate(directions):
            self.load_table.setItem(row, 0, self._locked_item(direction))
            for column in range(1, self.load_table.columnCount()):
                self.load_table.setItem(row, column, self._editable_item(""))
        self.load_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._fit_table_height(self.load_table)

    def _locked_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

    def _editable_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(
            Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsEditable
        )
        return item

    def _combo(self, values: list[str]) -> QComboBox:
        combo = QComboBox()
        combo.addItems(values)
        return combo

    def _disable_table_scroll(self, table: QTableWidget) -> None:
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    def _fit_table_height(self, table: QTableWidget) -> None:
        header_height = table.horizontalHeader().height()
        rows_height = sum(table.rowHeight(row) for row in range(table.rowCount()))
        frame = table.frameWidth() * 2
        table.setMinimumHeight(header_height + rows_height + frame + 8)
