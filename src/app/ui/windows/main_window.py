from __future__ import annotations

from base64 import b64encode
from io import BytesIO
from math import atan, ceil, cos, pi, sin, sqrt, tan
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.database.project_repository import ProjectRepository
from app.database.session import create_session_factory, create_sqlite_engine, initialize_database
from app.diagrams.export import SUPPORTED_EXPORT_FILTER, export_figure
from app.diagrams.rx_diagram import configure_rx_axes, plot_rx_diagram
from app.localization.translator import Translator
from app.models.project import ProjectData, ProjectMetadata
from app.services.calculation_service import CalculationResult, CalculationService
from app.services.calculations.phase_phase_zones import (
    PhasePhaseStageInput,
    phase_phase_stage_helpers,
    phase_phase_zone_polygons,
)
from app.services.calculations.phase_ground_zones import (
    PhaseGroundStageInput,
    phase_ground_stage_helpers,
    phase_ground_zone_polygons,
)
from app.services.calculations.psb_blocking_settings import (
    PsbBlockingResult,
    PsbLoadCutInput,
    PsbStageSettingInput,
    psb_blocking_settings,
)
from app.ui.dialogs.project_manager_dialog import ProjectManagerDialog
from app.ui.dialogs.settings_dialog import SettingsDialog
from app.ui.widgets.matplotlib_canvas import MatplotlibPanel
from app.ui.widgets.source_data_widget import SourceDataWidget
from app.utils.docx_export import export_html_to_docx
from app.utils.serialization import to_json


