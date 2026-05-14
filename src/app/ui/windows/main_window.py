# ruff: noqa: E501

from __future__ import annotations

import sys
from base64 import b64encode
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from itertools import pairwise
from math import atan, ceil, cos, pi, sin, sqrt, tan
from pathlib import Path
from shutil import copy2
from typing import Any, cast

from matplotlib.lines import Line2D
from matplotlib.patches import Polygon
from PySide6.QtCore import QEvent, QObject, QStandardPaths, Qt
from PySide6.QtGui import QFontMetrics, QIcon, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.database.project_repository import ProjectRepository
from app.database.session import create_session_factory, create_sqlite_engine, initialize_database
from app.diagrams.export import SUPPORTED_EXPORT_FILTER, export_figure
from app.diagrams.rx_diagram import configure_rx_axes
from app.localization.translator import Translator
from app.models.project import ProjectData, ProjectMetadata
from app.services.calculation_service import CalculationResult, CalculationService
from app.services.calculations.phase_ground_zones import (
    PhaseGroundStageHelpers,
    PhaseGroundStageInput,
    phase_ground_stage_helpers,
    phase_ground_zone_polygons,
)
from app.services.calculations.phase_phase_zones import (
    PhasePhaseStageHelpers,
    PhasePhaseStageInput,
    phase_phase_stage_helpers,
    phase_phase_zone_polygons,
)
from app.services.calculations.phs_selector_settings import (
    PhsSelectorResult,
    PhsStageInput,
    phs_selector_settings,
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
StageValue = float | int | bool | str | None
StageMapping = Mapping[str, StageValue]


@dataclass(frozen=True)
class DistanceDragTarget:
    graph_kind: str
    zone_name: str
    column: int
    row_name: str
    x_value: float
    y_min: float
    y_max: float
    segments: tuple[tuple[tuple[float, float], tuple[float, float]], ...]
    line: object
    zone_line: object


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
        self._distance_phase_phase_press_cid: int | None = None
        self._distance_phase_phase_release_cid: int | None = None
        self._distance_phase_phase_zone_visibility: dict[str, bool] = {}
        self._distance_phase_phase_point_targets: list[tuple[str, float, float]] = []
        self._distance_phase_phase_drag_targets: list[DistanceDragTarget] = []
        self._distance_phase_ground_pick_cid: int | None = None
        self._distance_phase_ground_motion_cid: int | None = None
        self._distance_phase_ground_press_cid: int | None = None
        self._distance_phase_ground_release_cid: int | None = None
        self._distance_phase_ground_zone_visibility: dict[str, bool] = {}
        self._distance_phase_ground_point_targets: list[tuple[str, float, float]] = []
        self._distance_phase_ground_drag_targets: list[DistanceDragTarget] = []
        self._distance_drag_overrides: dict[tuple[str, int], float] = {}
        self._distance_drag_original_values: dict[tuple[str, int], float] = {}
        self._distance_drag_active: DistanceDragTarget | None = None
        self._distance_drag_hover: DistanceDragTarget | None = None
        self._distance_drag_limits: tuple[tuple[float, float], tuple[float, float]] | None = None
        self._distance_drag_pending = False
        self._phs_zone_visibility: dict[str, bool] = {}
        self._phs_pick_cids: dict[int, int] = {}
        self._last_psb_blocking_result: PsbBlockingResult | None = None
        self._last_phs_result: PhsSelectorResult | None = None
        self._show_point_labels = False
        self._show_legends = True
        self._show_zone_names = True
        self._show_point_tooltips = True
        self._show_journal_tab = True
        self._zone_colors = self._default_zone_colors()
        self._results_locked = False
        self._dirty = False
        self._suppress_dirty = False
        self._locked_input_warning_open = False
        self._psd_calculated = False
        self._phs_calculated = False
        self._input_tab_index = 0
        self._distance_tab_index = 1
        self._psd_tab_index = 2
        self._phs_tab_index = 3
        self._journal_tab_index = 4

        database_path = self._database_path()
        engine = create_sqlite_engine(database_path)
        initialize_database(engine)
        self._session_factory = create_session_factory(engine)

        self._build_actions()
        self._build_ui()
        self._load_example_data()
        self._connect_dirty_tracking()
        self._install_locked_input_warning_filter()
        self._dirty = False
        self._retranslate()
        self._apply_pointer_cursors()
        self._update_result_tab_state()

    def _default_data_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent / "data"
        return Path(__file__).resolve().parents[4] / "data"

    def _database_path(self) -> Path:
        current_dir = self._default_data_dir()
        current_dir.mkdir(parents=True, exist_ok=True)
        current_path = current_dir / "rel_psd.sqlite"
        if not self._database_has_content(current_path):
            for legacy_path in self._legacy_database_paths(current_dir):
                if not legacy_path.exists() or not self._database_has_content(legacy_path):
                    continue
                copy2(legacy_path, current_path)
                try:
                    legacy_path.unlink()
                except OSError:
                    pass
                break
        return current_path

    def _legacy_database_paths(self, current_dir: Path) -> tuple[Path, ...]:
        legacy_paths: list[Path] = []
        app_data_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if app_data_path:
            app_data_dir = Path(app_data_path)
            legacy_paths.append(app_data_dir / "rel_psd.sqlite")
            legacy_paths.append(app_data_dir.parent / "REL-PSD" / "rel_psd.sqlite")
        old_app_data_dir = Path.home() / "Library" / "Application Support" / "REL-PSD"
        legacy_paths.append(old_app_data_dir / "rel_psd.sqlite")
        legacy_paths.append(old_app_data_dir.parent / "REL-PSD" / "rel_psd.sqlite")
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            legacy_paths.append(exe_dir / "rel_psd.sqlite")
            legacy_paths.append(exe_dir / ".rel_psd" / "rel_psd.sqlite")
        legacy_paths.append(current_dir.parent / "REL-PSD" / "rel_psd.sqlite")
        return tuple(dict.fromkeys(legacy_paths))

    def _database_has_content(self, path: Path) -> bool:
        return path.exists() and path.stat().st_size > 8192

    def _build_actions(self) -> None:
        self.file_menu = self.menuBar().addMenu("")
        self.new_action = self.file_menu.addAction("")
        self.save_action = self.file_menu.addAction("")
        self.save_as_action = self.file_menu.addAction("")
        self.open_action = self.file_menu.addAction("")
        self.file_menu.addSeparator()
        self.exit_action = self.file_menu.addAction("")

        self.settings_action = self.menuBar().addAction("")
        self.help_action = self.menuBar().addAction("")

        self.save_action.triggered.connect(self._save_project)
        self.save_as_action.triggered.connect(self._save_project_as)
        self.new_action.triggered.connect(self._new_project)
        self.open_action.triggered.connect(self._open_latest_project)
        self.exit_action.triggered.connect(self.close)
        self.settings_action.triggered.connect(self._open_settings)
        self.help_action.triggered.connect(self._open_help)

    def _build_ui(self) -> None:
        icon_path = self._resource_path("resources/app_icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.project_name = QLineEdit()
        self.author = QLineEdit()
        self.source_data_widget = SourceDataWidget(self._translator)

        self.calculate_button = QToolButton()
        self.calculate_button.setObjectName("calculateButton")
        self.calculate_button.setPopupMode(QToolButton.ToolButtonPopupMode.DelayedPopup)
        self.calculate_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.calculate_button.clicked.connect(self._calculate_all)
        self.clear_results_button = QPushButton()
        self.clear_results_button.setObjectName("dangerActionButton")
        self.clear_results_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.clear_results_button.setEnabled(False)
        self.clear_results_button.clicked.connect(self._confirm_clear_results)
        self.validation_message = QLabel()
        self.validation_message.setObjectName("validationMessage")
        self.validation_message.setWordWrap(True)
        self.validation_message.hide()
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
        self.phs_report_search = QLineEdit()
        self.phs_report_search.returnPressed.connect(self._find_phs_report_next)
        self.phs_report_find_next_button = QPushButton()
        self.phs_report_find_next_button.clicked.connect(self._find_phs_report_next)
        self.phs_report_find_prev_button = QPushButton()
        self.phs_report_find_prev_button.clicked.connect(self._find_phs_report_previous)
        self.export_psd_report_button = QPushButton()
        self.export_psd_report_button.clicked.connect(self._export_psd_report_docx)
        self.psd_report_zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.psd_report_zoom_slider.setRange(80, 160)
        self.psd_report_zoom_slider.setValue(100)
        self.psd_report_zoom_slider.setFixedWidth(120)
        self.psd_report_zoom_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.psd_report_zoom_slider.setTickInterval(20)
        self.psd_report_zoom_slider.valueChanged.connect(
            lambda value: self._set_report_zoom(self.psd_report_text, value)
        )
        self.export_psd_settings_button = QPushButton()
        self.export_psd_settings_button.clicked.connect(self._export_psd_settings_docx)
        self.export_phs_settings_button = QPushButton()
        self.export_phs_settings_button.clicked.connect(self._export_phs_settings_docx)
        self.export_phs_report_button = QPushButton()
        self.export_phs_report_button.clicked.connect(self._export_phs_report_docx)
        self.phs_report_zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.phs_report_zoom_slider.setRange(80, 160)
        self.phs_report_zoom_slider.setValue(100)
        self.phs_report_zoom_slider.setFixedWidth(120)
        self.phs_report_zoom_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.phs_report_zoom_slider.setTickInterval(20)
        self.phs_report_zoom_slider.valueChanged.connect(
            lambda value: self._set_report_zoom(self.phs_report_tab, value)
        )
        self.journal_zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.journal_zoom_slider.setRange(80, 160)
        self.journal_zoom_slider.setValue(100)
        self.journal_zoom_slider.setFixedWidth(120)
        self.journal_zoom_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.journal_zoom_slider.setTickInterval(20)
        self.journal_zoom_slider.valueChanged.connect(
            lambda value: self._set_report_zoom(self.report_text, value)
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
        self.tabs.addTab(self._build_phs_tab(), "")
        self.tabs.addTab(self._build_journal_tab(), "")
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("")
        self.tabs.currentChanged.connect(self._guard_result_tabs)

    def _resource_path(self, relative_path: str) -> Path:
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            return Path(frozen_root) / relative_path
        return Path(__file__).resolve().parents[4] / relative_path

    def _route_panel_coordinates_to_status(self, panel: MatplotlibPanel) -> None:
        if getattr(panel, "_rel_status_coordinates", False):
            return

        def show_message(message: str) -> None:
            if message:
                self.statusBar().showMessage(message)
            else:
                self.statusBar().clearMessage()

        panel.toolbar.set_message = show_message  # type: ignore[method-assign]
        panel._rel_status_coordinates = True  # type: ignore[attr-defined]

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
        right_layout.addWidget(self.validation_message)
        right_layout.addSpacing(30)
        right_layout.addWidget(self.calculate_button)
        right_layout.addWidget(self.clear_results_button)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([760, 420])
        root.addWidget(splitter)
        return page

    def _sync_calculate_menu_width(self) -> None:
        return

    def _guard_result_tabs(self, index: int) -> None:
        if not self.tabs.isTabVisible(index):
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(self._input_tab_index)
            self.tabs.blockSignals(False)
            return
        if (
            self._last_result is None
            and index not in {self._input_tab_index, self._journal_tab_index}
        ):
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(self._input_tab_index)
            self.tabs.blockSignals(False)
            self.statusBar().showMessage(self._translator.text("message.calculate_first"), 5000)
            return
        if index == self._distance_tab_index:
            self._update_distance_phase_ground_tab()
            stack_obj = getattr(self.distance_tabs, "_rel_psd_stack", None)
            if isinstance(stack_obj, QStackedWidget):
                stack = cast(QStackedWidget, stack_obj)
                current = stack.currentWidget()
                if current is self.distance_phase_ground_tab:
                    self._plot_distance_phase_ground_zones()
                else:
                    self._plot_distance_phase_phase_zones()

    def _apply_pointer_cursors(self) -> None:
        interactive_widgets = [
            *self.findChildren(QAbstractButton),
            *self.findChildren(QComboBox),
        ]
        for widget in interactive_widgets:
            widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tabs.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)
        self.menuBar().setCursor(Qt.CursorShape.PointingHandCursor)

    def _project_group(self) -> QGroupBox:
        self.project_group = QGroupBox()
        form = QFormLayout(self.project_group)
        self.project_name_label = QLabel()
        self.author_label = QLabel()
        form.addRow(self.project_name_label, self.project_name)
        form.addRow(self.author_label, self.author)
        return self.project_group

    def _build_psd_tab(self) -> QWidget:
        self.psd_settings_tab = self._build_psd_settings_tab()
        self.psd_phase_phase_tab = self._build_psd_phase_phase_tab()
        self.psd_phase_ground_tab = self._build_psd_phase_ground_tab()
        self.psd_report_tab = self._build_psd_report_tab()
        self.psd_tabs = self._segmented_module(
            "PSD",
            [
                ("psd.settings", self.psd_settings_tab),
                ("psd.phase_phase_graph", self.psd_phase_phase_tab),
                ("psd.phase_ground_graph", self.psd_phase_ground_tab),
                ("psd.report", self.psd_report_tab),
            ],
            self._on_psd_tab_changed,
        )
        self._update_psd_phase_ground_tab()
        return self.psd_tabs

    def _build_phs_tab(self) -> QWidget:
        self.phs_settings_tab = self._phs_settings_table()
        self.phs_phase_phase_2ph_panel = MatplotlibPanel()
        self.phs_phase_phase_3ph_panel = MatplotlibPanel()
        self.phs_phase_ground_panel = MatplotlibPanel()
        self.phs_load_cut_panel = MatplotlibPanel()
        self.phs_report_tab = QTextEdit()
        self.phs_report_tab.setReadOnly(True)
        self.phs_report_tab.setPlainText("PHS: розрахунок буде додано на наступному етапі.")
        self.phs_tabs = self._segmented_module(
            "PHS",
            [
                ("psd.settings", self._build_phs_settings_tab()),
                ("phs.phase_phase_2ph", self._build_phs_graph_tab(self.phs_phase_phase_2ph_panel)),
                ("phs.phase_phase_3ph", self._build_phs_graph_tab(self.phs_phase_phase_3ph_panel)),
                ("phs.phase_ground", self._build_phs_graph_tab(self.phs_phase_ground_panel)),
                ("phs.load_cut", self._build_phs_graph_tab(self.phs_load_cut_panel)),
                ("psd.report", self._build_phs_report_tab()),
            ],
            None,
        )
        return self.phs_tabs

    def _build_phs_settings_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.phs_settings_tab)
        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addWidget(self.export_phs_settings_button)
        footer.addStretch()
        layout.addLayout(footer)
        return page

    def _build_phs_graph_tab(self, panel: MatplotlibPanel) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._route_panel_coordinates_to_status(panel)
        layout.addWidget(panel)
        return page

    def _build_phs_report_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(self.phs_report_search)
        toolbar.addWidget(self.phs_report_find_prev_button)
        toolbar.addWidget(self.phs_report_find_next_button)
        toolbar.addStretch()
        toolbar.addWidget(self.export_phs_report_button)
        layout.addLayout(toolbar)
        layout.addWidget(self.phs_report_tab)
        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addStretch()
        footer.addSpacing(20)
        footer.addWidget(QLabel(self._translator.text("report.zoom")))
        footer.addWidget(self.phs_report_zoom_slider)
        layout.addLayout(footer)
        return page

    def _phs_settings_table(self) -> QTableWidget:
        table = QTableWidget()
        rows = [
            ("INBlockPP", self._translator.text("unit.ampere")),
            ("INBlockPE", self._translator.text("unit.ampere")),
            ("RLd Fw", self._translator.text("unit.ohm")),
            ("RLd Rv", self._translator.text("unit.ohm")),
            ("ArgLd", self._translator.text("unit.degree")),
            ("X1", self._translator.text("unit.ohm")),
            ("X0", self._translator.text("unit.ohm")),
            ("RFFwPP", self._translator.text("unit.ohm")),
            ("RFRvPP", self._translator.text("unit.ohm")),
            ("RFFw PE", self._translator.text("unit.ohm")),
            ("RFRv PE", self._translator.text("unit.ohm")),
        ]
        table.setRowCount(len(rows))
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(
            [
                self._translator.text("table.name"),
                self._translator.text("report.psd_setting_value"),
                self._translator.text("psd.unit").capitalize(),
            ]
        )
        table.verticalHeader().setVisible(False)
        for row, (name, unit) in enumerate(rows):
            table.setItem(row, 0, self._table_item(name))
            table.setItem(row, 1, self._table_item(""))
            table.setItem(row, 2, self._table_item(unit))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    def _build_psd_report_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        controls.setSpacing(10)
        controls.addWidget(self.psd_report_search)
        controls.addWidget(self.psd_report_find_prev_button)
        controls.addWidget(self.psd_report_find_next_button)
        controls.addStretch()
        controls.addWidget(self.export_psd_report_button)
        layout.addLayout(controls)
        layout.addWidget(self.psd_report_text)
        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addStretch()
        footer.addSpacing(20)
        footer.addWidget(QLabel(self._translator.text("report.zoom")))
        footer.addWidget(self.psd_report_zoom_slider)
        layout.addLayout(footer)
        return page

    def _build_journal_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.report_text)
        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addStretch()
        footer.addSpacing(20)
        footer.addWidget(QLabel(self._translator.text("report.zoom")))
        footer.addWidget(self.journal_zoom_slider)
        layout.addLayout(footer)
        return page

    def _build_distance_zones_tab(self) -> QWidget:
        self.distance_phase_phase_tab = self._build_distance_phase_phase_tab()
        self.distance_phase_ground_tab = self._build_distance_phase_ground_tab()
        self.distance_tabs = self._segmented_module(
            "Дистанційні зони",
            [
                ("distance.phase_phase_graph", self.distance_phase_phase_tab),
                ("distance.phase_ground_graph", self.distance_phase_ground_tab),
            ],
            self._on_distance_tab_changed,
        )
        self._update_distance_phase_ground_tab()
        return self.distance_tabs

    def _segmented_module(
        self,
        title: str,
        pages: list[tuple[str, QWidget]],
        callback: object | None,
    ) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        segmented = QWidget()
        segmented.setObjectName("segmentedControl")
        segmented_layout = QHBoxLayout(segmented)
        segmented_layout.setContentsMargins(0, 0, 0, 10)
        segmented_layout.setSpacing(10)
        stack = QStackedWidget()
        buttons: list[QPushButton] = []
        for index, (key, widget) in enumerate(pages):
            button = QPushButton()
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setProperty("translation_key", key)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda checked=False, i=index: self._select_segment(stack, i, callback))
            segmented_layout.addWidget(button)
            stack.addWidget(widget)
            buttons.append(button)
        if buttons:
            buttons[0].setChecked(True)
        segmented_layout.addStretch()
        layout.addWidget(segmented)
        layout.addWidget(stack)
        page._rel_psd_buttons = buttons  # type: ignore[attr-defined]
        page._rel_psd_stack = stack  # type: ignore[attr-defined]
        return page

    def _select_segment(self, stack: QStackedWidget, index: int, callback: object | None) -> None:
        stack.setCurrentIndex(index)
        if callback is not None:
            callback(index)  # type: ignore[operator]

    def _fit_segment_button_width(self, button: QPushButton) -> None:
        bold_font = button.font()
        bold_font.setBold(True)
        text_width = QFontMetrics(bold_font).horizontalAdvance(button.text())
        width = text_width + 22
        button.setMinimumWidth(width)
        button.setMaximumWidth(width)

    def _build_distance_phase_phase_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._route_panel_coordinates_to_status(self.distance_phase_phase_panel)
        self._build_distance_drag_actions("phase_phase")
        layout.addWidget(self.distance_phase_phase_panel)
        return page

    def _build_distance_phase_ground_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._route_panel_coordinates_to_status(self.distance_phase_ground_panel)
        self._build_distance_drag_actions("phase_ground")
        layout.addWidget(self.distance_phase_ground_panel)
        return page

    def _build_distance_drag_actions(self, graph_kind: str) -> None:
        cancel_button = QPushButton()
        apply_button = QPushButton()
        cancel_button.setObjectName("secondaryActionButton")
        apply_button.setObjectName("primaryActionButton")
        cancel_button.setEnabled(False)
        apply_button.setEnabled(False)
        cancel_button.clicked.connect(self._cancel_distance_drag_changes)
        apply_button.clicked.connect(self._apply_distance_drag_changes)
        toolbar = (
            self.distance_phase_phase_panel.toolbar
            if graph_kind == "phase_phase"
            else self.distance_phase_ground_panel.toolbar
        )
        toolbar.addSeparator()
        toolbar.addWidget(cancel_button)
        toolbar.addSeparator()
        toolbar.addWidget(apply_button)
        if graph_kind == "phase_phase":
            self.distance_phase_phase_drag_cancel_button = cancel_button
            self.distance_phase_phase_drag_apply_button = apply_button
        else:
            self.distance_phase_ground_drag_cancel_button = cancel_button
            self.distance_phase_ground_drag_apply_button = apply_button

    def _build_psd_settings_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.psd_reach_table = self._psd_reach_table()
        layout.addWidget(self.psd_reach_table)
        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addWidget(self.export_psd_settings_button)
        footer.addStretch()
        layout.addLayout(footer)
        return page

    def _build_psd_phase_phase_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._route_panel_coordinates_to_status(self.psd_phase_phase_panel)
        layout.addWidget(self.psd_phase_phase_panel)
        return page

    def _build_psd_phase_ground_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._route_panel_coordinates_to_status(self.psd_phase_ground_panel)
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
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

    def _update_psd_phase_ground_tab(self) -> None:
        if not hasattr(self, "psd_tabs"):
            return
        all_faults_selected = self.source_data_widget.protection_type_combo.currentIndex() == 0
        self._set_segment_visible(self.psd_tabs, self.psd_phase_ground_tab, all_faults_selected)

    def _update_distance_phase_ground_tab(self) -> None:
        if not hasattr(self, "distance_tabs"):
            return
        all_faults_selected = self.source_data_widget.protection_type_combo.currentIndex() == 0
        self._set_segment_visible(
            self.distance_tabs,
            self.distance_phase_ground_tab,
            all_faults_selected,
        )

    def _set_segment_visible(self, module: QWidget, widget: QWidget, visible: bool) -> None:
        stack_obj = getattr(module, "_rel_psd_stack", None)
        buttons = getattr(module, "_rel_psd_buttons", [])
        if not isinstance(stack_obj, QStackedWidget):
            return
        stack = cast(QStackedWidget, stack_obj)
        index = stack.indexOf(widget)
        if index < 0 or index >= len(buttons):
            return
        buttons[index].setVisible(visible)
        if not visible and stack.currentIndex() == index:
            for next_index, button in enumerate(buttons):
                if button.isVisible():
                    button.setChecked(True)
                    stack.setCurrentIndex(next_index)
                    if module is self.distance_tabs:
                        self._on_distance_tab_changed(next_index)
                    if module is self.psd_tabs:
                        self._on_psd_tab_changed(next_index)
                    break

    def _on_psd_tab_changed(self, index: int) -> None:
        stack_obj = getattr(self.psd_tabs, "_rel_psd_stack", None)
        if not isinstance(stack_obj, QStackedWidget):
            return
        stack = cast(QStackedWidget, stack_obj)
        current = stack.widget(index)
        if current is self.psd_phase_phase_tab:
            self._plot_psd_phase_phase_zones()
        if current is self.psd_phase_ground_tab:
            self._plot_psd_phase_ground_zones()

    def _on_distance_tab_changed(self, index: int) -> None:
        stack_obj = getattr(self.distance_tabs, "_rel_psd_stack", None)
        if not isinstance(stack_obj, QStackedWidget):
            return
        stack = cast(QStackedWidget, stack_obj)
        current = stack.widget(index)
        if current is self.distance_phase_phase_tab:
            self._plot_distance_phase_phase_zones()
        if current is self.distance_phase_ground_tab:
            self._plot_distance_phase_ground_zones()

    def _load_example_data(self) -> None:
        self.project_name.setText("REL-670-Calculate")
        self.author.setText("")
        self._clear_results(update_lock=False)

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

    def _calculate_all(self) -> None:
        errors = self.source_data_widget.validate_for_calculation("all")
        if errors:
            self.validation_message.setText("\n".join(errors))
            self.validation_message.show()
            self.statusBar().showMessage(self._translator.text("message.validation_failed"), 5000)
            return
        self.validation_message.hide()
        if self._calculate("psd", skip_validation=True):
            self._calculate_phs(skip_validation=True)

    def _calculate_psd(self) -> None:
        self._calculate("psd")

    def _calculate_phs(self, *, skip_validation: bool = False) -> None:
        if not skip_validation:
            errors = self.source_data_widget.validate_for_calculation("phs")
            if errors:
                self.validation_message.setText("\n".join(errors))
                self.validation_message.show()
                self.statusBar().showMessage(
                    self._translator.text("message.validation_failed"),
                    5000,
                )
                return
            self.validation_message.hide()
        if not self._psd_calculated:
            QMessageBox.warning(
                self,
                self._translator.text("phs.title"),
                self._translator.text("message.psd_required_for_phs"),
            )
            return
        use_psd_zone = self._confirm_use_psd_for_phs()
        progress = self._create_progress_dialog(self._translator.text("progress.phs"))
        try:
            self._advance_progress(progress, self._translator.text("progress.phs_stub"), 1)
            self._last_phs_result = self._calculate_phs_selector_settings(
                use_psd_zone=use_psd_zone
            )
            if self._last_phs_result is None:
                progress.close()
                QMessageBox.warning(
                    self,
                    self._translator.text("phs.title"),
                    self._translator.text("message.validation_failed"),
                )
                return
            self._update_phs_settings_table()
            self._plot_phs_graphs()
            self._phs_calculated = True
            self.phs_report_tab.setHtml(self._build_phs_report())
            self.report_text.setHtml(self._build_zone_construction_report())
            self._advance_progress(progress, self._translator.text("progress.done"), 2)
        except Exception as exc:
            progress.close()
            QMessageBox.critical(
                self,
                self._translator.text("phs.title"),
                str(exc),
            )
            return
        progress.close()
        self._update_result_tab_state()
        self.statusBar().showMessage(self._translator.text("message.calculated"), 5000)

    def _confirm_use_psd_for_phs(self) -> bool:
        dialog = QDialog(self)
        dialog.setWindowTitle(self._translator.text("phs.title"))
        dialog.setMinimumSize(980, 720)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        title = QLabel(self._translator.text("message.use_psd_for_phs_title"))
        title.setObjectName("dialogQuestionTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        details = QLabel(self._translator.text("message.use_psd_for_phs_details"))
        details.setObjectName("infoSection")
        details.setWordWrap(True)
        layout.addWidget(details)

        graph_pages = [
            (
                self._translator.text("psd.phase_phase_graph"),
                self._interactive_psd_preview_panel(
                    self.psd_phase_phase_panel,
                    self._psd_phase_phase_labels(),
                ),
            )
        ]
        if self.source_data_widget.protection_type_combo.currentIndex() == 0:
            graph_pages.append(
                (
                    self._translator.text("psd.phase_ground_graph"),
                    self._interactive_psd_preview_panel(
                        self.psd_phase_ground_panel,
                        self._psd_phase_ground_labels(),
                    ),
                )
            )
        layout.addWidget(
            self._dialog_segmented_graphs(graph_pages),
            1,
        )

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch()
        yes_button = QPushButton(self._translator.text("button.yes"))
        no_button = QPushButton(self._translator.text("button.no"))
        yes_button.setCursor(Qt.CursorShape.PointingHandCursor)
        no_button.setCursor(Qt.CursorShape.PointingHandCursor)
        yes_button.clicked.connect(dialog.accept)
        no_button.clicked.connect(dialog.reject)
        buttons.addWidget(yes_button)
        buttons.addWidget(no_button)
        layout.addLayout(buttons)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _dialog_segmented_graphs(self, pages: Sequence[tuple[str, QWidget]]) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        segmented = QWidget()
        segmented.setObjectName("segmentedControl")
        segmented_layout = QHBoxLayout(segmented)
        segmented_layout.setContentsMargins(0, 0, 0, 10)
        segmented_layout.setSpacing(10)
        stack = QStackedWidget()
        for index, (title, widget) in enumerate(pages):
            button = QPushButton(title)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            button.clicked.connect(
                lambda checked=False, selected=index: stack.setCurrentIndex(selected)
            )
            segmented_layout.addWidget(button)
            stack.addWidget(widget)
            if index == 0:
                button.setChecked(True)
        segmented_layout.addStretch()
        layout.addWidget(segmented)
        layout.addWidget(stack, 1)
        return page

    def _interactive_psd_preview_panel(
        self,
        source_panel: MatplotlibPanel,
        labels: dict[str, str],
    ) -> MatplotlibPanel:
        panel = MatplotlibPanel()
        axis = panel.axis
        axis.clear()
        configure_rx_axes(axis, labels)
        line_by_label: dict[str, Line2D] = {}
        for source_line in source_panel.axis.get_lines():
            label = source_line.get_label()
            if not isinstance(label, str) or not label:
                continue
            preview_label = label if not label.startswith("_") else "_nolegend_"
            x_data = [
                self._float_value(value)
                for value in cast(Iterable[object], source_line.get_xdata())
            ]
            y_data = [
                self._float_value(value)
                for value in cast(Iterable[object], source_line.get_ydata())
            ]
            line = axis.plot(
                x_data,
                y_data,
                color=source_line.get_color(),
                linestyle=source_line.get_linestyle(),
                linewidth=source_line.get_linewidth(),
                label=preview_label,
            )[0]
            line.set_visible(source_line.get_visible())
            if preview_label != "_nolegend_":
                line_by_label[label] = line
        self._autoscale_visible(axis)
        legend = axis.legend(loc="upper left") if self._show_legends and line_by_label else None
        if legend is not None:
            for legend_line, text in zip(legend.get_lines(), legend.get_texts(), strict=False):
                label = text.get_text()
                visible = line_by_label[label].get_visible()
                legend_line.set_picker(8)
                text.set_picker(True)
                legend_line.set_alpha(1.0 if visible else 0.25)
                text.set_alpha(1.0 if visible else 0.35)
                legend_line._rel_psd_zone_label = label  # type: ignore[attr-defined]
                text._rel_psd_zone_label = label  # type: ignore[attr-defined]

        def toggle_zone(event) -> None:  # type: ignore[no-untyped-def]
            label = getattr(event.artist, "_rel_psd_zone_label", None)
            if label not in line_by_label:
                return
            line = line_by_label[label]
            line.set_visible(not line.get_visible())
            if legend is not None:
                for legend_line, text in zip(
                    legend.get_lines(),
                    legend.get_texts(),
                    strict=False,
                ):
                    legend_label = text.get_text()
                    visible = line_by_label[legend_label].get_visible()
                    legend_line.set_alpha(1.0 if visible else 0.25)
                    text.set_alpha(1.0 if visible else 0.35)
            self._autoscale_visible(axis)
            panel.redraw()

        panel.canvas.mpl_connect("pick_event", toggle_zone)
        panel.redraw()
        return panel

    def _calculate(self, mode: str = "all", *, skip_validation: bool = False) -> bool:
        if not skip_validation:
            errors = self.source_data_widget.validate_for_calculation(mode)
            if errors:
                self.validation_message.setText("\n".join(errors))
                self.validation_message.show()
                self.statusBar().showMessage(self._translator.text("message.validation_failed"), 5000)
                return False
            self.validation_message.hide()
        progress = self._create_progress_dialog(
            self._translator.text(
                "progress.all" if mode == "all" else "progress.psd"
            )
        )
        self._advance_progress(progress, self._translator.text("progress.read_inputs"), 1)
        project = self._project_data()
        self._advance_progress(progress, self._translator.text("progress.engineering"), 2)
        self._last_result = self._calculation_service.calculate(project)
        if mode in {"all", "psd"}:
            self._advance_progress(progress, self._translator.text("progress.psd_settings"), 3)
            self._update_psd_reach_settings()
            self._plot_psd_phase_phase_zones()
            self._plot_psd_phase_ground_zones()
            self._plot_distance_phase_phase_zones()
            self._plot_distance_phase_ground_zones()
            self._psd_calculated = True
        if mode == "all":
            self._advance_progress(progress, self._translator.text("progress.distance_zones"), 4)
            self._plot_distance_phase_phase_zones()
            self._plot_distance_phase_ground_zones()
        self._advance_progress(progress, self._translator.text("progress.report"), 5)
        self.results_text.setPlainText(to_json(self._last_result))
        self.report_text.setHtml(self._build_zone_construction_report())
        self.psd_report_text.setHtml(self._build_psd_engineering_report())
        self._advance_progress(progress, self._translator.text("progress.done"), 6)
        progress.close()
        self._set_results_locked(True)
        self.statusBar().showMessage(self._translator.text("message.calculated"), 5000)
        return True

    def _create_progress_dialog(self, title: str) -> QProgressDialog:
        progress = QProgressDialog("", "", 0, 6, self)
        progress.setWindowTitle(title)
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.show()
        QApplication.processEvents()
        return progress

    def _advance_progress(
        self,
        progress: QProgressDialog,
        message: str,
        value: int,
    ) -> None:
        progress.setLabelText(message)
        progress.setValue(value)
        QApplication.processEvents()

    def _confirm_clear_results(self) -> None:
        if self._question_yes_no(
            self._translator.text("button.clear_results"),
            self._translator.text("message.confirm_clear_results"),
            default_yes=False,
        ):
            self._clear_results(update_lock=True)

    def _question_yes_no(self, title: str, text: str, *, default_yes: bool = True) -> bool:
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Question)
        message.setWindowTitle(title)
        message.setText(text)
        yes_button = message.addButton(
            self._translator.text("button.yes"),
            QMessageBox.ButtonRole.YesRole,
        )
        no_button = message.addButton(
            self._translator.text("button.no"),
            QMessageBox.ButtonRole.NoRole,
        )
        message.setDefaultButton(yes_button if default_yes else no_button)
        message.exec()
        return message.clickedButton() is yes_button

    def _clear_results(self, update_lock: bool = True) -> None:
        self._distance_drag_overrides.clear()
        self._distance_drag_original_values.clear()
        self._distance_drag_active = None
        self._distance_drag_limits = None
        self._set_distance_drag_pending(False)
        self._last_result = None
        self._last_psb_blocking_result = None
        self._last_phs_result = None
        self._psd_calculated = False
        self._phs_calculated = False
        self.results_text.clear()
        self.report_text.clear()
        self.psd_report_text.clear()
        self.phs_report_tab.clear() if hasattr(self, "phs_report_tab") else None
        if hasattr(self, "phs_settings_tab"):
            for row in range(self.phs_settings_tab.rowCount()):
                item = self.phs_settings_tab.item(row, 1)
                if item is not None:
                    item.setText("")
        for panel_name in (
            "phs_phase_phase_2ph_panel",
            "phs_phase_phase_3ph_panel",
            "phs_phase_ground_panel",
            "phs_load_cut_panel",
        ):
            if hasattr(self, panel_name):
                panel = getattr(self, panel_name)
                panel.axis.clear()
                panel.redraw()
        for panel in (
            self.rx_panel,
            self.psd_phase_phase_panel,
            self.psd_phase_ground_panel,
            self.distance_phase_phase_panel,
            self.distance_phase_ground_panel,
        ):
            panel.axis.clear()
            panel.redraw()
        for row in range(self.psd_reach_table.rowCount()):
            name_item = self.psd_reach_table.item(row, 0)
            value_item = self.psd_reach_table.item(row, 1)
            if name_item is not None and value_item is not None:
                value_item.setText(self._default_psd_value(name_item.text()))
        self.validation_message.hide()
        self.source_data_widget.clear_validation_errors()
        if update_lock:
            self._set_results_locked(False)
        else:
            self._update_result_tab_state()

    def _set_results_locked(self, locked: bool) -> None:
        self._results_locked = locked
        self.source_data_widget.set_inputs_locked(locked)
        self.project_name.setReadOnly(locked)
        self.author.setReadOnly(locked)
        self.clear_results_button.setEnabled(locked)
        self.calculate_button.setEnabled(not locked)
        self._update_result_tab_state()

    def _update_result_tab_state(self) -> None:
        self.calculate_button.setEnabled(not self._results_locked)
        visible_by_index = {
            self._input_tab_index: True,
            self._distance_tab_index: self._psd_calculated,
            self._psd_tab_index: self._psd_calculated,
            self._phs_tab_index: self._phs_calculated,
            self._journal_tab_index: self._show_journal_tab,
        }
        for index in range(self.tabs.count()):
            visible = visible_by_index.get(index, False)
            self.tabs.setTabVisible(index, visible)
            self.tabs.setTabEnabled(index, visible)
        current_index = self.tabs.currentIndex()
        if not visible_by_index.get(current_index, False):
            self.tabs.setCurrentIndex(self._input_tab_index)

    def _connect_dirty_tracking(self) -> None:
        self.project_name.textChanged.connect(self._mark_dirty)
        self.author.textChanged.connect(self._mark_dirty)
        self.source_data_widget.protection_type_combo.currentIndexChanged.connect(self._mark_dirty)
        self.source_data_widget.sensitive_stage_combo.currentIndexChanged.connect(self._mark_dirty)
        for editor in (
            self.source_data_widget.ktc_primary,
            self.source_data_widget.ktc_secondary,
            self.source_data_widget.ktn_primary,
            self.source_data_widget.ktn_secondary,
            self.source_data_widget.sensitivity_factor,
            self.source_data_widget.phs_sensitivity_factor,
            self.source_data_widget.max_psd_time,
            self.source_data_widget.delta_phi,
            self.source_data_widget.rejection_factor,
        ):
            editor.textChanged.connect(self._mark_dirty)
        self.source_data_widget.settings_table.itemChanged.connect(self._mark_dirty)
        self.source_data_widget.load_table.itemChanged.connect(self._mark_dirty)

    def _install_locked_input_warning_filter(self) -> None:
        for widget in self.source_data_widget.findChildren(QWidget):
            widget.installEventFilter(self)

    def _mark_dirty(self, *_args: object) -> None:
        if not self._suppress_dirty:
            self._dirty = True

    def eventFilter(self, obj: object, event: QEvent) -> bool:  # noqa: N802
        widget = cast(QWidget, obj) if isinstance(obj, QWidget) else None
        if (
            self._results_locked
            and widget is not None
            and not widget.isEnabled()
            and event.type()
            in {
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonDblClick,
                QEvent.Type.KeyPress,
            }
        ):
            self._show_locked_input_warning()
            return True
        if isinstance(obj, QObject):
            return super().eventFilter(obj, event)
        return False

    def _show_locked_input_warning(self) -> None:
        if self._locked_input_warning_open:
            return
        self._locked_input_warning_open = True
        try:
            QMessageBox.information(
                self,
                self._translator.text("message.results_locked_title"),
                self._translator.text("message.results_locked_body"),
            )
        finally:
            self._locked_input_warning_open = False

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

    @staticmethod
    def _stage_float(stage: StageMapping, key: str) -> float:
        value = stage[key]
        if value is None:
            raise ValueError(f"Stage field {key!r} is required.")
        return MainWindow._float_value(value)

    @staticmethod
    def _stage_float_any(stage: StageMapping, *keys: str) -> float:
        for key in keys:
            if key in stage:
                return MainWindow._stage_float(stage, key)
        raise KeyError(keys[0])

    @staticmethod
    def _stage_optional_float(stage: StageMapping, key: str) -> float | None:
        value = stage.get(key)
        return None if value is None else MainWindow._float_value(value)

    @staticmethod
    def _float_value(value: object) -> float:
        if isinstance(value, bool | int | float | str):
            return float(value)
        raise TypeError(f"Expected numeric value, got {type(value).__name__}.")

    @staticmethod
    def _required_float(value: float | None) -> float:
        if value is None:
            raise ValueError("Expected a calculated numeric value.")
        return float(value)

    @staticmethod
    def _psb_stage_setting_input(stage: StageMapping) -> PsbStageSettingInput:
        return PsbStageSettingInput(
            name=str(stage["name"]),
            is_forward=bool(stage["is_forward"]),
            x1=MainWindow._stage_float(stage, "x1"),
            r1=MainWindow._stage_float(stage, "r1"),
            x0=MainWindow._stage_float(stage, "x0"),
            r0=MainWindow._stage_float(stage, "r0"),
            rfpp=MainWindow._stage_float(stage, "rfpp"),
            rfpe=MainWindow._stage_float(stage, "rfpe"),
            arg_neg_res_deg=MainWindow._stage_float(stage, "arg_neg_res_deg"),
            arg_dir_deg=MainWindow._stage_float(stage, "arg_dir_deg"),
            load_angle_deg=MainWindow._stage_optional_float(stage, "load_angle_deg"),
            time_sec=MainWindow._stage_optional_float(stage, "time_sec"),
            compensated_load_angle_deg=MainWindow._stage_optional_float(
                stage,
                "compensated_load_angle_deg",
            ),
        )

    @staticmethod
    def _phase_phase_stage_input(stage: StageMapping) -> PhasePhaseStageInput:
        return PhasePhaseStageInput(
            name=str(stage["name"]),
            is_forward=bool(stage["is_forward"]),
            x1=MainWindow._stage_float(stage, "x1"),
            r1=MainWindow._stage_float(stage, "r1"),
            rpff=MainWindow._stage_float_any(stage, "rpff", "rfpp"),
            arg_neg_res_deg=MainWindow._stage_float(stage, "arg_neg_res_deg"),
            arg_dir_deg=MainWindow._stage_float(stage, "arg_dir_deg"),
        )

    @staticmethod
    def _phase_ground_stage_input(stage: StageMapping) -> PhaseGroundStageInput:
        return PhaseGroundStageInput(
            name=str(stage["name"]),
            is_forward=bool(stage["is_forward"]),
            x1=MainWindow._stage_float(stage, "x1"),
            r1=MainWindow._stage_float(stage, "r1"),
            x0=MainWindow._stage_float(stage, "x0"),
            r0=MainWindow._stage_float(stage, "r0"),
            rpff=MainWindow._stage_float_any(stage, "rpff", "rfpp"),
            rfpe=MainWindow._stage_float(stage, "rfpe"),
            arg_neg_res_deg=MainWindow._stage_float(stage, "arg_neg_res_deg"),
            arg_dir_deg=MainWindow._stage_float(stage, "arg_dir_deg"),
        )

    @staticmethod
    def _load_cut_input(values: Mapping[str, float | None]) -> PsbLoadCutInput:
        return PsbLoadCutInput(
            r_load_fw=values.get("r_load_fw"),
            x_load_fw=values.get("x_load_fw"),
            r_load_rv=values.get("r_load_rv"),
            x_load_rv=values.get("x_load_rv"),
            rejection_factor=values.get("rejection_factor"),
            delta_phi_deg=values.get("delta_phi_deg"),
            delta_r_secondary=values.get("delta_r_secondary"),
            delta_r_primary=values.get("delta_r_primary"),
        )

    @staticmethod
    def _table_cell_text(table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return item.text() if item is not None else ""

    @staticmethod
    def _table_header_text(table: QTableWidget, column: int) -> str:
        item = table.horizontalHeaderItem(column)
        return item.text() if item is not None else ""

    def _calculate_psb_blocking_settings(self) -> PsbBlockingResult | None:
        sensitivity_factor = self.source_data_widget.psd_sensitivity_factor_value()
        if sensitivity_factor is None:
            return None
        stages = [
            self._psb_stage_setting_input(stage)
            for stage in self.source_data_widget.psb_stage_setting_inputs()
        ]
        if not stages:
            return None
        return psb_blocking_settings(
            stages,
            sensitivity_factor,
            self._load_cut_input(self.source_data_widget.load_cut_inputs()),
            max_stage_time_sec=self.source_data_widget.max_psd_time_value(),
        )

    def _calculate_phs_selector_settings(self, *, use_psd_zone: bool) -> PhsSelectorResult | None:
        sensitivity_factor = self.source_data_widget.phs_sensitivity_factor_value()
        if sensitivity_factor is None:
            return None
        stage = self._phs_stage_input()
        if stage is None:
            return None
        return phs_selector_settings(
            stage,
            sensitivity_factor,
            self._load_cut_input(self.source_data_widget.load_cut_inputs()),
            self._last_psb_blocking_result if use_psd_zone else None,
            use_psd_zone=use_psd_zone,
        )

    def _disabled_psd_result(self) -> PsbBlockingResult:
        return PsbBlockingResult(
            sensitivity_factor=0.0,
            forward=None,
            reverse=None,
            included_forward_stage_names=(),
            included_reverse_stage_names=(),
            arg_dir_deg=None,
            arg_neg_res_deg=None,
            arg_dir_fw_deg=None,
            arg_neg_res_fw_deg=None,
            arg_dir_rv_deg=None,
            arg_neg_res_rv_deg=None,
            load_angle_deg=None,
            load_angle_candidates=(),
            load_angle_fw_deg=None,
            load_angle_rv_deg=None,
            load_angle_fw_candidates=(),
            load_angle_rv_candidates=(),
            x1_in_fw_coverage_phase=None,
            x1_in_fw_coverage_ground=None,
            x1_in_fw_reverse_intersection_phase=None,
            x1_in_fw_reverse_intersection_ground=None,
            x1_in_fw=0.0,
            r1f_in_fw_coverage_phase=None,
            r1f_in_fw_coverage_ground=None,
            r1f_in_fw_reverse_intersection_phase=None,
            r1f_in_fw_reverse_intersection_ground=None,
            r1f_in_fw=0.0,
            x1_in_rv_coverage_phase=None,
            x1_in_rv_coverage_ground=None,
            x1_in_rv_forward_intersection_phase=None,
            x1_in_rv_forward_intersection_ground=None,
            x1_in_rv=0.0,
            r1f_in_rv_coverage_phase=None,
            r1f_in_rv_coverage_ground=None,
            r1f_in_rv_forward_intersection_phase=None,
            r1f_in_rv_forward_intersection_ground=None,
            r1f_in_rv=0.0,
            r1l_in_fw=0.0,
            r1l_in_rv=0.0,
            r1l_in=0.0,
            load_cut=None,
            rld_out_fw_load=None,
            rld_out_rv_load=None,
            rld_in_fw_load=None,
            rld_in_rv_load=None,
            rld_in_fw=None,
            rld_in_rv=None,
            rld_out_fw=99999.0,
            rld_out_rv=99999.0,
            kld_fw=1.0,
            kld_rv=1.0,
            arg_ld_fw_base_deg=None,
            arg_ld_rv_base_deg=None,
            arg_ld_selected_deg=None,
            arg_ld_deg=0.0,
        )

    def _phs_stage_input(self) -> PhsStageInput | None:
        selected = self._selected_sensitive_stage()
        if selected is None:
            return None
        return PhsStageInput(
            name=str(selected["name"]),
            x1=self._stage_float(selected, "x1"),
            r1=self._stage_float(selected, "r1"),
            x0=self._stage_float(selected, "x0"),
            r0=self._stage_float(selected, "r0"),
            rfpp=self._stage_float(selected, "rfpp"),
            rfpe=self._stage_float(selected, "rfpe"),
            arg_dir_deg=self._stage_float(selected, "arg_dir_deg"),
            arg_neg_res_deg=self._stage_float(selected, "arg_neg_res_deg"),
            load_angle_ground_deg=self._stage_optional_float(
                selected,
                "compensated_load_angle_deg",
            ),
        )

    def _selected_sensitive_stage(self) -> StageMapping | None:
        stages = self.source_data_widget.psb_stage_setting_inputs()
        selected_column = int(self.source_data_widget.sensitive_stage_combo.currentData() or 0)
        selected_name = (
            self._translator.text("source.step_template", number=selected_column)
            if selected_column
            else ""
        )
        selected = next(
            (
                stage
                for stage in stages
                if selected_name and stage["name"] == selected_name and bool(stage["is_forward"])
            ),
            None,
        )
        if selected is None:
            forward_stages = [stage for stage in stages if bool(stage["is_forward"])]
            if not forward_stages:
                return None
            selected = max(forward_stages, key=lambda stage: self._stage_float(stage, "x1"))
        return selected

    def _update_phs_settings_table(self) -> None:
        result = self._last_phs_result
        if result is None:
            return
        values = {
            "INBlockPP": result.inblock_pp,
            "INBlockPE": result.inblock_pe,
            "RLd Fw": result.rld_fw,
            "RLd Rv": result.rld_rv,
            "ArgLd": result.arg_ld,
            "X1": result.x1,
            "X0": result.x0,
            "RFFwPP": result.rffw_pp,
            "RFRvPP": result.rfrv_pp,
            "RFFw PE": result.rffw_pe,
            "RFRv PE": result.rfrv_pe,
        }
        for row in range(self.phs_settings_tab.rowCount()):
            name_item = self.phs_settings_tab.item(row, 0)
            value_item = self.phs_settings_tab.item(row, 1)
            if name_item is None or value_item is None:
                continue
            value_item.setText(self._report_optional_number(values.get(name_item.text())))

    def _plot_phs_graphs(self) -> None:
        result = self._last_phs_result
        for panel, title in (
            (self.phs_phase_phase_2ph_panel, self._translator.text("phs.phase_phase_2ph")),
            (self.phs_phase_phase_3ph_panel, self._translator.text("phs.phase_phase_3ph")),
            (self.phs_phase_ground_panel, self._translator.text("phs.phase_ground")),
            (self.phs_load_cut_panel, self._translator.text("phs.load_cut")),
        ):
            axis = panel.axis
            axis.clear()
            configure_rx_axes(axis, {"title": title, "r_axis": "R, Ом", "x_axis": "X, Ом"})
            if result is None:
                panel.redraw()
        if result is None:
            return
        load_cut_values = self._phs_load_cut_values_by_direction(result)

        phase_phase_points = [
            (result.rffw_pp / 2.0, 0.0),
            (result.rffw_pp / 2.0 + result.x1 / tan(pi / 3.0), result.x1),
            (0.0, result.x1),
            (-result.rffw_pp / 2.0, result.x1),
            (-result.rffw_pp / 2.0, 0.0),
            (-(result.rffw_pp / 2.0 + result.x1 / tan(pi / 3.0)), -result.x1),
            (0.0, -result.x1),
            (result.rffw_pp / 2.0, -result.x1),
            (result.rffw_pp / 2.0, 0.0),
        ]
        phase_phase_3ph_points = [
            self._phs_three_phase_point(result.rffw_pp / 2.0, 0.0),
            self._phs_three_phase_point(
                result.rffw_pp / 2.0 + result.x1 / tan(pi / 3.0),
                result.x1,
            ),
            self._phs_three_phase_point(0.0, result.x1),
            self._phs_three_phase_point(-result.rfrv_pp / 2.0, result.x1),
            self._phs_three_phase_point(-result.rfrv_pp / 2.0, 0.0),
            self._phs_three_phase_point(
                -(result.rfrv_pp / 2.0 + result.x1 / tan(pi / 3.0)),
                -result.x1,
            ),
            self._phs_three_phase_point(0.0, -result.x1),
            self._phs_three_phase_point(result.rffw_pp / 2.0, -result.x1),
            self._phs_three_phase_point(result.rffw_pp / 2.0, 0.0),
        ]
        ground_reach = (2.0 * result.x1 + result.x0) / 3.0
        phase_ground_points = [
            (result.rffw_pe, 0.0),
            (result.rffw_pe + ground_reach / tan(pi / 3.0), ground_reach),
            (0.0, ground_reach),
            (-result.rfrv_pe, ground_reach),
            (-result.rfrv_pe, 0.0),
            (-(result.rfrv_pe + ground_reach / tan(pi / 3.0)), -ground_reach),
            (0.0, -ground_reach),
            (result.rffw_pe, -ground_reach),
            (result.rffw_pe, 0.0),
        ]
        load_cut_segments: list[list[tuple[float, float]]] = []
        load_cut_points: list[tuple[float, float]] = []
        if load_cut_values is not None:
            rld_fw, rld_rv, arg_ld_fw, arg_ld_rv = load_cut_values
            tan_arg_fw = tan(arg_ld_fw * pi / 180.0)
            tan_arg_rv = tan(arg_ld_rv * pi / 180.0)
            load_cut_segments = [
                [
                    (rld_fw, rld_fw * tan_arg_fw),
                    (rld_fw, -rld_fw * tan_arg_fw),
                ],
                [
                    (-rld_rv, -rld_rv * tan_arg_rv),
                    (-rld_rv, rld_rv * tan_arg_rv),
                ],
            ]
            load_cut_points = [point for segment in load_cut_segments for point in segment]
        for panel, label, points in (
            (self.phs_phase_phase_2ph_panel, "PHS 2ф", phase_phase_points),
            (self.phs_phase_phase_3ph_panel, "PHS 3ф", phase_phase_3ph_points),
            (self.phs_phase_ground_panel, "PHS фаза-земля", phase_ground_points),
            (self.phs_load_cut_panel, "Виріз від навантаження", load_cut_points),
        ):
            axis = panel.axis
            self._phs_zone_visibility.setdefault(self._phs_visibility_key(panel, label), True)
            point_targets: list[tuple[str, float, float]] = []
            line_by_label: dict[str, object] = {}
            visible = self._phs_zone_visible(panel, label)
            if panel is self.phs_load_cut_panel and load_cut_segments:
                color = self._zone_line_color(label)
                for segment_index, segment in enumerate(load_cut_segments):
                    xs = [point[0] for point in segment]
                    ys = [point[1] for point in segment]
                    line = axis.plot(
                        xs,
                        ys,
                        linewidth=1.0,
                        label=label if segment_index == 0 else "_nolegend_",
                        color=color,
                    )[0]
                    line.set_visible(visible)
                    if segment_index == 0:
                        line_by_label[label] = line
                    scatter = axis.scatter(
                        xs,
                        ys,
                        s=6,
                        zorder=4,
                        color=color,
                        label="_nolegend_",
                    )
                    scatter.set_visible(visible)
                plotted_points = load_cut_points
            else:
                xs = [point[0] for point in points]
                ys = [point[1] for point in points]
                color = self._zone_line_color(label)
                line = axis.plot(xs, ys, linewidth=1.0, label=label, color=color)[0]
                line.set_visible(visible)
                fill = axis.fill(
                    xs,
                    ys,
                    color=line.get_color(),
                    alpha=0.10,
                    linewidth=0,
                    label="_nolegend_",
                    zorder=0,
                )[0]
                fill.set_visible(visible)
                scatter = axis.scatter(xs, ys, s=6, zorder=4, label="_nolegend_")
                scatter.set_visible(visible)
                line_by_label[label] = line
                plotted_points = points

            if visible:
                for point_label, (x_value, y_value) in zip(
                    self._phs_point_labels_for_panel(panel, len(plotted_points)),
                    plotted_points,
                    strict=False,
                ):
                    point_targets.append((f"{label} {point_label}", x_value, y_value))
                    if self._show_point_labels:
                        axis.annotate(
                            point_label,
                            (x_value, y_value),
                            textcoords="offset points",
                            xytext=(5, 5),
                            fontsize=8,
                        )
            point_targets.extend(self._plot_sensitive_distance_zone_on_phs(panel, line_by_label))
            self._plot_phs_ld_zones(panel, result, line_by_label)
            for ld_label, ld_points in self._phs_ld_overlays(result):
                if self._phs_zone_visible(panel, ld_label):
                    for point_label, x_value, y_value in ld_points:
                        point_targets.append((f"{ld_label} {point_label}", x_value, y_value))
            self._autoscale_visible(axis)
            self._shade_rld_regions(
                axis,
                self._phs_ld_overlays(result),
                {
                    ld_label: self._phs_zone_visible(panel, ld_label)
                    for ld_label, _points in self._phs_ld_overlays(result)
                },
            )
            legend = axis.legend(loc="upper left") if self._show_legends and line_by_label else None
            if legend is not None:
                for legend_line, text in zip(legend.get_lines(), legend.get_texts(), strict=False):
                    legend_label = text.get_text()
                    legend_visible = self._legend_group_visible_for_phs(
                        panel,
                        legend_label,
                        line_by_label,
                    )
                    legend_line.set_picker(8)
                    text.set_picker(True)
                    legend_line.set_alpha(1.0 if legend_visible else 0.25)
                    text.set_alpha(1.0 if legend_visible else 0.35)
                    legend_line._rel_phs_zone_label = legend_label  # type: ignore[attr-defined]
                    text._rel_phs_zone_label = legend_label  # type: ignore[attr-defined]
            self._connect_phs_legend_picker(panel, line_by_label)
            self._connect_phs_point_tooltip(panel, point_targets)
            panel.redraw()

    @staticmethod
    def _phs_visibility_key(panel: MatplotlibPanel, label: str) -> str:
        return f"{id(panel)}:{label}"

    def _phs_zone_visible(self, panel: MatplotlibPanel, label: str) -> bool:
        return self._phs_zone_visibility.get(self._phs_visibility_key(panel, label), True)

    def _set_phs_zone_visible(self, panel: MatplotlibPanel, label: str, visible: bool) -> None:
        self._phs_zone_visibility[self._phs_visibility_key(panel, label)] = visible

    def _legend_group_visible_for_phs(
        self,
        panel: MatplotlibPanel,
        label: str,
        line_by_label: Mapping[str, object],
    ) -> bool:
        members = self._legend_group_members(label, line_by_label)
        return any(self._phs_zone_visible(panel, member) for member in members)

    @staticmethod
    def _phs_three_phase_point(re_value: float, im_value: float) -> tuple[float, float]:
        if re_value != 0.0:
            angle_deg = atan(im_value / re_value) * 180.0 / pi
            if re_value < 0.0:
                angle_deg += 180.0
        else:
            angle_deg = -90.0 if im_value < 0.0 else 90.0
        magnitude = (re_value * re_value + im_value * im_value) ** 0.5
        rotated_angle = (angle_deg + 30.0) * pi / 180.0
        scale = 2.0 / sqrt(3.0)
        return (
            scale * magnitude * cos(rotated_angle),
            scale * magnitude * sin(rotated_angle),
        )

    def _phs_point_labels_for_panel(self, panel: MatplotlibPanel, count: int) -> list[str]:
        if panel is self.phs_phase_phase_2ph_panel:
            return ["AA", "BB", "CC", "DD", "EE", "FF", "GG", "HH", "II"][:count]
        if panel is self.phs_phase_phase_3ph_panel:
            return ["AA'", "BB'", "CC'", "DD'", "EE'", "FF'", "GG'", "HH'"][:count]
        if panel is self.phs_phase_ground_panel:
            return ["AA''", "BB''", "CC''", "DD''", "EE''", "FF''", "GG''", "HH''", "II''"][:count]
        return self._point_labels_for_count(count)

    def _connect_phs_point_tooltip(
        self,
        panel: MatplotlibPanel,
        targets: list[tuple[str, float, float]],
    ) -> None:
        cid = getattr(panel, "_rel_phs_motion_cid", None)
        if cid is not None:
            panel.canvas.mpl_disconnect(cid)
        panel._rel_phs_motion_cid = self._connect_point_tooltip(panel, targets)  # type: ignore[attr-defined]

    def _connect_phs_legend_picker(
        self,
        panel: MatplotlibPanel,
        line_by_label: dict[str, object],
    ) -> None:
        panel_key = id(panel)
        previous_cid = self._phs_pick_cids.get(panel_key)
        if previous_cid is not None:
            panel.canvas.mpl_disconnect(previous_cid)

        def toggle_zone(event) -> None:  # type: ignore[no-untyped-def]
            label = getattr(event.artist, "_rel_phs_zone_label", None)
            if not isinstance(label, str):
                return
            members = self._legend_group_members(label, line_by_label)
            if not members:
                return
            current = any(self._phs_zone_visible(panel, member) for member in members)
            for member in members:
                self._set_phs_zone_visible(panel, member, not current)
            self._plot_phs_graphs()

        self._phs_pick_cids[panel_key] = panel.canvas.mpl_connect("pick_event", toggle_zone)

    @staticmethod
    def _phs_load_cut_values(result: PhsSelectorResult) -> tuple[float, float, float] | None:
        if result.rld_fw is None or result.rld_rv is None or result.arg_ld is None:
            return None
        return float(result.rld_fw), float(result.rld_rv), float(result.arg_ld)

    @staticmethod
    def _min_existing_float(*values: float | None) -> float | None:
        complete_values = [float(value) for value in values if value is not None]
        return min(complete_values) if complete_values else None

    @staticmethod
    def _phs_load_cut_values_by_direction(
        result: PhsSelectorResult,
    ) -> tuple[float, float, float, float] | None:
        if result.rld_fw is None or result.rld_rv is None:
            return None
        arg_ld_fw = MainWindow._min_existing_float(result.arg_ld_load, result.arg_ld_fw_psd)
        arg_ld_rv = MainWindow._min_existing_float(result.arg_ld_load, result.arg_ld_rv_psd)
        if arg_ld_fw is None:
            arg_ld_fw = float(result.arg_ld) if result.arg_ld is not None else None
        if arg_ld_rv is None:
            arg_ld_rv = float(result.arg_ld) if result.arg_ld is not None else None
        if arg_ld_fw is None or arg_ld_rv is None:
            return None
        return float(result.rld_fw), float(result.rld_rv), arg_ld_fw, arg_ld_rv

    def _phs_ld_overlays(self, result: PhsSelectorResult) -> list[OverlayPolygon]:
        values = self._phs_load_cut_values_by_direction(result)
        if values is None:
            return []
        return self._ld_overlays(*values)

    def _ld_overlays(
        self,
        rld_fw: float,
        rld_rv: float,
        arg_ld_fw_deg: float,
        arg_ld_rv_deg: float | None = None,
    ) -> list[OverlayPolygon]:
        tan_arg_fw = tan(arg_ld_fw_deg * pi / 180.0)
        rv_angle = arg_ld_rv_deg if arg_ld_rv_deg is not None else arg_ld_fw_deg
        tan_arg_rv = tan(rv_angle * pi / 180.0)
        return [
            (
                "Ld Fw",
                (
                    ("A", 2.0 * rld_fw, 2.0 * rld_fw * tan_arg_fw),
                    ("B", rld_fw, rld_fw * tan_arg_fw),
                    ("C", rld_fw, 0.0),
                    ("D", rld_fw, -rld_fw * tan_arg_fw),
                    ("E", 2.0 * rld_fw, -2.0 * rld_fw * tan_arg_fw),
                ),
            ),
            (
                "Ld Rv",
                (
                    ("A'", -2.0 * rld_rv, -2.0 * rld_rv * tan_arg_rv),
                    ("B'", -rld_rv, -rld_rv * tan_arg_rv),
                    ("C'", -rld_rv, 0.0),
                    ("D'", -rld_rv, rld_rv * tan_arg_rv),
                    ("E'", -2.0 * rld_rv, 2.0 * rld_rv * tan_arg_rv),
                ),
            ),
        ]

    def _plot_phs_ld_zones(
        self,
        panel: MatplotlibPanel,
        result: PhsSelectorResult,
        line_by_label: dict[str, object],
    ) -> None:  # type: ignore[no-untyped-def]
        axis = panel.axis
        for label, points in self._phs_ld_overlays(result):
            self._phs_zone_visibility.setdefault(self._phs_visibility_key(panel, label), True)
            xs = [point[1] for point in points]
            ys = [point[2] for point in points]
            line = axis.plot(
                xs,
                ys,
                linewidth=1.0,
                color=self._zone_line_color(label),
                label=self._legend_label_for_group(
                    label,
                    {self._legend_group_label(key) for key in line_by_label},
                ),
            )[0]
            visible = self._phs_zone_visible(panel, label)
            line.set_visible(visible)
            scatter = axis.scatter(xs, ys, s=14, color=self._zone_line_color(label), zorder=4)
            scatter.set_visible(visible)
            line_by_label[label] = line

    def _plot_sensitive_distance_zone_on_phs(
        self,
        panel: MatplotlibPanel,
        line_by_label: dict[str, object],
    ) -> list[tuple[str, float, float]]:
        label = "Чутлива зона"
        self._phs_zone_visibility.setdefault(self._phs_visibility_key(panel, label), True)
        stage = self._selected_sensitive_stage()
        if stage is None:
            return []
        try:
            if panel is self.phs_phase_ground_panel:
                zones = phase_ground_zone_polygons(
                    [self._phase_ground_stage_input(stage)]
                )
            else:
                zones = phase_phase_zone_polygons(
                    [self._phase_phase_stage_input(stage)]
                )
        except (TypeError, ValueError):
            return []
        if not zones:
            return []
        zone = zones[0]
        xs = [point[0] for point in zone.points]
        ys = [point[1] for point in zone.points]
        color = self._zone_line_color(zone.name) or "#334155"
        line = panel.axis.plot(
            xs,
            ys,
            linewidth=1.0,
            color=color,
            label=label,
        )[0]
        visible = self._phs_zone_visible(panel, label)
        line.set_visible(visible)
        panel.axis.fill(
            xs,
            ys,
            color=line.get_color(),
            alpha=0.10,
            linewidth=0,
            label="_nolegend_",
            zorder=0,
        )[0].set_visible(visible)
        scatter = panel.axis.scatter(
            xs,
            ys,
            s=9,
            zorder=4,
            color=line.get_color(),
            label="_nolegend_",
        )
        scatter.set_visible(visible)
        line_by_label[label] = line
        targets: list[tuple[str, float, float]] = []
        if not visible:
            return targets
        for point_label, x_value, y_value in zip(
            self._point_labels_for_count(len(zone.points)),
            xs,
            ys,
            strict=False,
        ):
            targets.append((f"Чутлива зона {point_label}", x_value, y_value))
            if self._show_point_labels:
                panel.axis.annotate(
                    point_label,
                    (x_value, y_value),
                    textcoords="offset points",
                    xytext=(5, 5),
                    fontsize=8,
                )
        return targets

    def _shade_phs_load_cut(self, axis, result: PhsSelectorResult) -> None:  # type: ignore[no-untyped-def]
        values = self._phs_load_cut_values(result)
        if values is None:
            return
        rld_fw, rld_rv, arg_ld = values
        color = "#16697a"
        tan_arg = tan(arg_ld * pi / 180.0)
        inner_fw = (
            ("AA", rld_fw, rld_fw * tan_arg),
            ("BB", rld_fw, -rld_fw * tan_arg),
        )
        inner_rv = (
            ("EE", -rld_rv, rld_rv * tan_arg),
            ("FF", -rld_rv, -rld_rv * tan_arg),
        )
        x_min, x_max = axis.get_xlim()
        for points, edge_x in ((inner_fw, x_max), (inner_rv, x_min)):
            xs = [points[0][1], edge_x, edge_x, points[1][1]]
            ys = [points[0][2], points[0][2], points[1][2], points[1][2]]
            axis.fill(xs, ys, color=color, alpha=0.10, linewidth=0, label="_nolegend_", zorder=0)

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

        x1_fw = self._required_float(result.x1_in_fw)
        x1_rv = self._required_float(result.x1_in_rv)
        r_fw = self._required_float(result.r1f_in_fw)
        r_rv = self._required_float(result.r1f_in_rv)
        r_line = self._required_float(result.r1l_in)
        rld_out_fw = self._required_float(result.rld_out_fw)
        rld_out_rv = self._required_float(result.rld_out_rv)
        rld_out_fw_load = self._required_float(result.rld_out_fw_load)
        rld_out_rv_load = self._required_float(result.rld_out_rv_load)
        rld_in_fw_load = self._required_float(result.rld_in_fw_load)
        rld_in_rv_load = self._required_float(result.rld_in_rv_load)
        kld_fw = self._required_float(result.kld_fw)
        kld_rv = self._required_float(result.kld_rv)
        arg_ld = self._required_float(result.arg_ld_deg)
        delta_fw = rld_out_fw - rld_out_fw * kld_fw
        delta_rv = rld_out_rv - rld_out_rv * kld_rv
        rld_out_fw_plot = abs(rld_out_fw_load)
        rld_out_rv_plot = abs(rld_out_rv_load)
        rld_in_fw_plot = abs(rld_in_fw_load)
        rld_in_rv_plot = abs(rld_in_rv_load)
        delta_fw_plot = abs(delta_fw)
        delta_rv_plot = abs(delta_rv)
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
                rld_in_fw_plot * 1.5,
                (rld_in_fw_plot * 1.5 + delta_fw_plot) * tan_arg_ld,
            ),
            ("BB", rld_in_fw_plot, rld_out_fw_plot * tan_arg_ld),
            ("CC", rld_in_fw_plot, -rld_out_fw_plot * tan_arg_ld),
            (
                "DD",
                rld_in_fw_plot * 1.5,
                -(rld_in_fw_plot * 1.5 + delta_fw_plot) * tan_arg_ld,
            ),
        )
        rld_inner_rv = (
            (
                "EE",
                -rld_in_rv_plot * 1.5,
                (rld_in_rv_plot * 1.5 + delta_rv_plot) * tan_arg_ld,
            ),
            ("FF", -rld_in_rv_plot, rld_out_rv_plot * tan_arg_ld),
            ("GG", -rld_in_rv_plot, -rld_out_rv_plot * tan_arg_ld),
            (
                "HH",
                -rld_in_rv_plot * 1.5,
                -(rld_in_rv_plot * 1.5 + delta_rv_plot) * tan_arg_ld,
            ),
        )
        rld_outer_fw = (
            ("AA'", rld_out_fw_plot * 1.5, (rld_out_fw_plot * 1.5) * tan_arg_ld),
            ("BB'", rld_out_fw_plot, rld_out_fw_plot * tan_arg_ld),
            ("CC'", rld_out_fw_plot, -rld_out_fw_plot * tan_arg_ld),
            ("DD'", rld_out_fw_plot * 1.5, -(rld_out_fw_plot * 1.5) * tan_arg_ld),
        )
        rld_outer_rv = (
            ("EE'", -rld_out_rv_plot * 1.5, (rld_out_rv_plot * 1.5) * tan_arg_ld),
            ("FF'", -rld_out_rv_plot, rld_out_rv_plot * tan_arg_ld),
            ("GG'", -rld_out_rv_plot, -rld_out_rv_plot * tan_arg_ld),
            ("HH'", -rld_out_rv_plot * 1.5, -(rld_out_rv_plot * 1.5) * tan_arg_ld),
        )
        overlays = [
            ("PSD inner", inner),
            ("PSD outer", outer),
            ("RLD inner", rld_inner_fw),
            ("RLD inner", rld_inner_rv),
            ("RLD outer", rld_outer_fw),
            ("RLD outer", rld_outer_rv),
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

    @staticmethod
    def _default_zone_colors() -> dict[str, str]:
        return {
            "1 ступінь": "#2563eb",
            "2 ступінь": "#f97316",
            "3 ступінь": "#16a34a",
            "4 ступінь": "#dc2626",
            "5 ступінь": "#9333ea",
            "PSD": "#7c3aed",
            "RLD inner": "#0e7490",
            "RLD outer": "#0369a1",
            "Виріз від навантаження": "#f59e0b",
            "Zнав": "#92400e",
            "PHS": "#2563eb",
        }

    def _zone_color_options(self) -> list[tuple[str, str]]:
        return [
            ("1 ступінь", "Дистанційна зона: 1 ступінь"),
            ("2 ступінь", "Дистанційна зона: 2 ступінь"),
            ("3 ступінь", "Дистанційна зона: 3 ступінь"),
            ("4 ступінь", "Дистанційна зона: 4 ступінь"),
            ("5 ступінь", "Дистанційна зона: 5 ступінь"),
            ("PSD", "PSD: зона"),
            ("RLD inner", "RLD: внутрішня межа"),
            ("RLD outer", "RLD: зовнішня межа"),
            ("Виріз від навантаження", "Виріз від навантаження"),
            ("Zнав", "Опір навантаження"),
            ("PHS", "PHS: зона"),
        ]

    def _zone_line_style(self, label: str) -> str:
        return "--" if label.startswith("RLD inner") else "-"

    def _zone_line_color(self, label: str) -> str | None:
        if label.startswith("Ld ") or label == "Виріз від навантаження":
            return self._zone_colors.get("Виріз від навантаження")
        if label.startswith("Zнав "):
            return self._zone_colors.get("Zнав")
        if label.startswith("PSD "):
            return self._zone_colors.get("PSD")
        if label.startswith("PHS "):
            return self._zone_colors.get("PHS")
        if label in self._zone_colors:
            return self._zone_colors[label]
        for key in self._zone_colors:
            if label.startswith(key):
                return self._zone_colors[key]
        if "ступінь" in label:
            for key in ("1 ступінь", "2 ступінь", "3 ступінь", "4 ступінь", "5 ступінь"):
                if label.startswith(key):
                    return self._zone_colors.get(key)
        return None

    def _legend_label_for_group(self, label: str, plotted_labels: set[str]) -> str:
        display_label = self._legend_group_label(label)
        if display_label in plotted_labels:
            return "_nolegend_"
        plotted_labels.add(display_label)
        return display_label

    def _legend_group_label(self, label: str) -> str:
        if label.startswith("Ld ") or label == "Виріз від навантаження":
            return "Виріз від навантаження"
        if label.startswith("Zнав "):
            return "Zнав"
        return label

    @staticmethod
    def _legend_group_members(label: str, line_by_label: Mapping[str, object]) -> list[str]:
        if label == "Виріз від навантаження":
            return [
                key
                for key in line_by_label
                if key.startswith("Ld ") or key == "Виріз від навантаження"
            ]
        if label == "Zнав":
            return [key for key in line_by_label if key.startswith("Zнав ")]
        return [label] if label in line_by_label else []

    def _legend_group_visible(
        self,
        label: str,
        line_by_label: Mapping[str, object],
        visibility: Mapping[str, bool],
    ) -> bool:
        members = self._legend_group_members(label, line_by_label)
        return any(visibility.get(member, True) for member in members)

    def _plot_psd_phase_phase_zones(self) -> None:
        stages = [
            self._phase_phase_stage_input(stage)
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
            line = axis.plot(
                xs,
                ys,
                linewidth=1.0,
                label=zone.name,
                color=self._zone_line_color(zone.name),
            )[0]
            visible = self._psd_phase_phase_zone_visibility.get(zone.name, True)
            line.set_visible(visible)
            fill = axis.fill(
                xs,
                ys,
                color=line.get_color(),
                alpha=0.10,
                linewidth=0,
                label="_nolegend_",
                zorder=0,
            )[0]
            fill.set_visible(visible)
            line_by_label[zone.name] = line
            if visible:
                point_labels = self._point_labels_for_count(len(zone.points))
                axis.scatter(xs, ys, s=10, zorder=4, label="_nolegend_")
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
        overlay_colors: dict[str, object] = {}
        plotted_overlay_labels: set[str] = set()
        for label, points in self._psd_overlay_polygons():
            self._psd_phase_phase_zone_visibility.setdefault(label, True)
            xs = [point[1] for point in points]
            ys = [point[2] for point in points]
            color = overlay_colors.get(label) or self._zone_line_color(label)
            line = axis.plot(
                xs,
                ys,
                linewidth=1.0,
                linestyle=self._zone_line_style(label),
                label=self._legend_label_for_group(label, plotted_overlay_labels),
                color=color,
            )[0]
            overlay_colors.setdefault(label, line.get_color())
            visible = self._psd_phase_phase_zone_visibility.get(label, True)
            line.set_visible(visible)
            line_by_label[label] = line
            if visible:
                axis.scatter(xs, ys, s=9, zorder=4, label="_nolegend_")
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
        self._shade_psd_gap_regions(
            axis,
            self._psd_overlay_polygons(),
            self._psd_phase_phase_zone_visibility,
        )
        self._shade_rld_regions(
            axis,
            self._psd_overlay_polygons(),
            self._psd_phase_phase_zone_visibility,
        )
        legend = axis.legend(loc="upper left") if self._show_legends and line_by_label else None
        if legend is not None:
            for legend_line, text in zip(legend.get_lines(), legend.get_texts(), strict=False):
                label = text.get_text()
                visible = self._legend_group_visible(
                    label,
                    line_by_label,
                    self._psd_phase_phase_zone_visibility,
                )
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
            self._phase_ground_stage_input(stage)
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
            line = axis.plot(
                xs,
                ys,
                linewidth=1.0,
                label=zone.name,
                color=self._zone_line_color(zone.name),
            )[0]
            visible = self._psd_phase_ground_zone_visibility.get(zone.name, True)
            line.set_visible(visible)
            fill = axis.fill(
                xs,
                ys,
                color=line.get_color(),
                alpha=0.10,
                linewidth=0,
                label="_nolegend_",
                zorder=0,
            )[0]
            fill.set_visible(visible)
            line_by_label[zone.name] = line
            if visible:
                axis.scatter(xs, ys, s=10, zorder=4, label="_nolegend_")
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
        overlay_colors: dict[str, object] = {}
        plotted_overlay_labels: set[str] = set()
        for label, points in self._psd_overlay_polygons():
            self._psd_phase_ground_zone_visibility.setdefault(label, True)
            xs = [point[1] for point in points]
            ys = [point[2] for point in points]
            color = overlay_colors.get(label) or self._zone_line_color(label)
            line = axis.plot(
                xs,
                ys,
                linewidth=1.0,
                linestyle=self._zone_line_style(label),
                label=self._legend_label_for_group(label, plotted_overlay_labels),
                color=color,
            )[0]
            overlay_colors.setdefault(label, line.get_color())
            visible = self._psd_phase_ground_zone_visibility.get(label, True)
            line.set_visible(visible)
            line_by_label[label] = line
            if visible:
                axis.scatter(xs, ys, s=9, zorder=4, label="_nolegend_")
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
        self._shade_psd_gap_regions(
            axis,
            self._psd_overlay_polygons(),
            self._psd_phase_ground_zone_visibility,
        )
        self._shade_rld_regions(
            axis,
            self._psd_overlay_polygons(),
            self._psd_phase_ground_zone_visibility,
        )
        legend = axis.legend(loc="upper left") if self._show_legends and line_by_label else None
        if legend is not None:
            for legend_line, text in zip(legend.get_lines(), legend.get_texts(), strict=False):
                label = text.get_text()
                visible = self._legend_group_visible(
                    label,
                    line_by_label,
                    self._psd_phase_ground_zone_visibility,
                )
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

    def _distance_ld_overlays(self) -> list[OverlayPolygon]:
        if self._last_phs_result is None:
            return []
        result = self._last_phs_result
        if (
            result.rld_fw_load is None
            or result.rld_rv_load is None
            or result.arg_ld_load is None
        ):
            return []
        return self._ld_overlays(
            float(result.rld_fw_load),
            float(result.rld_rv_load),
            float(result.arg_ld_load),
        )

    def _stage_with_distance_override(
        self,
        stage: StageMapping,
        graph_kind: str,
    ) -> dict[str, StageValue]:
        column = self._stage_column(stage)
        key = (graph_kind, column)
        if key not in self._distance_drag_overrides:
            return dict(stage)
        updated = dict(stage)
        if graph_kind == "phase_phase":
            updated["rpff"] = self._distance_drag_overrides[key]
        else:
            updated["rfpe"] = self._distance_drag_overrides[key]
        return updated

    @staticmethod
    def _stage_column(stage: StageMapping) -> int:
        value = stage.get("column")
        return int(value) if isinstance(value, (float, int)) else 0

    def _distance_drag_key(self, target: DistanceDragTarget) -> tuple[str, int]:
        return (target.graph_kind, target.column)

    def _distance_drag_value_from_x(self, target: DistanceDragTarget, x_value: float) -> float:
        if target.graph_kind == "phase_phase":
            return abs(x_value) * 2.0
        return abs(x_value)

    def _distance_drag_actions_visible(self, visible: bool) -> None:
        for name in (
            "distance_phase_phase_drag_cancel_button",
            "distance_phase_phase_drag_apply_button",
            "distance_phase_ground_drag_cancel_button",
            "distance_phase_ground_drag_apply_button",
        ):
            if hasattr(self, name):
                getattr(self, name).setEnabled(visible)

    def _set_distance_drag_pending(self, pending: bool) -> None:
        self._distance_drag_pending = pending
        self._distance_drag_actions_visible(pending)

    def _register_distance_drag_target(
        self,
        graph_kind: str,
        zone_name: str,
        column: int,
        row_name: str,
        points: Sequence[tuple[float, float]],
        axis: object,
        zone_line: object,
    ) -> None:
        if column <= 0 or len(points) < 2:
            return
        x_value = max(point[0] for point in points)
        closed_points = list(points)
        if closed_points[0] != closed_points[-1]:
            closed_points.append(closed_points[0])
        right_segments = tuple(
            (start, end)
            for start, end in pairwise(closed_points)
            if abs(max(start[0], end[0]) - x_value) < 1e-6
        )
        if not right_segments:
            right_points = [point for point in points if abs(point[0] - x_value) < 1e-6]
            y_values = tuple(point[1] for point in right_points) or tuple(
                point[1] for point in points
            )
            right_segments = (((x_value, min(y_values)), (x_value, max(y_values))),)
        y_values = tuple(point[1] for segment in right_segments for point in segment)
        line_xs: list[float] = []
        line_ys: list[float] = []
        for start, end in right_segments:
            line_xs.extend([start[0], end[0], float("nan")])
            line_ys.extend([start[1], end[1], float("nan")])
        line = axis.plot(  # type: ignore[attr-defined]
            line_xs,
            line_ys,
            color=self._zone_line_color(zone_name) or "#334155",
            linewidth=1.0,
            alpha=0.0,
            label="_nolegend_",
            zorder=6,
        )[0]
        target = DistanceDragTarget(
            graph_kind=graph_kind,
            zone_name=zone_name,
            column=column,
            row_name=row_name,
            x_value=x_value,
            y_min=min(y_values),
            y_max=max(y_values),
            segments=right_segments,
            line=line,
            zone_line=zone_line,
        )
        if graph_kind == "phase_phase":
            self._distance_phase_phase_drag_targets.append(target)
        else:
            self._distance_phase_ground_drag_targets.append(target)

    def _highlight_distance_drag_target(self, target: DistanceDragTarget | None) -> None:
        if self._distance_drag_hover is target:
            return
        if self._distance_drag_hover is not None:
            line = self._distance_drag_hover.line
            zone_line = self._distance_drag_hover.zone_line
            line.set_linewidth(1.0)  # type: ignore[attr-defined]
            line.set_alpha(0.0)  # type: ignore[attr-defined]
            zone_line.set_linewidth(1.0)  # type: ignore[attr-defined]
        self._distance_drag_hover = target
        if target is not None:
            target.line.set_linewidth(4.0)  # type: ignore[attr-defined]
            target.line.set_alpha(0.0)  # type: ignore[attr-defined]
            target.zone_line.set_linewidth(4.0)  # type: ignore[attr-defined]

    def _find_distance_drag_target(
        self,
        graph_kind: str,
        x_value: float | None,
        y_value: float | None,
    ) -> DistanceDragTarget | None:
        if x_value is None or y_value is None:
            return None
        targets = (
            self._distance_phase_phase_drag_targets
            if graph_kind == "phase_phase"
            else self._distance_phase_ground_drag_targets
        )
        axis = (
            self.distance_phase_phase_panel.axis
            if graph_kind == "phase_phase"
            else self.distance_phase_ground_panel.axis
        )
        x_min, x_max = axis.get_xlim()
        tolerance = max(abs(x_max - x_min) * 0.012, 0.5)
        nearest: DistanceDragTarget | None = None
        nearest_distance = tolerance
        for target in targets:
            if y_value < target.y_min - tolerance or y_value > target.y_max + tolerance:
                continue
            distance = min(
                self._distance_to_segment((x_value, y_value), start, end)
                for start, end in target.segments
            )
            if distance <= nearest_distance:
                nearest = target
                nearest_distance = distance
        return nearest

    @staticmethod
    def _distance_to_segment(
        point: tuple[float, float],
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> float:
        px, py = point
        x1, y1 = start
        x2, y2 = end
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0.0 and dy == 0.0:
            return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        nearest_x = x1 + t * dx
        nearest_y = y1 + t * dy
        return ((px - nearest_x) ** 2 + (py - nearest_y) ** 2) ** 0.5

    def _redraw_distance_graph(self, graph_kind: str) -> None:
        axis = (
            self.distance_phase_phase_panel.axis
            if graph_kind == "phase_phase"
            else self.distance_phase_ground_panel.axis
        )
        limits = self._distance_drag_limits or (axis.get_xlim(), axis.get_ylim())
        if graph_kind == "phase_phase":
            self._plot_distance_phase_phase_zones()
        else:
            self._plot_distance_phase_ground_zones()
        axis = (
            self.distance_phase_phase_panel.axis
            if graph_kind == "phase_phase"
            else self.distance_phase_ground_panel.axis
        )
        axis.set_xlim(*limits[0])
        axis.set_ylim(*limits[1])
        axis.figure.canvas.draw_idle()

    @staticmethod
    def _toolbar_interaction_active(panel: MatplotlibPanel) -> bool:
        mode = str(panel.toolbar.mode).lower()
        return "pan" in mode or "zoom" in mode

    @staticmethod
    def _toolbar_mode_cursor(panel: MatplotlibPanel) -> Qt.CursorShape:
        mode = str(panel.toolbar.mode).lower()
        if "pan" in mode:
            return Qt.CursorShape.OpenHandCursor
        if "zoom" in mode:
            return Qt.CursorShape.CrossCursor
        return Qt.CursorShape.ArrowCursor

    def _connect_distance_drag_handlers(self, graph_kind: str) -> None:
        panel = (
            self.distance_phase_phase_panel
            if graph_kind == "phase_phase"
            else self.distance_phase_ground_panel
        )
        canvas = panel.canvas
        cid_names = (
            (
                "_distance_phase_phase_motion_cid",
                "_distance_phase_phase_press_cid",
                "_distance_phase_phase_release_cid",
            )
            if graph_kind == "phase_phase"
            else (
                "_distance_phase_ground_motion_cid",
                "_distance_phase_ground_press_cid",
                "_distance_phase_ground_release_cid",
            )
        )
        for cid_name in cid_names:
            cid = getattr(self, cid_name)
            if cid is not None:
                canvas.mpl_disconnect(cid)
        tooltip = panel.axis.annotate(
            "",
            xy=(0.0, 0.0),
            xytext=(12, 12),
            textcoords="offset points",
            bbox={"boxstyle": "round,pad=0.35", "fc": "#ffffff", "ec": "#64748b"},
            arrowprops={"arrowstyle": "->", "color": "#64748b"},
        )
        tooltip.set_visible(False)
        point_targets = (
            self._distance_phase_phase_point_targets
            if graph_kind == "phase_phase"
            else self._distance_phase_ground_point_targets
        )

        def show_nearest_point(event) -> bool:  # type: ignore[no-untyped-def]
            if not self._show_point_tooltips or event.xdata is None or event.ydata is None:
                if tooltip.get_visible():
                    tooltip.set_visible(False)
                    canvas.draw_idle()
                return False
            x_min, x_max = panel.axis.get_xlim()
            y_min, y_max = panel.axis.get_ylim()
            tolerance = max(abs(x_max - x_min), abs(y_max - y_min)) * 0.015
            nearest = None
            nearest_distance = tolerance
            for label, x_value, y_value in point_targets:
                distance = ((event.xdata - x_value) ** 2 + (event.ydata - y_value) ** 2) ** 0.5
                if distance <= nearest_distance:
                    nearest = (label, x_value, y_value)
                    nearest_distance = distance
            if nearest is None:
                if tooltip.get_visible():
                    tooltip.set_visible(False)
                    canvas.draw_idle()
                return False
            label, x_value, y_value = nearest
            cast(Any, tooltip).xy = (x_value, y_value)
            tooltip.set_text(
                f"{label}\nr={self._report_number(x_value)}; x={self._report_number(y_value)}"
            )
            tooltip.set_visible(True)
            canvas.draw_idle()
            return True

        def motion(event) -> None:  # type: ignore[no-untyped-def]
            if event.inaxes is not panel.axis:
                self._highlight_distance_drag_target(None)
                canvas.setCursor(self._toolbar_mode_cursor(panel))
                if tooltip.get_visible():
                    tooltip.set_visible(False)
                    canvas.draw_idle()
                return
            if self._toolbar_interaction_active(panel):
                self._highlight_distance_drag_target(None)
                canvas.setCursor(self._toolbar_mode_cursor(panel))
                return
            if self._distance_drag_active is not None:
                target = self._distance_drag_active
                if event.xdata is None:
                    return
                key = self._distance_drag_key(target)
                self._distance_drag_overrides[key] = self._distance_drag_value_from_x(
                    target,
                    float(event.xdata),
                )
                self._set_distance_drag_pending(True)
                self._redraw_distance_graph(target.graph_kind)
                return
            target = self._find_distance_drag_target(graph_kind, event.xdata, event.ydata)
            self._highlight_distance_drag_target(target)
            canvas.setCursor(
                Qt.CursorShape.SizeHorCursor if target is not None else Qt.CursorShape.ArrowCursor
            )
            if target is None:
                show_nearest_point(event)
            elif tooltip.get_visible():
                tooltip.set_visible(False)
            panel.redraw()

        def press(event) -> None:  # type: ignore[no-untyped-def]
            if event.inaxes is not panel.axis or event.button != 1:
                return
            if self._toolbar_interaction_active(panel):
                return
            target = self._find_distance_drag_target(graph_kind, event.xdata, event.ydata)
            if target is None:
                return
            self._distance_drag_active = target
            key = self._distance_drag_key(target)
            self._distance_drag_original_values.setdefault(
                key,
                self._distance_drag_value_from_x(target, target.x_value),
            )
            self._distance_drag_limits = (panel.axis.get_xlim(), panel.axis.get_ylim())
            canvas.setCursor(Qt.CursorShape.SizeHorCursor)

        def release(event) -> None:  # type: ignore[no-untyped-def]
            if self._distance_drag_active is None:
                return
            self._distance_drag_active = None
            self._distance_drag_limits = None
            canvas.setCursor(self._toolbar_mode_cursor(panel))

        setattr(self, cid_names[0], canvas.mpl_connect("motion_notify_event", motion))
        setattr(self, cid_names[1], canvas.mpl_connect("button_press_event", press))
        setattr(self, cid_names[2], canvas.mpl_connect("button_release_event", release))

    def _cancel_distance_drag_changes(self) -> None:
        self._distance_drag_overrides.clear()
        self._distance_drag_original_values.clear()
        self._distance_drag_active = None
        self._distance_drag_limits = None
        self._set_distance_drag_pending(False)
        self._plot_distance_phase_phase_zones()
        self._plot_distance_phase_ground_zones()

    def _apply_distance_drag_changes(self) -> None:
        if not self._distance_drag_overrides:
            self._set_distance_drag_pending(False)
            return
        for (graph_kind, column), value in sorted(self._distance_drag_overrides.items()):
            row_name = "RPFF" if graph_kind == "phase_phase" else "RFPE"
            self.source_data_widget.set_setting_number(row_name, column, value)
        self._distance_drag_overrides.clear()
        self._distance_drag_original_values.clear()
        self._distance_drag_active = None
        self._set_distance_drag_pending(False)
        self._clear_results(update_lock=True)
        self._calculate_all()

    def _plot_distance_phase_phase_zones(self) -> None:
        if self._last_result is None:
            axis = self.distance_phase_phase_panel.axis
            axis.clear()
            configure_rx_axes(axis, self._phase_phase_distance_labels())
            self.distance_phase_phase_panel.redraw()
            return
        raw_stages = [
            self._stage_with_distance_override(stage, "phase_phase")
            for stage in self.source_data_widget.phase_phase_stage_inputs()
        ]
        stages = [self._phase_phase_stage_input(stage) for stage in raw_stages]
        zones = phase_phase_zone_polygons(stages)
        for zone in zones:
            self._distance_phase_phase_zone_visibility.setdefault(zone.name, True)
        axis = self.distance_phase_phase_panel.axis
        axis.clear()
        configure_rx_axes(axis, self._phase_phase_distance_labels())
        line_by_label = {}
        self._distance_phase_phase_point_targets = []
        self._distance_phase_phase_drag_targets = []
        for raw_stage, zone in zip(raw_stages, zones, strict=False):
            xs = [point[0] for point in zone.points]
            ys = [point[1] for point in zone.points]
            line = axis.plot(
                xs,
                ys,
                linewidth=1.0,
                label=zone.name,
                color=self._zone_line_color(zone.name),
            )[0]
            visible = self._distance_phase_phase_zone_visibility.get(zone.name, True)
            line.set_visible(visible)
            fill = axis.fill(
                xs,
                ys,
                color=line.get_color(),
                alpha=0.12,
                linewidth=0,
                label="_nolegend_",
            )[0]
            fill.set_visible(visible)
            line_by_label[zone.name] = line
            if visible:
                self._register_distance_drag_target(
                    "phase_phase",
                    zone.name,
                    self._stage_column(raw_stage),
                    "RPFF",
                    zone.points,
                    axis,
                    line,
                )
                axis.scatter(xs, ys, s=10, zorder=4, label="_nolegend_")
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
        overlay_colors: dict[str, object] = {}
        plotted_overlay_labels: set[str] = set()
        for label, points in self._distance_ld_overlays():
            self._distance_phase_phase_zone_visibility.setdefault(label, True)
            xs = [point[1] for point in points]
            ys = [point[2] for point in points]
            color = overlay_colors.get(label) or self._zone_line_color(label)
            line = axis.plot(
                xs,
                ys,
                linewidth=1.0,
                linestyle=self._zone_line_style(label),
                label=self._legend_label_for_group(label, plotted_overlay_labels),
                color=color,
            )[0]
            overlay_colors.setdefault(label, line.get_color())
            visible = self._distance_phase_phase_zone_visibility.get(label, True)
            line.set_visible(visible)

            line_by_label[label] = line
            if visible:
                axis.scatter(xs, ys, s=9, zorder=4, label="_nolegend_")
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
        self._shade_rld_regions(
            axis,
            self._distance_ld_overlays(),
            self._distance_phase_phase_zone_visibility,
        )
        legend = axis.legend(loc="upper left") if self._show_legends and line_by_label else None
        if legend is not None:
            for legend_line, text in zip(legend.get_lines(), legend.get_texts(), strict=False):
                label = text.get_text()
                visible = self._legend_group_visible(
                    label,
                    line_by_label,
                    self._distance_phase_phase_zone_visibility,
                )
                legend_line.set_picker(8)
                text.set_picker(True)
                legend_line.set_alpha(1.0 if visible else 0.25)
                text.set_alpha(1.0 if visible else 0.35)
                legend_line._rel_psd_zone_label = label  # type: ignore[attr-defined]
                text._rel_psd_zone_label = label  # type: ignore[attr-defined]
        self._connect_distance_phase_phase_legend_picker(line_by_label)
        self._connect_distance_drag_handlers("phase_phase")
        self.distance_phase_phase_panel.redraw()

    def _plot_distance_phase_ground_zones(self) -> None:
        if self._last_result is None:
            axis = self.distance_phase_ground_panel.axis
            axis.clear()
            configure_rx_axes(axis, self._phase_ground_distance_labels())
            self.distance_phase_ground_panel.redraw()
            return
        raw_stages = [
            self._stage_with_distance_override(stage, "phase_ground")
            for stage in self.source_data_widget.phase_ground_stage_inputs()
        ]
        stages = [self._phase_ground_stage_input(stage) for stage in raw_stages]
        zones = phase_ground_zone_polygons(stages)
        for zone in zones:
            self._distance_phase_ground_zone_visibility.setdefault(zone.name, True)
        axis = self.distance_phase_ground_panel.axis
        axis.clear()
        configure_rx_axes(axis, self._phase_ground_distance_labels())
        line_by_label = {}
        self._distance_phase_ground_point_targets = []
        self._distance_phase_ground_drag_targets = []
        for raw_stage, zone in zip(raw_stages, zones, strict=False):
            xs = [point[0] for point in zone.points]
            ys = [point[1] for point in zone.points]
            line = axis.plot(
                xs,
                ys,
                linewidth=1.0,
                label=zone.name,
                color=self._zone_line_color(zone.name),
            )[0]
            visible = self._distance_phase_ground_zone_visibility.get(zone.name, True)
            line.set_visible(visible)
            fill = axis.fill(
                xs,
                ys,
                color=line.get_color(),
                alpha=0.12,
                linewidth=0,
                label="_nolegend_",
            )[0]
            fill.set_visible(visible)
            line_by_label[zone.name] = line
            if visible:
                self._register_distance_drag_target(
                    "phase_ground",
                    zone.name,
                    self._stage_column(raw_stage),
                    "RFPE",
                    zone.points,
                    axis,
                    line,
                )
                axis.scatter(xs, ys, s=10, zorder=4, label="_nolegend_")
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
        overlay_colors: dict[str, object] = {}
        plotted_overlay_labels: set[str] = set()
        for label, points in self._distance_ld_overlays():
            self._distance_phase_ground_zone_visibility.setdefault(label, True)
            xs = [point[1] for point in points]
            ys = [point[2] for point in points]
            color = overlay_colors.get(label) or self._zone_line_color(label)
            line = axis.plot(
                xs,
                ys,
                linewidth=1.0,
                linestyle=self._zone_line_style(label),
                label=self._legend_label_for_group(label, plotted_overlay_labels),
                color=color,
            )[0]
            overlay_colors.setdefault(label, line.get_color())
            visible = self._distance_phase_ground_zone_visibility.get(label, True)
            line.set_visible(visible)
            fill = axis.fill(
                xs,
                ys,
                color=line.get_color(),
                alpha=0.10,
                linewidth=0,
                label="_nolegend_",
            )[0]
            fill.set_visible(visible)
            line_by_label[label] = line
            if visible:
                axis.scatter(xs, ys, s=9, zorder=4, label="_nolegend_")
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
        self._shade_rld_regions(
            axis,
            self._distance_ld_overlays(),
            self._distance_phase_ground_zone_visibility,
        )
        legend = axis.legend(loc="upper left") if self._show_legends and line_by_label else None
        if legend is not None:
            for legend_line, text in zip(legend.get_lines(), legend.get_texts(), strict=False):
                label = text.get_text()
                visible = self._legend_group_visible(
                    label,
                    line_by_label,
                    self._distance_phase_ground_zone_visibility,
                )
                legend_line.set_picker(8)
                text.set_picker(True)
                legend_line.set_alpha(1.0 if visible else 0.25)
                text.set_alpha(1.0 if visible else 0.35)
                legend_line._rel_psd_zone_label = label  # type: ignore[attr-defined]
                text._rel_psd_zone_label = label  # type: ignore[attr-defined]
        self._connect_distance_phase_ground_legend_picker(line_by_label)
        self._connect_distance_drag_handlers("phase_ground")
        self.distance_phase_ground_panel.redraw()

    def _connect_psd_phase_phase_legend_picker(self, line_by_label: dict[str, object]) -> None:
        canvas = self.psd_phase_phase_panel.canvas
        if self._psd_phase_phase_pick_cid is not None:
            canvas.mpl_disconnect(self._psd_phase_phase_pick_cid)

        def toggle_zone(event) -> None:  # type: ignore[no-untyped-def]
            label = getattr(event.artist, "_rel_psd_zone_label", None)
            if not isinstance(label, str):
                return
            members = self._legend_group_members(label, line_by_label)
            if not members:
                return
            current = any(self._psd_phase_phase_zone_visibility.get(member, True) for member in members)
            for member in members:
                self._psd_phase_phase_zone_visibility[member] = not current
            self._plot_psd_phase_phase_zones()

        self._psd_phase_phase_pick_cid = canvas.mpl_connect("pick_event", toggle_zone)

    def _connect_psd_phase_phase_point_tooltip(self) -> None:
        canvas = self.psd_phase_phase_panel.canvas
        if self._psd_phase_phase_motion_cid is not None:
            canvas.mpl_disconnect(self._psd_phase_phase_motion_cid)
        if not self._show_point_tooltips:
            self._psd_phase_phase_motion_cid = None
            return
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
            cast(Any, tooltip).xy = (x_value, y_value)
            tooltip.set_text(
                f"{label}\nr={self._report_number(x_value)}; x={self._report_number(y_value)}"
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
            if not isinstance(label, str):
                return
            members = self._legend_group_members(label, line_by_label)
            if not members:
                return
            current = any(self._psd_phase_ground_zone_visibility.get(member, True) for member in members)
            for member in members:
                self._psd_phase_ground_zone_visibility[member] = not current
            self._plot_psd_phase_ground_zones()

        self._psd_phase_ground_pick_cid = canvas.mpl_connect("pick_event", toggle_zone)

    def _connect_psd_phase_ground_point_tooltip(self) -> None:
        canvas = self.psd_phase_ground_panel.canvas
        if self._psd_phase_ground_motion_cid is not None:
            canvas.mpl_disconnect(self._psd_phase_ground_motion_cid)
        if not self._show_point_tooltips:
            self._psd_phase_ground_motion_cid = None
            return
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
            cast(Any, tooltip).xy = (x_value, y_value)
            tooltip.set_text(
                f"{label}\nr={self._report_number(x_value)}; x={self._report_number(y_value)}"
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
            if not isinstance(label, str):
                return
            members = self._legend_group_members(label, line_by_label)
            if not members:
                return
            current = any(
                self._distance_phase_phase_zone_visibility.get(member, True)
                for member in members
            )
            for member in members:
                self._distance_phase_phase_zone_visibility[member] = not current
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
            if not isinstance(label, str):
                return
            members = self._legend_group_members(label, line_by_label)
            if not members:
                return
            current = any(
                self._distance_phase_ground_zone_visibility.get(member, True)
                for member in members
            )
            for member in members:
                self._distance_phase_ground_zone_visibility[member] = not current
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
        if not self._show_point_tooltips:
            return 0
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
            cast(Any, tooltip).xy = (x_value, y_value)
            tooltip.set_text(
                f"{label}\nr={self._report_number(x_value)}; x={self._report_number(y_value)}"
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

    def _shade_rld_regions(
        self,
        axis,  # type: ignore[no-untyped-def]
        overlays: list[OverlayPolygon],
        visibility: dict[str, bool],
    ) -> None:
        for cid in getattr(axis, "_rel_rld_extension_cids", []):
            axis.callbacks.disconnect(cid)
        axis._rel_rld_extension_cids = []  # type: ignore[attr-defined]

        groups: dict[str, tuple[OverlayPoint, ...]] = {}
        group_colors: dict[str, str] = {}
        for label, points in overlays:
            if not (label.startswith("RLD ") or label.startswith("Ld ")):
                continue
            if not visibility.get(label, True):
                continue
            if not points:
                continue
            average_x = sum(point[1] for point in points) / len(points)
            direction = "fw" if average_x >= 0.0 else "rv"
            kind = "inner" if "inner" in label else "outer"
            group_key = f"{kind}_{direction}"
            groups[group_key] = points
            group_colors[group_key] = self._zone_line_color(label) or "#16697a"

        dynamic_edge_fills: list[tuple[Polygon, tuple[OverlayPoint, ...], str]] = []
        dynamic_gap_fills: list[
            tuple[Polygon, tuple[OverlayPoint, ...], tuple[OverlayPoint, ...]]
        ] = []
        dynamic_extension_lines: list[tuple[Line2D, OverlayPoint, OverlayPoint]] = []
        x_min, x_max = axis.get_xlim()
        for direction in ("fw", "rv"):
            outer = groups.get(f"outer_{direction}")
            inner = groups.get(f"inner_{direction}")
            color = (
                group_colors.get(f"outer_{direction}")
                or group_colors.get(f"inner_{direction}")
                or "#16697a"
            )
            if outer is not None:
                outer_path = self._points_top_to_bottom(outer)
                edge_x = x_max if direction == "fw" else x_min
                edge_polygon_x = [point[1] for point in outer_path] + [edge_x, edge_x]
                edge_polygon_y = [point[2] for point in outer_path] + [
                    outer_path[-1][2],
                    outer_path[0][2],
                ]
                fill = axis.fill(
                    edge_polygon_x,
                    edge_polygon_y,
                    color=color,
                    alpha=0.10,
                    linewidth=0,
                    label="_nolegend_",
                    zorder=0,
                )[0]
                dynamic_edge_fills.append((fill, outer, direction))
            if outer is not None and inner is not None:
                outer_path = self._points_top_to_bottom(outer)
                inner_path = self._points_top_to_bottom(inner)
                gap_fill = axis.fill(
                    [point[1] for point in outer_path]
                    + [point[1] for point in reversed(inner_path)],
                    [point[2] for point in outer_path]
                    + [point[2] for point in reversed(inner_path)],
                    color=color,
                    alpha=0.18,
                    linewidth=0,
                    label="_nolegend_",
                    zorder=0,
                )[0]
                dynamic_gap_fills.append((gap_fill, outer, inner))
            for points, linestyle in ((outer, "-"), (inner, "--")):
                if points is None or len(points) < 4:
                    continue
                top_outer, top_inner, bottom_outer, bottom_inner = self._load_cut_boundary_segments(points)
                for outer_point, inner_point in (
                    (top_outer, top_inner),
                    (bottom_outer, bottom_inner),
                ):
                    line = axis.plot(
                        [],
                        [],
                        color=color,
                        linestyle=linestyle,
                        linewidth=1.0,
                        label="_nolegend_",
                        zorder=2,
                    )[0]
                    dynamic_extension_lines.append((line, outer_point, inner_point))

        def update_dynamic_rld_edges(_axis=axis) -> None:  # type: ignore[no-untyped-def]
            x_min_current, x_max_current = _axis.get_xlim()
            for fill, points, direction in dynamic_edge_fills:
                edge_x = x_max_current if direction == "fw" else x_min_current
                top_outer, top_inner, bottom_outer, bottom_inner = self._load_cut_boundary_segments(points)
                top_end = self._extend_line_to_axis_edge(_axis, top_outer, top_inner)
                bottom_end = self._extend_line_to_axis_edge(_axis, bottom_outer, bottom_inner)
                path = self._points_top_to_bottom(points)
                xs = [point[1] for point in path] + [bottom_end[0], edge_x, edge_x, top_end[0]]
                ys = [point[2] for point in path] + [bottom_end[1], bottom_end[1], top_end[1], top_end[1]]
                fill.set_xy(list(zip(xs, ys, strict=False)))
            for fill, outer, inner in dynamic_gap_fills:
                outer_top, outer_top_inner, outer_bottom, outer_bottom_inner = (
                    self._load_cut_boundary_segments(outer)
                )
                inner_top, inner_top_inner, inner_bottom, inner_bottom_inner = (
                    self._load_cut_boundary_segments(inner)
                )
                outer_top_end = self._extend_line_to_axis_edge(_axis, outer_top, outer_top_inner)
                outer_bottom_end = self._extend_line_to_axis_edge(_axis, outer_bottom, outer_bottom_inner)
                inner_top_end = self._extend_line_to_axis_edge(_axis, inner_top, inner_top_inner)
                inner_bottom_end = self._extend_line_to_axis_edge(_axis, inner_bottom, inner_bottom_inner)
                outer_path = self._points_top_to_bottom(outer)
                inner_path = self._points_top_to_bottom(inner)
                xs = (
                    [outer_top_end[0]]
                    + [point[1] for point in outer_path]
                    + [outer_bottom_end[0], inner_bottom_end[0]]
                    + [point[1] for point in reversed(inner_path)]
                    + [inner_top_end[0]]
                )
                ys = (
                    [outer_top_end[1]]
                    + [point[2] for point in outer_path]
                    + [outer_bottom_end[1], inner_bottom_end[1]]
                    + [point[2] for point in reversed(inner_path)]
                    + [inner_top_end[1]]
                )
                fill.set_xy(list(zip(xs, ys, strict=False)))
            for line, outer_point, inner_point in dynamic_extension_lines:
                end_x, end_y = self._extend_line_to_axis_edge(_axis, outer_point, inner_point)
                line.set_data([outer_point[1], end_x], [outer_point[2], end_y])

        update_dynamic_rld_edges()
        axis._rel_rld_extension_cids = [  # type: ignore[attr-defined]
            axis.callbacks.connect("xlim_changed", update_dynamic_rld_edges),
            axis.callbacks.connect("ylim_changed", update_dynamic_rld_edges),
        ]

    def _shade_psd_gap_regions(
        self,
        axis,  # type: ignore[no-untyped-def]
        overlays: list[OverlayPolygon],
        visibility: dict[str, bool],
    ) -> None:
        if not visibility.get("PSD inner", True) or not visibility.get("PSD outer", True):
            return
        inner = next((points for label, points in overlays if label == "PSD inner"), None)
        outer = next((points for label, points in overlays if label == "PSD outer"), None)
        if inner is None or outer is None:
            return
        color = self._zone_line_color("PSD outer") or "#16697a"
        xs = [point[1] for point in outer] + [point[1] for point in reversed(inner)]
        ys = [point[2] for point in outer] + [point[2] for point in reversed(inner)]
        axis.fill(
            xs,
            ys,
            color=color,
            alpha=0.18,
            linewidth=0,
            label="_nolegend_",
            zorder=0,
        )

    def _points_top_to_bottom(self, points: tuple[OverlayPoint, ...]) -> tuple[OverlayPoint, ...]:
        ordered = tuple(points)
        if ordered and ordered[0][2] < ordered[-1][2]:
            return tuple(reversed(ordered))
        return ordered

    def _load_cut_boundary_segments(
        self,
        points: tuple[OverlayPoint, ...],
    ) -> tuple[OverlayPoint, OverlayPoint, OverlayPoint, OverlayPoint]:
        top_outer = max(points, key=lambda point: point[2])
        bottom_outer = min(points, key=lambda point: point[2])

        def nearest_inner(outer: OverlayPoint) -> OverlayPoint:
            candidates = [
                point
                for point in points
                if point is not outer and abs(point[1]) < abs(outer[1]) - 1e-9
            ]
            if not candidates:
                candidates = [
                    point
                    for point in points
                    if point is not outer and abs(point[1]) <= abs(outer[1]) + 1e-9
                ]
            if not candidates:
                candidates = [point for point in points if point is not outer]
            return min(
                candidates,
                key=lambda point: abs(point[2] - outer[2]),
            )

        return top_outer, nearest_inner(top_outer), bottom_outer, nearest_inner(bottom_outer)

    def _extend_line_to_axis_edge(
        self,
        axis,  # type: ignore[no-untyped-def]
        outer_point: OverlayPoint,
        inner_point: OverlayPoint,
    ) -> tuple[float, float]:
        x_min, x_max = axis.get_xlim()
        y_min, y_max = axis.get_ylim()
        x0 = float(outer_point[1])
        y0 = float(outer_point[2])
        dx = float(outer_point[1] - inner_point[1])
        dy = float(outer_point[2] - inner_point[2])
        candidates: list[float] = []
        if abs(dx) > 1e-12:
            candidates.extend(
                value
                for value in ((x_min - x0) / dx, (x_max - x0) / dx)
                if value > 1e-9
            )
        if abs(dy) > 1e-12:
            candidates.extend(
                value
                for value in ((y_min - y0) / dy, (y_max - y0) / dy)
                if value > 1e-9
            )
        for scale in sorted(candidates):
            x_value = x0 + dx * scale
            y_value = y0 + dy * scale
            if (
                x_min - 1e-9 <= x_value <= x_max + 1e-9
                and y_min - 1e-9 <= y_value <= y_max + 1e-9
            ):
                return x_value, y_value
        return x0, y0

    def _build_zone_construction_report(self) -> str:
        phase_phase_stages = [
            self._phase_phase_stage_input(stage)
            for stage in self.source_data_widget.phase_phase_stage_inputs()
        ]
        phase_phase_zones = phase_phase_zone_polygons(phase_phase_stages)
        include_phase_ground = self.source_data_widget.protection_type_combo.currentIndex() == 0
        phase_ground_stages = (
            [
                self._phase_ground_stage_input(stage)
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
        if self._last_phs_result is not None:
            sections.append(self._phs_journal_report())
            sections.append("<h3>Координати PHS для 2ф КЗ</h3>")
            sections.append(self._phs_phase_phase_2ph_coordinate_report(self._last_phs_result))
            sections.append("<h3>Координати зон Ld на графіках PHS</h3>")
            sections.append(self._phs_ld_coordinate_report(self._last_phs_result))
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
        self._report_table_counter = 0
        self._report_table_refs: dict[str, int] = {}

        sections = [
            f"<h2>{self._html(t('report.psd_engineering_title'))}</h2>",
            f"<p>{self._html(t('report.psd_engineering_intro'))}</p>",
            f"<h3>{self._html(t('report.psd_input_data'))}</h3>",
            self._protection_settings_report_table(result),
            f"<p style='margin-bottom: 14px;'>{self._math_html(t('report.psd_sensitivity_used', value=k))}</p>",
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
            [self._translator.text("source.sensitivity_factor_psd"), self._report_optional_number(result.sensitivity_factor), "в.о."],
            [self._translator.text("source.sensitivity_factor_phs"), widget.phs_sensitivity_factor.text(), "в.о."],
            [self._translator.text("source.max_psd_time"), widget.max_psd_time.text(), "с"],
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

    def _phs_report_graphs_html(self) -> str:
        items = [
            (self._translator.text("phs.phase_phase_2ph"), self.phs_phase_phase_2ph_panel),
            (self._translator.text("phs.phase_phase_3ph"), self.phs_phase_phase_3ph_panel),
            (self._translator.text("phs.phase_ground"), self.phs_phase_ground_panel),
            (self._translator.text("phs.load_cut"), self.phs_load_cut_panel),
        ]
        html = ["<h3>Графіки PHS</h3>"]
        for title, panel in items:
            uri = self._figure_data_uri(panel)
            html.append(f"<p><b>{self._html(title)}</b></p>")
            html.append(
                f"<p><img src='{uri}' width='680' alt='{self._html(title)}' /></p>"
            )
        return "\n".join(html)

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
            ("X1", lambda stage: self._report_optional_number(self._stage_float(stage, "x1"))),
            ("R1", lambda stage: self._report_optional_number(self._stage_float(stage, "r1"))),
            ("X0", lambda stage: self._report_optional_number(self._stage_float(stage, "x0"))),
            ("R0", lambda stage: self._report_optional_number(self._stage_float(stage, "r0"))),
            (
                "RFPP",
                lambda stage: self._report_optional_number(
                    self._stage_float_any(stage, "rfpp", "rpff")
                ),
            ),
            ("RFPE", lambda stage: self._report_optional_number(self._stage_float(stage, "rfpe"))),
            (
                "ArgNegRes",
                lambda stage: self._report_optional_number(
                    self._stage_float(stage, "arg_neg_res_deg")
                ),
            ),
            (
                "ArgDir",
                lambda stage: self._report_optional_number(
                    self._stage_float(stage, "arg_dir_deg")
                ),
            ),
            (
                "t, c",
                lambda stage: self._report_optional_number(
                    self._stage_optional_float(stage, "time_sec")
                ),
            ),
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
                ],
                [
                    ["X1InFw", self._report_value_with_unit(result.x1_in_fw, "Ом")],
                    ["R1FInFw", self._report_value_with_unit(result.r1f_in_fw, "Ом")],
                    ["X1InRv", self._report_value_with_unit(result.x1_in_rv, "Ом")],
                    ["R1FInRv", self._report_value_with_unit(result.r1f_in_rv, "Ом")],
                    ["R1LIn", self._report_value_with_unit(result.r1l_in, "Ом")],
                    ["RLdOutFw", self._report_value_with_unit(result.rld_out_fw, "Ом")],
                    ["RLdOutRv", self._report_value_with_unit(result.rld_out_rv, "Ом")],
                    ["ArgLd", self._report_value_with_unit(result.arg_ld_deg, "град")],
                    ["KLdFw", self._report_value_with_unit(result.kld_fw, "в.о.")],
                    ["KLdRv", self._report_value_with_unit(result.kld_rv, "в.о.")],
                ],
            )
        )

    def _phs_journal_report(self, *, include_heading: bool = True) -> str:
        result = self._last_phs_result
        if result is None:
            return ""
        return (
            ("<h2>PHS</h2>" if include_heading else "")
            + self._report_table_title("Прийняті уставки PHS")
            + self._simple_table(
                ["Назва", "Уставка"],
                [
                    ["INBlockPP", self._report_value_with_unit(result.inblock_pp, "А")],
                    ["INBlockPE", self._report_value_with_unit(result.inblock_pe, "А")],
                    ["RLd Fw", self._report_value_with_unit(result.rld_fw, "Ом")],
                    ["RLd Rv", self._report_value_with_unit(result.rld_rv, "Ом")],
                    ["ArgLd", self._report_value_with_unit(result.arg_ld, "град")],
                    ["X1", self._report_value_with_unit(result.x1, "Ом")],
                    ["X0", self._report_value_with_unit(result.x0, "Ом")],
                    ["RFFwPP", self._report_value_with_unit(result.rffw_pp, "Ом")],
                    ["RFRvPP", self._report_value_with_unit(result.rfrv_pp, "Ом")],
                    ["RFFw PE", self._report_value_with_unit(result.rffw_pe, "Ом")],
                    ["RFRv PE", self._report_value_with_unit(result.rfrv_pe, "Ом")],
                ],
            )
        )

    def _phs_input_tables(self, result: PhsSelectorResult) -> str:
        stage = result.stage
        load_cut = self._load_cut_input(self.source_data_widget.load_cut_inputs())
        parts = [
            "<p>"
            + self._math_html(
                "Параметри налаштування PHS прийнято такими: "
                f"KчPHS = {self._report_value_with_unit(result.phs_sensitivity_factor, 'в.о.')}; "
                f"Kвід = {self._report_value_with_unit(load_cut.rejection_factor, 'в.о.')}; "
                f"∆φ = {self._report_value_with_unit(load_cut.delta_phi_deg, 'град')}."
            ),
            "</p>",
            self._report_table_title("Уставки чутливого ступеня PHS")
            + self._simple_table(
                ["Назва", stage.name],
                [
                    ["X1Zm", self._report_value_with_unit(stage.x1, "Ом")],
                    ["R1Zm", self._report_value_with_unit(stage.r1, "Ом")],
                    ["X0Zm", self._report_value_with_unit(stage.x0, "Ом")],
                    ["R0Zm", self._report_value_with_unit(stage.r0, "Ом")],
                    ["RFPPZm", self._report_value_with_unit(stage.rfpp, "Ом")],
                    ["RFPEZm", self._report_value_with_unit(stage.rfpe, "Ом")],
                    ["ArgDir", self._report_value_with_unit(stage.arg_dir_deg, "град")],
                    ["ArgNegRes", self._report_value_with_unit(stage.arg_neg_res_deg, "град")],
                    ["Fлк", self._report_value_with_unit(stage.load_angle_ground_deg, "град")],
                ],
            ),
            self._report_table_title("Параметри навантаження PHS")
            + self._load_modes_report_table()
            + self._report_table_title("Опори навантаження PHS")
            + self._simple_table(
                [
                    self._translator.text("source.direction"),
                    "Rнав",
                    "Xнав",
                    "RLd",
                    "Fнав",
                ],
                [
                    [
                        "Fw",
                        self._report_value_with_unit(load_cut.r_load_fw, "Ом"),
                        self._report_value_with_unit(load_cut.x_load_fw, "Ом"),
                        self._report_value_with_unit(result.rld_fw_load, "Ом"),
                        self._report_value_with_unit(self._load_angle_for_report(load_cut.r_load_fw, load_cut.x_load_fw), "град"),
                    ],
                    [
                        "Rv",
                        self._report_value_with_unit(load_cut.r_load_rv, "Ом"),
                        self._report_value_with_unit(load_cut.x_load_rv, "Ом"),
                        self._report_value_with_unit(result.rld_rv_load, "Ом"),
                        self._report_value_with_unit(self._load_angle_for_report(load_cut.r_load_rv, load_cut.x_load_rv), "град"),
                    ],
                ],
            ),
        ]
        if result.use_psd_zone and self._last_psb_blocking_result is not None:
            psd = self._last_psb_blocking_result
            parts.append(
                self._report_table_title("Уставки PSD для розрахунку PHS")
                + self._simple_table(
                    ["Назва", "Уставка"],
                    [
                        ["ArgLdPSD", self._report_value_with_unit(psd.arg_ld_deg, "град")],
                        ["KLdFwPSD", self._report_value_with_unit(psd.kld_fw, "в.о.")],
                        ["KLdRvPSD", self._report_value_with_unit(psd.kld_rv, "в.о.")],
                        ["RLdOutFwPSD", self._report_value_with_unit(psd.rld_out_fw, "Ом")],
                        ["RLdOutRvPSD", self._report_value_with_unit(psd.rld_out_rv, "Ом")],
                    ],
                )
            )
        return "".join(parts)

    def _report_value_with_unit(self, value: float | None, unit: str) -> str:
        return f"{self._report_optional_number(value)} {unit}"

    def _load_angle_for_report(self, r_value: float | None, x_value: float | None) -> float | None:
        if r_value in (None, 0.0) or x_value is None:
            return None
        return abs(atan(x_value / r_value) * 180.0 / pi)

    def _phs_formula_sources_text(self, formula: str) -> str:
        settings_ref = "п. Вихідні дані"
        stage_ref = self._table_reference("Уставки чутливого ступеня PHS")
        load_ref = self._table_reference("Опори навантаження PHS")
        psd_ref = self._table_reference("Уставки PSD для розрахунку PHS")
        sources: list[str] = []
        for token in ("KчPHS", "Kвід", "∆φ"):
            if token in formula:
                sources.append(f"{token} - {settings_ref}")
        for token in (
            "X1Zm",
            "R1Zm",
            "X0Zm",
            "R0Zm",
            "RFPPZm",
            "RFPEZm",
            "ArgDir",
            "ArgNegRes",
            "Fлк",
        ):
            if token in formula:
                sources.append(f"{token} - {stage_ref}")
        for token in ("RнавFw", "RнавRv", "Fнав"):
            if token in formula:
                sources.append(f"{token} - {load_ref}")
        for token in ("ArgLdPSD", "KLdFwPSD", "KLdRvPSD", "RLdOutFwPSD", "RLdOutRvPSD"):
            if token in formula:
                sources.append(f"{token} - {psd_ref}")
        if not sources:
            return self._translator.text("report.formula_sources_none")
        return self._translator.text(
            "report.formula_sources",
            sources="; ".join(dict.fromkeys(sources)),
        )

    def _phs_engineering_calculation_line(
        self,
        name: str,
        formula: str,
        substituted: str,
        value: float | None,
        unit: str,
    ) -> str:
        return (
            f"{self._math_html(name)} = {self._math_html(formula)} = "
            f"{self._html(substituted)} = "
            f"{self._html(self._report_optional_number(value))} ({self._html(unit)})"
            f"<br/><span>{self._math_html(self._phs_formula_sources_text(formula))}</span>"
        )

    def _phs_selection_block(
        self,
        name: str,
        conditions: list[tuple[str, list[str]]],
        compared_values: list[float | None],
        final_value: float | None,
        unit: str,
        *,
        selection_rule: str,
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
            for line in lines:
                formula_part, _, source_part = line.partition("<br/>")
                condition_parts.append(
                    f"<p style='margin: 6px 0 2px 28px;'>{formula_part}</p>"
                    f"<p style='margin: 0 0 12px 46px;'>{source_part}</p>"
                )
        final_value_text = self._html(self._report_optional_number(final_value))
        final_value_html = (
            f"<b>{final_value_text}</b>" if len(values) > 1 else final_value_text
        )
        return (
            "<li>"
            f"<p><b>{self._math_html(self._translator.text('report.psd_setting_choice', name=name))}</b></p>"
            + "\n".join(condition_parts)
            + "<p>"
            f"Вибирається {self._html(selection_rule)} зі значень ({self._html(values_text)}): "
            f"{final_value_html} ({self._html(unit)})."
            + "</p>"
            "</li>"
        )

    def _build_phs_report(self) -> str:
        result = self._last_phs_result
        if result is None:
            return "<h2>PHS</h2><p>Дані для розрахунку відсутні.</p>"
        n = self._report_optional_number
        k = result.phs_sensitivity_factor
        stage = result.stage
        load_cut = self._load_cut_input(self.source_data_widget.load_cut_inputs())
        f_load_fw = self._load_angle_for_report(load_cut.r_load_fw, load_cut.x_load_fw)
        f_load_rv = self._load_angle_for_report(load_cut.r_load_rv, load_cut.x_load_rv)
        self._report_table_counter = 0
        self._report_table_refs = {}

        sections = [
            "<h2>Розрахунок уставок фазового селектора PHS</h2>",
            "<p>Розрахунок виконано за уставками чутливого прямого ступеня "
            f"{self._html(stage.name)}. Усі тригонометричні функції у розрахунку "
            "виконуються з переведенням кутів із градусів у радіани; у звіті кути "
            "наведені у градусах.</p>",
            "<h3>Вихідні дані</h3>",
            self._phs_input_tables(result),
            "<h3>Вибір уставок фазового селектора</h3>",
            "<ol>",
            self._phs_selection_block(
                "X1",
                [
                    (
                        "З умови забезпечення чутливості до 1ф КЗ на землю і 2ф КЗ у кінці ПЛ, що захищається.",
                        [
                            self._phs_engineering_calculation_line(
                                "X1",
                                "KчPHS*X1Zm",
                                f"{n(k)}*{n(stage.x1)}",
                                result.x1_ground_fault,
                                "Ом",
                            )
                        ],
                    ),
                    (
                        "При 3ф КЗ для направлених вперед ступенів: по охопленню ступеня в I чверті.",
                        [
                            self._phs_engineering_calculation_line(
                                "X1",
                                "KчPHS*(X1Zm*2/SQRT(3))",
                                f"{n(k)}*({n(stage.x1)}*2/SQRT(3))",
                                result.x1_three_phase_q1,
                                "Ом",
                            ),
                        ],
                    ),
                    (
                        "При 3ф КЗ для направлених вперед ступенів: по охопленню ступеня в IV чверті.",
                        [
                            self._phs_engineering_calculation_line(
                                "X1",
                                "KчPHS*(RFPPZm/(2*cosArgDir)*sin(30+ArgDir))",
                                f"{n(k)}*({n(stage.rfpp)}/(2*cos({n(stage.arg_dir_deg)}))*sin(30+{n(stage.arg_dir_deg)}))",
                                result.x1_three_phase_q4,
                                "Ом",
                            ),
                        ],
                    ),
                ],
                [result.x1_ground_fault, result.x1_three_phase_q1, result.x1_three_phase_q4],
                result.x1,
                "Ом",
                selection_rule="максимальне значення",
            ),
            self._phs_selection_block(
                "X0",
                [
                    (
                        "З умови забезпечення чутливості до 1ф КЗ у кінці ПЛ, що захищається.",
                        [
                            self._phs_engineering_calculation_line(
                                "X0",
                                "KчPHS*X0Zm",
                                f"{n(k)}*{n(stage.x0)}",
                                result.x0,
                                "Ом",
                            )
                        ],
                    )
                ],
                [result.x0],
                result.x0,
                "Ом",
                selection_rule="розраховане значення",
            ),
            self._phs_selection_block(
                "RFRv PE",
                [
                    (
                        "З умови перетину з лінією напрямленості у II чверті.",
                        [
                            self._phs_engineering_calculation_line(
                                "RFRv PE",
                                "KчPHS*(X1Zm+(X0Zm-X1Zm)/3)*tg(ArgNegRes-90)",
                                f"{n(k)}*({n(stage.x1)}+({n(stage.x0)}-{n(stage.x1)})/3)"
                                f"*tg({n(stage.arg_neg_res_deg)}-90)",
                                result.rfrv_pe,
                                "Ом",
                            )
                        ],
                    )
                ],
                [result.rfrv_pe],
                result.rfrv_pe,
                "Ом",
                selection_rule="розраховане значення",
            ),
            self._phs_selection_block(
                "RFFw PE",
                [
                    (
                        "З умови забезпечення чутливості до однофазних КЗ для прямого напрямку.",
                        [
                            self._phs_engineering_calculation_line(
                                "RFFw PE",
                                "KчPHS*RFPEZm"
                                if (stage.load_angle_ground_deg or 0.0) > 60.0
                                else "KчPHS*2*((R0Zm+2*R1Zm)/3+RFPEZm-(X0Zm+2*X1Zm)*ctg60/3)",
                                (
                                    f"{n(k)}*{n(stage.rfpe)}"
                                    if (stage.load_angle_ground_deg or 0.0) > 60.0
                                    else f"{n(k)}*2*(({n(stage.r0)}+2*{n(stage.r1)})/3+{n(stage.rfpe)}-({n(stage.x0)}+2*{n(stage.x1)})*ctg60/3)"
                                ),
                                result.rffw_pe,
                                "Ом",
                            )
                        ],
                    )
                ],
                [result.rffw_pe],
                result.rffw_pe,
                "Ом",
                selection_rule="розраховане значення",
            ),
            self._phs_selection_block(
                "RFFwPP",
                [
                    (
                        "З умови забезпечення чутливості до міжфазних КЗ у кінці ПЛ при 2ф КЗ.",
                        [
                            self._phs_engineering_calculation_line(
                                "RFFwPP",
                                "KчPHS*RFPPZm"
                                if (stage.load_angle_ground_deg or 0.0) > 60.0
                                else "KчPHS*(2*R1Zm+RFPPZm-X1Zm*ctg60)",
                                (
                                    f"{n(k)}*{n(stage.rfpp)}"
                                    if (stage.load_angle_ground_deg or 0.0) > 60.0
                                    else f"{n(k)}*(2*{n(stage.r1)}+{n(stage.rfpp)}-{n(stage.x1)}*ctg60)"
                                ),
                                result.rffw_pp_two_phase,
                                "Ом",
                            )
                        ],
                    ),
                    (
                        "З умови забезпечення чутливості до міжфазних КЗ у кінці ПЛ при 3ф КЗ.",
                        [
                            self._phs_engineering_calculation_line(
                                "RFFwPP",
                                "KчPHS*(2*R1Zm+RFPPZm)*2/SQRT(3)",
                                f"{n(k)}*(2*{n(stage.r1)}+{n(stage.rfpp)})*2/SQRT(3)",
                                result.rffw_pp_three_phase,
                                "Ом",
                            )
                        ],
                    ),
                ],
                [result.rffw_pp_two_phase, result.rffw_pp_three_phase],
                result.rffw_pp,
                "Ом",
                selection_rule="максимальне значення",
            ),
            "<li><p><b>Вибір уставок вирізу від навантаження</b></p><ol>",
            self._phs_selection_block(
                "RLdFw",
                [
                    (
                        "Розрахунок за умовою відлаштування від режиму навантаження.",
                        [
                            self._phs_engineering_calculation_line(
                                "RLdFw",
                                "Kвід*RнавFw",
                                f"{n(load_cut.rejection_factor)}*{n(load_cut.r_load_fw)}",
                                result.rld_fw_load,
                                "Ом",
                            )
                        ],
                    ),
                    *(
                        [
                            (
                                "Розрахунок з урахуванням зони блокування від хитань PSD.",
                                [
                                    self._phs_engineering_calculation_line(
                                        "RLdFw",
                                        "KLdFwPSD*RLdOutFwPSD",
                                        f"{n(self._last_psb_blocking_result.kld_fw if self._last_psb_blocking_result else None)}*"
                                        f"{n(self._last_psb_blocking_result.rld_out_fw if self._last_psb_blocking_result else None)}",
                                        result.rld_fw_psd,
                                        "Ом",
                                    )
                                ],
                            )
                        ]
                        if result.use_psd_zone
                        else []
                    ),
                ],
                [result.rld_fw_load, result.rld_fw_psd],
                result.rld_fw,
                "Ом",
                selection_rule="мінімальне значення",
            ),
            self._phs_selection_block(
                "RLdRv",
                [
                    (
                        "Розрахунок за умовою відлаштування від режиму навантаження.",
                        [
                            self._phs_engineering_calculation_line(
                                "RLdRv",
                                "Kвід*RнавRv",
                                f"{n(load_cut.rejection_factor)}*{n(load_cut.r_load_rv)}",
                                result.rld_rv_load,
                                "Ом",
                            )
                        ],
                    ),
                    *(
                        [
                            (
                                "Розрахунок з урахуванням зони блокування від хитань PSD.",
                                [
                                    self._phs_engineering_calculation_line(
                                        "RLdRv",
                                        "KLdRvPSD*RLdOutRvPSD",
                                        f"{n(self._last_psb_blocking_result.kld_rv if self._last_psb_blocking_result else None)}*"
                                        f"{n(self._last_psb_blocking_result.rld_out_rv if self._last_psb_blocking_result else None)}",
                                        result.rld_rv_psd,
                                        "Ом",
                                    )
                                ],
                            )
                        ]
                        if result.use_psd_zone
                        else []
                    ),
                ],
                [result.rld_rv_load, result.rld_rv_psd],
                result.rld_rv,
                "Ом",
                selection_rule="мінімальне значення",
            ),
            self._phs_selection_block(
                "ArgLd",
                [
                    (
                        "Розрахунок кута вирізу від навантаження за режимами навантаження.",
                        [
                            self._phs_engineering_calculation_line(
                                "ArgLd",
                                "max(FнавFw; FнавRv)+∆φ",
                                f"max({n(f_load_fw)}; {n(f_load_rv)})+{n(load_cut.delta_phi_deg)}",
                                result.arg_ld_load,
                                "град",
                            )
                        ],
                    ),
                    *(
                        [
                            (
                                "Розрахунок кута вирізу від навантаження з урахуванням PSD.",
                                [
                                    self._phs_engineering_calculation_line(
                                        "ArgLdFw",
                                        "arctg(tgArgLdPSD/KLdFwPSD)",
                                        f"arctg(tg({n(self._last_psb_blocking_result.arg_ld_deg if self._last_psb_blocking_result else None)})/"
                                        f"{n(self._last_psb_blocking_result.kld_fw if self._last_psb_blocking_result else None)})",
                                        result.arg_ld_fw_psd,
                                        "град",
                                    ),
                                    self._phs_engineering_calculation_line(
                                        "ArgLdRv",
                                        "arctg(tgArgLdPSD/KLdRvPSD)",
                                        f"arctg(tg({n(self._last_psb_blocking_result.arg_ld_deg if self._last_psb_blocking_result else None)})/"
                                        f"{n(self._last_psb_blocking_result.kld_rv if self._last_psb_blocking_result else None)})",
                                        result.arg_ld_rv_psd,
                                        "град",
                                    ),
                                ],
                            )
                        ]
                        if result.use_psd_zone
                        else []
                    ),
                ],
                [result.arg_ld_load, result.arg_ld_fw_psd, result.arg_ld_rv_psd],
                result.arg_ld,
                "град",
                selection_rule="мінімальне значення",
            ),
            "</ol></li>",
        ]
        if not result.use_psd_zone:
            sections.append(
                "<p>Зону PSD не враховано, тому умови відлаштування RLD з урахуванням PSD "
                "не розраховувалися і не брали участі у виборі результуючих уставок PHS.</p>"
            )
        sections.extend(
            [
                "</ol>",
                "<p>"
                + self._math_html(
                    "Результуючі значення RLD вибрано як мінімальні з розрахованих умов: "
                    f"RLdFw = {n(result.rld_fw)} (Ом); "
                    f"RLdRv = {n(result.rld_rv)} (Ом); "
                    f"ArgLd = {n(result.arg_ld)} (град)."
                )
                + "</p>",
                self._phs_report_graphs_html(),
                "<h3>6. Прийняті уставки PHS</h3>",
                self._phs_journal_report(include_heading=False),
            ]
        )
        return "\n".join(sections)

    def _phs_phase_phase_2ph_coordinate_report(self, result: PhsSelectorResult) -> str:
        n = self._report_optional_number
        tan_60 = tan(pi / 3.0)
        x_shift = result.x1 / tan_60
        rows = [
            [
                "AA",
                f"x = RF<sub>FwPP</sub>/2 = {n(result.rffw_pp)}/2 = {n(result.rffw_pp / 2.0)}",
                "y = 0",
            ],
            [
                "BB",
                "x = RF<sub>FwPP</sub>/2 + X<sub>1</sub>/tg(60) = "
                f"{n(result.rffw_pp)}/2 + {n(result.x1)}/{n(tan_60)} = "
                f"{n(result.rffw_pp / 2.0 + x_shift)}",
                f"y = X<sub>1</sub> = {n(result.x1)}",
            ],
            ["CC", "x = 0", f"y = X<sub>1</sub> = {n(result.x1)}"],
            [
                "DD",
                f"x = -RF<sub>FwPP</sub>/2 = -{n(result.rffw_pp)}/2 = {n(-result.rffw_pp / 2.0)}",
                f"y = X<sub>1</sub> = {n(result.x1)}",
            ],
            [
                "EE",
                f"x = -RF<sub>FwPP</sub>/2 = -{n(result.rffw_pp)}/2 = {n(-result.rffw_pp / 2.0)}",
                "y = 0",
            ],
            [
                "FF",
                "x = -(RF<sub>FwPP</sub>/2 + X<sub>1</sub>/tg(60)) = "
                f"-({n(result.rffw_pp)}/2 + {n(result.x1)}/{n(tan_60)}) = "
                f"{n(-(result.rffw_pp / 2.0 + x_shift))}",
                f"y = -X<sub>1</sub> = {n(-result.x1)}",
            ],
            ["GG", "x = 0", f"y = -X<sub>1</sub> = {n(-result.x1)}"],
            [
                "HH",
                f"x = RF<sub>FwPP</sub>/2 = {n(result.rffw_pp)}/2 = {n(result.rffw_pp / 2.0)}",
                f"y = -X<sub>1</sub> = {n(-result.x1)}",
            ],
            [
                "II",
                f"x = RF<sub>FwPP</sub>/2 = {n(result.rffw_pp)}/2 = {n(result.rffw_pp / 2.0)}",
                "y = 0",
            ],
        ]
        return self._raw_table(["Точка", "x", "y"], rows)

    def _phs_ld_coordinate_report(self, result: PhsSelectorResult) -> str:
        n = self._report_optional_number
        values = self._phs_load_cut_values_by_direction(result)
        if values is None:
            return ""
        r_fw, r_rv, arg_fw, arg_rv = values
        tan_arg_fw = tan(arg_fw * pi / 180.0)
        tan_arg_rv = tan(arg_rv * pi / 180.0)
        rows: list[list[str]] = []

        def add_row(
            zone: str,
            point: str,
            x_formula: str,
            x_substitution: str,
            x_value: float,
            y_formula: str,
            y_substitution: str,
            y_value: float,
        ) -> None:
            rows.append(
                [
                    zone,
                    point,
                    f"x = {x_formula} = {x_substitution} = {n(x_value)}",
                    f"y = {y_formula} = {y_substitution} = {n(y_value)}",
                ]
            )

        tg_fw = n(tan_arg_fw)
        tg_rv = n(tan_arg_rv)
        add_row("LdFw", "A", "2*R<sub>LdFw</sub>", f"2*{n(r_fw)}", 2 * r_fw, "2*R<sub>LdFw</sub>*tg(Arg<sub>LdFw</sub>)", f"2*{n(r_fw)}*tg({n(arg_fw)}) = 2*{n(r_fw)}*{tg_fw}", 2 * r_fw * tan_arg_fw)
        add_row("LdFw", "B", "R<sub>LdFw</sub>", n(r_fw), r_fw, "R<sub>LdFw</sub>*tg(Arg<sub>LdFw</sub>)", f"{n(r_fw)}*tg({n(arg_fw)}) = {n(r_fw)}*{tg_fw}", r_fw * tan_arg_fw)
        add_row("LdFw", "C", "R<sub>LdFw</sub>", n(r_fw), r_fw, "0", "0", 0.0)
        add_row("LdFw", "D", "R<sub>LdFw</sub>", n(r_fw), r_fw, "-R<sub>LdFw</sub>*tg(Arg<sub>LdFw</sub>)", f"-{n(r_fw)}*tg({n(arg_fw)}) = -{n(r_fw)}*{tg_fw}", -r_fw * tan_arg_fw)
        add_row("LdFw", "E", "2*R<sub>LdFw</sub>", f"2*{n(r_fw)}", 2 * r_fw, "-2*R<sub>LdFw</sub>*tg(Arg<sub>LdFw</sub>)", f"-2*{n(r_fw)}*tg({n(arg_fw)}) = -2*{n(r_fw)}*{tg_fw}", -2 * r_fw * tan_arg_fw)
        add_row("LdRv", "A'", "-2*R<sub>LdRv</sub>", f"-2*{n(r_rv)}", -2 * r_rv, "-2*R<sub>LdRv</sub>*tg(Arg<sub>LdRv</sub>)", f"-2*{n(r_rv)}*tg({n(arg_rv)}) = -2*{n(r_rv)}*{tg_rv}", -2 * r_rv * tan_arg_rv)
        add_row("LdRv", "B'", "-R<sub>LdRv</sub>", f"-{n(r_rv)}", -r_rv, "-R<sub>LdRv</sub>*tg(Arg<sub>LdRv</sub>)", f"-{n(r_rv)}*tg({n(arg_rv)}) = -{n(r_rv)}*{tg_rv}", -r_rv * tan_arg_rv)
        add_row("LdRv", "C'", "-R<sub>LdRv</sub>", f"-{n(r_rv)}", -r_rv, "0", "0", 0.0)
        add_row("LdRv", "D'", "-R<sub>LdRv</sub>", f"-{n(r_rv)}", -r_rv, "R<sub>LdRv</sub>*tg(Arg<sub>LdRv</sub>)", f"{n(r_rv)}*tg({n(arg_rv)}) = {n(r_rv)}*{tg_rv}", r_rv * tan_arg_rv)
        add_row("LdRv", "E'", "-2*R<sub>LdRv</sub>", f"-2*{n(r_rv)}", -2 * r_rv, "2*R<sub>LdRv</sub>*tg(Arg<sub>LdRv</sub>)", f"2*{n(r_rv)}*tg({n(arg_rv)}) = 2*{n(r_rv)}*{tg_rv}", 2 * r_rv * tan_arg_rv)
        return self._raw_table(["Зона", "Точка", "x", "y"], rows)

    def _psd_detailed_setting_sections(self, result: PsbBlockingResult) -> list[str]:
        t = self._translator.text
        forward = result.forward
        reverse = result.reverse
        load_cut = result.load_cut
        k = result.sensitivity_factor
        n = self._report_optional_number

        def tg(angle: float | None) -> str:
            return f"tg({n(angle)})"

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
                                "KчPSD*X1Fw",
                                f"{n(k)}*{n(forward.x1 if forward else None)}",
                                result.x1_in_fw_coverage_phase,
                            ),
                            self._engineering_calculation_line(
                                "X1InFw",
                                "KчPSD*(X1Fw+(X0Fw-X1Fw)/3)",
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
                                "KчPSD*(RFPPRv/2)*tg(ArgDirFw)",
                                f"{n(k)}*({n(reverse.rfpp if reverse else None)}/2)*{tg(result.arg_dir_fw_deg)}",
                                result.x1_in_fw_reverse_intersection_phase,
                            ),
                            self._engineering_calculation_line(
                                "X1InFw",
                                "KчPSD*RFPERv*tg(ArgDirFw)",
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
                                "KчPSD*(RFPPFw/2)",
                                f"{n(k)}*({n(forward.rfpp if forward else None)}/2)",
                                result.r1f_in_fw_coverage_phase,
                            ),
                            self._engineering_calculation_line(
                                "R1FInFw",
                                "KчPSD*RFPEFw",
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
                                "KчPSD*X1Rv*tg(ArgNegResFw-90)",
                                f"{n(k)}*{n(reverse.x1 if reverse else None)}*{tg((result.arg_neg_res_fw_deg or 0.0) - 90.0 if result.arg_neg_res_fw_deg is not None else None)}",
                                result.r1f_in_fw_reverse_intersection_phase,
                            ),
                            self._engineering_calculation_line(
                                "R1FInFw",
                                "KчPSD*(X1Rv+(X0Rv-X1Rv)/3)*tg(ArgNegResFw-90)",
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
                                "KчPSD*X1Rv",
                                f"{n(k)}*{n(reverse.x1 if reverse else None)}",
                                result.x1_in_rv_coverage_phase,
                            ),
                            self._engineering_calculation_line(
                                "X1InRv",
                                "KчPSD*(X1Rv+(X0Rv-X1Rv)/3)",
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
                                "KчPSD*(RFPPFw/2)*tg(ArgDirRv)",
                                f"{n(k)}*({n(forward.rfpp if forward else None)}/2)*{tg(result.arg_dir_rv_deg)}",
                                result.x1_in_rv_forward_intersection_phase,
                            ),
                            self._engineering_calculation_line(
                                "X1InRv",
                                "KчPSD*RFPEFw*tg(ArgDirRv)",
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
                                "KчPSD*(RFPPRv/2)",
                                f"{n(k)}*({n(reverse.rfpp if reverse else None)}/2)",
                                result.r1f_in_rv_coverage_phase,
                            ),
                            self._engineering_calculation_line(
                                "R1FInRv",
                                "KчPSD*RFPERv",
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
                                "KчPSD*X1Fw*tg(ArgNegResRv-90)",
                                f"{n(k)}*{n(forward.x1 if forward else None)}*{tg((result.arg_neg_res_rv_deg or 0.0) - 90.0 if result.arg_neg_res_rv_deg is not None else None)}",
                                result.r1f_in_rv_forward_intersection_phase,
                            ),
                            self._engineering_calculation_line(
                                "R1FInRv",
                                "KчPSD*(X1Fw+(X0Fw-X1Fw)/3)*tg(ArgNegResRv-90)",
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
            self._table_header_text(table, column)
            for column in range(table.columnCount())
        ]
        rows = []
        for row in range(table.rowCount()):
            rows.append(
                [
                    self._table_cell_text(table, row, column)
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
            f"<br/><span>{self._math_html(self._formula_sources_text(formula))}</span>"
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
            for line in lines:
                formula_part, _, source_part = line.partition("<br/>")
                condition_parts.append(
                    f"<p style='margin: 6px 0 2px 28px;'>{formula_part} ({self._html(unit)})</p>"
                    f"<p style='margin: 0 0 12px 46px;'>{source_part}</p>"
                )
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
            + self._math_html(final_text).replace(token, final_value_html)
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
            "KчPSD",
            "KчPHS",
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
            "KчPSD": "K<sub>чPSD</sub>",
            "KчPHS": "K<sub>чPHS</sub>",
            "X1Zm": "X<sub>1Zm</sub>",
            "R1Zm": "R<sub>1Zm</sub>",
            "X0Zm": "X<sub>0Zm</sub>",
            "R0Zm": "R<sub>0Zm</sub>",
            "RFPPZm": "RF<sub>FPPZm</sub>",
            "RFPEZm": "RF<sub>FPEZm</sub>",
            "RFRv PE": "RF<sub>Rv PE</sub>",
            "RFFw PE": "RF<sub>Fw PE</sub>",
            "RFFwPP": "RF<sub>FwPP</sub>",
            "RFPP": "RF<sub>FPP</sub>",
            "RFPE": "RF<sub>FPE</sub>",
            "ArgNegRes": "ArgNegRes",
            "ArgDir": "ArgDir",
            "Fлк": "F<sub>лк</sub>",
            "ArgNegResFw": "ArgNegRes<sub>Fw</sub>",
            "ArgNegResRv": "ArgNegRes<sub>Rv</sub>",
            "ArgDirFw": "ArgDir<sub>Fw</sub>",
            "ArgDirRv": "ArgDir<sub>Rv</sub>",
            "RFPPRv": "R<sub>FPPRv</sub>",
            "RFPERv": "R<sub>FPERv</sub>",
            "RFPPFw": "RFPP<sub>Fw</sub>",
            "RFPEFw": "RFPE<sub>Fw</sub>",
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
            "FлFw": "F<sub>лFw</sub>",
            "FлRv": "F<sub>лRv</sub>",
            "KLdFw": "K<sub>LdFw</sub>",
            "KLdRv": "K<sub>LdRv</sub>",
            "X1Fw": "X<sub>1Fw</sub>",
            "X0Fw": "X<sub>0Fw</sub>",
            "X1Rv": "X<sub>1Rv</sub>",
            "X0Rv": "X<sub>0Rv</sub>",
            "Kч": "K<sub>ч</sub>",
            "Kвід": "K<sub>від</sub>",
            "RнавFw": "R<sub>навFw</sub>",
            "RнавRv": "R<sub>навRv</sub>",
            "RLdFw": "R<sub>LdFw</sub>",
            "RLdRv": "R<sub>LdRv</sub>",
            "X1": "X<sub>1</sub>",
            "X0": "X<sub>0</sub>",
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

        x1_fw = self._required_float(result.x1_in_fw)
        x1_rv = self._required_float(result.x1_in_rv)
        r_fw = self._required_float(result.r1f_in_fw)
        r_rv = self._required_float(result.r1f_in_rv)
        r_line = self._required_float(result.r1l_in)
        rld_out_fw = self._required_float(result.rld_out_fw)
        rld_out_rv = self._required_float(result.rld_out_rv)
        rld_out_fw_load = self._required_float(result.rld_out_fw_load)
        rld_out_rv_load = self._required_float(result.rld_out_rv_load)
        rld_in_fw_load = self._required_float(result.rld_in_fw_load)
        rld_in_rv_load = self._required_float(result.rld_in_rv_load)
        kld_fw = self._required_float(result.kld_fw)
        kld_rv = self._required_float(result.kld_rv)
        arg_ld = self._required_float(result.arg_ld_deg)
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
        tg_line = f"tg({n(line_angle)})"
        tg_arg_ld = f"tg({n(arg_ld)})"
        tg_90_line = f"tg((90-{n(line_angle)}))"

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
                    "-(R1FInRv + X1InRv/tg(Line Angle))",
                    f"-({n(r_rv)} + {n(x1_rv)}/{tg_line})",
                    left_inner_x,
                    "-X1InRv",
                    f"-{n(x1_rv)}",
                    -x1_rv,
                ),
                p(
                    "M",
                    "-(R1FInRv + X1InRv/tg(Line Angle))",
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
                    "R1LIn + R1FInFw + DELTA FW + DELTA FW*tg((90-Line Angle))",
                    f"{n(r_line)} + {n(r_fw)} + {n(delta_fw)} + {n(delta_fw)}*{tg_90_line}",
                    b_prime_x,
                    "X1InFw + DELTA FW",
                    f"{n(x1_fw)} + {n(delta_fw)}",
                    x1_fw + delta_fw,
                ),
                p(
                    "C'",
                    "R1LIn + R1FInFw + DELTA FW + DELTA FW*tg((90-Line Angle))",
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
                    "-(R1FInRv + X1InRv/tg(Line Angle) + DELTA RV + DELTA RV/tg(Line Angle))",
                    f"-({n(r_rv)} + {n(x1_rv)}/{tg_line} + {n(delta_rv)} + {n(delta_rv)}/{tg_line})",
                    left_outer_x,
                    "-X1InRv - DELTA RV",
                    f"-{n(x1_rv)} - {n(delta_rv)}",
                    -x1_rv - delta_rv,
                ),
                p(
                    "M'",
                    "-(R1FInRv + X1InRv/tg(Line Angle) + DELTA RV + DELTA RV/tg(Line Angle))",
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
            p("AA", "RLdInFw_load*1,5", f"{n(rld_in_fw_load)}*1,5", rld_in_fw_load * 1.5, "(RLdInFw_load*1,5 + DELTA FW)*tg(ArgLd)", f"({n(rld_in_fw_load)}*1,5 + {n(delta_fw)})*{tg_arg_ld}", (rld_in_fw_load * 1.5 + delta_fw) * tan_arg_ld),
            p("BB", "RLdInFw_load", n(rld_in_fw_load), rld_in_fw_load, "RLdOutFw_load*tg(ArgLd)", f"{n(rld_out_fw_load)}*{tg_arg_ld}", rld_out_fw_load * tan_arg_ld),
            p("CC", "RLdInFw_load", n(rld_in_fw_load), rld_in_fw_load, "-RLdOutFw_load*tg(ArgLd)", f"-{n(rld_out_fw_load)}*{tg_arg_ld}", -rld_out_fw_load * tan_arg_ld),
            p("DD", "RLdInFw_load*1,5", f"{n(rld_in_fw_load)}*1,5", rld_in_fw_load * 1.5, "-(RLdInFw_load*1,5 + DELTA FW)*tg(ArgLd)", f"-({n(rld_in_fw_load)}*1,5 + {n(delta_fw)})*{tg_arg_ld}", -(rld_in_fw_load * 1.5 + delta_fw) * tan_arg_ld),
        )
        rld_inner_rv = (
            p("EE", "-RLdInRv_load*1,5", f"-{n(rld_in_rv_load)}*1,5", -rld_in_rv_load * 1.5, "(RLdInRv_load*1,5 + DELTA RV)*tg(ArgLd)", f"({n(rld_in_rv_load)}*1,5 + {n(delta_rv)})*{tg_arg_ld}", (rld_in_rv_load * 1.5 + delta_rv) * tan_arg_ld),
            p("FF", "-RLdInRv_load", f"-{n(rld_in_rv_load)}", -rld_in_rv_load, "RLdOutRv_load*tg(ArgLd)", f"{n(rld_out_rv_load)}*{tg_arg_ld}", rld_out_rv_load * tan_arg_ld),
            p("GG", "-RLdInRv_load", f"-{n(rld_in_rv_load)}", -rld_in_rv_load, "-RLdOutRv_load*tg(ArgLd)", f"-{n(rld_out_rv_load)}*{tg_arg_ld}", -rld_out_rv_load * tan_arg_ld),
            p("HH", "-RLdInRv_load*1,5", f"-{n(rld_in_rv_load)}*1,5", -rld_in_rv_load * 1.5, "-(RLdInRv_load*1,5 + DELTA RV)*tg(ArgLd)", f"-({n(rld_in_rv_load)}*1,5 + {n(delta_rv)})*{tg_arg_ld}", -(rld_in_rv_load * 1.5 + delta_rv) * tan_arg_ld),
        )
        rld_outer_fw = (
            p("AA'", "RLdOutFw_load*1,5", f"{n(rld_out_fw_load)}*1,5", rld_out_fw_load * 1.5, "RLdOutFw_load*1,5*tg(ArgLd)", f"{n(rld_out_fw_load)}*1,5*{tg_arg_ld}", rld_out_fw_load * 1.5 * tan_arg_ld),
            p("BB'", "RLdOutFw_load", n(rld_out_fw_load), rld_out_fw_load, "RLdOutFw_load*tg(ArgLd)", f"{n(rld_out_fw_load)}*{tg_arg_ld}", rld_out_fw_load * tan_arg_ld),
            p("CC'", "RLdOutFw_load", n(rld_out_fw_load), rld_out_fw_load, "-RLdOutFw_load*tg(ArgLd)", f"-{n(rld_out_fw_load)}*{tg_arg_ld}", -rld_out_fw_load * tan_arg_ld),
            p("DD'", "RLdOutFw_load*1,5", f"{n(rld_out_fw_load)}*1,5", rld_out_fw_load * 1.5, "-RLdOutFw_load*1,5*tg(ArgLd)", f"-{n(rld_out_fw_load)}*1,5*{tg_arg_ld}", -rld_out_fw_load * 1.5 * tan_arg_ld),
        )
        rld_outer_rv = (
            p("EE'", "-RLdOutRv_load*1,5", f"-{n(rld_out_rv_load)}*1,5", -rld_out_rv_load * 1.5, "RLdOutRv_load*1,5*tg(ArgLd)", f"{n(rld_out_rv_load)}*1,5*{tg_arg_ld}", rld_out_rv_load * 1.5 * tan_arg_ld),
            p("FF'", "-RLdOutRv_load", f"-{n(rld_out_rv_load)}", -rld_out_rv_load, "RLdOutRv_load*tg(ArgLd)", f"{n(rld_out_rv_load)}*{tg_arg_ld}", rld_out_rv_load * tan_arg_ld),
            p("GG'", "-RLdOutRv_load", f"-{n(rld_out_rv_load)}", -rld_out_rv_load, "-RLdOutRv_load*tg(ArgLd)", f"-{n(rld_out_rv_load)}*{tg_arg_ld}", -rld_out_rv_load * tan_arg_ld),
            p("HH'", "-RLdOutRv_load*1,5", f"-{n(rld_out_rv_load)}*1,5", -rld_out_rv_load * 1.5, "-RLdOutRv_load*1,5*tg(ArgLd)", f"-{n(rld_out_rv_load)}*1,5*{tg_arg_ld}", -rld_out_rv_load * 1.5 * tan_arg_ld),
        )

        return [
            ("PSD inner", inner),
            ("PSD outer", outer),
            ("RLD inner", rld_inner_fw),
            ("RLD inner", rld_inner_rv),
            ("RLD outer", rld_outer_fw),
            ("RLD outer", rld_outer_rv),
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

    def _raw_table(self, headers: list[str], rows: list[list[str]]) -> str:
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
                table.append(f"<td style='{self._report_cell_style()}'>{value}</td>")
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
            return f"tg({self._report_number(angle_deg)})"

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
            "1.1 X1InFw: KчPSD*X1Fw",
            result.x1_in_fw_coverage_phase,
            t("report.psb.forward_coverage_comment"),
            "1.1 X1InFw = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.forward, 'x1')}",
        )
        add_condition(
            t("report.psb.forward_coverage"),
            "1.1 X1InFw: KчPSD*(X1Fw+(X0Fw-X1Fw)/3)",
            result.x1_in_fw_coverage_ground,
            t("report.psb.forward_coverage_comment"),
            "1.1 X1InFw = "
            f"{value_text(result.sensitivity_factor)}*("
            f"{extreme_text(result.forward, 'x1')}+"
            f"({extreme_text(result.forward, 'x0')}-{extreme_text(result.forward, 'x1')})/3)",
        )
        add_summary(
            t("report.psb.forward_coverage"),
            "1.1 X1InFw = max(KчPSD*X1Fw; KчPSD*(X1Fw+(X0Fw-X1Fw)/3))",
            x1_fw_11,
            ("KчPSD*X1Fw", result.x1_in_fw_coverage_phase),
            ("KчPSD*(X1Fw+(X0Fw-X1Fw)/3)", result.x1_in_fw_coverage_ground),
        )
        add_condition(
            t("report.psb.forward_coverage"),
            "1.1 R1FInFw: KчPSD*(RFPPFw/2)",
            result.r1f_in_fw_coverage_phase,
            t("report.psb.forward_coverage_comment"),
            "1.1 R1FInFw = "
            f"{value_text(result.sensitivity_factor)}*({extreme_text(result.forward, 'rfpp')}/2)",
        )
        add_condition(
            t("report.psb.forward_coverage"),
            "1.1 R1FInFw: KчPSD*RFPEFw",
            result.r1f_in_fw_coverage_ground,
            t("report.psb.forward_coverage_comment"),
            "1.1 R1FInFw = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.forward, 'rfpe')}",
        )
        add_summary(
            t("report.psb.forward_coverage"),
            "1.1 R1FInFw = max(KчPSD*(RFPPFw/2); KчPSD*RFPEFw)",
            r1f_fw_11,
            ("KчPSD*(RFPPFw/2)", result.r1f_in_fw_coverage_phase),
            ("KчPSD*RFPEFw", result.r1f_in_fw_coverage_ground),
        )
        add_condition(
            t("report.psb.forward_reverse_intersection"),
            "1.3 X1InFw: KчPSD*(RFPPRv/2)*tg(ArgDirFw)",
            result.x1_in_fw_reverse_intersection_phase,
            t("report.psb.forward_reverse_intersection_comment"),
            "1.3 X1InFw = "
            f"{value_text(result.sensitivity_factor)}*({extreme_text(result.reverse, 'rfpp')}/2)"
            f"*{tan_text(arg_dir_fw)}",
        )
        add_condition(
            t("report.psb.forward_reverse_intersection"),
            "1.3 X1InFw: KчPSD*RFPERv*tg(ArgDirFw)",
            result.x1_in_fw_reverse_intersection_ground,
            t("report.psb.forward_reverse_intersection_comment"),
            "1.3 X1InFw = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.reverse, 'rfpe')}"
            f"*{tan_text(arg_dir_fw)}",
        )
        add_summary(
            t("report.psb.forward_reverse_intersection"),
            "1.3 X1InFw = max(KчPSD*(RFPPRv/2)*tg(ArgDirFw); KчPSD*RFPERv*tg(ArgDirFw))",
            x1_fw_13,
            ("KчPSD*(RFPPRv/2)*tg(ArgDirFw)", result.x1_in_fw_reverse_intersection_phase),
            ("KчPSD*RFPERv*tg(ArgDirFw)", result.x1_in_fw_reverse_intersection_ground),
        )
        add_condition(
            t("report.psb.forward_reverse_intersection"),
            "1.3 R1FInFw: KчPSD*X1Rv*tg(ArgNegResFw-90)",
            result.r1f_in_fw_reverse_intersection_phase,
            t("report.psb.forward_reverse_intersection_comment"),
            "1.3 R1FInFw = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.reverse, 'x1')}"
            f"*{tan_text((arg_neg_res_fw or 0.0) - 90.0 if arg_neg_res_fw is not None else None)}",
        )
        add_condition(
            t("report.psb.forward_reverse_intersection"),
            "1.3 R1FInFw: KчPSD*(X1Rv+(X0Rv-X1Rv)/3)*tg(ArgNegResFw-90)",
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
            "1.3 R1FInFw = max(KчPSD*X1Rv*tg(ArgNegResFw-90); "
            "KчPSD*(X1Rv+(X0Rv-X1Rv)/3)*tg(ArgNegResFw-90))",
            r1f_fw_13,
            ("KчPSD*X1Rv*tg(ArgNegResFw-90)", result.r1f_in_fw_reverse_intersection_phase),
            (
                "KчPSD*(X1Rv+(X0Rv-X1Rv)/3)*tg(ArgNegResFw-90)",
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
            "2.1 X1InRv: KчPSD*X1Rv",
            result.x1_in_rv_coverage_phase,
            t("report.psb.reverse_coverage_comment"),
            "2.1 X1InRv = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.reverse, 'x1')}",
        )
        add_condition(
            t("report.psb.reverse_coverage"),
            "2.1 X1InRv: KчPSD*(X1Rv+(X0Rv-X1Rv)/3)",
            result.x1_in_rv_coverage_ground,
            t("report.psb.reverse_coverage_comment"),
            "2.1 X1InRv = "
            f"{value_text(result.sensitivity_factor)}*("
            f"{extreme_text(result.reverse, 'x1')}+"
            f"({extreme_text(result.reverse, 'x0')}-{extreme_text(result.reverse, 'x1')})/3)",
        )
        add_summary(
            t("report.psb.reverse_coverage"),
            "2.1 X1InRv = max(KчPSD*X1Rv; KчPSD*(X1Rv+(X0Rv-X1Rv)/3))",
            x1_rv_21,
            ("KчPSD*X1Rv", result.x1_in_rv_coverage_phase),
            ("KчPSD*(X1Rv+(X0Rv-X1Rv)/3)", result.x1_in_rv_coverage_ground),
        )
        add_condition(
            t("report.psb.reverse_coverage"),
            "2.1 R1FInRv: KчPSD*(RFPPRv/2)",
            result.r1f_in_rv_coverage_phase,
            t("report.psb.reverse_coverage_comment"),
            "2.1 R1FInRv = "
            f"{value_text(result.sensitivity_factor)}*({extreme_text(result.reverse, 'rfpp')}/2)",
        )
        add_condition(
            t("report.psb.reverse_coverage"),
            "2.1 R1FInRv: KчPSD*RFPERv",
            result.r1f_in_rv_coverage_ground,
            t("report.psb.reverse_coverage_comment"),
            "2.1 R1FInRv = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.reverse, 'rfpe')}",
        )
        add_summary(
            t("report.psb.reverse_coverage"),
            "2.1 R1FInRv = max(KчPSD*(RFPPRv/2); KчPSD*RFPERv)",
            r1f_rv_21,
            ("KчPSD*(RFPPRv/2)", result.r1f_in_rv_coverage_phase),
            ("KчPSD*RFPERv", result.r1f_in_rv_coverage_ground),
        )
        add_condition(
            t("report.psb.reverse_forward_intersection"),
            "2.3 X1InRv: KчPSD*(RFPPFw/2)*tg(ArgDirRv)",
            result.x1_in_rv_forward_intersection_phase,
            t("report.psb.reverse_forward_intersection_comment"),
            "2.3 X1InRv = "
            f"{value_text(result.sensitivity_factor)}*({extreme_text(result.forward, 'rfpp')}/2)"
            f"*{tan_text(arg_dir_rv)}",
        )
        add_condition(
            t("report.psb.reverse_forward_intersection"),
            "2.3 X1InRv: KчPSD*RFPEFw*tg(ArgDirRv)",
            result.x1_in_rv_forward_intersection_ground,
            t("report.psb.reverse_forward_intersection_comment"),
            "2.3 X1InRv = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.forward, 'rfpe')}"
            f"*{tan_text(arg_dir_rv)}",
        )
        add_summary(
            t("report.psb.reverse_forward_intersection"),
            "2.3 X1InRv = max(KчPSD*(RFPPFw/2)*tg(ArgDirRv); KчPSD*RFPEFw*tg(ArgDirRv))",
            x1_rv_23,
            ("KчPSD*(RFPPFw/2)*tg(ArgDirRv)", result.x1_in_rv_forward_intersection_phase),
            ("KчPSD*RFPEFw*tg(ArgDirRv)", result.x1_in_rv_forward_intersection_ground),
        )
        add_condition(
            t("report.psb.reverse_forward_intersection"),
            "2.3 R1FInRv: KчPSD*X1Fw*tg(ArgNegResRv-90)",
            result.r1f_in_rv_forward_intersection_phase,
            t("report.psb.reverse_forward_intersection_comment"),
            "2.3 R1FInRv = "
            f"{value_text(result.sensitivity_factor)}*{extreme_text(result.forward, 'x1')}"
            f"*{tan_text((arg_neg_res_rv or 0.0) - 90.0 if arg_neg_res_rv is not None else None)}",
        )
        add_condition(
            t("report.psb.reverse_forward_intersection"),
            "2.3 R1FInRv: KчPSD*(X1Fw+(X0Fw-X1Fw)/3)*tg(ArgNegResRv-90)",
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
            "2.3 R1FInRv = max(KчPSD*X1Fw*tg(ArgNegResRv-90); "
            "KчPSD*(X1Fw+(X0Fw-X1Fw)/3)*tg(ArgNegResRv-90))",
            r1f_rv_23,
            ("KчPSD*X1Fw*tg(ArgNegResRv-90)", result.r1f_in_rv_forward_intersection_phase),
            (
                "KчPSD*(X1Fw+(X0Fw-X1Fw)/3)*tg(ArgNegResRv-90)",
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
            + self._math_html(
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
        helpers: PhasePhaseStageHelpers | PhaseGroundStageHelpers,
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
                "IF RES1>ArgNegRes THEN -tg((ArgNegRes-90))*X1 ELSE -RPFF/2",
                "IF RES1>ArgNegRes THEN 0 ELSE -RPFF/2",
                "IF RES1>ArgNegRes THEN 0 ELSE B33",
                "0",
            ],
            "y": [
                "0",
                "-RPFF/2*tg(ArgDir)",
                "0",
                "X1",
                "X1",
                "X1",
                "IF RES1>ArgNegRes THEN 0 ELSE X1",
                "IF RES1>ArgNegRes THEN 0 ELSE (1/tg((ArgNegRes-90)))*(RPFF/2)",
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
                "IF RES1>ArgNegRes THEN -tg((ArgNegRes-90))*X1 ELSE 0",
                "IF RES1>ArgNegRes THEN 0 ELSE -RFPE",
                "IF RES1>ArgNegRes THEN 0 ELSE B33",
                "0",
            ],
            "y": [
                "0",
                "-RFPE*tg(ArgDir)",
                "0",
                "(2*X1+X0)/3",
                "(2*X1+X0)/3",
                "(2*X1+X0)/3",
                "IF RES1>ArgNegRes THEN 0 ELSE (2*X1+X0)/3",
                "IF RES1>ArgNegRes THEN 0 ELSE (1/tg((ArgNegRes-90)))*RFPE",
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
        if self._current_project_id is None and not self._prompt_project_name():
            return
        self._save_project_record(project_id=self._current_project_id)

    def _save_project_as(self) -> None:
        if not self._prompt_project_name():
            return
        self._save_project_record(project_id=None)

    def _prompt_project_name(self) -> bool:
        current_name = self.project_name.text().strip()
        name, accepted = QInputDialog.getText(
            self,
            self._translator.text("dialog.project_name_title"),
            self._translator.text("dialog.project_name_label"),
            text=current_name,
        )
        if not accepted:
            return False
        name = name.strip()
        if not name:
            QMessageBox.warning(
                self,
                self._translator.text("dialog.project_name_title"),
                self._translator.text("message.project_name_required"),
            )
            return False
        self.project_name.setText(name)
        return True

    def _save_project_record(self, project_id: int | None) -> None:
        with self._session_factory() as session:
            repository = ProjectRepository(session)
            name = self.project_name.text().strip()
            existing = next(
                (
                    record
                    for record in repository.list_projects()
                    if record.name == name and record.id != project_id
                ),
                None,
            )
            if existing is not None:
                answer = QMessageBox.question(
                    self,
                    self._translator.text("dialog.project_name_title"),
                    self._translator.text("message.confirm_project_overwrite", name=name),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
                project_id = existing.id
            self._current_project_id = repository.save(
                self._project_data(),
                results={"calculation": self._last_result},
                project_id=project_id,
            )
        self._dirty = False
        self.statusBar().showMessage(self._translator.text("message.saved"), 5000)

    def _new_project(self) -> None:
        if not self._confirm_unsaved_changes():
            return
        self._suppress_dirty = True
        self._last_result = None
        self._last_psb_blocking_result = None
        self._current_project_id = None
        self.project_name.clear()
        self.author.clear()
        self.source_data_widget.reset()
        self._clear_results(update_lock=True)
        self._dirty = False
        self._suppress_dirty = False

    def closeEvent(self, event) -> None:  # noqa: N802  # type: ignore[no-untyped-def]
        if self._confirm_unsaved_changes():
            event.accept()
        else:
            event.ignore()

    def _confirm_unsaved_changes(self) -> bool:
        if not self._dirty:
            return True
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Question)
        message.setWindowTitle(self._translator.text("message.unsaved_changes_title"))
        message.setText(self._translator.text("message.unsaved_changes_body"))
        save_button = cast(
            QPushButton,
            message.addButton(
                self._translator.text("button.save"),
                QMessageBox.ButtonRole.AcceptRole,
            ),
        )
        discard_button = cast(
            QPushButton,
            message.addButton(
                self._translator.text("button.discard"),
                QMessageBox.ButtonRole.DestructiveRole,
            ),
        )
        cancel_button = cast(
            QPushButton,
            message.addButton(
                self._translator.text("button.cancel"),
                QMessageBox.ButtonRole.RejectRole,
            ),
        )
        save_button.setObjectName("primaryActionButton")
        discard_button.setObjectName("dangerActionButton")
        cancel_button.setObjectName("secondaryActionButton")
        message.setDefaultButton(save_button)
        message.exec()
        clicked_button = message.clickedButton()
        if clicked_button is save_button:
            self._save_project()
            return not self._dirty
        return clicked_button is discard_button

    def _open_latest_project(self) -> None:
        if not self._confirm_unsaved_changes():
            return
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
        self._suppress_dirty = True
        self._translator.set_language(project.metadata.language)
        self.project_name.setText(project.metadata.name)
        self.author.setText(project.metadata.author)
        self._retranslate()
        self.source_data_widget.from_dict(project.source_data)
        self._update_psd_phase_ground_tab()
        self._clear_results(update_lock=True)
        self._dirty = False
        self._suppress_dirty = False

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
                    self._table_cell_text(self.psd_reach_table, row, column)
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

    def _export_phs_settings_docx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._translator.text("dialog.export_word_title"),
            str(Path.cwd() / "phs_settings.docx"),
            self._translator.text("dialog.word_filter"),
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".docx":
            target = target.with_suffix(".docx")
        export_html_to_docx(self._phs_settings_export_html(), target)
        self.statusBar().showMessage(self._translator.text("message.exported"), 5000)

    def _phs_settings_export_html(self) -> str:
        rows = []
        for row in range(self.phs_settings_tab.rowCount()):
            rows.append(
                [
                    self._table_cell_text(self.phs_settings_tab, row, column)
                    for column in range(self.phs_settings_tab.columnCount())
                ]
            )
        return (
            f"<h2>PHS - {self._html(self._translator.text('psd.settings'))}</h2>"
            + self._simple_table(
                [
                    self._translator.text("table.name"),
                    self._translator.text("report.psd_setting_value"),
                    self._translator.text("psd.unit").capitalize(),
                ],
                rows,
            )
        )

    def _export_phs_report_docx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._translator.text("dialog.export_word_title"),
            str(Path.cwd() / "phs_report.docx"),
            self._translator.text("dialog.word_filter"),
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".docx":
            target = target.with_suffix(".docx")
        export_html_to_docx(self._build_phs_report(), target)
        self.statusBar().showMessage(self._translator.text("message.exported"), 5000)

    def _find_psd_report_next(self) -> None:
        self._find_psd_report(backward=False)

    def _find_psd_report_previous(self) -> None:
        self._find_psd_report(backward=True)

    def _find_psd_report(self, *, backward: bool) -> None:
        self._find_in_report(
            editor=self.psd_report_text,
            search=self.psd_report_search,
            backward=backward,
        )

    def _find_phs_report_next(self) -> None:
        self._find_phs_report(backward=False)

    def _find_phs_report_previous(self) -> None:
        self._find_phs_report(backward=True)

    def _find_phs_report(self, *, backward: bool) -> None:
        self._find_in_report(
            editor=self.phs_report_tab,
            search=self.phs_report_search,
            backward=backward,
        )

    def _find_in_report(
        self,
        *,
        editor: QTextEdit,
        search: QLineEdit,
        backward: bool,
    ) -> None:
        text = search.text().strip()
        if not text:
            return
        flags = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
        if editor.find(text, flags):
            return
        editor.moveCursor(
            QTextCursor.MoveOperation.End
            if backward
            else QTextCursor.MoveOperation.Start
        )
        editor.find(text, flags)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            self._translator,
            self,
            show_point_labels=self._show_point_labels,
            show_legends=self._show_legends,
            show_zone_names=self._show_zone_names,
            show_point_tooltips=self._show_point_tooltips,
            show_journal_tab=self._show_journal_tab,
            zone_colors=self._zone_colors,
            zone_color_options=self._zone_color_options(),
        )
        if dialog.exec():
            progress = self._create_progress_dialog(
                self._translator.text("progress.apply_settings")
            )
            try:
                self._advance_progress(
                    progress,
                    self._translator.text("progress.settings_language"),
                    1,
                )
                self._translator.set_language(dialog.selected_language)
                self._show_point_labels = dialog.show_point_labels
                self._show_legends = dialog.show_legends
                self._show_zone_names = dialog.show_zone_names
                self._show_point_tooltips = dialog.show_point_tooltips
                self._show_journal_tab = dialog.show_journal_tab
                self._zone_colors = dialog.zone_colors
                self._advance_progress(
                    progress,
                    self._translator.text("progress.settings_interface"),
                    2,
                )
                self._retranslate()
                self._update_result_tab_state()
                self._advance_progress(
                    progress,
                    self._translator.text("progress.settings_graphs"),
                    3,
                )
                self._redraw_psd_charts()
                self._advance_progress(
                    progress,
                    self._translator.text("progress.settings_graphs"),
                    4,
                )
                self._plot_phs_graphs()
                self._advance_progress(
                    progress,
                    self._translator.text("progress.report"),
                    5,
                )
                if self._last_phs_result is not None:
                    self.phs_report_tab.setHtml(self._build_phs_report())
                self._advance_progress(
                    progress,
                    self._translator.text("progress.done"),
                    6,
                )
            finally:
                progress.close()

    def _set_report_zoom(self, editor: QTextEdit, value: int) -> None:
        font = editor.document().defaultFont()
        font.setPointSizeF(10.0 * value / 100.0)
        editor.document().setDefaultFont(font)

    def _open_help(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self._translator.text("menu.help"))
        dialog.setMinimumSize(980, 720)
        layout = QVBoxLayout(dialog)
        search = QLineEdit()
        search.setPlaceholderText(self._translator.text("help.search_placeholder"))
        layout.addWidget(search)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        navigation = QListWidget()
        content = QTextBrowser()
        content.setOpenExternalLinks(False)
        sections = self._help_sections()
        for title, _html in sections:
            navigation.addItem(QListWidgetItem(title))
        splitter.addWidget(navigation)
        splitter.addWidget(content)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        layout.addWidget(splitter, 1)
        zoom_slider = QSlider(Qt.Orientation.Horizontal)
        zoom_slider.setRange(80, 160)
        zoom_slider.setValue(100)
        zoom_slider.setFixedWidth(120)
        zoom_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        zoom_slider.setTickInterval(20)
        zoom_slider.valueChanged.connect(lambda value: self._set_report_zoom(content, value))
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(QLabel(self._translator.text("report.zoom")))
        footer.addWidget(zoom_slider)
        layout.addLayout(footer)

        def show_section(row: int) -> None:
            if row < 0:
                return
            content.setHtml(sections[row][1])
            content.moveCursor(QTextCursor.MoveOperation.Start)

        def find_next() -> None:
            text = search.text().strip()
            if text and not content.find(text):
                content.moveCursor(QTextCursor.MoveOperation.Start)
                content.find(text)

        navigation.currentRowChanged.connect(show_section)
        search.returnPressed.connect(find_next)
        if sections:
            navigation.setCurrentRow(0)
        dialog.exec()

    def _help_sections(self) -> list[tuple[str, str]]:
        t = self._translator.text
        style = (
            "<style>body{font-family:Segoe UI;color:#111827;font-size:11pt;}"
            "h2{margin-top:0;} h3{margin-top:18px;} "
            "p{line-height:1.45;} .formula{margin:6px 0 10px 18px;}"
            "table{border-collapse:collapse;width:100%;margin:10px 0 18px 0;}"
            "th,td{border:1px solid #cbd5e1;padding:6px;text-align:left;vertical-align:top;}"
            "th{background:#eef2f7;}"
            "</style>"
        )
        distance_points = self._help_table(
            ["Точка", "x", "y"],
            [
                ["O", "0", "0"],
                ["A`", "RF<sub>PP</sub>/2", "-RF<sub>PP</sub>/2*tg(ArgDir)"],
                ["A", "RF<sub>PP</sub>/2", "0"],
                ["B", "R<sub>1</sub>+RF<sub>PP</sub>/2", "X<sub>1</sub>"],
                ["C", "0", "X<sub>1</sub>"],
                ["C`", "IF RES1&gt;ArgNegRes; -tg(ArgNegRes-90)*X<sub>1</sub>; -RF<sub>PP</sub>/2", "X<sub>1</sub>"],
                ["D", "IF RES1&gt;ArgNegRes; 0; -RF<sub>PP</sub>/2", "IF RES1&gt;ArgNegRes; 0; X<sub>1</sub>"],
                ["D`", "IF RES1&gt;ArgNegRes; 0; B33", "IF RES1&gt;ArgNegRes; 0; RF<sub>PP</sub>/2/tg(ArgNegRes-90)"],
                ["E", "0", "0"],
            ],
        )
        phase_ground_points = self._help_table(
            ["Точка", "x", "y"],
            [
                ["O", "0", "0"],
                ["A`", "RF<sub>PE</sub>", "-RF<sub>PE</sub>*tg(ArgDir)"],
                ["A", "RF<sub>PE</sub>", "0"],
                ["B", "(2*R<sub>1</sub>+R<sub>0</sub>)/3 + RF<sub>PE</sub>", "(2*X<sub>1</sub>+X<sub>0</sub>)/3"],
                ["C", "0", "(2*X<sub>1</sub>+X<sub>0</sub>)/3"],
                ["C`", "IF RES1&gt;ArgNegRes; -tg(ArgNegRes-90)*X<sub>1</sub>; 0", "(2*X<sub>1</sub>+X<sub>0</sub>)/3"],
                ["D", "IF RES1&gt;ArgNegRes; 0; -RF<sub>PE</sub>", "IF RES1&gt;ArgNegRes; 0; (2*X<sub>1</sub>+X<sub>0</sub>)/3"],
                ["D`", "IF RES1&gt;ArgNegRes; 0; B33", "IF RES1&gt;ArgNegRes; 0; RF<sub>PE</sub>/tg(ArgNegRes-90)"],
                ["E", "0", "0"],
            ],
        )
        psd_inner_points = self._help_table(
            ["Точка", "x", "y"],
            [
                ["A", "0", "X<sub>1InFw</sub>"],
                ["B", "R<sub>1LIn</sub>+R<sub>1FInFw</sub>", "X<sub>1InFw</sub>"],
                ["C", "R<sub>1FInFw</sub>+X<sub>1InFw</sub>/tg(LineAngle)", "0"],
                ["D", "R<sub>1FInFw</sub>", "0"],
                ["G", "R<sub>1FInFw</sub>", "-X<sub>1InRv</sub>"],
                ["I", "0", "-X<sub>1InRv</sub>"],
                ["L", "-(R<sub>1FInRv</sub>+X<sub>1InRv</sub>/tg(LineAngle))", "-X<sub>1InRv</sub>"],
                ["N", "-R<sub>1FInRv</sub>", "0"],
                ["Q", "-R<sub>1FInRv</sub>", "X<sub>1InFw</sub>"],
            ],
        )
        psd_outer_points = self._help_table(
            ["Точка", "x", "y"],
            [
                ["A`", "0", "X<sub>1InFw</sub>+DELTA<sub>FW</sub>"],
                ["B`", "R<sub>1LIn</sub>+R<sub>1FInFw</sub>+DELTA<sub>FW</sub>+DELTA<sub>FW</sub>*tg(90-LineAngle)", "X<sub>1InFw</sub>+DELTA<sub>FW</sub>"],
                ["F`", "R<sub>1FInFw</sub>+DELTA<sub>FW</sub>", "0"],
                ["G`", "R<sub>1FInFw</sub>+DELTA<sub>FW</sub>", "-X<sub>1InRv</sub>-DELTA<sub>RV</sub>"],
                ["I`", "0", "-X<sub>1InRv</sub>-DELTA<sub>RV</sub>"],
                ["L`", "-(R<sub>1FInRv</sub>+X<sub>1InRv</sub>/tg(LineAngle)+DELTA<sub>RV</sub>+DELTA<sub>RV</sub>/tg(LineAngle))", "-X<sub>1InRv</sub>-DELTA<sub>RV</sub>"],
                ["N`", "-R<sub>1FInRv</sub>-DELTA<sub>RV</sub>", "0"],
                ["Q`", "-R<sub>1FInRv</sub>-DELTA<sub>RV</sub>", "X<sub>1InFw</sub>+DELTA<sub>FW</sub>"],
            ],
        )
        rld_points = self._help_table(
            ["Зона", "Точка", "x", "y"],
            [
                ["RLD inner Fw", "AA", "RLd<sub>InFw</sub>*1,5", "(RLd<sub>InFw</sub>*1,5+∆RFw)*tg(ArgLd)"],
                ["RLD inner Fw", "BB", "RLd<sub>InFw</sub>", "RLd<sub>OutFw</sub>*tg(ArgLd)"],
                ["RLD inner Fw", "CC", "RLd<sub>InFw</sub>", "-RLd<sub>OutFw</sub>*tg(ArgLd)"],
                ["RLD inner Rv", "EE", "-RLd<sub>InRv</sub>*1,5", "(RLd<sub>InRv</sub>*1,5+∆RRv)*tg(ArgLd)"],
                ["RLD outer Fw", "AA`", "RLd<sub>OutFw</sub>*1,5", "RLd<sub>OutFw</sub>*1,5*tg(ArgLd)"],
                ["RLD outer Rv", "EE`", "-RLd<sub>OutRv</sub>*1,5", "RLd<sub>OutRv</sub>*1,5*tg(ArgLd)"],
            ],
        )
        phs_points = self._help_table(
            ["Графік", "Точка", "x", "y"],
            [
                ["Фаза-фаза (2ф КЗ)", "AA", "RF<sub>FwPP</sub>/2", "0"],
                ["Фаза-фаза (2ф КЗ)", "BB", "RF<sub>FwPP</sub>/2 + X<sub>1</sub>/tg(60)", "X<sub>1</sub>"],
                ["Фаза-фаза (2ф КЗ)", "CC", "0", "X<sub>1</sub>"],
                ["Фаза-фаза (2ф КЗ)", "DD", "-RF<sub>FwPP</sub>/2", "X<sub>1</sub>"],
                ["Фаза-фаза (2ф КЗ)", "EE", "-RF<sub>FwPP</sub>/2", "0"],
                ["Фаза-фаза (2ф КЗ)", "FF", "-(RF<sub>FwPP</sub>/2 + X<sub>1</sub>/tg(60))", "-X<sub>1</sub>"],
                ["Фаза-фаза (2ф КЗ)", "GG", "0", "-X<sub>1</sub>"],
                ["Фаза-фаза (2ф КЗ)", "HH", "RF<sub>FwPP</sub>/2", "-X<sub>1</sub>"],
                ["Фаза-фаза (2ф КЗ)", "II", "RF<sub>FwPP</sub>/2", "0"],
                ["Фаза-фаза (3ф КЗ)", "A", "RF<sub>FwPP</sub>", "0"],
                ["Фаза-фаза (3ф КЗ)", "B", "RF<sub>FwPP</sub>/2", "X<sub>1</sub>"],
                ["Фаза-фаза (3ф КЗ)", "C", "-RF<sub>RvPP</sub>/2", "X<sub>1</sub>"],
                ["Фаза-фаза (3ф КЗ)", "D", "-RF<sub>RvPP</sub>", "0"],
                ["Фаза-земля", "AA''", "RF<sub>FwPE</sub>", "0"],
                ["Фаза-земля", "BB''", "RF<sub>FwPE</sub> + ((2*X<sub>1</sub>+X<sub>0</sub>)/3)/tg(60)", "(2*X<sub>1</sub>+X<sub>0</sub>)/3"],
                ["Фаза-земля", "CC''", "0", "(2*X<sub>1</sub>+X<sub>0</sub>)/3"],
                ["Фаза-земля", "DD''", "-RF<sub>RvPE</sub>", "(2*X<sub>1</sub>+X<sub>0</sub>)/3"],
                ["Фаза-земля", "EE''", "-RF<sub>RvPE</sub>", "0"],
                ["Фаза-земля", "FF''", "-(RF<sub>RvPE</sub> + (2*X<sub>1</sub>+X<sub>0</sub>)/3)/tg(60)", "-(2*X<sub>1</sub>+X<sub>0</sub>)/3"],
                ["Фаза-земля", "GG''", "0", "-(2*X<sub>1</sub>+X<sub>0</sub>)/3"],
                ["Фаза-земля", "HH''", "RF<sub>FwPE</sub>", "-(2*X<sub>1</sub>+X<sub>0</sub>)/3"],
                ["Фаза-земля", "II''", "RF<sub>FwPE</sub>", "0"],
                ["Ld Fw", "A", "2*RLd<sub>Fw</sub>", "2*RLd<sub>Fw</sub>*tg(ArgLd)"],
                ["Ld Fw", "B", "RLd<sub>Fw</sub>", "RLd<sub>Fw</sub>*tg(ArgLd)"],
                ["Ld Fw", "C", "RLd<sub>Fw</sub>", "0"],
                ["Ld Fw", "D", "RLd<sub>Fw</sub>", "-RLd<sub>Fw</sub>*tg(ArgLd)"],
                ["Ld Fw", "E", "2*RLd<sub>Fw</sub>", "-2*RLd<sub>Fw</sub>*tg(ArgLd)"],
                ["Ld Rv", "A`", "-2*RLd<sub>Rv</sub>", "-2*RLd<sub>Rv</sub>*tg(ArgLd)"],
                ["Ld Rv", "B`", "-RLd<sub>Rv</sub>", "-RLd<sub>Rv</sub>*tg(ArgLd)"],
                ["Ld Rv", "C`", "-RLd<sub>Rv</sub>", "0"],
                ["Ld Rv", "D`", "-RLd<sub>Rv</sub>", "RLd<sub>Rv</sub>*tg(ArgLd)"],
                ["Ld Rv", "E`", "-2*RLd<sub>Rv</sub>", "2*RLd<sub>Rv</sub>*tg(ArgLd)"],
            ],
        )
        sections = [
            (
                t("help.overview.title"),
                style
                + f"<h2>{self._html(t('help.overview.title'))}</h2>"
                + f"<p>{self._html(t('help.overview.text'))}</p>",
            ),
            (
                t("help.distance.title"),
                style
                + f"<h2>{self._html(t('help.distance.title'))}</h2>"
                + "<p>1. Для кожної ступені зчитуються напрямок, X1, R1, X0, R0, RFPP, RFPE, TPP, TPE, ArgNegRes, ArgDir.</p>"
                + "<p>2. Для прямих і зворотних ступенів будуються полігони на R-X площині. Зворотні ступені відображаються дзеркально.</p>"
                + "<p class='formula'>RES1 = ATAN(X<sub>1</sub>/(-RF<sub>PP</sub>/2))*180/PI або 90/-90 при нульовому RF<sub>PP</sub>.</p>"
                + "<p class='formula'>B33 = IF RES1 &gt; ArgNegRes; 0; -RF<sub>PP</sub>/2.</p>"
                + "<h3>Координати зони фаза-фаза</h3>"
                + distance_points
                + "<h3>Координати зони фаза-земля</h3>"
                + phase_ground_points,
            ),
            (
                t("help.psd.title"),
                style
                + f"<h2>{self._html(t('help.psd.title'))}</h2>"
                + "<p>1. До розрахунку PSD беруться ступені, для яких min(TPP, TPE) &lt;= 2,5 c. Якщо час не заданий, він приймається рівним 0 c. Окремо користувач вибирає чутливий ступінь, який використовується як контрольна уставка для подальших розрахунків.</p>"
                + "<p>2. Для прямих ступенів визначаються X<sub>1Fw</sub>, X<sub>0Fw</sub>, RF<sub>PPFw</sub>, RF<sub>PEFw</sub> як максимальні значення відповідних уставок серед відібраних ступенів. Для зворотних ступенів аналогічно визначаються X<sub>1Rv</sub>, X<sub>0Rv</sub>, RF<sub>PPRv</sub>, RF<sub>PERv</sub>. Кути ArgDir та ArgNegRes вибираються окремо для прямого і зворотного напрямку як мінімальні значення у своїх групах.</p>"
                + "<p>3. Вибір внутрішньої зони у прямому напрямку виконується за умовами охоплення максимальних ступенів і перевірки перетину зворотного ступеня з лінією напрямленості у IV квадранті.</p>"
                + "<p class='formula'>X<sub>1InFw</sub> = max(K<sub>чPSD</sub>*X<sub>1Fw</sub>; K<sub>чPSD</sub>*(X<sub>1Fw</sub>+(X<sub>0Fw</sub>-X<sub>1Fw</sub>)/3); K<sub>чPSD</sub>*(RF<sub>PPRv</sub>/2)*tg(ArgDir<sub>Rv</sub>); K<sub>чPSD</sub>*RF<sub>PERv</sub>*tg(ArgDir<sub>Rv</sub>)).</p>"
                + "<p class='formula'>R<sub>1FInFw</sub> = max(K<sub>чPSD</sub>*RF<sub>PPFw</sub>/2; K<sub>чPSD</sub>*RF<sub>PEFw</sub>; K<sub>чPSD</sub>*X<sub>1Rv</sub>*tg(ArgNegRes<sub>Rv</sub>-90); K<sub>чPSD</sub>*(X<sub>1Rv</sub>+(X<sub>0Rv</sub>-X<sub>1Rv</sub>)/3)*tg(ArgNegRes<sub>Rv</sub>-90)).</p>"
                + "<p>4. Для зворотного напрямку використовується така сама логіка з перестановкою напрямків Fw/Rv: охоплюється зворотний ступінь і перевіряється перетин прямого ступеня з лінією напрямленості у II квадранті.</p>"
                + "<p class='formula'>X<sub>1InRv</sub> = max(K<sub>чPSD</sub>*X<sub>1Rv</sub>; K<sub>чPSD</sub>*(X<sub>1Rv</sub>+(X<sub>0Rv</sub>-X<sub>1Rv</sub>)/3); K<sub>чPSD</sub>*(RF<sub>PPFw</sub>/2)*tg(ArgDir<sub>Fw</sub>); K<sub>чPSD</sub>*RF<sub>PEFw</sub>*tg(ArgDir<sub>Fw</sub>)).</p>"
                + "<p class='formula'>R<sub>1FInRv</sub> = max(K<sub>чPSD</sub>*RF<sub>PPRv</sub>/2; K<sub>чPSD</sub>*RF<sub>PERv</sub>; K<sub>чPSD</sub>*X<sub>1Fw</sub>*tg(ArgNegRes<sub>Fw</sub>-90); K<sub>чPSD</sub>*(X<sub>1Fw</sub>+(X<sub>0Fw</sub>-X<sub>1Fw</sub>)/3)*tg(ArgNegRes<sub>Fw</sub>-90)).</p>"
                + "<p>5. Мінімальний кут нахилу береться окремо серед прямих і серед зворотних ступенів: F<sub>лFw</sub> = min(F<sub>л</sub> прямих ступенів), F<sub>лRv</sub> = min(F<sub>л</sub> зворотних ступенів). Далі R<sub>1LIn</sub> приймається як більше з двох значень.</p>"
                + "<p class='formula'>R<sub>1LIn</sub> = max(X<sub>1InFw</sub>/tg(F<sub>лFw</sub>); X<sub>1InRv</sub>/tg(F<sub>лRv</sub>)).</p>"
                + "<p>6. Уставки вирізу від навантаження визначаються за опорами навантаження, коефіцієнтом відлаштування K<sub>від</sub>, кутом навантаження і запасом ∆φ. Для результуючих умов вибору внутрішньої зони використовується округлення до цілого з правилом 12,49 → 13.</p>"
                + "<p class='formula'>RLd<sub>OutFw</sub> = K<sub>від</sub>*R<sub>навFw</sub>; RLd<sub>OutRv</sub> = K<sub>від</sub>*R<sub>навRv</sub>; ArgLd = max(F<sub>навFw</sub>; F<sub>навRv</sub>) + ∆φ.</p>"
                + "<p>7. За результатами розрахунку будуються внутрішня і зовнішня зони PSD, а також внутрішня і зовнішня зони RLD. Пунктиром відображається лише внутрішня зона RLD.</p>"
                + "<h3>Координати внутрішньої зони PSD</h3>"
                + psd_inner_points
                + "<h3>Координати зовнішньої зони PSD</h3>"
                + psd_outer_points
                + "<h3>Координати зон вирізу від навантаження RLD</h3>"
                + rld_points,
            ),
            (
                t("help.phs.title"),
                style
                + f"<h2>{self._html(t('help.phs.title'))}</h2>"
                + "<p>1. Для PHS використовується вибраний чутливий ступінь. Якщо він не вибраний, розрахунок блокується, а поле підсвічується як обов'язкове. Коефіцієнт чутливості PHS задається окремо як K<sub>чPHS</sub>.</p>"
                + "<p>2. Уставка X<sub>1</sub> вибирається як максимальна з умов чутливості до КЗ у кінці лінії: 1ф КЗ на землю, 2ф КЗ, 3ф КЗ для прямонапрямлених ступенів у I чверті та охоплення ступеня у IV чверті.</p>"
                + "<p class='formula'>X<sub>1</sub> = max(K<sub>чPHS</sub>*X<sub>1Zm</sub>; K<sub>чPHS</sub>*X<sub>1Zm</sub>*2/SQRT(3); K<sub>чPHS</sub>*(RF<sub>FPPZm</sub>/(2*cos(ArgDir))*sin(30+ArgDir))).</p>"
                + "<p>3. Уставка X<sub>0</sub> забезпечує чутливість до однофазного КЗ на землю в кінці лінії.</p>"
                + "<p class='formula'>X<sub>0</sub> = K<sub>чPHS</sub>*X<sub>0Zm</sub>.</p>"
                + "<p>4. Уставка RF<sub>RvPE</sub> вибирається за умовою перетину з лінією напрямленості у II чверті.</p>"
                + "<p class='formula'>RF<sub>RvPE</sub> = K<sub>чPHS</sub>*(X<sub>1Zm</sub>+(X<sub>0Zm</sub>-X<sub>1Zm</sub>)/3)*tg(ArgNegRes-90).</p>"
                + "<p>5. Уставка RF<sub>FwPE</sub> має розгалужену логіку: якщо F<sub>лк</sub> &gt; 60°, використовується пряма умова охоплення; інакше враховується активний та реактивний опір чутливого ступеня з поправкою через ctg60°.</p>"
                + "<p class='formula'>Якщо F<sub>лк</sub> &gt; 60°: RF<sub>FwPE</sub> = K<sub>чPHS</sub>*RF<sub>PEZm</sub>.</p>"
                + "<p class='formula'>Інакше: RF<sub>FwPE</sub> = K<sub>чPHS</sub>*2*((R<sub>0Zm</sub>+2*R<sub>1Zm</sub>)/3 + RF<sub>PEZm</sub> - (X<sub>0Zm</sub>+2*X<sub>1Zm</sub>)*ctg60°/3).</p>"
                + "<p>6. Уставка RF<sub>FwPP</sub> вибирається як максимальна з умов для 2ф і 3ф КЗ. Для 2ф КЗ застосовується окрема умова залежно від F<sub>лк</sub>, для 3ф КЗ використовується RF<sub>PPZm</sub>.</p>"
                + "<p class='formula'>Якщо F<sub>лк</sub> &gt; 60°: RF<sub>FwPP</sub> = K<sub>чPHS</sub>*RF<sub>PPZm</sub>; інакше RF<sub>FwPP</sub> = K<sub>чPHS</sub>*(2*R<sub>1Zm</sub>+RF<sub>PPZm</sub>-X<sub>1Zm</sub>*ctg60°).</p>"
                + "<p class='formula'>RF<sub>FwPP</sub> = K<sub>чPHS</sub>*(2*R<sub>1Zm</sub>+RF<sub>PPZm</sub>)*2/SQRT(3) для 3ф КЗ.</p>"
                + "<p>7. Уставки вирізу від навантаження PHS вибираються за мінімальним значенням. Спочатку виконується відлаштування від режиму навантаження, а якщо користувач підтвердив врахування PSD, додатково перевіряється умова з урахуванням зони PSD.</p>"
                + "<p class='formula'>RLd<sub>Fw</sub> = K<sub>від</sub>*R<sub>навFw</sub>; RLd<sub>Rv</sub> = K<sub>від</sub>*R<sub>навRv</sub>; ArgLd = max(F<sub>навFw</sub>; F<sub>навRv</sub>) + ∆φ.</p>"
                + "<p class='formula'>Якщо PSD враховується: ArgLd<sub>Fw</sub> = arctg(tg(ArgLd<sub>PSD</sub>)/KLd<sub>FwPSD</sub>); ArgLd<sub>Rv</sub> = arctg(tg(ArgLd<sub>PSD</sub>)/KLd<sub>RvPSD</sub>); RLd<sub>Fw</sub> = KLd<sub>FwPSD</sub>*RLd<sub>OutFwPSD</sub>; RLd<sub>Rv</sub> = KLd<sub>RvPSD</sub>*RLd<sub>OutRvPSD</sub>.</p>"
                + "<p>8. На графіках PHS додатково будуються зони Ld<sub>Fw</sub> та Ld<sub>Rv</sub>. Їх похилі межі штучно продовжуються до поточних меж графіка, тому заливка автоматично коригується під час масштабування або переміщення R-X площини.</p>"
                + "<h3>Координати графіків PHS</h3>"
                + phs_points,
            ),
        ]
        return sections

    def _help_table(self, headers: list[str], rows: list[list[str]]) -> str:
        html = ["<table><tr>"]
        html.extend(f"<th>{self._html(header)}</th>" for header in headers)
        html.append("</tr>")
        for row in rows:
            html.append("<tr>")
            html.extend(f"<td>{cell}</td>" for cell in row)
            html.append("</tr>")
        html.append("</table>")
        return "".join(html)

    def _retranslate(self) -> None:
        t = self._translator.text
        self.setWindowTitle(t("app.title"))
        self.file_menu.setTitle(t("menu.file"))
        self.new_action.setText(t("menu.new"))
        self.save_action.setText(t("menu.save"))
        self.save_as_action.setText(t("menu.save_as"))
        self.open_action.setText(t("menu.open"))
        self.exit_action.setText(t("menu.exit"))
        self.settings_action.setText(t("menu.settings"))
        self.help_action.setText(t("menu.help"))
        self.tabs.setTabText(0, t("tab.inputs"))
        self.tabs.setTabText(1, t("tab.distance_zones"))
        self.tabs.setTabText(2, t("tab.psd"))
        self.tabs.setTabText(3, t("tab.phs"))
        self.tabs.setTabText(4, t("tab.journal"))
        self._retranslate_segmented_module(self.distance_tabs, t("tab.distance_zones"))
        self._update_distance_phase_ground_tab()
        self._retranslate_segmented_module(self.psd_tabs, "PSD")
        self._retranslate_segmented_module(self.phs_tabs, "PHS")
        self.export_psd_report_button.setText(t("button.export_word"))
        self.export_psd_settings_button.setText(t("button.export_word"))
        self.export_phs_settings_button.setText(t("button.export_word"))
        self.export_phs_report_button.setText(t("button.export_word"))
        self.psd_report_search.setPlaceholderText(t("report.search_placeholder"))
        self.psd_report_find_prev_button.setText(t("button.find_previous"))
        self.psd_report_find_next_button.setText(t("button.find_next"))
        self.phs_report_search.setPlaceholderText(t("report.search_placeholder"))
        self.phs_report_find_prev_button.setText(t("button.find_previous"))
        self.phs_report_find_next_button.setText(t("button.find_next"))
        for name in (
            "distance_phase_phase_drag_cancel_button",
            "distance_phase_ground_drag_cancel_button",
        ):
            if hasattr(self, name):
                getattr(self, name).setText(t("button.cancel_changes"))
        for name in (
            "distance_phase_phase_drag_apply_button",
            "distance_phase_ground_drag_apply_button",
        ):
            if hasattr(self, name):
                getattr(self, name).setText(t("button.apply_changes"))
        self._update_psd_phase_ground_tab()
        self._retranslate_psd_tables()
        self.project_group.setTitle(t("group.project"))
        self.project_name_label.setText(t("label.project_name"))
        self.author_label.setText(t("label.author"))
        self.calculate_button.setText(t("button.calculate_all"))
        self.clear_results_button.setText(t("button.clear_results"))
        self.source_data_widget.retranslate()
        if self._last_result is not None:
            self._redraw_psd_charts()

    def _retranslate_segmented_module(self, module: QWidget, title: str) -> None:
        buttons = getattr(module, "_rel_psd_buttons", [])
        for button in buttons:
            key = button.property("translation_key")
            if isinstance(key, str):
                button.setText(self._translator.text(key))
            self._fit_segment_button_width(button)

    def _retranslate_psd_tables(self) -> None:
        self.psd_reach_table.setHorizontalHeaderLabels(
            [
                self._translator.text("table.name"),
                self._translator.text("report.psd_setting_value"),
                self._translator.text("psd.unit").capitalize(),
            ]
        )
        if hasattr(self, "phs_settings_tab"):
            self.phs_settings_tab.setHorizontalHeaderLabels(
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


