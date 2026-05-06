from __future__ import annotations

from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.database.project_repository import ProjectRepository
from app.localization.translator import Translator
from app.models.project import ProjectData
from app.utils.serialization import from_json, to_json


class ProjectManagerDialog(QDialog):
    def __init__(
        self,
        translator: Translator,
        session_factory: Callable[[], Session],
        current_project: ProjectData,
        parent=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._session_factory = session_factory
        self._current_project = current_project
        self.selected_project_id: int | None = None
        self._build_ui()
        self._retranslate()
        self._refresh_projects()

    def _build_ui(self) -> None:
        self.projects_list = QListWidget()
        self.projects_list.itemDoubleClicked.connect(lambda _: self._open_selected())

        self.create_button = QPushButton()
        self.delete_button = QPushButton()
        self.open_button = QPushButton()
        self.export_button = QPushButton()
        self.import_button = QPushButton()
        self.close_button = QPushButton()

        self.create_button.clicked.connect(self._create_project)
        self.delete_button.clicked.connect(self._delete_selected)
        self.open_button.clicked.connect(self._open_selected)
        self.export_button.clicked.connect(self._export_selected)
        self.import_button.clicked.connect(self._import_project)
        self.close_button.clicked.connect(self.reject)

        actions = QHBoxLayout()
        for button in (
            self.create_button,
            self.delete_button,
            self.open_button,
            self.export_button,
            self.import_button,
        ):
            actions.addWidget(button)
        actions.addStretch()
        actions.addWidget(self.close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.projects_list)
        layout.addLayout(actions)
        self.resize(760, 420)

    def _retranslate(self) -> None:
        t = self._translator.text
        self.setWindowTitle(t("project.dialog_title"))
        self.create_button.setText(t("project.create"))
        self.delete_button.setText(t("project.delete"))
        self.open_button.setText(t("project.open"))
        self.export_button.setText(t("project.export"))
        self.import_button.setText(t("project.import"))
        self.close_button.setText(t("project.close"))

    def _refresh_projects(self) -> None:
        self.projects_list.clear()
        with self._session_factory() as session:
            repository = ProjectRepository(session)
            for record in repository.list_projects():
                item = QListWidgetItem(
                    f"{record.name}    {record.updated_at:%Y-%m-%d %H:%M}"
                )
                item.setData(256, record.id)
                self.projects_list.addItem(item)
        if self.projects_list.count():
            self.projects_list.setCurrentRow(0)

    def _selected_id(self) -> int | None:
        item = self.projects_list.currentItem()
        return int(item.data(256)) if item is not None else None

    def _create_project(self) -> None:
        with self._session_factory() as session:
            repository = ProjectRepository(session)
            repository.save(self._current_project)
        self._refresh_projects()

    def _delete_selected(self) -> None:
        project_id = self._selected_id()
        if project_id is None:
            return
        with self._session_factory() as session:
            repository = ProjectRepository(session)
            repository.delete(project_id)
        self._refresh_projects()

    def _open_selected(self) -> None:
        self.selected_project_id = self._selected_id()
        if self.selected_project_id is not None:
            self.accept()

    def _export_selected(self) -> None:
        project_id = self._selected_id()
        if project_id is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._translator.text("project.export_title"),
            "rel-psd-project.json",
            "JSON (*.json)",
        )
        if not path:
            return
        with self._session_factory() as session:
            repository = ProjectRepository(session)
            bundle = repository.export_bundle(project_id)
        Path(path).write_text(to_json(bundle), encoding="utf-8")

    def _import_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._translator.text("project.import_title"),
            "",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            bundle = from_json(Path(path).read_text(encoding="utf-8"))
            with self._session_factory() as session:
                repository = ProjectRepository(session)
                repository.import_bundle(bundle)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            QMessageBox.warning(
                self,
                self._translator.text("project.import_title"),
                str(exc),
            )
            return
        self._refresh_projects()