OverlayPoint = tuple[str, float, float]
OverlayPolygon = tuple[str, tuple[OverlayPoint, ...]]
FormulaPoint = tuple[str, str, str, float, str, str, float]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._translator = Translator()
        self._calculation_service = CalculationService()
        self._last_result: CalculationResult | None = None
        self._current_project_id: int | None = None
        self._psd_phase_phase_pick_cid: int | None = None
        self._psd_phase_phase_motion_cid: int | None = None
        self._psd_phase_phase_zone_visibility: dict[str, bool] = {}
        self._psd_phase_phase_point_targets: list[tuple[str, float, float]] = []
        self._psd_phase_ground_pick_cid: int | None = None
        self._psd_phase_ground_motion_cid: int | None = None
        self._psd_phase_ground_zone_visibility: dict[str, bool] = {}
        self._psd_phase_ground_point_targets: list[tuple[str, float, float]] = []
        self._distance_phase_phase_pick_cid: int | None = None
        self._distance_phase_phase_motion_cid: int | None = None
        self._distance_phase_phase_zone_visibility: dict[str, bool] = {}
        self._distance_phase_phase_point_targets: list[tuple[str, float, float]] = []
        self._distance_phase_ground_pick_cid: int | None = None
        self._distance_phase_ground_motion_cid: int | None = None
        self._distance_phase_ground_zone_visibility: dict[str, bool] = {}
        self._distance_phase_ground_point_targets: list[tuple[str, float, float]] = []
        self._last_psb_blocking_result: PsbBlockingResult | None = None
        self._show_point_labels = True

        database_path = self._default_data_dir() / "rel_psd.sqlite"
        engine = create_sqlite_engine(database_path)
        initialize_database(engine)
        self._session_factory = create_session_factory(engine)

        self._build_actions()
        self._build_ui()
        self._load_example_data()
        self._retranslate()

    def _default_data_dir(self) -> Path:
        path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        return Path(path) if path else Path.cwd() / ".rel_psd"

    def _build_actions(self) -> None:
        self.file_menu = self.menuBar().addMenu("")
        self.new_action = self.file_menu.addAction("")
        self.save_action = self.file_menu.addAction("")
        self.open_action = self.file_menu.addAction("")
        self.export_action = self.file_menu.addAction("")
        self.file_menu.addSeparator()
        self.exit_action = self.file_menu.addAction("")

        self.settings_menu = self.menuBar().addMenu("")
        self.language_action = self.settings_menu.addAction("")

        self.save_action.triggered.connect(self._save_project)
        self.new_action.triggered.connect(self._new_project)
        self.open_action.triggered.connect(self._open_latest_project)
        self.export_action.triggered.connect(self._export_rx_diagram)
        self.exit_action.triggered.connect(self.close)
        self.language_action.triggered.connect(self._open_settings)

    def _build_ui(self) -> None:
        self.project_name = QLineEdit()
        self.author = QLineEdit()
        self.source_data_widget = SourceDataWidget(self._translator)

        self.calculate_button = QPushButton()
        self.calculate_button.clicked.connect(self._calculate)
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)

        self.rx_panel = MatplotlibPanel()
        self.psd_phase_phase_panel = MatplotlibPanel()
        self.psd_phase_ground_panel = MatplotlibPanel()
        self.distance_phase_phase_panel = MatplotlibPanel()
        self.distance_phase_ground_panel = MatplotlibPanel()
        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        self.psd_report_text = QTextEdit()
        self.psd_report_text.setReadOnly(True)
        self.psd_report_search = QLineEdit()
        self.psd_report_search.returnPressed.connect(self._find_psd_report_next)
        self.psd_report_find_next_button = QPushButton()
        self.psd_report_find_next_button.clicked.connect(self._find_psd_report_next)
        self.psd_report_find_prev_button = QPushButton()
        self.psd_report_find_prev_button.clicked.connect(self._find_psd_report_previous)
        self.export_psd_report_button = QPushButton()
        self.export_psd_report_button.clicked.connect(self._export_psd_report_docx)
        self.export_psd_settings_button = QPushButton()
        self.export_psd_settings_button.clicked.connect(self._export_psd_settings_docx)
        self.export_psd_phase_phase_graph_button = QPushButton()
        self.export_psd_phase_phase_graph_button.clicked.connect(
            lambda: self._export_graph_panel(self.psd_phase_phase_panel, "psd_phase_phase")
        )
        self.export_psd_phase_ground_graph_button = QPushButton()
        self.export_psd_phase_ground_graph_button.clicked.connect(
            lambda: self._export_graph_panel(self.psd_phase_ground_panel, "psd_phase_ground")
        )
        self.export_distance_phase_phase_graph_button = QPushButton()
        self.export_distance_phase_phase_graph_button.clicked.connect(
            lambda: self._export_graph_panel(self.distance_phase_phase_panel, "distance_phase_phase")
        )
        self.export_distance_phase_ground_graph_button = QPushButton()
        self.export_distance_phase_ground_graph_button.clicked.connect(
            lambda: self._export_graph_panel(self.distance_phase_ground_panel, "distance_phase_ground")
        )
        self.source_data_widget.protection_type_combo.currentIndexChanged.connect(
            self._update_psd_phase_ground_tab
        )
        self.source_data_widget.protection_type_combo.currentIndexChanged.connect(
            self._update_distance_phase_ground_tab
        )

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_input_tab(), "")
        self.tabs.addTab(self._build_distance_zones_tab(), "")
        self.tabs.addTab(self._build_psd_tab(), "")
        self.tabs.addTab(self.report_text, "")
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("")
        self.psd_tabs.currentChanged.connect(self._on_psd_tab_changed)
        self.distance_tabs.currentChanged.connect(self._on_distance_tab_changed)

    def _build_input_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        splitter = QSplitter()

        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)
        left_layout.addWidget(self.source_data_widget)
        left_layout.addStretch()

        left = QScrollArea()
        left.setWidgetResizable(True)
        left.setFrameShape(QScrollArea.Shape.NoFrame)
        left.setWidget(left_content)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_scroll_content = QWidget()
        right_scroll_layout = QVBoxLayout(right_scroll_content)
        right_scroll_layout.addWidget(self._project_group())
        right_scroll_layout.addWidget(self.source_data_widget.controls_panel)
        right_scroll_layout.addStretch()

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        right_scroll.setWidget(right_scroll_content)

        right_layout.addWidget(right_scroll)
        right_layout.addSpacing(30)
        right_layout.addWidget(self.calculate_button)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([760, 420])
        root.addWidget(splitter)
        return page

    def _project_group(self) -> QGroupBox:
        self.project_group = QGroupBox()
        form = QFormLayout(self.project_group)
        self.project_name_label = QLabel()
        self.author_label = QLabel()
        form.addRow(self.project_name_label, self.project_name)
        form.addRow(self.author_label, self.author)
        return self.project_group

    def _build_psd_tab(self) -> QWidget:
        self.psd_tabs = QTabWidget()
        self.psd_settings_tab = self._build_psd_settings_tab()
        self.psd_phase_phase_tab = self._build_psd_phase_phase_tab()
        self.psd_phase_ground_tab = self._build_psd_phase_ground_tab()
        self.psd_tabs.addTab(self.psd_settings_tab, "")
        self.psd_tabs.addTab(self.psd_phase_phase_tab, "")
        self.psd_tabs.addTab(self.psd_phase_ground_tab, "")
        self.psd_report_tab = self._build_psd_report_tab()
        self.psd_tabs.addTab(self.psd_report_tab, "")
        self._update_psd_phase_ground_tab()
        return self.psd_tabs

    def _build_psd_report_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        controls.addWidget(self.psd_report_search)
        controls.addWidget(self.psd_report_find_prev_button)
        controls.addWidget(self.psd_report_find_next_button)
        controls.addStretch()
        controls.addWidget(self.export_psd_report_button)
        layout.addLayout(controls)
        layout.addWidget(self.psd_report_text)
        return page

    def _build_distance_zones_tab(self) -> QWidget:
        self.distance_tabs = QTabWidget()
        self.distance_phase_phase_tab = self._build_distance_phase_phase_tab()
        self.distance_phase_ground_tab = self._build_distance_phase_ground_tab()
        self.distance_tabs.addTab(self.distance_phase_phase_tab, "")
        self.distance_tabs.addTab(self.distance_phase_ground_tab, "")
        self._update_distance_phase_ground_tab()
        return self.distance_tabs

    def _build_distance_phase_phase_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        toolbar.addWidget(self.export_distance_phase_phase_graph_button)
        layout.addLayout(toolbar)
        layout.addWidget(self.distance_phase_phase_panel)
        return page

    def _build_distance_phase_ground_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        toolbar.addWidget(self.export_distance_phase_ground_graph_button)
        layout.addLayout(toolbar)
        layout.addWidget(self.distance_phase_ground_panel)
        return page

    def _build_psd_settings_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        toolbar.addWidget(self.export_psd_settings_button)
        self.psd_reach_table = self._psd_reach_table()
        layout.addLayout(toolbar)
        layout.addWidget(self.psd_reach_table)
        return page

    def _build_psd_phase_phase_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        toolbar.addWidget(self.export_psd_phase_phase_graph_button)
        layout.addLayout(toolbar)
        layout.addWidget(self.psd_phase_phase_panel)
        return page

    def _build_psd_phase_ground_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        toolbar.addWidget(self.export_psd_phase_ground_graph_button)
        layout.addLayout(toolbar)
        layout.addWidget(self.psd_phase_ground_panel)
        return page

    def _psd_reach_table(self) -> QTableWidget:
        table = QTableWidget()
        rows = [
            "X1InFw",
            "R1LIn",
            "R1FInFw",
            "X1InRv",
            "R1FInRv",
            "RLdOutFw",
            "ArgLd",
            "RLdOutRv",
            "KLdFw",
            "KLdRv",
            "tP1",
            "tP2",
            "tW",
            "tH",
            "tEF",
            "tR1",
            "tR2",
        ]
        table.setRowCount(len(rows))
        table.setColumnCount(3)
        self._psd_reach_rows = {name: row for row, name in enumerate(rows)}
        self._psd_row_units = {
            "ArgLd": "град",
            "KLdFw": "в.о.",
            "KLdRv": "в.о.",
            "tP1": "с",
            "tP2": "с",
            "tW": "с",
            "tH": "с",
            "tEF": "с",
            "tR1": "с",
            "tR2": "с",
        }
        table.setHorizontalHeaderLabels(
            [
                self._translator.text("table.name"),
                self._translator.text("report.psd_setting_value"),
                self._translator.text("psd.unit").capitalize(),
            ]
        )
        table.verticalHeader().setVisible(False)
        for row, name in enumerate(rows):
            table.setItem(row, 0, self._table_item(name))
            table.setItem(row, 1, self._table_item(self._default_psd_value(name)))
            table.setItem(row, 2, self._table_item(self._psd_row_units.get(name, "Ом")))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    def _default_psd_value(self, name: str) -> str:
        defaults = {
            "tP1": "0,040",
            "tP2": "0,015",
            "tW": "0,250",
            "tH": "3,000",
            "tEF": "0,000",
            "tR1": "0,300",
            "tR2": "3,000",
        }
        return defaults.get(name, "")

    def _table_item(
        self,
        text: str,
    ) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        return item

    def _update_psd_phase_ground_tab(self) -> None:
        if not hasattr(self, "psd_tabs"):
            return
        ground_index = self.psd_tabs.indexOf(self.psd_phase_ground_tab)
        all_faults_selected = self.source_data_widget.protection_type_combo.currentIndex() == 0
        if all_faults_selected and ground_index == -1:
            report_index = self.psd_tabs.indexOf(self.psd_report_tab)
            insert_index = report_index if report_index != -1 else self.psd_tabs.count()
            self.psd_tabs.insertTab(
                insert_index,
                self.psd_phase_ground_tab,
                self._translator.text("psd.phase_ground_graph"),
            )
        elif all_faults_selected and ground_index != -1:
            self.psd_tabs.setTabText(
                ground_index,
                self._translator.text("psd.phase_ground_graph"),
            )
        elif not all_faults_selected and ground_index != -1:
            self.psd_tabs.removeTab(ground_index)

    def _update_distance_phase_ground_tab(self) -> None:
        if not hasattr(self, "distance_tabs"):
            return
        ground_index = self.distance_tabs.indexOf(self.distance_phase_ground_tab)
        all_faults_selected = self.source_data_widget.protection_type_combo.currentIndex() == 0
        if all_faults_selected and ground_index == -1:
            self.distance_tabs.addTab(
                self.distance_phase_ground_tab,
                self._translator.text("psd.phase_ground_graph"),
            )
        elif all_faults_selected and ground_index != -1:
            self.distance_tabs.setTabText(
                ground_index,
                self._translator.text("psd.phase_ground_graph"),
            )
        elif not all_faults_selected and ground_index != -1:
            self.distance_tabs.removeTab(ground_index)

    def _on_psd_tab_changed(self, index: int) -> None:
        if index == self.psd_tabs.indexOf(self.psd_phase_phase_tab):
            self._plot_psd_phase_phase_zones()
        if index == self.psd_tabs.indexOf(self.psd_phase_ground_tab):
            self._plot_psd_phase_ground_zones()

    def _on_distance_tab_changed(self, index: int) -> None:
        if index == self.distance_tabs.indexOf(self.distance_phase_phase_tab):
            self._plot_distance_phase_phase_zones()
        if index == self.distance_tabs.indexOf(self.distance_phase_ground_tab):
            self._plot_distance_phase_ground_zones()

    def _load_example_data(self) -> None:
        self.project_name.setText("RET670 PSB Study")
        self.author.setText("")
        self._calculate()

    def _project_data(self) -> ProjectData:
        return ProjectData(
            metadata=ProjectMetadata(
                name=self.project_name.text().strip() or "Untitled",
                author=self.author.text().strip(),
                language=self._translator.language,
            ),
            impedance_points=[],
            phasors=[],
            distance_zones=[],
            source_data=self.source_data_widget.to_dict(),
            psb_settings=None,
        )

    def _calculate(self) -> None:
        project = self._project_data()
        self._last_result = self._calculation_service.calculate(project)
        plot_rx_diagram(
            self.rx_panel.axis,
            project.impedance_points,
            self._last_result.distance_zones,
            self._last_result.psb_characteristic,
            self._rx_labels(),
        )
        self.rx_panel.redraw()
        self._update_psd_reach_settings()
        self._plot_psd_phase_phase_zones()
        self._plot_psd_phase_ground_zones()
        self._plot_distance_phase_phase_zones()
        self._plot_distance_phase_ground_zones()
        self.results_text.setPlainText(to_json(self._last_result))
        self.report_text.setHtml(self._build_zone_construction_report())
        self.psd_report_text.setHtml(self._build_psd_engineering_report())
        self.statusBar().showMessage(self._translator.text("message.calculated"), 5000)

    def _redraw_psd_charts(self) -> None:
        self._plot_psd_phase_phase_zones()
        self._plot_psd_phase_ground_zones()
        self._plot_distance_phase_phase_zones()
        self._plot_distance_phase_ground_zones()

    def _update_psd_reach_settings(self) -> None:
        self._last_psb_blocking_result = self._calculate_psb_blocking_settings()
        values = {
            "X1InFw": self._last_psb_blocking_result.x1_in_fw
            if self._last_psb_blocking_result
            else None,
            "R1LIn": self._last_psb_blocking_result.r1l_in
            if self._last_psb_blocking_result
            else None,
            "R1FInFw": self._last_psb_blocking_result.r1f_in_fw
            if self._last_psb_blocking_result
            else None,
            "X1InRv": self._last_psb_blocking_result.x1_in_rv
            if self._last_psb_blocking_result
            else None,
            "R1FInRv": self._last_psb_blocking_result.r1f_in_rv
            if self._last_psb_blocking_result
            else None,
            "RLdOutFw": self._last_psb_blocking_result.rld_out_fw
            if self._last_psb_blocking_result
            else None,
            "ArgLd": self._last_psb_blocking_result.arg_ld_deg
            if self._last_psb_blocking_result
            else None,
            "RLdOutRv": self._last_psb_blocking_result.rld_out_rv
            if self._last_psb_blocking_result
            else None,
            "KLdFw": self._last_psb_blocking_result.kld_fw
            if self._last_psb_blocking_result
            else None,
            "KLdRv": self._last_psb_blocking_result.kld_rv
            if self._last_psb_blocking_result
            else None,
        }
        for name, value in values.items():
            row = self._psd_reach_rows.get(name)
            if row is None:
                continue
            item = self.psd_reach_table.item(row, 1)
            if item is not None:
                item.setText(self._psd_setting_number(name, value))

    def _psd_setting_number(self, name: str, value: float | None) -> str:
        if value is None:
            return ""
        if name in {"KLdFw", "KLdRv"}:
            return f"{value:.2f}".replace(".", ",")
        return self._report_number(value)

    def _calculate_psb_blocking_settings(self) -> PsbBlockingResult | None:
        sensitivity_factor = self.source_data_widget.sensitivity_factor_value()
        if sensitivity_factor is None:
            return None
        stages = [
            PsbStageSettingInput(**stage)
            for stage in self.source_data_widget.psb_stage_setting_inputs()
        ]
        if not stages:
            return None
        return psb_blocking_settings(
            stages,
            sensitivity_factor,
            PsbLoadCutInput(**self.source_data_widget.load_cut_inputs()),
        )

    def _psd_overlay_polygons(
        self,
    ) -> list[OverlayPolygon]:
        result = self._last_psb_blocking_result
        if result is None:
            return []
        required = (
            result.x1_in_fw,
            result.x1_in_rv,
            result.r1f_in_fw,
            result.r1f_in_rv,
            result.r1l_in,
            result.rld_out_fw,
            result.rld_out_rv,
            result.rld_out_fw_load,
            result.rld_out_rv_load,
            result.rld_in_fw_load,
            result.rld_in_rv_load,
            result.kld_fw,
            result.kld_rv,
            result.arg_ld_deg,
        )
        if any(value is None for value in required):
            return []

        x1_fw = float(result.x1_in_fw)
        x1_rv = float(result.x1_in_rv)
        r_fw = float(result.r1f_in_fw)
        r_rv = float(result.r1f_in_rv)
        r_line = float(result.r1l_in)
        rld_out_fw = float(result.rld_out_fw)
        rld_out_rv = float(result.rld_out_rv)
        rld_out_fw_load = float(result.rld_out_fw_load)
        rld_out_rv_load = float(result.rld_out_rv_load)
        rld_in_fw_load = float(result.rld_in_fw_load)
        rld_in_rv_load = float(result.rld_in_rv_load)
        kld_fw = float(result.kld_fw)
        kld_rv = float(result.kld_rv)
        arg_ld = float(result.arg_ld_deg)
        delta_fw = rld_out_fw - rld_out_fw * kld_fw
        delta_rv = rld_out_rv - rld_out_rv * kld_rv
        if r_line == 0.0:
            return []
        line_angle = atan(x1_fw / r_line) * 180.0 / pi
        tan_line = tan(line_angle * pi / 180.0)
        tan_arg_ld = tan(arg_ld * pi / 180.0)
        if tan_line == 0.0 or tan_arg_ld == 0.0:
            return []

        b_prime_x = r_line + r_fw + delta_fw + delta_fw * tan(
            (90.0 - line_angle) * pi / 180.0
        )
        left_inner_x = -(r_rv + x1_rv / tan_line)
        left_outer_x = -(r_rv + x1_rv / tan_line + delta_rv + delta_rv / tan_line)

        inner = self._deduplicate_overlay_points(
            (
                ("A", 0.0, x1_fw),
                ("B", r_line + r_fw, x1_fw),
                ("C", r_fw, 0.0),
                ("D", r_fw, 0.0),
                ("E", r_fw, 0.0),
                ("F", r_fw, 0.0),
                ("G", r_fw, -x1_rv),
                ("H", r_fw, -x1_rv),
                ("I", 0.0, -x1_rv),
                ("L", left_inner_x, -x1_rv),
                ("M", left_inner_x, -x1_rv),
                ("N", -r_rv, 0.0),
                ("O", -r_rv, 0.0),
                ("P", -r_rv, 0.0),
                ("Q", -r_rv, x1_fw),
                ("R", -r_rv, x1_fw),
                ("A", 0.0, x1_fw),
            )
        )
        outer = self._deduplicate_overlay_points(
            (
                ("A'", 0.0, x1_fw + delta_fw),
                ("B'", b_prime_x, x1_fw + delta_fw),
                ("C'", b_prime_x, x1_fw + delta_fw),
                ("D'", r_fw + rld_out_fw * (1.0 - kld_fw), 0.0),
                ("E'", r_fw + rld_out_fw * (1.0 - kld_fw), 0.0),
                ("F'", r_fw + delta_fw, 0.0),
                ("G'", r_fw + delta_fw, -x1_rv - delta_rv),
                ("H'", r_fw + delta_fw, -x1_rv - delta_rv),
                ("I'", 0.0, -x1_rv - delta_rv),
                ("L'", left_outer_x, -x1_rv - delta_rv),
                ("M'", left_outer_x, -x1_rv - delta_rv),
                ("N'", -r_rv - delta_rv, 0.0),
                ("O'", -r_rv - delta_rv, 0.0),
                ("P'", -r_rv - delta_rv, 0.0),
                ("Q'", -r_rv - delta_rv, x1_fw + delta_fw),
                ("R'", -r_rv - delta_rv, x1_fw + delta_fw),
                ("A'", 0.0, x1_fw + delta_fw),
            )
        )
        rld_inner_fw = (
            (
                "AA",
                rld_in_fw_load * 1.5,
                (rld_in_fw_load * 1.5 + delta_fw) * tan_arg_ld,
            ),
            ("BB", rld_in_fw_load, rld_out_fw_load * tan_arg_ld),
            ("CC", rld_in_fw_load, -rld_out_fw_load * tan_arg_ld),
            (
                "DD",
                rld_in_fw_load * 1.5,
                -(rld_in_fw_load * 1.5 + delta_fw) * tan_arg_ld,
            ),
        )
        rld_inner_rv = (
            (
                "EE",
                -rld_in_rv_load * 1.5,
                (rld_in_rv_load * 1.5 + delta_fw) * tan_arg_ld,
            ),
            ("FF", -rld_in_rv_load, rld_out_rv_load * tan_arg_ld),
            ("GG", -rld_in_rv_load, -rld_out_rv_load * tan_arg_ld),
            (
                "HH",
                -rld_in_rv_load * 1.5,
                -(rld_in_rv_load * 1.5 + delta_fw) * tan_arg_ld,
            ),
        )
        rld_outer_fw = (
            ("AA'", rld_out_fw_load * 1.5, (rld_out_fw_load * 1.5) * tan_arg_ld),
            ("BB'", rld_out_fw_load, rld_out_fw_load * tan_arg_ld),
            ("CC'", rld_out_fw_load, -rld_out_fw_load * tan_arg_ld),
            ("DD'", rld_out_fw_load * 1.5, -(rld_out_fw_load * 1.5) * tan_arg_ld),
        )
        rld_outer_rv = (
            ("EE'", -rld_out_rv_load * 1.5, (rld_out_rv_load * 1.5) * tan_arg_ld),
            ("FF'", -rld_out_rv_load, rld_out_rv_load * tan_arg_ld),
            ("GG'", -rld_out_rv_load, -rld_out_rv_load * tan_arg_ld),
            ("HH'", -rld_out_rv_load * 1.5, -(rld_out_rv_load * 1.5) * tan_arg_ld),
        )
        overlays = [
            ("PSD inner", inner),
            ("PSD outer", outer),
            ("RLD inner Fw", rld_inner_fw),
            ("RLD inner Rv", rld_inner_rv),
            ("RLD outer Fw", rld_outer_fw),
            ("RLD outer Rv", rld_outer_rv),
        ]
        load_cut = result.load_cut
        if load_cut is not None and load_cut.rejection_factor is not None:
            k = load_cut.rejection_factor
            if load_cut.r_load_fw is not None and load_cut.x_load_fw is not None:
                overlays.append(
                    (
                        "Zнав Fw",
                        (
                            ("II", 0.0, 0.0),
                            ("JJ", k * load_cut.r_load_fw, k * load_cut.x_load_fw),
                            ("KK", load_cut.r_load_fw, load_cut.x_load_fw),
                        ),
                    )
                )
            if load_cut.r_load_rv is not None and load_cut.x_load_rv is not None:
                overlays.append(
                    (
                        "Zнав Rv",
                        (
                            ("LL", 0.0, 0.0),
                            ("MM", -k * load_cut.r_load_rv, -k * load_cut.x_load_rv),
                            ("NN", -load_cut.r_load_rv, -load_cut.x_load_rv),
                        ),
                    )
                )
        return overlays

    def _deduplicate_overlay_points(
        self,
        points: tuple[OverlayPoint, ...],
    ) -> tuple[OverlayPoint, ...]:
        filtered: list[OverlayPoint] = []
        for point in points:
            if filtered and (
                abs(filtered[-1][1] - point[1]) < 1e-9
                and abs(filtered[-1][2] - point[2]) < 1e-9
            ):
                continue
            filtered.append(point)
        return tuple(filtered)

    def _deduplicate_formula_points(
        self,
        points: tuple[FormulaPoint, ...],
    ) -> tuple[FormulaPoint, ...]:
        filtered: list[FormulaPoint] = []
        for point in points:
            if filtered and (
                abs(filtered[-1][3] - point[3]) < 1e-9
                and abs(filtered[-1][6] - point[6]) < 1e-9
            ):
                continue
            filtered.append(point)
        return tuple(filtered)

    def _plot_psd_phase_phase_zones(self) -> None:
        stages = [
            PhasePhaseStageInput(**stage)
            for stage in self.source_data_widget.phase_phase_stage_inputs()
        ]
        zones = phase_phase_zone_polygons(stages)
        included_stage_names = self._psd_included_stage_names()
        zones = [zone for zone in zones if zone.name in included_stage_names]
        for zone in zones:
            self._psd_phase_phase_zone_visibility.setdefault(zone.name, True)
        axis = self.psd_phase_phase_panel.axis
        axis.clear()
        configure_rx_axes(axis, self._psd_phase_phase_labels())
        line_by_label = {}
        self._psd_phase_phase_point_targets = []
        for zone in zones:
            xs = [point[0] for point in zone.points]
            ys = [point[1] for point in zone.points]
            line = axis.plot(xs, ys, linewidth=1.8, label=zone.name)[0]
            visible = self._psd_phase_phase_zone_visibility.get(zone.name, True)
            line.set_visible(visible)
            line_by_label[zone.name] = line
            if visible:
                point_labels = self._point_labels_for_count(len(zone.points))
                axis.scatter(xs, ys, s=22, zorder=4, label="_nolegend_")
                for point_label, x_value, y_value in zip(
                    point_labels,
                    xs,
                    ys,
                    strict=False,
                ):
                    if self._show_point_labels:
                        axis.annotate(
                            point_label,
                            (x_value, y_value),
                            textcoords="offset points",
                            xytext=(5, 5),
                            fontsize=8,
                        )
                    self._psd_phase_phase_point_targets.append(
                        (f"{zone.name} {point_label}", x_value, y_value)
                    )
        for label, points in self._psd_overlay_polygons():
            self._psd_phase_phase_zone_visibility.setdefault(label, True)
            xs = [point[1] for point in points]
            ys = [point[2] for point in points]
            line = axis.plot(xs, ys, linewidth=1.8, linestyle="--", label=label)[0]
            visible = self._psd_phase_phase_zone_visibility.get(label, True)
            line.set_visible(visible)
            line_by_label[label] = line
            if visible:
                axis.scatter(xs, ys, s=20, zorder=4, label="_nolegend_")
                for point_label, x_value, y_value in points:
                    if self._show_point_labels:
                        axis.annotate(
                            point_label,
                            (x_value, y_value),
                            textcoords="offset points",
                            xytext=(5, 5),
                            fontsize=8,
                        )
                    self._psd_phase_phase_point_targets.append(
                        (f"{label} {point_label}", x_value, y_value)
                    )
        self._autoscale_visible(axis)
        legend = axis.legend(loc="upper left") if line_by_label else None
        if legend is not None:
            for legend_line, text in zip(legend.get_lines(), legend.get_texts(), strict=False):
                label = text.get_text()
                visible = self._psd_phase_phase_zone_visibility.get(label, True)
                legend_line.set_picker(8)
                text.set_picker(True)
                legend_line.set_alpha(1.0 if visible else 0.25)
                text.set_alpha(1.0 if visible else 0.35)
                legend_line._rel_psd_zone_label = label  # type: ignore[attr-defined]
                text._rel_psd_zone_label = label  # type: ignore[attr-defined]
        self._connect_psd_phase_phase_legend_picker(line_by_label)
        self._connect_psd_phase_phase_point_tooltip()
        self.psd_phase_phase_panel.redraw()

    def _plot_psd_phase_ground_zones(self) -> None:
        stages = [
            PhaseGroundStageInput(**stage)
            for stage in self.source_data_widget.phase_ground_stage_inputs()
        ]
        zones = phase_ground_zone_polygons(stages)
        included_stage_names = self._psd_included_stage_names()
        zones = [zone for zone in zones if zone.name in included_stage_names]
        for zone in zones:
            self._psd_phase_ground_zone_visibility.setdefault(zone.name, True)
        axis = self.psd_phase_ground_panel.axis
        axis.clear()
        configure_rx_axes(axis, self._psd_phase_ground_labels())
        line_by_label = {}
        self._psd_phase_ground_point_targets = []
        for zone in zones:
            xs = [point[0] for point in zone.points]
            ys = [point[1] for point in zone.points]
            line = axis.plot(xs, ys, linewidth=1.8, label=zone.name)[0]
            visible = self._psd_phase_ground_zone_visibility.get(zone.name, True)
            line.set_visible(visible)
            line_by_label[zone.name] = line
            if visible:
                axis.scatter(xs, ys, s=22, zorder=4, label="_nolegend_")
                for point_label, x_value, y_value in zip(
                    self._point_labels_for_count(len(zone.points)),
                    xs,
                    ys,
                    strict=False,
                ):
                    if self._show_point_labels:
                        axis.annotate(
                            point_label,
                            (x_value, y_value),
                            textcoords="offset points",
                            xytext=(5, 5),
                            fontsize=8,
                        )
                    self._psd_phase_ground_point_targets.append(
                        (f"{zone.name} {point_label}", x_value, y_value)
                    )
        for label, points in self._psd_overlay_polygons():
            self._psd_phase_ground_zone_visibility.setdefault(label, True)
            xs = [point[1] for point in points]
            ys = [point[2] for point in points]
            line = axis.plot(xs, ys, linewidth=1.8, linestyle="--", label=label)[0]
            visible = self._psd_phase_ground_zone_visibility.get(label, True)
            line.set_visible(visible)
            line_by_label[label] = line
            if visible:
                axis.scatter(xs, ys, s=20, zorder=4, label="_nolegend_")
                for point_label, x_value, y_value in points:
                    if self._show_point_labels:
                        axis.annotate(
                            point_label,
                            (x_value, y_value),
                            textcoords="offset points",
                            xytext=(5, 5),
                            fontsize=8,
                        )
                    self._psd_phase_ground_point_targets.append(
                        (f"{label} {point_label}", x_value, y_value)
                    )
        self._autoscale_visible(axis)
        legend = axis.legend(loc="upper left") if line_by_label else None
        if legend is not None:
            for legend_line, text in zip(legend.get_lines(), legend.get_texts(), strict=False):
                label = text.get_text()
                visible = self._psd_phase_ground_zone_visibility.get(label, True)
                legend_line.set_picker(8)
                text.set_picker(True)
                legend_line.set_alpha(1.0 if visible else 0.25)
                text.set_alpha(1.0 if visible else 0.35)
                legend_line._rel_psd_zone_label = label  # type: ignore[attr-defined]
                text._rel_psd_zone_label = label  # type: ignore[attr-defined]
        self._connect_psd_phase_ground_legend_picker(line_by_label)
        self._connect_psd_phase_ground_point_tooltip()
        self.psd_phase_ground_panel.redraw()

    def _psd_included_stage_names(self) -> set[str]:
        result = self._last_psb_blocking_result
        if result is None:
            return set()
        return set(result.included_forward_stage_names) | set(result.included_reverse_stage_names)

    def _outer_load_cut_overlays(self) -> list[OverlayPolygon]:
        return [
            (label, points)
            for label, points in self._psd_overlay_polygons()
            if label.startswith("RLD outer")
        ]

    def _plot_distance_phase_phase_zones(self) -> None:
        stages = [
            PhasePhaseStageInput(**stage)
            for stage in self.source_data_widget.phase_phase_stage_inputs()
        ]
        zones = phase_phase_zone_polygons(stages)
        for zone in zones:
            self._distance_phase_phase_zone_visibility.setdefault(zone.name, True)
        axis = self.distance_phase_phase_panel.axis
        axis.clear()
        configure_rx_axes(axis, self._phase_phase_distance_labels())
        line_by_label = {}
        self._distance_phase_phase_point_targets = []
        for zone in zones:
            xs = [point[0] for point in zone.points]
            ys = [point[1] for point in zone.points]
            line = axis.plot(xs, ys, linewidth=1.8, label=zone.name)[0]
            visible = self._distance_phase_phase_zone_visibility.get(zone.name, True)
            line.set_visible(visible)
            line_by_label[zone.name] = line
            if visible:
                axis.scatter(xs, ys, s=22, zorder=4, label="_nolegend_")
                for point_label, x_value, y_value in zip(
                    self._point_labels_for_count(len(zone.points)),
                    xs,
                    ys,
                    strict=False,
                ):
                    if self._show_point_labels:
                        axis.annotate(
                            point_label,
                            (x_value, y_value),
                            textcoords="offset points",
                            xytext=(5, 5),
                            fontsize=8,
                        )
                    self._distance_phase_phase_point_targets.append(
                        (f"{zone.name} {point_label}", x_value, y_value)
                    )
        for label, points in self._outer_load_cut_overlays():
            self._distance_phase_phase_zone_visibility.setdefault(label, True)
            xs = [point[1] for point in points]
            ys = [point[2] for point in points]
            line = axis.plot(xs, ys, linewidth=1.8, linestyle="--", label=label)[0]
            visible = self._distance_phase_phase_zone_visibility.get(label, True)
            line.set_visible(visible)
            line_by_label[label] = line
            if visible:
                axis.scatter(xs, ys, s=20, zorder=4, label="_nolegend_")
                for point_label, x_value, y_value in points:
                    if self._show_point_labels:
                        axis.annotate(
                            point_label,
                            (x_value, y_value),
                            textcoords="offset points",
                            xytext=(5, 5),
                            fontsize=8,
                        )
                    self._distance_phase_phase_point_targets.append(
                        (f"{label} {point_label}", x_value, y_value)
                    )
        self._autoscale_visible(axis)
        legend = axis.legend(loc="upper left") if line_by_label else None
        if legend is not None:
            for legend_line, text in zip(legend.get_lines(), legend.get_texts(), strict=False):
                label = text.get_text()
                visible = self._distance_phase_phase_zone_visibility.get(label, True)
                legend_line.set_picker(8)
                text.set_picker(True)
                legend_line.set_alpha(1.0 if visible else 0.25)
                text.set_alpha(1.0 if visible else 0.35)
                legend_line._rel_psd_zone_label = label  # type: ignore[attr-defined]
                text._rel_psd_zone_label = label  # type: ignore[attr-defined]
        self._connect_distance_phase_phase_legend_picker(line_by_label)
        self._connect_distance_phase_phase_point_tooltip()
        self.distance_phase_phase_panel.redraw()

    def _plot_distance_phase_ground_zones(self) -> None:
        stages = [
            PhaseGroundStageInput(**stage)
            for stage in self.source_data_widget.phase_ground_stage_inputs()
        ]
        zones = phase_ground_zone_polygons(stages)
        for zone in zones:
            self._distance_phase_ground_zone_visibility.setdefault(zone.name, True)
        axis = self.distance_phase_ground_panel.axis
        axis.clear()
        configure_rx_axes(axis, self._phase_ground_distance_labels())
        line_by_label = {}
        self._distance_phase_ground_point_targets = []
        for zone in zones:
            xs = [point[0] for point in zone.points]
            ys = [point[1] for point in zone.points]
            line = axis.plot(xs, ys, linewidth=1.8, label=zone.name)[0]
            visible = self._distance_phase_ground_zone_visibility.get(zone.name, True)
            line.set_visible(visible)
            line_by_label[zone.name] = line
            if visible:
                axis.scatter(xs, ys, s=22, zorder=4, label="_nolegend_")
                for point_label, x_value, y_value in zip(
                    self._point_labels_for_count(len(zone.points)),
                    xs,
                    ys,
                    strict=False,
                ):
                    if self._show_point_labels:
                        axis.annotate(
                            point_label,
                            (x_value, y_value),
                            textcoords="offset points",
                            xytext=(5, 5),
                            fontsize=8,
                        )
                    self._distance_phase_ground_point_targets.append(
                        (f"{zone.name} {point_label}", x_value, y_value)
                    )
        for label, points in self._outer_load_cut_overlays():
            self._distance_phase_ground_zone_visibility.setdefault(label, True)
            xs = [point[1] for point in points]
            ys = [point[2] for point in points]
            line = axis.plot(xs, ys, linewidth=1.8, linestyle="--", label=label)[0]
            visible = self._distance_phase_ground_zone_visibility.get(label, True)
            line.set_visible(visible)
            line_by_label[label] = line
            if visible:
                axis.scatter(xs, ys, s=20, zorder=4, label="_nolegend_")
                for point_label, x_value, y_value in points:
                    if self._show_point_labels:
                        axis.annotate(
                            point_label,
                            (x_value, y_value),
                            textcoords="offset points",
                            xytext=(5, 5),
                            fontsize=8,
                        )
                    self._distance_phase_ground_point_targets.append(
                        (f"{label} {point_label}", x_value, y_value)
                    )
        self._autoscale_visible(axis)
        legend = axis.legend(loc="upper left") if line_by_label else None
        if legend is not None:
            for legend_line, text in zip(legend.get_lines(), legend.get_texts(), strict=False):
                label = text.get_text()
                visible = self._distance_phase_ground_zone_visibility.get(label, True)
                legend_line.set_picker(8)
                text.set_picker(True)
                legend_line.set_alpha(1.0 if visible else 0.25)
                text.set_alpha(1.0 if visible else 0.35)
                legend_line._rel_psd_zone_label = label  # type: ignore[attr-defined]
                text._rel_psd_zone_label = label  # type: ignore[attr-defined]
        self._connect_distance_phase_ground_legend_picker(line_by_label)
        self._connect_distance_phase_ground_point_tooltip()
        self.distance_phase_ground_panel.redraw()

    def _connect_psd_phase_phase_legend_picker(self, line_by_label: dict[str, object]) -> None:
        canvas = self.psd_phase_phase_panel.canvas
        if self._psd_phase_phase_pick_cid is not None:
            canvas.mpl_disconnect(self._psd_phase_phase_pick_cid)

        def toggle_zone(event) -> None:  # type: ignore[no-untyped-def]
            label = getattr(event.artist, "_rel_psd_zone_label", None)
            if label not in line_by_label:
                return
            current = self._psd_phase_phase_zone_visibility.get(label, True)
            self._psd_phase_phase_zone_visibility[label] = not current
            self._plot_psd_phase_phase_zones()

        self._psd_phase_phase_pick_cid = canvas.mpl_connect("pick_event", toggle_zone)

    def _connect_psd_phase_phase_point_tooltip(self) -> None:
        canvas = self.psd_phase_phase_panel.canvas
        if self._psd_phase_phase_motion_cid is not None:
            canvas.mpl_disconnect(self._psd_phase_phase_motion_cid)
        tooltip = self.psd_phase_phase_panel.axis.annotate(
            "",
            xy=(0.0, 0.0),
            xytext=(12, 12),
            textcoords="offset points",
            bbox={"boxstyle": "round,pad=0.35", "fc": "#ffffff", "ec": "#64748b"},
            arrowprops={"arrowstyle": "->", "color": "#64748b"},
        )
        tooltip.set_visible(False)

        def show_point(event) -> None:  # type: ignore[no-untyped-def]
            if event.inaxes != self.psd_phase_phase_panel.axis:
                if tooltip.get_visible():
                    tooltip.set_visible(False)
                    canvas.draw_idle()
                return
            if event.xdata is None or event.ydata is None:
                return
            x_min, x_max = self.psd_phase_phase_panel.axis.get_xlim()
            y_min, y_max = self.psd_phase_phase_panel.axis.get_ylim()
            tolerance = max(abs(x_max - x_min), abs(y_max - y_min)) * 0.015
            nearest = None
            nearest_distance = tolerance
            for label, x_value, y_value in self._psd_phase_phase_point_targets:
                distance = ((event.xdata - x_value) ** 2 + (event.ydata - y_value) ** 2) ** 0.5
                if distance <= nearest_distance:
                    nearest = (label, x_value, y_value)
                    nearest_distance = distance
            if nearest is None:
                if tooltip.get_visible():
                    tooltip.set_visible(False)
                    canvas.draw_idle()
                return
            label, x_value, y_value = nearest
            tooltip.xy = (x_value, y_value)
            tooltip.set_text(
                f"{label}\nx={self._report_number(x_value)}; y={self._report_number(y_value)}"
            )
            tooltip.set_visible(True)
            canvas.draw_idle()

        self._psd_phase_phase_motion_cid = canvas.mpl_connect("motion_notify_event", show_point)

    def _connect_psd_phase_ground_legend_picker(self, line_by_label: dict[str, object]) -> None:
        canvas = self.psd_phase_ground_panel.canvas
        if self._psd_phase_ground_pick_cid is not None:
            canvas.mpl_disconnect(self._psd_phase_ground_pick_cid)

        def toggle_zone(event) -> None:  # type: ignore[no-untyped-def]
            label = getattr(event.artist, "_rel_psd_zone_label", None)
            if label not in line_by_label:
                return
            current = self._psd_phase_ground_zone_visibility.get(label, True)
            self._psd_phase_ground_zone_visibility[label] = not current
            self._plot_psd_phase_ground_zones()

        self._psd_phase_ground_pick_cid = canvas.mpl_connect("pick_event", toggle_zone)

    def _connect_psd_phase_ground_point_tooltip(self) -> None:
        canvas = self.psd_phase_ground_panel.canvas
        if self._psd_phase_ground_motion_cid is not None:
            canvas.mpl_disconnect(self._psd_phase_ground_motion_cid)
        tooltip = self.psd_phase_ground_panel.axis.annotate(
            "",
            xy=(0.0, 0.0),
            xytext=(12, 12),
            textcoords="offset points",
            bbox={"boxstyle": "round,pad=0.35", "fc": "#ffffff", "ec": "#64748b"},
            arrowprops={"arrowstyle": "->", "color": "#64748b"},
        )
        tooltip.set_visible(False)

        def show_point(event) -> None:  # type: ignore[no-untyped-def]
            if event.inaxes != self.psd_phase_ground_panel.axis:
                if tooltip.get_visible():
                    tooltip.set_visible(False)
                    canvas.draw_idle()
                return
            if event.xdata is None or event.ydata is None:
                return
            x_min, x_max = self.psd_phase_ground_panel.axis.get_xlim()
            y_min, y_max = self.psd_phase_ground_panel.axis.get_ylim()
            tolerance = max(abs(x_max - x_min), abs(y_max - y_min)) * 0.015
            nearest = None
            nearest_distance = tolerance
            for label, x_value, y_value in self._psd_phase_ground_point_targets:
                distance = ((event.xdata - x_value) ** 2 + (event.ydata - y_value) ** 2) ** 0.5
                if distance <= nearest_distance:
                    nearest = (label, x_value, y_value)
                    nearest_distance = distance
            if nearest is None:
                if tooltip.get_visible():
                    tooltip.set_visible(False)
                    canvas.draw_idle()
                return
            label, x_value, y_value = nearest
            tooltip.xy = (x_value, y_value)
            tooltip.set_text(
                f"{label}\nx={self._report_number(x_value)}; y={self._report_number(y_value)}"
            )
            tooltip.set_visible(True)
            canvas.draw_idle()

        self._psd_phase_ground_motion_cid = canvas.mpl_connect("motion_notify_event", show_point)

    def _connect_distance_phase_phase_legend_picker(
        self,
        line_by_label: dict[str, object],
    ) -> None:
        canvas = self.distance_phase_phase_panel.canvas
        if self._distance_phase_phase_pick_cid is not None:
            canvas.mpl_disconnect(self._distance_phase_phase_pick_cid)

        def toggle_zone(event) -> None:  # type: ignore[no-untyped-def]
            label = getattr(event.artist, "_rel_psd_zone_label", None)
            if label not in line_by_label:
                return
            current = self._distance_phase_phase_zone_visibility.get(label, True)
            self._distance_phase_phase_zone_visibility[label] = not current
            self._plot_distance_phase_phase_zones()

        self._distance_phase_phase_pick_cid = canvas.mpl_connect("pick_event", toggle_zone)

    def _connect_distance_phase_ground_legend_picker(
        self,
        line_by_label: dict[str, object],
    ) -> None:
        canvas = self.distance_phase_ground_panel.canvas
        if self._distance_phase_ground_pick_cid is not None:
            canvas.mpl_disconnect(self._distance_phase_ground_pick_cid)

        def toggle_zone(event) -> None:  # type: ignore[no-untyped-def]
            label = getattr(event.artist, "_rel_psd_zone_label", None)
            if label not in line_by_label:
                return
            current = self._distance_phase_ground_zone_visibility.get(label, True)
            self._distance_phase_ground_zone_visibility[label] = not current
            self._plot_distance_phase_ground_zones()

        self._distance_phase_ground_pick_cid = canvas.mpl_connect("pick_event", toggle_zone)

    def _connect_distance_phase_phase_point_tooltip(self) -> None:
        canvas = self.distance_phase_phase_panel.canvas
        if self._distance_phase_phase_motion_cid is not None:
            canvas.mpl_disconnect(self._distance_phase_phase_motion_cid)
        self._distance_phase_phase_motion_cid = self._connect_point_tooltip(
            self.distance_phase_phase_panel,
            self._distance_phase_phase_point_targets,
        )

    def _connect_distance_phase_ground_point_tooltip(self) -> None:
        canvas = self.distance_phase_ground_panel.canvas
        if self._distance_phase_ground_motion_cid is not None:
            canvas.mpl_disconnect(self._distance_phase_ground_motion_cid)
        self._distance_phase_ground_motion_cid = self._connect_point_tooltip(
            self.distance_phase_ground_panel,
            self._distance_phase_ground_point_targets,
        )

    def _connect_point_tooltip(
        self,
        panel: MatplotlibPanel,
        targets: list[tuple[str, float, float]],
    ) -> int:
        canvas = panel.canvas
        axis = panel.axis
        tooltip = axis.annotate(
            "",
            xy=(0.0, 0.0),
            xytext=(12, 12),
            textcoords="offset points",
            bbox={"boxstyle": "round,pad=0.35", "fc": "#ffffff", "ec": "#64748b"},
            arrowprops={"arrowstyle": "->", "color": "#64748b"},
        )
        tooltip.set_visible(False)

        def show_point(event) -> None:  # type: ignore[no-untyped-def]
            if event.inaxes != axis:
                if tooltip.get_visible():
                    tooltip.set_visible(False)
                    canvas.draw_idle()
                return
            if event.xdata is None or event.ydata is None:
                return
            x_min, x_max = axis.get_xlim()
            y_min, y_max = axis.get_ylim()
            tolerance = max(abs(x_max - x_min), abs(y_max - y_min)) * 0.015
            nearest = None
            nearest_distance = tolerance
            for label, x_value, y_value in targets:
                distance = ((event.xdata - x_value) ** 2 + (event.ydata - y_value) ** 2) ** 0.5
                if distance <= nearest_distance:
                    nearest = (label, x_value, y_value)
                    nearest_distance = distance
            if nearest is None:
                if tooltip.get_visible():
                    tooltip.set_visible(False)
                    canvas.draw_idle()
                return
            label, x_value, y_value = nearest
            tooltip.xy = (x_value, y_value)
            tooltip.set_text(
                f"{label}\nx={self._report_number(x_value)}; y={self._report_number(y_value)}"
            )
            tooltip.set_visible(True)
            canvas.draw_idle()

        return canvas.mpl_connect("motion_notify_event", show_point)

    def _point_labels_for_count(self, count: int) -> list[str]:
        labels = [
            "O",
            "A'",
            "A",
            "B",
            "C",
            "C'",
            "D",
            "D'",
            "E",
            "F",
            "G",
            "H",
            "I",
            "L",
            "M",
            "N",
            "O",
            "P",
            "Q",
            "R",
        ]
        return labels[:count]

    def _autoscale_visible(self, axis) -> None:  # type: ignore[no-untyped-def]
        xs: list[float] = []
        ys: list[float] = []
        for line in axis.lines:
            if not line.get_visible():
                continue
            xs.extend(float(value) for value in line.get_xdata())
            ys.extend(float(value) for value in line.get_ydata())
        if not xs or not ys:
            return
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        x_margin = max((x_max - x_min) * 0.08, 1.0)
        y_margin = max((y_max - y_min) * 0.08, 1.0)
        axis.set_xlim(x_min - x_margin, x_max + x_margin)
        axis.set_ylim(y_min - y_margin, y_max + y_margin)

    def _build_zone_construction_report(self) -> str:
        phase_phase_stages = [
            PhasePhaseStageInput(**stage)
            for stage in self.source_data_widget.phase_phase_stage_inputs()
        ]
        phase_phase_zones = phase_phase_zone_polygons(phase_phase_stages)
        include_phase_ground = self.source_data_widget.protection_type_combo.currentIndex() == 0
        phase_ground_stages = (
            [
                PhaseGroundStageInput(**stage)
                for stage in self.source_data_widget.phase_ground_stage_inputs()
            ]
            if include_phase_ground
            else []
        )
        phase_ground_zones = phase_ground_zone_polygons(phase_ground_stages)
        t = self._translator.text
        if not phase_phase_zones and not phase_ground_zones:
            return (
                "<h2>"
                + self._html(t("report.zone_construction_title"))
                + "</h2><p>"
                + self._html(t("report.no_zone_data"))
                + "</p>"
            )

        sections = [f"<h2>{self._html(t('report.zone_construction_title'))}</h2>"]
        if phase_phase_zones:
            sections.append(f"<h3>{self._html(t('report.phase_phase_zones'))}</h3>")
        for stage, zone in zip(phase_phase_stages, phase_phase_zones, strict=False):
            sections.append(
                self._zone_stage_report(
                    stage_name=stage.name,
                    is_forward=stage.is_forward,
                    inputs=self._phase_phase_inputs_text(stage),
                    helpers=phase_phase_stage_helpers(stage),
                    formulas=self._phase_phase_formula_lines(stage.is_forward),
                    points=zone.points,
                )
            )
        if phase_ground_zones:
            sections.append(f"<h3>{self._html(t('report.phase_ground_zones'))}</h3>")
        for stage, zone in zip(phase_ground_stages, phase_ground_zones, strict=False):
            sections.append(
                self._zone_stage_report(
                    stage_name=stage.name,
                    is_forward=stage.is_forward,
                    inputs=self._phase_ground_inputs_text(stage),
                    helpers=phase_ground_stage_helpers(stage),
                    formulas=self._phase_ground_formula_lines(stage.is_forward),
                    points=zone.points,
                )
            )
        if self._last_psb_blocking_result is not None:
            sections.append(self._psb_blocking_report(self._last_psb_blocking_result))
            sections.append(self._psd_overlay_report(self._last_psb_blocking_result))
        return "\n".join(sections)

    def _psd_overlay_report(self, result: PsbBlockingResult) -> str:
        t = self._translator.text
        sections = [
            f"<h2>{self._html(t('report.psd_geometry_title'))}</h2>",
            self._psd_overlay_formula_table(result),
        ]
        sections.append(f"<h3>{self._html(t('report.load_resistance_title'))}</h3>")
        load_cut = result.load_cut
        load_rows = [
            (
                "Fw",
                load_cut.r_load_fw if load_cut else None,
                load_cut.x_load_fw if load_cut else None,
                result.rld_out_fw_load,
                result.rld_in_fw_load,
            ),
            (
                "Rv",
                load_cut.r_load_rv if load_cut else None,
                load_cut.x_load_rv if load_cut else None,
                result.rld_out_rv_load,
                result.rld_in_rv_load,
            ),
        ]
        sections.append(
            self._simple_table(
                ["Напрямок", "Rнав, Ом", "Xнав, Ом", "RLdOut, Ом", "RLdIn, Ом"],
                [
                    [
                        name,
                        self._report_optional_number(r_value),
                        self._report_optional_number(x_value),
                        self._report_optional_number(out_value),
                        self._report_optional_number(in_value),
                    ]
                    for name, r_value, x_value, out_value, in_value in load_rows
                ],
            )
        )
        return "\n".join(sections)

    def _build_psd_engineering_report(self) -> str:
        result = self._last_psb_blocking_result
        t = self._translator.text
        if result is None:
            return f"<h2>{self._html(t('psd.report'))}</h2><p>{self._html(t('report.no_zone_data'))}</p>"

        n = self._report_optional_number
        k = n(result.sensitivity_factor)
        forward = result.forward
        reverse = result.reverse
        self._report_table_counter = 0
        self._report_table_refs: dict[str, int] = {}

        sections = [
            f"<h2>{self._html(t('report.psd_engineering_title'))}</h2>",
            f"<p>{self._html(t('report.psd_engineering_intro'))}</p>",
            f"<h3>{self._html(t('report.psd_input_data'))}</h3>",
            self._protection_settings_report_table(result),
            f"<p style='margin-bottom: 14px;'>{self._html(t('report.psd_sensitivity_used', value=k))}</p>",
            self._psd_included_stages_table(result),
        ]

        sections.extend(self._psd_detailed_setting_sections(result))
        sections.append(self._psd_report_graphs_html())
        sections.append(self._psd_selected_settings_table(result))
        return "\n".join(sections)

    def _protection_settings_report_table(self, result: PsbBlockingResult) -> str:
        widget = self.source_data_widget
        protection_type = widget.protection_type_combo.currentText()
        sensitive_stage = widget.sensitive_stage_combo.currentText()
        load_cut = result.load_cut
        rows = [
            [self._translator.text("source.protection_type"), protection_type, "-"],
            [self._translator.text("source.sensitive_stage"), sensitive_stage, "-"],
            [self._translator.text("source.ktc_primary"), widget.ktc_primary.text(), "A"],
            [self._translator.text("source.ktc_secondary"), widget.ktc_secondary.text(), "A"],
            [self._translator.text("source.ktn_primary"), widget.ktn_primary.text(), "В"],
            [self._translator.text("source.ktn_secondary"), widget.ktn_secondary.text(), "В"],
            [self._translator.text("source.sensitivity_factor"), self._report_optional_number(result.sensitivity_factor), "в.о."],
            [self._translator.text("source.delta_phi"), self._report_optional_number(load_cut.delta_phi_deg if load_cut else None), "град"],
            [self._translator.text("source.rejection_factor"), self._report_optional_number(load_cut.rejection_factor if load_cut else None), "в.о."],
            [self._translator.text("source.delta_r_fw_rv"), self._report_optional_number(load_cut.delta_r_secondary if load_cut else None), "Ом"],
        ]
        return (
            self._report_table_title(self._translator.text("report.protection_settings_table_title"))
            + self._simple_table(
                [
                    self._translator.text("table.name"),
                    self._translator.text("report.value"),
                    self._translator.text("psd.unit").capitalize(),
                ],
                rows,
            )
        )

    def _psd_report_graphs_html(self) -> str:
        items = [
            (
                self._translator.text("psd.phase_phase_graph"),
                self._figure_data_uri(self.psd_phase_phase_panel),
            )
        ]
        if self.source_data_widget.protection_type_combo.currentIndex() == 0:
            items.append(
                (
                    self._translator.text("psd.phase_ground_graph"),
                    self._figure_data_uri(self.psd_phase_ground_panel),
                )
            )
        html = [f"<h3>{self._html(self._translator.text('report.psd_graphs_title'))}</h3>"]
        for title, uri in items:
            html.append(f"<p><b>{self._html(title)}</b></p>")
            html.append(
                f"<p><img src='{uri}' width='680' alt='{self._html(title)}' /></p>"
            )
        return "\n".join(html)

    def _figure_data_uri(self, panel: MatplotlibPanel) -> str:
        buffer = BytesIO()
        panel.figure.savefig(buffer, format="png", dpi=160, bbox_inches="tight")
        encoded = b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def _psd_included_stages_table(self, result: PsbBlockingResult) -> str:
        included_names = (
            set(result.included_forward_stage_names)
            | set(result.included_reverse_stage_names)
        )
        stage_rows = []
        for stage in self.source_data_widget.psb_stage_setting_inputs():
            if str(stage["name"]) not in included_names:
                continue
            stage_rows.append(stage)
        if not stage_rows:
            return f"<p>{self._html(self._translator.text('report.psb.no_stages'))}</p>"
        settings = [
            (
                self._translator.text("source.direction"),
                lambda stage: self._translator.text(
                    "source.direction_forward"
                    if bool(stage["is_forward"])
                    else "source.direction_reverse"
                ),
            ),
            ("X1", lambda stage: self._report_optional_number(float(stage["x1"]))),
            ("R1", lambda stage: self._report_optional_number(float(stage["r1"]))),
            ("X0", lambda stage: self._report_optional_number(float(stage["x0"]))),
            ("R0", lambda stage: self._report_optional_number(float(stage["r0"]))),
            ("RFPP", lambda stage: self._report_optional_number(float(stage["rfpp"]))),
            ("RFPE", lambda stage: self._report_optional_number(float(stage["rfpe"]))),
            ("ArgNegRes", lambda stage: self._report_optional_number(float(stage["arg_neg_res_deg"]))),
            ("ArgDir", lambda stage: self._report_optional_number(float(stage["arg_dir_deg"]))),
            ("t, c", lambda stage: self._report_optional_number(float(stage["time_sec"]) if stage["time_sec"] is not None else None)),
        ]
        headers = [self._translator.text("source.setting_name")] + [
            str(stage["name"]) for stage in stage_rows
        ]
        rows = [
            [setting_name] + [value_getter(stage) for stage in stage_rows]
            for setting_name, value_getter in settings
        ]
        return (
            self._report_table_title(self._translator.text("report.distance_stages_table_title"))
            + self._simple_table(headers, rows)
        )

    def _psd_selected_settings_table(self, result: PsbBlockingResult) -> str:
        return (
            f"<h3>{self._html(self._translator.text('report.psd_selected_settings'))}</h3>"
            + self._report_table_title(self._translator.text("report.psd_selected_settings_table_title"))
            + self._simple_table(
                [
                    self._translator.text("table.name"),
                    self._translator.text("report.psd_setting_value"),
                    self._translator.text("psd.unit").capitalize(),
                ],
                [
                    ["X₁InFw", self._report_optional_number(result.x1_in_fw), "Ом"],
                    ["R₁FInFw", self._report_optional_number(result.r1f_in_fw), "Ом"],
                    ["X₁InRv", self._report_optional_number(result.x1_in_rv), "Ом"],
                    ["R₁FInRv", self._report_optional_number(result.r1f_in_rv), "Ом"],
                    ["R₁LIn", self._report_optional_number(result.r1l_in), "Ом"],
                    ["RᴸᵈOutFw", self._report_optional_number(result.rld_out_fw), "Ом"],
                    ["RᴸᵈOutRv", self._report_optional_number(result.rld_out_rv), "Ом"],
                    ["ArgLd", self._report_optional_number(result.arg_ld_deg), "град"],
                    ["KᴸᵈFw", self._report_optional_number(result.kld_fw), "в.о."],
                    ["KᴸᵈRv", self._report_optional_number(result.kld_rv), "в.о."],
                ],
            )
        )

    def _psd_detailed_setting_sections(self, result: PsbBlockingResult) -> list[str]:
        t = self._translator.text
        forward = result.forward
        reverse = result.reverse
        load_cut = result.load_cut
        k = result.sensitivity_factor
        n = self._report_optional_number

        def tg(angle: float | None) -> str:
            return f"tg({n(angle)}*pi/180)"

        sections = [f"<h3>{self._html(t('report.psd_inner_forward'))}</h3>", "<ol>"]
        sections.append(
            self._engineering_selection_block(
                "X1InFw",
                [
                    (
                        t("report.psb.forward_coverage_comment"),
                        [
                            self._engineering_calculation_line(
                                "X1InFw",
                                "Kч*X1Fw",
                                f"{n(k)}*{n(forward.x1 if forward else None)}",
                                result.x1_in_fw_coverage_phase,
                            ),
                            self._engineering_calculation_line(
                                "X1InFw",
                                "Kч*(X1Fw+(X0Fw-X1Fw)/3)",
                                f"{n(k)}*({n(forward.x1 if forward else None)}+({n(forward.x0 if forward else None)}-{n(forward.x1 if forward else None)})/3)",
                                result.x1_in_fw_coverage_ground,
                            ),
                        ],
                    ),
                    (
                        t("report.psb.forward_reverse_intersection_comment"),
                        [
                            self._engineering_calculation_line(
                                "X1InFw",
                                "Kч*(RFPPRv/2)*tg(ArgDirFw)",
                                f"{n(k)}*({n(reverse.rfpp if reverse else None)}/2)*{tg(result.arg_dir_fw_deg)}",
                                result.x1_in_fw_reverse_intersection_phase,
                            ),
                            self._engineering_calculation_line(
                                "X1InFw",
                                "Kч*RFPERv*tg(ArgDirFw)",
                                f"{n(k)}*{n(reverse.rfpe if reverse else None)}*{tg(result.arg_dir_fw_deg)}",
                                result.x1_in_fw_reverse_intersection_ground,
                            ),
                        ],
                    ),
                ],
                [
                    result.x1_in_fw_coverage_phase,
                    result.x1_in_fw_coverage_ground,
                    result.x1_in_fw_reverse_intersection_phase,
                    result.x1_in_fw_reverse_intersection_ground,
                ],
                result.x1_in_fw,
                "Ом",
            )
        )
        sections.append(
            self._engineering_selection_block(
                "R1FInFw",
                [
                    (
                        t("report.psb.forward_coverage_comment"),
                        [
                            self._engineering_calculation_line(
                                "R1FInFw",
                                "Kч*(RFPPFw/2)",
                                f"{n(k)}*({n(forward.rfpp if forward else None)}/2)",
                                result.r1f_in_fw_coverage_phase,
                            ),
                            self._engineering_calculation_line(
                                "R1FInFw",
                                "Kч*RFPEFw",
                                f"{n(k)}*{n(forward.rfpe if forward else None)}",
                                result.r1f_in_fw_coverage_ground,
                            ),
                        ],
                    ),
                    (
                        t("report.psb.forward_reverse_intersection_comment"),
                        [
                            self._engineering_calculation_line(
                                "R1FInFw",
                                "Kч*X1Rv*tg(ArgNegResFw-90)",
                                f"{n(k)}*{n(reverse.x1 if reverse else None)}*{tg((result.arg_neg_res_fw_deg or 0.0) - 90.0 if result.arg_neg_res_fw_deg is not None else None)}",
                                result.r1f_in_fw_reverse_intersection_phase,
                            ),
                            self._engineering_calculation_line(
                                "R1FInFw",
                                "Kч*(X1Rv+(X0Rv-X1Rv)/3)*tg(ArgNegResFw-90)",
                                f"{n(k)}*({n(reverse.x1 if reverse else None)}+({n(reverse.x0 if reverse else None)}-{n(reverse.x1 if reverse else None)})/3)*{tg((result.arg_neg_res_fw_deg or 0.0) - 90.0 if result.arg_neg_res_fw_deg is not None else None)}",
                                result.r1f_in_fw_reverse_intersection_ground,
                            ),
                        ],
                    ),
                ],
                [
                    result.r1f_in_fw_coverage_phase,
                    result.r1f_in_fw_coverage_ground,
                    result.r1f_in_fw_reverse_intersection_phase,
                    result.r1f_in_fw_reverse_intersection_ground,
                ],
                result.r1f_in_fw,
                "Ом",
            )
        )
        sections.extend(["</ol>", f"<h3>{self._html(t('report.psd_inner_reverse'))}</h3>", "<ol>"])
        sections.append(
            self._engineering_selection_block(
                "X1InRv",
                [
                    (
                        t("report.psb.reverse_coverage_comment"),
                        [
                            self._engineering_calculation_line(
                                "X1InRv",
                                "Kч*X1Rv",
                                f"{n(k)}*{n(reverse.x1 if reverse else None)}",
                                result.x1_in_rv_coverage_phase,
                            ),
                            self._engineering_calculation_line(
                                "X1InRv",
                                "Kч*(X1Rv+(X0Rv-X1Rv)/3)",
                                f"{n(k)}*({n(reverse.x1 if reverse else None)}+({n(reverse.x0 if reverse else None)}-{n(reverse.x1 if reverse else None)})/3)",
                                result.x1_in_rv_coverage_ground,
                            ),
                        ],
                    ),
                    (
                        t("report.psb.reverse_forward_intersection_comment"),
                        [
                            self._engineering_calculation_line(
                                "X1InRv",
                                "Kч*(RFPPFw/2)*tg(ArgDirRv)",
                                f"{n(k)}*({n(forward.rfpp if forward else None)}/2)*{tg(result.arg_dir_rv_deg)}",
                                result.x1_in_rv_forward_intersection_phase,
                            ),
                            self._engineering_calculation_line(
                                "X1InRv",
                                "Kч*RFPEFw*tg(ArgDirRv)",
                                f"{n(k)}*{n(forward.rfpe if forward else None)}*{tg(result.arg_dir_rv_deg)}",
                                result.x1_in_rv_forward_intersection_ground,
                            ),
                        ],
                    ),
                ],
                [
                    result.x1_in_rv_coverage_phase,
                    result.x1_in_rv_coverage_ground,
                    result.x1_in_rv_forward_intersection_phase,
                    result.x1_in_rv_forward_intersection_ground,
                ],
                result.x1_in_rv,
                "Ом",
            )
        )
        sections.append(
            self._engineering_selection_block(
                "R1FInRv",
                [
                    (
                        t("report.psb.reverse_coverage_comment"),
                        [
                            self._engineering_calculation_line(
                                "R1FInRv",
                                "Kч*(RFPPRv/2)",
                                f"{n(k)}*({n(reverse.rfpp if reverse else None)}/2)",
                                result.r1f_in_rv_coverage_phase,
                            ),
                            self._engineering_calculation_line(
                                "R1FInRv",
                                "Kч*RFPERv",
                                f"{n(k)}*{n(reverse.rfpe if reverse else None)}",
                                result.r1f_in_rv_coverage_ground,
                            ),
                        ],
                    ),
                    (
                        t("report.psb.reverse_forward_intersection_comment"),
                        [
                            self._engineering_calculation_line(
                                "R1FInRv",
                                "Kч*X1Fw*tg(ArgNegResRv-90)",
                                f"{n(k)}*{n(forward.x1 if forward else None)}*{tg((result.arg_neg_res_rv_deg or 0.0) - 90.0 if result.arg_neg_res_rv_deg is not None else None)}",
                                result.r1f_in_rv_forward_intersection_phase,
                            ),
                            self._engineering_calculation_line(
                                "R1FInRv",
                                "Kч*(X1Fw+(X0Fw-X1Fw)/3)*tg(ArgNegResRv-90)",
                                f"{n(k)}*({n(forward.x1 if forward else None)}+({n(forward.x0 if forward else None)}-{n(forward.x1 if forward else None)})/3)*{tg((result.arg_neg_res_rv_deg or 0.0) - 90.0 if result.arg_neg_res_rv_deg is not None else None)}",
                                result.r1f_in_rv_forward_intersection_ground,
                            ),
                        ],
                    ),
                ],
                [
                    result.r1f_in_rv_coverage_phase,
                    result.r1f_in_rv_coverage_ground,
                    result.r1f_in_rv_forward_intersection_phase,
                    result.r1f_in_rv_forward_intersection_ground,
                ],
                result.r1f_in_rv,
                "Ом",
            )
        )
        sections.extend(["</ol>", f"<h3>{self._html(t('report.psd_slope_and_load_cut'))}</h3>", "<ol>"])
        sections.append(self._load_cut_input_block(result))
        sections.append(
            self._engineering_selection_block(
                "R1LIn",
                [
                    (
                        t("report.psb.load_angle_comment"),
                        [
                            self._engineering_calculation_line(
                                "R1LInFw",
                                "X1InFw/tg(FлFw)",
                                f"{n(result.x1_in_fw)}/{tg(result.load_angle_fw_deg)}",
                                result.r1l_in_fw,
                            ),
                            self._engineering_calculation_line(
                                "R1LInRv",
                                "X1InRv/tg(FлRv)",
                                f"{n(result.x1_in_rv)}/{tg(result.load_angle_rv_deg)}",
                                result.r1l_in_rv,
                            ),
                        ],
                    ),
                ],
                [result.r1l_in_fw, result.r1l_in_rv],
                result.r1l_in,
                "Ом",
            )
        )
        sections.append(
            self._engineering_selection_block(
                "RLdOutFw",
                [
                    (
                        t("report.psb.load_cut_detuning_comment"),
                        [
                            self._engineering_calculation_line(
                                "RLdOutFw",
                                "Kвід*RнавFw",
                                f"{n(load_cut.rejection_factor if load_cut else None)}*{n(load_cut.r_load_fw if load_cut else None)}",
                                result.rld_out_fw_load,
                            )
                        ],
                    )
                ],
                [result.rld_out_fw_load],
                result.rld_out_fw_load,
                "Ом",
            )
        )
        sections.append(
            self._engineering_selection_block(
                "RLdOutRv",
                [
                    (
                        t("report.psb.load_cut_detuning_comment"),
                        [
                            self._engineering_calculation_line(
                                "RLdOutRv",
                                "Kвід*RнавRv",
                                f"{n(load_cut.rejection_factor if load_cut else None)}*{n(load_cut.r_load_rv if load_cut else None)}",
                                result.rld_out_rv_load,
                            )
                        ],
                    )
                ],
                [result.rld_out_rv_load],
                result.rld_out_rv_load,
                "Ом",
            )
        )
        sections.append(
            self._engineering_selection_block(
                "KLdFw",
                [
                    (
                        t("report.psb.load_cut_ratio_comment"),
                        [
                            self._engineering_calculation_line(
                                "KLdFw",
                                "RLdInFw/RLdOutFw",
                                f"{n(result.rld_in_fw)}/{n(result.rld_out_fw)}",
                                result.kld_fw,
                            )
                        ],
                    )
                ],
                [result.kld_fw],
                result.kld_fw,
                "в.о.",
            )
        )
        sections.append(
            self._engineering_selection_block(
                "KLdRv",
                [
                    (
                        t("report.psb.load_cut_ratio_comment"),
                        [
                            self._engineering_calculation_line(
                                "KLdRv",
                                "RLdInRv/RLdOutRv",
                                f"{n(result.rld_in_rv)}/{n(result.rld_out_rv)}",
                                result.kld_rv,
                            )
                        ],
                    )
                ],
                [result.kld_rv],
                result.kld_rv,
                "в.о.",
            )
        )
        sections.extend(["</ol>", f"<p>{self._html(t('report.psd_angle_note'))}</p>"])
        return sections

    def _load_cut_input_block(self, result: PsbBlockingResult) -> str:
        t = self._translator.text
        return (
            "<li>"
            f"<p><b>{self._html(t('report.psd_load_input_item'))}</b></p>"
            + self._report_table_title(t("report.load_modes_table_title"))
            + self._load_modes_report_table()
            + self._report_table_title(t("report.load_resistance_title"))
            + self._load_resistance_report_table(result)
            + "</li>"
        )

    def _load_modes_report_table(self) -> str:
        table = self.source_data_widget.load_table
        headers = [
            table.horizontalHeaderItem(column).text()
            if table.horizontalHeaderItem(column) is not None
            else ""
            for column in range(table.columnCount())
        ]
        rows = []
        for row in range(table.rowCount()):
            rows.append(
                [
                    table.item(row, column).text()
                    if table.item(row, column) is not None
                    else ""
                    for column in range(table.columnCount())
                ]
            )
        return self._simple_table(headers, rows)

    def _load_resistance_report_table(self, result: PsbBlockingResult) -> str:
        load_cut = result.load_cut
        return self._simple_table(
            [
                self._translator.text("source.direction"),
                "Rнав (Ом)",
                "Xнав (Ом)",
                "RLdOut (Ом)",
                "RLdIn (Ом)",
            ],
            [
                [
                    "Fw",
                    self._report_optional_number(load_cut.r_load_fw if load_cut else None),
                    self._report_optional_number(load_cut.x_load_fw if load_cut else None),
                    self._report_optional_number(result.rld_out_fw_load),
                    self._report_optional_number(result.rld_in_fw_load),
                ],
                [
                    "Rv",
                    self._report_optional_number(load_cut.r_load_rv if load_cut else None),
                    self._report_optional_number(load_cut.x_load_rv if load_cut else None),
                    self._report_optional_number(result.rld_out_rv_load),
                    self._report_optional_number(result.rld_in_rv_load),
                ],
            ],
        )

    def _engineering_calculation_line(
        self,
        name: str,
        formula: str,
        substituted: str,
        value: float | None,
    ) -> str:
        return (
            f"{self._math_html(name)} = {self._math_html(formula)} = "
            f"{self._html(substituted)} = {self._html(self._report_optional_number(value))}"
            f"<br/><span>{self._html(self._formula_sources_text(formula))}</span>"
        )

    def _engineering_selection_block(
        self,
        name: str,
        conditions: list[tuple[str, list[str]]],
        compared_values: list[float | None],
        final_value: float | None,
        unit: str,
    ) -> str:
        values = [
            self._report_optional_number(value)
            for value in compared_values
            if value is not None
        ]
        values_text = "; ".join(values) if values else "-"
        condition_parts = []
        for condition, lines in conditions:
            condition_parts.append(f"<p>- {self._html(condition)}</p>")
            condition_parts.append("<ul style='margin-top: 4px; margin-bottom: 12px;'>")
            for line in lines:
                formula_part, _, source_part = line.partition("<br/>")
                condition_parts.append(
                    "<li>"
                    f"<p style='margin-bottom: 2px;'>{formula_part} ({self._html(unit)})</p>"
                    f"<p style='margin-top: 0; margin-left: 18px;'>{source_part}</p>"
                    "</li>"
                )
            condition_parts.append("</ul>")
        final_value_text = self._html(self._report_optional_number(final_value))
        final_value_html = (
            f"<b>{final_value_text}</b>" if len(values) > 1 else final_value_text
        )
        token = "__VALUE__"
        final_text = self._translator.text(
            "report.psd_max_selected",
            values=values_text,
            value=token,
            unit=f"({unit})",
        )
        return (
            "<li>"
            f"<p><b>{self._math_html(self._translator.text('report.psd_setting_choice', name=name))}</b></p>"
            + "\n".join(condition_parts)
            + "<p>"
            + self._html(final_text).replace(token, final_value_html)
            + "</p>"
            "</li>"
        )

    def _report_table_title(self, text: str) -> str:
        self._report_table_counter = getattr(self, "_report_table_counter", 0) + 1
        if not hasattr(self, "_report_table_refs"):
            self._report_table_refs = {}
        self._report_table_refs[text] = self._report_table_counter
        title = self._translator.text(
            "report.table_numbered_title",
            number=self._report_table_counter,
            title=text,
        )
        return (
            "<p style='margin-top: 16px; margin-bottom: 6px;'>"
            f"<b>{self._html(title)}</b></p>"
        )

    def _table_reference(self, title: str) -> str:
        number = getattr(self, "_report_table_refs", {}).get(title)
        if number is None:
            return self._translator.text("report.table_generic_reference")
        return self._translator.text("report.table_short_reference", number=number)

    def _formula_sources_text(self, formula: str) -> str:
        protection_ref = self._table_reference(
            self._translator.text("report.protection_settings_table_title")
        )
        stages_ref = self._table_reference(
            self._translator.text("report.distance_stages_table_title")
        )
        load_ref = self._table_reference(
            self._translator.text("report.load_resistance_title")
        )
        sources: list[str] = []
        for token in (
            "Kч",
            "Kвід",
            "∆RFw",
            "∆φ",
        ):
            if token in formula:
                sources.append(f"{token} - {protection_ref}")
        for token in (
            "X1Fw",
            "X0Fw",
            "RFPPFw",
            "RFPEFw",
            "X1Rv",
            "X0Rv",
            "RFPPRv",
            "RFPERv",
            "ArgDirFw",
            "ArgDirRv",
            "ArgNegResFw",
            "ArgNegResRv",
            "FлFw",
            "FлRv",
        ):
            if token in formula:
                sources.append(f"{token} - {stages_ref}")
        for token in (
            "RнавFw",
            "RнавRv",
            "RLdOutFw",
            "RLdOutRv",
            "RLdInFw",
            "RLdInRv",
        ):
            if token in formula:
                sources.append(f"{token} - {load_ref}")
        if not sources:
            return self._translator.text("report.formula_sources_none")
        return self._translator.text(
            "report.formula_sources",
            sources="; ".join(dict.fromkeys(sources)),
        )

    def _math_html(self, text: str) -> str:
        escaped = self._html(text)
        replacements = {
            "X1InFw": "X<sub>1InFw</sub>",
            "R1FInFw": "R<sub>1FInFw</sub>",
            "X1InRv": "X<sub>1InRv</sub>",
            "R1FInRv": "R<sub>1FInRv</sub>",
            "R1LInFw": "R<sub>1LInFw</sub>",
            "R1LInRv": "R<sub>1LInRv</sub>",
            "R1LIn": "R<sub>1LIn</sub>",
            "RLdOutFw": "R<sub>LdOutFw</sub>",
            "RLdOutRv": "R<sub>LdOutRv</sub>",
            "RLdInFw": "R<sub>LdInFw</sub>",
            "RLdInRv": "R<sub>LdInRv</sub>",
            "KLdFw": "K<sub>LdFw</sub>",
            "KLdRv": "K<sub>LdRv</sub>",
            "X1Fw": "X<sub>1Fw</sub>",
            "X0Fw": "X<sub>0Fw</sub>",
            "X1Rv": "X<sub>1Rv</sub>",
            "X0Rv": "X<sub>0Rv</sub>",
        }
        for source, target in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
            escaped = escaped.replace(source, target)
        return escaped

    def _psd_overlay_formula_table(self, result: PsbBlockingResult) -> str:
        rows: list[list[str]] = []
        for zone_label, points in self._psd_overlay_formula_points(result):
            for point_label, x_formula, x_calc, x_value, y_formula, y_calc, y_value in points:
                rows.append(
                    [
                        zone_label,
                        point_label,
                        x_formula,
                        x_calc,
                        self._report_number(x_value),
                        y_formula,
                        y_calc,
                        self._report_number(y_value),
                    ]
                )
        if not rows:
            return ""
        return self._simple_table(
            [
                "Зона",
                "Точка",
                "Формула x",
                "Розрахунок x",
                "x",
                "Формула y",
                "Розрахунок y",
                "y",
            ],
            rows,
        )

    def _psd_overlay_formula_points(
        self,
        result: PsbBlockingResult,
    ) -> list[tuple[str, tuple[FormulaPoint, ...]]]:
        required = (
            result.x1_in_fw,
            result.x1_in_rv,
            result.r1f_in_fw,
            result.r1f_in_rv,
            result.r1l_in,
            result.rld_out_fw,
            result.rld_out_rv,
            result.rld_out_fw_load,
            result.rld_out_rv_load,
            result.rld_in_fw_load,
            result.rld_in_rv_load,
            result.kld_fw,
            result.kld_rv,
            result.arg_ld_deg,
        )
        if any(value is None for value in required):
            return []

        x1_fw = float(result.x1_in_fw)
        x1_rv = float(result.x1_in_rv)
        r_fw = float(result.r1f_in_fw)
        r_rv = float(result.r1f_in_rv)
        r_line = float(result.r1l_in)
        rld_out_fw = float(result.rld_out_fw)
        rld_out_rv = float(result.rld_out_rv)
        rld_out_fw_load = float(result.rld_out_fw_load)
        rld_out_rv_load = float(result.rld_out_rv_load)
        rld_in_fw_load = float(result.rld_in_fw_load)
        rld_in_rv_load = float(result.rld_in_rv_load)
        kld_fw = float(result.kld_fw)
        kld_rv = float(result.kld_rv)
        arg_ld = float(result.arg_ld_deg)
        delta_fw = rld_out_fw - rld_out_fw * kld_fw
        delta_rv = rld_out_rv - rld_out_rv * kld_rv
        if r_line == 0.0:
            return []
        line_angle = atan(x1_fw / r_line) * 180.0 / pi
        tan_line = tan(line_angle * pi / 180.0)
        tan_arg_ld = tan(arg_ld * pi / 180.0)
        if tan_line == 0.0 or tan_arg_ld == 0.0:
            return []

        n = self._report_number
        tg_line = f"tg({n(line_angle)}*pi/180)"
        tg_arg_ld = f"tg({n(arg_ld)}*pi/180)"
        tg_90_line = f"tg((90-{n(line_angle)})*pi/180)"

        def p(
            label: str,
            x_formula: str,
            x_substituted: str,
            x_value: float,
            y_formula: str,
            y_substituted: str,
            y_value: float,
        ) -> FormulaPoint:
            return (
                label,
                x_formula,
                x_substituted,
                x_value,
                y_formula,
                y_substituted,
                y_value,
            )

        b_prime_x = r_line + r_fw + delta_fw + delta_fw * tan(
            (90.0 - line_angle) * pi / 180.0
        )
        left_inner_x = -(r_rv + x1_rv / tan_line)
        left_outer_x = -(r_rv + x1_rv / tan_line + delta_rv + delta_rv / tan_line)
        inner = self._deduplicate_formula_points(
            (
                p("A", "0", "0", 0.0, "X1InFw", n(x1_fw), x1_fw),
                p(
                    "B",
                    "R1LIn + R1FInFw",
                    f"{n(r_line)} + {n(r_fw)}",
                    r_line + r_fw,
                    "X1InFw",
                    n(x1_fw),
                    x1_fw,
                ),
                p("C", "R1FInFw", n(r_fw), r_fw, "0", "0", 0.0),
                p("D", "R1FInFw", n(r_fw), r_fw, "0", "0", 0.0),
                p("E", "R1FInFw", n(r_fw), r_fw, "0", "0", 0.0),
                p("F", "R1FInFw", n(r_fw), r_fw, "0", "0", 0.0),
                p("G", "R1FInFw", n(r_fw), r_fw, "-X1InRv", f"-{n(x1_rv)}", -x1_rv),
                p("H", "R1FInFw", n(r_fw), r_fw, "-X1InRv", f"-{n(x1_rv)}", -x1_rv),
                p("I", "0", "0", 0.0, "-X1InRv", f"-{n(x1_rv)}", -x1_rv),
                p(
                    "L",
                    "-(R1FInRv + X1InRv/tg(Line Angle*pi/180))",
                    f"-({n(r_rv)} + {n(x1_rv)}/{tg_line})",
                    left_inner_x,
                    "-X1InRv",
                    f"-{n(x1_rv)}",
                    -x1_rv,
                ),
                p(
                    "M",
                    "-(R1FInRv + X1InRv/tg(Line Angle*pi/180))",
                    f"-({n(r_rv)} + {n(x1_rv)}/{tg_line})",
                    left_inner_x,
                    "-X1InRv",
                    f"-{n(x1_rv)}",
                    -x1_rv,
                ),
                p("N", "-R1FInRv", f"-{n(r_rv)}", -r_rv, "0", "0", 0.0),
                p("O", "-R1FInRv", f"-{n(r_rv)}", -r_rv, "0", "0", 0.0),
                p("P", "-R1FInRv", f"-{n(r_rv)}", -r_rv, "0", "0", 0.0),
                p("Q", "-R1FInRv", f"-{n(r_rv)}", -r_rv, "X1InFw", n(x1_fw), x1_fw),
                p("R", "-R1FInRv", f"-{n(r_rv)}", -r_rv, "X1InFw", n(x1_fw), x1_fw),
                p("A", "0", "0", 0.0, "X1InFw", n(x1_fw), x1_fw),
            )
        )
        outer = self._deduplicate_formula_points(
            (
                p("A'", "0", "0", 0.0, "X1InFw + DELTA FW", f"{n(x1_fw)} + {n(delta_fw)}", x1_fw + delta_fw),
                p(
                    "B'",
                    "R1LIn + R1FInFw + DELTA FW + DELTA FW*tg((90-Line Angle)*pi/180)",
                    f"{n(r_line)} + {n(r_fw)} + {n(delta_fw)} + {n(delta_fw)}*{tg_90_line}",
                    b_prime_x,
                    "X1InFw + DELTA FW",
                    f"{n(x1_fw)} + {n(delta_fw)}",
                    x1_fw + delta_fw,
                ),
                p(
                    "C'",
                    "R1LIn + R1FInFw + DELTA FW + DELTA FW*tg((90-Line Angle)*pi/180)",
                    f"{n(r_line)} + {n(r_fw)} + {n(delta_fw)} + {n(delta_fw)}*{tg_90_line}",
                    b_prime_x,
                    "X1InFw + DELTA FW",
                    f"{n(x1_fw)} + {n(delta_fw)}",
                    x1_fw + delta_fw,
                ),
                p(
                    "D'",
                    "R1FInFw + RLdOutFw*(1-KLdFw)",
                    f"{n(r_fw)} + {n(rld_out_fw)}*(1-{n(kld_fw)})",
                    r_fw + rld_out_fw * (1.0 - kld_fw),
                    "0",
                    "0",
                    0.0,
                ),
                p(
                    "E'",
                    "R1FInFw + RLdOutFw*(1-KLdFw)",
                    f"{n(r_fw)} + {n(rld_out_fw)}*(1-{n(kld_fw)})",
                    r_fw + rld_out_fw * (1.0 - kld_fw),
                    "0",
                    "0",
                    0.0,
                ),
                p("F'", "R1FInFw + DELTA FW", f"{n(r_fw)} + {n(delta_fw)}", r_fw + delta_fw, "0", "0", 0.0),
                p(
                    "G'",
                    "R1FInFw + DELTA FW",
                    f"{n(r_fw)} + {n(delta_fw)}",
                    r_fw + delta_fw,
                    "-X1InRv - DELTA RV",
                    f"-{n(x1_rv)} - {n(delta_rv)}",
                    -x1_rv - delta_rv,
                ),
                p(
                    "H'",
                    "R1FInFw + DELTA FW",
                    f"{n(r_fw)} + {n(delta_fw)}",
                    r_fw + delta_fw,
                    "-X1InRv - DELTA RV",
                    f"-{n(x1_rv)} - {n(delta_rv)}",
                    -x1_rv - delta_rv,
                ),
                p("I'", "0", "0", 0.0, "-X1InRv - DELTA RV", f"-{n(x1_rv)} - {n(delta_rv)}", -x1_rv - delta_rv),
                p(
                    "L'",
                    "-(R1FInRv + X1InRv/tg(Line Angle*pi/180) + DELTA RV + DELTA RV/tg(Line Angle*pi/180))",
                    f"-({n(r_rv)} + {n(x1_rv)}/{tg_line} + {n(delta_rv)} + {n(delta_rv)}/{tg_line})",
                    left_outer_x,
                    "-X1InRv - DELTA RV",
                    f"-{n(x1_rv)} - {n(delta_rv)}",
                    -x1_rv - delta_rv,
                ),
                p(
                    "M'",
                    "-(R1FInRv + X1InRv/tg(Line Angle*pi/180) + DELTA RV + DELTA RV/tg(Line Angle*pi/180))",
                    f"-({n(r_rv)} + {n(x1_rv)}/{tg_line} + {n(delta_rv)} + {n(delta_rv)}/{tg_line})",
                    left_outer_x,
                    "-X1InRv - DELTA RV",
                    f"-{n(x1_rv)} - {n(delta_rv)}",
                    -x1_rv - delta_rv,
                ),
                p("N'", "-R1FInRv - DELTA RV", f"-{n(r_rv)} - {n(delta_rv)}", -r_rv - delta_rv, "0", "0", 0.0),
                p("O'", "-R1FInRv - DELTA RV", f"-{n(r_rv)} - {n(delta_rv)}", -r_rv - delta_rv, "0", "0", 0.0),
                p("P'", "-R1FInRv - DELTA RV", f"-{n(r_rv)} - {n(delta_rv)}", -r_rv - delta_rv, "0", "0", 0.0),
                p(
                    "Q'",
                    "-R1FInRv - DELTA RV",
                    f"-{n(r_rv)} - {n(delta_rv)}",
                    -r_rv - delta_rv,
                    "X1InFw + DELTA FW",
                    f"{n(x1_fw)} + {n(delta_fw)}",
                    x1_fw + delta_fw,
                ),
                p(
                    "R'",
                    "-R1FInRv - DELTA RV",
                    f"-{n(r_rv)} - {n(delta_rv)}",
                    -r_rv - delta_rv,
                    "X1InFw + DELTA FW",
                    f"{n(x1_fw)} + {n(delta_fw)}",
                    x1_fw + delta_fw,
                ),
                p("A'", "0", "0", 0.0, "X1InFw + DELTA FW", f"{n(x1_fw)} + {n(delta_fw)}", x1_fw + delta_fw),
            )
        )

        rld_inner_fw = (
            p("AA", "RLdInFw_load*1,5", f"{n(rld_in_fw_load)}*1,5", rld_in_fw_load * 1.5, "(RLdInFw_load*1,5 + DELTA FW)*tg(ArgLd*pi/180)", f"({n(rld_in_fw_load)}*1,5 + {n(delta_fw)})*{tg_arg_ld}", (rld_in_fw_load * 1.5 + delta_fw) * tan_arg_ld),
            p("BB", "RLdInFw_load", n(rld_in_fw_load), rld_in_fw_load, "RLdOutFw_load*tg(ArgLd*pi/180)", f"{n(rld_out_fw_load)}*{tg_arg_ld}", rld_out_fw_load * tan_arg_ld),
            p("CC", "RLdInFw_load", n(rld_in_fw_load), rld_in_fw_load, "-RLdOutFw_load*tg(ArgLd*pi/180)", f"-{n(rld_out_fw_load)}*{tg_arg_ld}", -rld_out_fw_load * tan_arg_ld),
            p("DD", "RLdInFw_load*1,5", f"{n(rld_in_fw_load)}*1,5", rld_in_fw_load * 1.5, "-(RLdInFw_load*1,5 + DELTA FW)*tg(ArgLd*pi/180)", f"-({n(rld_in_fw_load)}*1,5 + {n(delta_fw)})*{tg_arg_ld}", -(rld_in_fw_load * 1.5 + delta_fw) * tan_arg_ld),
        )
        rld_inner_rv = (
            p("EE", "-RLdInRv_load*1,5", f"-{n(rld_in_rv_load)}*1,5", -rld_in_rv_load * 1.5, "(RLdInRv_load*1,5 + DELTA FW)*tg(ArgLd*pi/180)", f"({n(rld_in_rv_load)}*1,5 + {n(delta_fw)})*{tg_arg_ld}", (rld_in_rv_load * 1.5 + delta_fw) * tan_arg_ld),
            p("FF", "-RLdInRv_load", f"-{n(rld_in_rv_load)}", -rld_in_rv_load, "RLdOutRv_load*tg(ArgLd*pi/180)", f"{n(rld_out_rv_load)}*{tg_arg_ld}", rld_out_rv_load * tan_arg_ld),
            p("GG", "-RLdInRv_load", f"-{n(rld_in_rv_load)}", -rld_in_rv_load, "-RLdOutRv_load*tg(ArgLd*pi/180)", f"-{n(rld_out_rv_load)}*{tg_arg_ld}", -rld_out_rv_load * tan_arg_ld),
            p("HH", "-RLdInRv_load*1,5", f"-{n(rld_in_rv_load)}*1,5", -rld_in_rv_load * 1.5, "-(RLdInRv_load*1,5 + DELTA FW)*tg(ArgLd*pi/180)", f"-({n(rld_in_rv_load)}*1,5 + {n(delta_fw)})*{tg_arg_ld}", -(rld_in_rv_load * 1.5 + delta_fw) * tan_arg_ld),
        )
        rld_outer_fw = (
            p("AA'", "RLdOutFw_load*1,5", f"{n(rld_out_fw_load)}*1,5", rld_out_fw_load * 1.5, "RLdOutFw_load*1,5*tg(ArgLd*pi/180)", f"{n(rld_out_fw_load)}*1,5*{tg_arg_ld}", rld_out_fw_load * 1.5 * tan_arg_ld),
            p("BB'", "RLdOutFw_load", n(rld_out_fw_load), rld_out_fw_load, "RLdOutFw_load*tg(ArgLd*pi/180)", f"{n(rld_out_fw_load)}*{tg_arg_ld}", rld_out_fw_load * tan_arg_ld),
            p("CC'", "RLdOutFw_load", n(rld_out_fw_load), rld_out_fw_load, "-RLdOutFw_load*tg(ArgLd*pi/180)", f"-{n(rld_out_fw_load)}*{tg_arg_ld}", -rld_out_fw_load * tan_arg_ld),
            p("DD'", "RLdOutFw_load*1,5", f"{n(rld_out_fw_load)}*1,5", rld_out_fw_load * 1.5, "-RLdOutFw_load*1,5*tg(ArgLd*pi/180)", f"-{n(rld_out_fw_load)}*1,5*{tg_arg_ld}", -rld_out_fw_load * 1.5 * tan_arg_ld),
        )
        rld_outer_rv = (
            p("EE'", "-RLdOutRv_load*1,5", f"-{n(rld_out_rv_load)}*1,5", -rld_out_rv_load * 1.5, "RLdOutRv_load*1,5*tg(ArgLd*pi/180)", f"{n(rld_out_rv_load)}*1,5*{tg_arg_ld}", rld_out_rv_load * 1.5 * tan_arg_ld),
            p("FF'", "-RLdOutRv_load", f"-{n(rld_out_rv_load)}", -rld_out_rv_load, "RLdOutRv_load*tg(ArgLd*pi/180)", f"{n(rld_out_rv_load)}*{tg_arg_ld}", rld_out_rv_load * tan_arg_ld),
            p("GG'", "-RLdOutRv_load", f"-{n(rld_out_rv_load)}", -rld_out_rv_load, "-RLdOutRv_load*tg(ArgLd*pi/180)", f"-{n(rld_out_rv_load)}*{tg_arg_ld}", -rld_out_rv_load * tan_arg_ld),
            p("HH'", "-RLdOutRv_load*1,5", f"-{n(rld_out_rv_load)}*1,5", -rld_out_rv_load * 1.5, "-RLdOutRv_load*1,5*tg(ArgLd*pi/180)", f"-{n(rld_out_rv_load)}*1,5*{tg_arg_ld}", -rld_out_rv_load * 1.5 * tan_arg_ld),
        )

        return [
            ("PSD inner", inner),
            ("PSD outer", outer),
            ("RLD inner Fw", rld_inner_fw),
            ("RLD inner Rv", rld_inner_rv),
            ("RLD outer Fw", rld_outer_fw),
            ("RLD outer Rv", rld_outer_rv),
        ]

    def _coordinate_table(
        self,
        polygons: list[OverlayPolygon],
    ) -> str:
        rows: list[list[str]] = []
        for label, points in polygons:
            for point_label, x_value, y_value in points:
                rows.append(
                    [
                        label,
                        point_label,
                        self._report_number(x_value),
                        self._report_number(y_value),
                    ]
                )
        return self._simple_table(["Зона", "Точка", "x", "y"], rows)

    def _simple_table(self, headers: list[str], rows: list[list[str]]) -> str:
        table = [
            "<table cellspacing='0' cellpadding='6' "
            "style='border-collapse: collapse; width: 100%; margin-bottom: 18px;'>",
            "<tr>",
        ]
        for header in headers:
            header = header[:1].upper() + header[1:] if header else header
            table.append(
                f"<th style='{self._report_cell_style(header=True)}'>{self._html(header)}</th>"
            )
        table.append("</tr>")
        for row in rows:
            table.append("<tr>")
            for value in row:
                table.append(f"<td style='{self._report_cell_style()}'>{self._html(value)}</td>")
            table.append("</tr>")
        table.append("</table>")
        return "".join(table)

    def _psb_blocking_report(self, result: PsbBlockingResult) -> str:
        t = self._translator.text
        rows: list[tuple[str, str, float | None, str]] = []

        def rounded_max(*values: float | None) -> float | None:
            return self._rounded_report_value(self._max_report_value(*values))

        def comparison_comment(*items: tuple[str, float | None]) -> str:
            values = "; ".join(
                f"{label}={self._report_optional_number(value)}" for label, value in items
            )
            return t("report.psb.max_comment") + " " + t(
                "report.psb.compared_values",
                values=values,
            )

        def formula_with_values(formula: str, substitution: str) -> str:
            return f"{formula}\n{substitution}"

        def value_text(value: float | None) -> str:
            return self._report_optional_number(value)

        def extreme_text(container: object | None, field_name: str) -> str:
            return self._report_optional_extreme(container, field_name)

        def tan_text(angle_deg: float | None) -> str:
            if angle_deg is None:
                return "tg(-)"
            return f"tg({self._report_number(angle_deg)}*pi/180)"

        def min_text(*values: float | None) -> str:
            complete_values = [value_text(value) for value in values if value is not None]
            return "min(" + "; ".join(complete_values) + ")" if complete_values else "min(-)"

        def load_angle_min_text(
            label: str,
            candidates: tuple[tuple[str, float], ...],
            value: float | None,
        ) -> str:
            values = [candidate_value for _, candidate_value in candidates]
            return f"{label}={min_text(*values)}={value_text(value)}"

        def add_condition(
            step: str,
            formula: str,
            value: float | None,
            comment: str,
            substitution: str,
        ) -> None:
            rows.append((step, formula_with_values(formula, substitution), value, comment))

        def add_summary(
            step: str,
            formula: str,
            value: float | None,
            *items: tuple[str, float | None],
        ) -> None:
            substituted = "max(" + "; ".join(value_text(item_value) for _, item_value in items) + ")"
            rows.append(
                (
                    step,
                    formula_with_values(formula, substituted),
                    value,
                    comparison_comment(*items),
                )
            )

        x1_fw_11 = rounded_max(result.x1_in_fw_coverage_phase, result.x1_in_fw_coverage_ground)
        r1f_fw_11 = rounded_max(
            result.r1f_in_fw_coverage_phase,
            result.r1f_in_fw_coverage_ground,
        )
        x1_fw_13 = rounded_max(
            result.x1_in_fw_reverse_intersection_phase,
            result.x1_in_fw_reverse_intersection_ground,
        )
        r1f_fw_13 = rounded_max(
            result.r1f_in_fw_reverse_intersection_phase,
            result.r1f_in_fw_reverse_intersection_ground,
        )
        x1_rv_21 = rounded_max(result.x1_in_rv_coverage_phase, result.x1_in_rv_coverage_ground)
        r1f_rv_21 = rounded_max(
            result.r1f_in_rv_coverage_phase,
            result.r1f_in_rv_coverage_ground,
        )
        x1_rv_23 = rounded_max(
            result.x1_in_rv_forward_intersection_phase,
            result.x1_in_rv_forward_intersection_ground,
        )
        r1f_rv_23 = rounded_max(
            result.r1f_in_rv_forward_intersection_phase,
            result.r1f_in_rv_forward_intersection_ground,
        )
        arg_dir_fw = result.arg_dir_fw_deg
        arg_neg_res_fw = result.arg_neg_res_fw_deg
        arg_dir_rv = result.arg_dir_rv_deg
        arg_neg_res_rv = result.arg_neg_res_rv_deg

        add_condition(
            t("report.psb.forward_coverage"),
            "1.1 X1InFw: Kч*X1Fw",
            result.x1_in_fw_coverage_phase,
            t("report.psb.forward_coverage_comment"),
            "1.1 X1InFw = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.forward, 'x1')}",
        )
        add_condition(
            t("report.psb.forward_coverage"),
            "1.1 X1InFw: Kч*(X1Fw+(X0Fw-X1Fw)/3)",
            result.x1_in_fw_coverage_ground,
            t("report.psb.forward_coverage_comment"),
            "1.1 X1InFw = "
            f"{value_text(result.sensitivity_factor)}*("
            f"{extreme_text(result.forward, 'x1')}+"
            f"({extreme_text(result.forward, 'x0')}-{extreme_text(result.forward, 'x1')})/3)",
        )
        add_summary(
            t("report.psb.forward_coverage"),
            "1.1 X1InFw = max(Kч*X1Fw; Kч*(X1Fw+(X0Fw-X1Fw)/3))",
            x1_fw_11,
            ("Kч*X1Fw", result.x1_in_fw_coverage_phase),
            ("Kч*(X1Fw+(X0Fw-X1Fw)/3)", result.x1_in_fw_coverage_ground),
        )
        add_condition(
            t("report.psb.forward_coverage"),
            "1.1 R1FInFw: Kч*(RFPPFw/2)",
            result.r1f_in_fw_coverage_phase,
            t("report.psb.forward_coverage_comment"),
            "1.1 R1FInFw = "
            f"{value_text(result.sensitivity_factor)}*({extreme_text(result.forward, 'rfpp')}/2)",
        )
        add_condition(
            t("report.psb.forward_coverage"),
            "1.1 R1FInFw: Kч*RFPEFw",
            result.r1f_in_fw_coverage_ground,
            t("report.psb.forward_coverage_comment"),
            "1.1 R1FInFw = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.forward, 'rfpe')}",
        )
        add_summary(
            t("report.psb.forward_coverage"),
            "1.1 R1FInFw = max(Kч*(RFPPFw/2); Kч*RFPEFw)",
            r1f_fw_11,
            ("Kч*(RFPPFw/2)", result.r1f_in_fw_coverage_phase),
            ("Kч*RFPEFw", result.r1f_in_fw_coverage_ground),
        )
        add_condition(
            t("report.psb.forward_reverse_intersection"),
            "1.3 X1InFw: Kч*(RFPPRv/2)*tg(ArgDirFw)",
            result.x1_in_fw_reverse_intersection_phase,
            t("report.psb.forward_reverse_intersection_comment"),
            "1.3 X1InFw = "
            f"{value_text(result.sensitivity_factor)}*({extreme_text(result.reverse, 'rfpp')}/2)"
            f"*{tan_text(arg_dir_fw)}",
        )
        add_condition(
            t("report.psb.forward_reverse_intersection"),
            "1.3 X1InFw: Kч*RFPERv*tg(ArgDirFw)",
            result.x1_in_fw_reverse_intersection_ground,
            t("report.psb.forward_reverse_intersection_comment"),
            "1.3 X1InFw = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.reverse, 'rfpe')}"
            f"*{tan_text(arg_dir_fw)}",
        )
        add_summary(
            t("report.psb.forward_reverse_intersection"),
            "1.3 X1InFw = max(Kч*(RFPPRv/2)*tg(ArgDirFw); Kч*RFPERv*tg(ArgDirFw))",
            x1_fw_13,
            ("Kч*(RFPPRv/2)*tg(ArgDirFw)", result.x1_in_fw_reverse_intersection_phase),
            ("Kч*RFPERv*tg(ArgDirFw)", result.x1_in_fw_reverse_intersection_ground),
        )
        add_condition(
            t("report.psb.forward_reverse_intersection"),
            "1.3 R1FInFw: Kч*X1Rv*tg(ArgNegResFw-90)",
            result.r1f_in_fw_reverse_intersection_phase,
            t("report.psb.forward_reverse_intersection_comment"),
            "1.3 R1FInFw = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.reverse, 'x1')}"
            f"*{tan_text((arg_neg_res_fw or 0.0) - 90.0 if arg_neg_res_fw is not None else None)}",
        )
        add_condition(
            t("report.psb.forward_reverse_intersection"),
            "1.3 R1FInFw: Kч*(X1Rv+(X0Rv-X1Rv)/3)*tg(ArgNegResFw-90)",
            result.r1f_in_fw_reverse_intersection_ground,
            t("report.psb.forward_reverse_intersection_comment"),
            "1.3 R1FInFw = "
            f"{value_text(result.sensitivity_factor)}*("
            f"{extreme_text(result.reverse, 'x1')}+"
            f"({extreme_text(result.reverse, 'x0')}-{extreme_text(result.reverse, 'x1')})/3)"
            f"*{tan_text((arg_neg_res_fw or 0.0) - 90.0 if arg_neg_res_fw is not None else None)}",
        )
        add_summary(
            t("report.psb.forward_reverse_intersection"),
            "1.3 R1FInFw = max(Kч*X1Rv*tg(ArgNegResFw-90); "
            "Kч*(X1Rv+(X0Rv-X1Rv)/3)*tg(ArgNegResFw-90))",
            r1f_fw_13,
            ("Kч*X1Rv*tg(ArgNegResFw-90)", result.r1f_in_fw_reverse_intersection_phase),
            (
                "Kч*(X1Rv+(X0Rv-X1Rv)/3)*tg(ArgNegResFw-90)",
                result.r1f_in_fw_reverse_intersection_ground,
            ),
        )
        add_summary(
            t("report.psb.forward_result"),
            "X1InFw = max(1.1 X1InFw; 1.3 X1InFw)",
            result.x1_in_fw,
            ("1.1 X1InFw", x1_fw_11),
            ("1.3 X1InFw", x1_fw_13),
        )
        add_summary(
            t("report.psb.forward_result"),
            "R1FInFw = max(1.1 R1FInFw; 1.3 R1FInFw)",
            result.r1f_in_fw,
            ("1.1 R1FInFw", r1f_fw_11),
            ("1.3 R1FInFw", r1f_fw_13),
        )
        add_condition(
            t("report.psb.reverse_coverage"),
            "2.1 X1InRv: Kч*X1Rv",
            result.x1_in_rv_coverage_phase,
            t("report.psb.reverse_coverage_comment"),
            "2.1 X1InRv = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.reverse, 'x1')}",
        )
        add_condition(
            t("report.psb.reverse_coverage"),
            "2.1 X1InRv: Kч*(X1Rv+(X0Rv-X1Rv)/3)",
            result.x1_in_rv_coverage_ground,
            t("report.psb.reverse_coverage_comment"),
            "2.1 X1InRv = "
            f"{value_text(result.sensitivity_factor)}*("
            f"{extreme_text(result.reverse, 'x1')}+"
            f"({extreme_text(result.reverse, 'x0')}-{extreme_text(result.reverse, 'x1')})/3)",
        )
        add_summary(
            t("report.psb.reverse_coverage"),
            "2.1 X1InRv = max(Kч*X1Rv; Kч*(X1Rv+(X0Rv-X1Rv)/3))",
            x1_rv_21,
            ("Kч*X1Rv", result.x1_in_rv_coverage_phase),
            ("Kч*(X1Rv+(X0Rv-X1Rv)/3)", result.x1_in_rv_coverage_ground),
        )
        add_condition(
            t("report.psb.reverse_coverage"),
            "2.1 R1FInRv: Kч*(RFPPRv/2)",
            result.r1f_in_rv_coverage_phase,
            t("report.psb.reverse_coverage_comment"),
            "2.1 R1FInRv = "
            f"{value_text(result.sensitivity_factor)}*({extreme_text(result.reverse, 'rfpp')}/2)",
        )
        add_condition(
            t("report.psb.reverse_coverage"),
            "2.1 R1FInRv: Kч*RFPERv",
            result.r1f_in_rv_coverage_ground,
            t("report.psb.reverse_coverage_comment"),
            "2.1 R1FInRv = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.reverse, 'rfpe')}",
        )
        add_summary(
            t("report.psb.reverse_coverage"),
            "2.1 R1FInRv = max(Kч*(RFPPRv/2); Kч*RFPERv)",
            r1f_rv_21,
            ("Kч*(RFPPRv/2)", result.r1f_in_rv_coverage_phase),
            ("Kч*RFPERv", result.r1f_in_rv_coverage_ground),
        )
        add_condition(
            t("report.psb.reverse_forward_intersection"),
            "2.3 X1InRv: Kч*(RFPPFw/2)*tg(ArgDirRv)",
            result.x1_in_rv_forward_intersection_phase,
            t("report.psb.reverse_forward_intersection_comment"),
            "2.3 X1InRv = "
            f"{value_text(result.sensitivity_factor)}*({extreme_text(result.forward, 'rfpp')}/2)"
            f"*{tan_text(arg_dir_rv)}",
        )
        add_condition(
            t("report.psb.reverse_forward_intersection"),
            "2.3 X1InRv: Kч*RFPEFw*tg(ArgDirRv)",
            result.x1_in_rv_forward_intersection_ground,
            t("report.psb.reverse_forward_intersection_comment"),
            "2.3 X1InRv = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.forward, 'rfpe')}"
            f"*{tan_text(arg_dir_rv)}",
        )
        add_summary(
            t("report.psb.reverse_forward_intersection"),
            "2.3 X1InRv = max(Kч*(RFPPFw/2)*tg(ArgDirRv); Kч*RFPEFw*tg(ArgDirRv))",
            x1_rv_23,
            ("Kч*(RFPPFw/2)*tg(ArgDirRv)", result.x1_in_rv_forward_intersection_phase),
            ("Kч*RFPEFw*tg(ArgDirRv)", result.x1_in_rv_forward_intersection_ground),
        )
        add_condition(
            t("report.psb.reverse_forward_intersection"),
            "2.3 R1FInRv: Kч*X1Fw*tg(ArgNegResRv-90)",
            result.r1f_in_rv_forward_intersection_phase,
            t("report.psb.reverse_forward_intersection_comment"),
            "2.3 R1FInRv = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.forward, 'x1')}"
            f"*{tan_text((arg_neg_res_rv or 0.0) - 90.0 if arg_neg_res_rv is not None else None)}",
        )
        add_condition(
            t("report.psb.reverse_forward_intersection"),
            "2.3 R1FInRv: Kч*(X1Fw+(X0Fw-X1Fw)/3)*tg(ArgNegResRv-90)",
            result.r1f_in_rv_forward_intersection_ground,
            t("report.psb.reverse_forward_intersection_comment"),
            "2.3 R1FInRv = "
            f"{value_text(result.sensitivity_factor)}*("
            f"{extreme_text(result.forward, 'x1')}+"
            f"({extreme_text(result.forward, 'x0')}-{extreme_text(result.forward, 'x1')})/3)"
            f"*{tan_text((arg_neg_res_rv or 0.0) - 90.0 if arg_neg_res_rv is not None else None)}",
        )
        add_summary(
            t("report.psb.reverse_forward_intersection"),
            "2.3 R1FInRv = max(Kч*X1Fw*tg(ArgNegResRv-90); "
            "Kч*(X1Fw+(X0Fw-X1Fw)/3)*tg(ArgNegResRv-90))",
            r1f_rv_23,
            ("Kч*X1Fw*tg(ArgNegResRv-90)", result.r1f_in_rv_forward_intersection_phase),
            (
                "Kч*(X1Fw+(X0Fw-X1Fw)/3)*tg(ArgNegResRv-90)",
                result.r1f_in_rv_forward_intersection_ground,
            ),
        )
        add_summary(
            t("report.psb.reverse_result"),
            "X1InRv = max(2.1 X1InRv; 2.3 X1InRv)",
            result.x1_in_rv,
            ("2.1 X1InRv", x1_rv_21),
            ("2.3 X1InRv", x1_rv_23),
        )
        add_summary(
            t("report.psb.reverse_result"),
            "R1FInRv = max(2.1 R1FInRv; 2.3 R1FInRv)",
            result.r1f_in_rv,
            ("2.1 R1FInRv", r1f_rv_21),
            ("2.3 R1FInRv", r1f_rv_23),
        )
        add_condition(
            t("report.psb.load_angle_condition"),
            "R1LInFw = X1InFw/tg(Fл); Fл = min(Fл ступенів)",
            result.r1l_in_fw,
            t("report.psb.load_angle_comment"),
            f"{load_angle_min_text('FлFw', result.load_angle_fw_candidates, result.load_angle_fw_deg)}; "
            f"R1LInFw = {value_text(result.x1_in_fw)}/{tan_text(result.load_angle_fw_deg)}",
        )
        add_condition(
            t("report.psb.load_angle_condition"),
            "R1LInRv = X1InRv/tg(Fл); Fл = min(Fл ступенів)",
            result.r1l_in_rv,
            t("report.psb.load_angle_comment"),
            f"{load_angle_min_text('FлRv', result.load_angle_rv_candidates, result.load_angle_rv_deg)}; "
            f"R1LInRv = {value_text(result.x1_in_rv)}/{tan_text(result.load_angle_rv_deg)}",
        )
        add_summary(
            t("report.psb.load_angle_condition"),
            "R1LIn = max(X1InFw/tg(FлFw); X1InRv/tg(FлRv))",
            result.r1l_in,
            ("R1LInFw", result.r1l_in_fw),
            ("R1LInRv", result.r1l_in_rv),
        )
        load_cut = result.load_cut
        delta_r_primary = load_cut.delta_r_primary if load_cut else None
        delta_r_secondary = load_cut.delta_r_secondary if load_cut else None
        add_condition(
            t("report.psb.load_cut_primary_delta"),
            "∆RFw(Rv)перв = ∆RFw(Rv)втор*(Uтн перв/Uтн вт)/(Iтс перв/Iтс вт)",
            delta_r_primary,
            t("report.psb.load_cut_primary_delta_comment"),
            "∆RFw(Rv)перв = "
            f"{value_text(delta_r_secondary)}*(Uтн перв/Uтн вт)/(Iтс перв/Iтс вт)",
        )
        add_condition(
            t("report.psb.load_cut_detuning"),
            "RLdOutFw = Kвід*Rнав(Fw)",
            result.rld_out_fw_load,
            t("report.psb.load_cut_detuning_comment"),
            "RLdOutFw = "
            f"{value_text(load_cut.rejection_factor if load_cut else None)}*"
            f"{value_text(load_cut.r_load_fw if load_cut else None)}",
        )
        add_condition(
            t("report.psb.load_cut_detuning"),
            "RLdOutRv = Kвід*Rнав(Rv)",
            result.rld_out_rv_load,
            t("report.psb.load_cut_detuning_comment"),
            "RLdOutRv = "
            f"{value_text(load_cut.rejection_factor if load_cut else None)}*"
            f"{value_text(load_cut.r_load_rv if load_cut else None)}",
        )
        add_condition(
            t("report.psb.load_cut_detuning"),
            "RLdInFw = RLdOutFw - ∆RFw(Rv)перв",
            result.rld_in_fw_load,
            t("report.psb.load_cut_detuning_comment"),
            f"RLdInFw = {value_text(result.rld_out_fw_load)}-{value_text(delta_r_primary)}",
        )
        add_condition(
            t("report.psb.load_cut_detuning"),
            "RLdInRv = RLdOutRv - ∆RFw(Rv)перв",
            result.rld_in_rv_load,
            t("report.psb.load_cut_detuning_comment"),
            f"RLdInRv = {value_text(result.rld_out_rv_load)}-{value_text(delta_r_primary)}",
        )
        add_condition(
            t("report.psb.load_cut_sensitivity_compare"),
            "RLdInFw = min(R1FInFw; RLdInFw за відлаштуванням від навантаження)",
            result.rld_in_fw,
            t("report.psb.load_cut_sensitivity_comment"),
            f"RLdInFw = min({value_text(result.r1f_in_fw)}; {value_text(result.rld_in_fw_load)})",
        )
        add_condition(
            t("report.psb.load_cut_sensitivity_compare"),
            "RLdInRv = min(R1FInRv; RLdInRv за відлаштуванням від навантаження)",
            result.rld_in_rv,
            t("report.psb.load_cut_sensitivity_comment"),
            f"RLdInRv = min({value_text(result.r1f_in_rv)}; {value_text(result.rld_in_rv_load)})",
        )
        add_condition(
            t("report.psb.load_cut_sensitivity_compare"),
            "RLdOutFw = RLdInFw + ∆RFw(Rv)перв",
            result.rld_out_fw,
            t("report.psb.load_cut_sensitivity_comment"),
            f"RLdOutFw = {value_text(result.rld_in_fw)}+{value_text(delta_r_primary)}",
        )
        add_condition(
            t("report.psb.load_cut_sensitivity_compare"),
            "RLdOutRv = RLdInRv + ∆RFw(Rv)перв",
            result.rld_out_rv,
            t("report.psb.load_cut_sensitivity_comment"),
            f"RLdOutRv = {value_text(result.rld_in_rv)}+{value_text(delta_r_primary)}",
        )
        add_condition(
            t("report.psb.load_cut_ratio"),
            "KLdFw = RLdInFw/RLdOutFw",
            result.kld_fw,
            t("report.psb.load_cut_ratio_comment"),
            f"KLdFw = {value_text(result.rld_in_fw)}/{value_text(result.rld_out_fw)}",
        )
        add_condition(
            t("report.psb.load_cut_ratio"),
            "KLdRv = RLdInRv/RLdOutRv",
            result.kld_rv,
            t("report.psb.load_cut_ratio_comment"),
            f"KLdRv = {value_text(result.rld_in_rv)}/{value_text(result.rld_out_rv)}",
        )
        add_condition(
            t("report.psb.load_cut_angle"),
            "ArgLd = max(max(abs(atan(Xнав/Rнав))) + ∆φ; 30)",
            result.arg_ld_deg,
            t("report.psb.load_cut_angle_comment"),
            "ArgLd = max(max("
            f"{value_text(result.arg_ld_fw_base_deg)}; "
            f"{value_text(result.arg_ld_rv_base_deg)}) + "
            f"{value_text(load_cut.delta_phi_deg if load_cut else None)}; 30)",
        )
        section = [
            f"<h2>{self._html(t('report.psb.title'))}</h2>",
            "<p><b>"
            + self._html(t("report.psb.included_forward"))
            + ":</b> "
            + self._html(self._stage_name_list(result.included_forward_stage_names))
            + "<br><b>"
            + self._html(t("report.psb.included_reverse"))
            + ":</b> "
            + self._html(self._stage_name_list(result.included_reverse_stage_names))
            + "</p>",
            "<p>"
            + self._html(
                t(
                    "report.psb.extremes",
                    k=self._report_number(result.sensitivity_factor),
                    x1_fw=self._report_optional_extreme(result.forward, "x1"),
                    x0_fw=self._report_optional_extreme(result.forward, "x0"),
                    rfpp_fw=self._report_optional_extreme(result.forward, "rfpp"),
                    rfpe_fw=self._report_optional_extreme(result.forward, "rfpe"),
                    x1_rv=self._report_optional_extreme(result.reverse, "x1"),
                    x0_rv=self._report_optional_extreme(result.reverse, "x0"),
                    rfpp_rv=self._report_optional_extreme(result.reverse, "rfpp"),
                    rfpe_rv=self._report_optional_extreme(result.reverse, "rfpe"),
                    arg_dir_fw=self._report_optional_number(result.arg_dir_fw_deg),
                    arg_neg_res_fw=self._report_optional_number(result.arg_neg_res_fw_deg),
                    arg_dir_rv=self._report_optional_number(result.arg_dir_rv_deg),
                    arg_neg_res_rv=self._report_optional_number(result.arg_neg_res_rv_deg),
                    f_l=self._load_angle_min_report(result),
                )
            )
            + "</p>",
            "<table cellspacing='0' cellpadding='6' "
            "style='border-collapse: collapse; width: 100%; margin-bottom: 18px;'>",
            "<tr>"
            f"<th style='{self._report_cell_style(header=True)}'>{self._html(t('report.psb.step'))}</th>"
            f"<th style='{self._report_cell_style(header=True)}'>{self._html(t('report.formula'))}</th>"
            f"<th style='{self._report_cell_style(header=True)}'>{self._html(t('report.result'))}</th>"
            f"<th style='{self._report_cell_style(header=True)}'>{self._html(t('report.psb.comment'))}</th>"
            "</tr>",
        ]
        previous_step = ""
        for step, formula, value, comment in rows:
            style = self._report_cell_style()
            formula_html = self._html(formula).replace("\n", "<br>")
            step_text = step if step != previous_step else ""
            previous_step = step
            section.append(
                "<tr>"
                f"<td style='{style}'>{self._html(step_text)}</td>"
                f"<td style='{style}'><code>{formula_html}</code></td>"
                f"<td style='{style}'>{self._html(self._report_optional_number(value))}</td>"
                f"<td style='{style}'>{self._html(comment)}</td>"
                "</tr>"
            )
        section.append("</table>")
        return "\n".join(section)

    def _stage_name_list(self, names: tuple[str, ...]) -> str:
        return ", ".join(names) if names else self._translator.text("report.psb.no_stages")

    def _zone_stage_report(
        self,
        stage_name: str,
        is_forward: bool,
        inputs: str,
        helpers: object,
        formulas: dict[str, list[str]],
        points: tuple[tuple[float, float], ...],
    ) -> str:
        t = self._translator.text
        direction = t("source.direction_forward") if is_forward else t("source.direction_reverse")
        return (
            "<h4>"
            + self._html(t("report.stage_header", stage=stage_name))
            + "</h4>"
            + "<p><b>"
            + self._html(t("report.direction_label"))
            + ":</b> "
            + self._html(direction)
            + "</p>"
            + "<p><b>"
            + self._html(t("report.inputs_label"))
            + ":</b> "
            + self._html(inputs)
            + "</p>"
            + "<p><b>"
            + self._html(t("report.helper_res1"))
            + ":</b> "
            + self._html(self._report_number(helpers.res1_deg))
            + "; <b>"
            + self._html(t("report.helper_d32"))
            + ":</b> "
            + self._html(str(helpers.d32))
            + "; <b>"
            + self._html(t("report.helper_b33"))
            + ":</b> "
            + self._html(self._report_number(helpers.b33))
            + "</p>"
            + self._zone_formula_result_table(formulas, points)
        )

    def _phase_phase_inputs_text(self, stage: PhasePhaseStageInput) -> str:
        return self._translator.text(
            "report.inputs_values",
            x1=self._report_number(stage.x1),
            r1=self._report_number(stage.r1),
            rpff=self._report_number(stage.rpff),
            arg_neg_res=self._report_number(stage.arg_neg_res_deg),
            arg_dir=self._report_number(stage.arg_dir_deg),
        )

    def _phase_ground_inputs_text(self, stage: PhaseGroundStageInput) -> str:
        return self._translator.text(
            "report.phase_ground_inputs_values",
            x1=self._report_number(stage.x1),
            r1=self._report_number(stage.r1),
            x0=self._report_number(stage.x0),
            r0=self._report_number(stage.r0),
            rpff=self._report_number(stage.rpff),
            rfpe=self._report_number(stage.rfpe),
            arg_neg_res=self._report_number(stage.arg_neg_res_deg),
            arg_dir=self._report_number(stage.arg_dir_deg),
        )

    def _zone_formula_result_table(
        self,
        formulas: dict[str, list[str]],
        points: tuple[tuple[float, float], ...],
    ) -> str:
        t = self._translator.text
        rows = [
            "<table cellspacing='0' cellpadding='6' "
            "style='border-collapse: collapse; width: 100%; margin-bottom: 18px;'>",
            "<tr>"
            f"<th style='{self._report_cell_style(header=True)}'>"
            f"{self._html(t('report.point'))}</th>"
            f"<th style='{self._report_cell_style(header=True)}'>"
            f"{self._html(t('report.formula_x'))}</th>"
            f"<th style='{self._report_cell_style(header=True)}'>"
            "x</th>"
            f"<th style='{self._report_cell_style(header=True)}'>"
            f"{self._html(t('report.formula_y'))}</th>"
            f"<th style='{self._report_cell_style(header=True)}'>"
            "y</th>"
            "</tr>",
        ]
        point_names = formulas["points"]
        for (x_value, y_value), x_formula, y_formula, point_name in zip(
            points,
            formulas["x"],
            formulas["y"],
            point_names,
            strict=False,
        ):
            rows.append(
                "<tr>"
                f"<td style='{self._report_cell_style()}'>{self._html(point_name)}</td>"
                f"<td style='{self._report_cell_style()}'>{self._html(x_formula)}</td>"
                f"<td style='{self._report_cell_style()}'>{self._html(self._report_number(x_value))}</td>"
                f"<td style='{self._report_cell_style()}'>{self._html(y_formula)}</td>"
                f"<td style='{self._report_cell_style()}'>{self._html(self._report_number(y_value))}</td>"
                "</tr>"
            )
        rows.append("</table>")
        return "\n".join(rows)

    def _report_table_row(self, coordinate: str, formula: str, result: str) -> str:
        style = self._report_cell_style()
        return (
            "<tr>"
            f"<td style='{style}'>{self._html(coordinate)}</td>"
            f"<td style='{style}'><code>{self._html(formula)}</code></td>"
            f"<td style='{style}'>{self._html(result)}</td>"
            "</tr>"
        )

    def _report_cell_style(self, header: bool = False) -> str:
        background = "#e9eef5" if header else "#ffffff"
        weight = "font-weight: 700;" if header else ""
        return f"border: 1px solid #cbd5e1; background: {background}; {weight}"

    def _html(self, text: str) -> str:
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _phase_phase_formula_lines(self, is_forward: bool) -> dict[str, list[str]]:
        formulas = {
            "points": ["O", "A'", "A", "B", "C", "C'", "D", "D'", "E"],
            "x": [
                "0",
                "RPFF/2",
                "RPFF/2",
                "R1+RPFF/2",
                "0",
                "IF RES1>ArgNegRes THEN -tg((ArgNegRes-90)*pi/180)*X1 ELSE -RPFF/2",
                "IF RES1>ArgNegRes THEN 0 ELSE -RPFF/2",
                "IF RES1>ArgNegRes THEN 0 ELSE B33",
                "0",
            ],
            "y": [
                "0",
                "-RPFF/2*tg(ArgDir*pi/180)",
                "0",
                "X1",
                "X1",
                "X1",
                "IF RES1>ArgNegRes THEN 0 ELSE X1",
                "IF RES1>ArgNegRes THEN 0 ELSE (1/tg((ArgNegRes-90)*pi/180))*(RPFF/2)",
                "0",
            ],
        }
        if is_forward:
            return formulas
        formulas["x"] = [self._mirrored_formula(formula) for formula in formulas["x"]]
        formulas["y"] = [self._mirrored_formula(formula) for formula in formulas["y"]]
        return formulas

    def _phase_ground_formula_lines(self, is_forward: bool) -> dict[str, list[str]]:
        formulas = {
            "points": ["O", "A'", "A", "B", "C", "C'", "D", "D'", "E"],
            "x": [
                "0",
                "RFPE",
                "RFPE",
                "(2*R1+R0)/3+RFPE",
                "0",
                "IF RES1>ArgNegRes THEN -tg((ArgNegRes-90)*pi/180)*X1 ELSE 0",
                "IF RES1>ArgNegRes THEN 0 ELSE -RFPE",
                "IF RES1>ArgNegRes THEN 0 ELSE B33",
                "0",
            ],
            "y": [
                "0",
                "-RFPE*tg(ArgDir*pi/180)",
                "0",
                "(2*X1+X0)/3",
                "(2*X1+X0)/3",
                "(2*X1+X0)/3",
                "IF RES1>ArgNegRes THEN 0 ELSE (2*X1+X0)/3",
                "IF RES1>ArgNegRes THEN 0 ELSE (1/tg((ArgNegRes-90)*pi/180))*RFPE",
                "0",
            ],
        }
        if is_forward:
            return formulas
        formulas["x"] = [self._mirrored_formula(formula) for formula in formulas["x"]]
        formulas["y"] = [self._mirrored_formula(formula) for formula in formulas["y"]]
        return formulas

    def _mirrored_formula(self, formula: str) -> str:
        return "0" if formula == "0" else f"-({formula})"

    def _report_number(self, value: float) -> str:
        rounded = f"{value:.2f}".rstrip("0").rstrip(".")
        return rounded.replace(".", ",")

    def _report_optional_number(self, value: float | None) -> str:
        return self._report_number(value) if value is not None else "-"

    def _max_report_value(self, *values: float | None) -> float | None:
        complete_values = [value for value in values if value is not None]
        return max(complete_values) if complete_values else None

    def _rounded_report_value(self, value: float | None) -> float | None:
        if value is None:
            return None
        return float(ceil(value))

    def _report_optional_extreme(self, container: object | None, field_name: str) -> str:
        if container is None:
            return "-"
        value = getattr(container, field_name, None)
        return self._report_optional_number(value)

    def _load_angle_min_report(self, result: PsbBlockingResult) -> str:
        fw = self._named_min_report("FлFw", result.load_angle_fw_candidates, result.load_angle_fw_deg)
        rv = self._named_min_report("FлRv", result.load_angle_rv_candidates, result.load_angle_rv_deg)
        return f"{fw}; {rv}"

    def _named_min_report(
        self,
        label: str,
        candidates: tuple[tuple[str, float], ...],
        selected: float | None,
    ) -> str:
        if not candidates:
            return f"{label}=-"
        values = "; ".join(
            f"{name}={self._report_number(value)}" for name, value in candidates
        )
        return f"{label}=min({values})={self._report_optional_number(selected)}"

    def _save_project(self) -> None:
        if self._last_result is None:
            self._calculate()
        with self._session_factory() as session:
            repository = ProjectRepository(session)
            self._current_project_id = repository.save(
                self._project_data(),
                results={"calculation": self._last_result},
                project_id=self._current_project_id,
            )
        self.statusBar().showMessage(self._translator.text("message.saved"), 5000)

    def _new_project(self) -> None:
        self._last_result = None
        self._current_project_id = None
        self.project_name.clear()
        self.author.clear()
        self.source_data_widget.reset()
        self.results_text.clear()
        self.report_text.clear()

    def _open_latest_project(self) -> None:
        dialog = ProjectManagerDialog(
            self._translator,
            self._session_factory,
            self._project_data(),
            self,
        )
        if not dialog.exec() or dialog.selected_project_id is None:
            return
        with self._session_factory() as session:
            repository = ProjectRepository(session)
            project = repository.load(dialog.selected_project_id)
        self._current_project_id = dialog.selected_project_id
        self._apply_project(project)
        self.statusBar().showMessage(self._translator.text("message.loaded"), 5000)

    def _apply_project(self, project: ProjectData) -> None:
        self._translator.set_language(project.metadata.language)
        self.project_name.setText(project.metadata.name)
        self.author.setText(project.metadata.author)
        self._retranslate()
        self.source_data_widget.from_dict(project.source_data)
        self._update_psd_phase_ground_tab()
        self._calculate()

    def _export_rx_diagram(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._translator.text("dialog.export_title"),
            str(Path.cwd() / "rx_diagram.svg"),
            SUPPORTED_EXPORT_FILTER,
        )
        if path:
            export_figure(self.rx_panel.figure, Path(path))

    def _export_graph_panel(self, panel: MatplotlibPanel, default_name: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._translator.text("dialog.export_title"),
            str(Path.cwd() / f"{default_name}.png"),
            SUPPORTED_EXPORT_FILTER,
        )
        if path:
            export_figure(panel.figure, Path(path))
            self.statusBar().showMessage(self._translator.text("message.exported"), 5000)

    def _export_psd_settings_docx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._translator.text("dialog.export_word_title"),
            str(Path.cwd() / "psd_settings.docx"),
            self._translator.text("dialog.word_filter"),
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".docx":
            target = target.with_suffix(".docx")
        export_html_to_docx(self._psd_settings_export_html(), target)
        self.statusBar().showMessage(self._translator.text("message.exported"), 5000)

    def _psd_settings_export_html(self) -> str:
        rows = []
        for row in range(self.psd_reach_table.rowCount()):
            rows.append(
                [
                    self.psd_reach_table.item(row, column).text()
                    if self.psd_reach_table.item(row, column) is not None
                    else ""
                    for column in range(self.psd_reach_table.columnCount())
                ]
            )
        return (
            f"<h2>{self._html(self._translator.text('psd.settings'))}</h2>"
            + self._simple_table(
                [
                    self._translator.text("table.name"),
                    self._translator.text("report.psd_setting_value"),
                    self._translator.text("psd.unit").capitalize(),
                ],
                rows,
            )
        )

    def _export_psd_report_docx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._translator.text("dialog.export_word_title"),
            str(Path.cwd() / "psd_report.docx"),
            self._translator.text("dialog.word_filter"),
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".docx":
            target = target.with_suffix(".docx")
        export_html_to_docx(self._build_psd_engineering_report(), target)
        self.statusBar().showMessage(self._translator.text("message.exported"), 5000)

    def _find_psd_report_next(self) -> None:
        self._find_psd_report(backward=False)

    def _find_psd_report_previous(self) -> None:
        self._find_psd_report(backward=True)

    def _find_psd_report(self, *, backward: bool) -> None:
        text = self.psd_report_search.text().strip()
        if not text:
            return
        flags = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
        if self.psd_report_text.find(text, flags):
            return
        self.psd_report_text.moveCursor(
            QTextCursor.MoveOperation.End
            if backward
            else QTextCursor.MoveOperation.Start
        )
        self.psd_report_text.find(text, flags)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            self._translator,
            self,
            show_point_labels=self._show_point_labels,
        )
        if dialog.exec():
            self._translator.set_language(dialog.selected_language)
            self._show_point_labels = dialog.show_point_labels
            self._retranslate()
            self._redraw_psd_charts()

    def _retranslate(self) -> None:
        t = self._translator.text
        self.setWindowTitle(t("app.title"))
        self.file_menu.setTitle(t("menu.file"))
        self.new_action.setText(t("menu.new"))
        self.save_action.setText(t("menu.save"))
        self.open_action.setText(t("menu.open"))
        self.export_action.setText(t("menu.export"))
        self.exit_action.setText(t("menu.exit"))
        self.settings_menu.setTitle(t("menu.settings"))
        self.language_action.setText(t("menu.language"))
        self.tabs.setTabText(0, t("tab.inputs"))
        self.tabs.setTabText(1, t("tab.distance_zones"))
        self.tabs.setTabText(2, t("tab.psd"))
        self.tabs.setTabText(3, t("tab.journal"))
        self.distance_tabs.setTabText(0, t("psd.phase_phase_graph"))
        self._update_distance_phase_ground_tab()
        self.psd_tabs.setTabText(0, t("psd.settings"))
        self.psd_tabs.setTabText(1, t("psd.phase_phase_graph"))
        self.psd_tabs.setTabText(self.psd_tabs.indexOf(self.psd_report_tab), t("psd.report"))
        self.export_psd_report_button.setText(t("button.export_word"))
        self.export_psd_settings_button.setText(t("button.export_word"))
        self.export_psd_phase_phase_graph_button.setText(t("button.export_graph"))
        self.export_psd_phase_ground_graph_button.setText(t("button.export_graph"))
        self.export_distance_phase_phase_graph_button.setText(t("button.export_graph"))
        self.export_distance_phase_ground_graph_button.setText(t("button.export_graph"))
        self.psd_report_search.setPlaceholderText(t("report.search_placeholder"))
        self.psd_report_find_prev_button.setText(t("button.find_previous"))
        self.psd_report_find_next_button.setText(t("button.find_next"))
        self._update_psd_phase_ground_tab()
        self._retranslate_psd_tables()
        self.project_group.setTitle(t("group.project"))
        self.project_name_label.setText(t("label.project_name"))
        self.author_label.setText(t("label.author"))
        self.calculate_button.setText(t("button.calculate"))
        self.source_data_widget.retranslate()
        if self._last_result is not None:
            self._calculate()

    def _retranslate_psd_tables(self) -> None:
        self.psd_reach_table.setHorizontalHeaderLabels(
            [
                self._translator.text("table.name"),
                self._translator.text("report.psd_setting_value"),
                self._translator.text("psd.unit").capitalize(),
            ]
        )

    def _rx_labels(self) -> dict[str, str]:
        t = self._translator.text
        return {
            "title": t("diagram.rx_title"),
            "r_axis": t("diagram.r_axis"),
            "x_axis": t("diagram.x_axis"),
            "psb_outer": t("diagram.psb_outer"),
            "psb_inner": t("diagram.psb_inner"),
            "trajectory": t("diagram.trajectory"),
        }

    def _psd_phase_phase_labels(self) -> dict[str, str]:
        labels = self._rx_labels()
        labels["title"] = self._translator.text("psd.phase_phase_graph")
        return labels

    def _psd_phase_ground_labels(self) -> dict[str, str]:
        labels = self._rx_labels()
        labels["title"] = self._translator.text("psd.phase_ground_graph")
        return labels

    def _phase_phase_distance_labels(self) -> dict[str, str]:
        labels = self._rx_labels()
        labels["title"] = self._translator.text("distance.phase_phase_graph")
        return labels

    def _phase_ground_distance_labels(self) -> dict[str, str]:
        labels = self._rx_labels()
        labels["title"] = self._translator.text("distance.phase_ground_graph")
        return labels
