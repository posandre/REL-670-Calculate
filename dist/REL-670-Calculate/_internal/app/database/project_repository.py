from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.entities import ProjectRecord
from app.models.electrical import ImpedancePoint, Phasor
from app.models.project import ProjectData, ProjectMetadata
from app.models.protection import DistanceZoneSettings, PsbSettings, ZoneDirection
from app.utils.serialization import from_json, to_json


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(
        self,
        project: ProjectData,
        results: dict[str, Any] | None = None,
        project_id: int | None = None,
    ) -> int:
        now = datetime.utcnow()
        project.metadata.updated_at = now
        record = self._session.get(ProjectRecord, project_id) if project_id else None
        if record is None:
            record = ProjectRecord(
                name=project.metadata.name,
                language=project.metadata.language,
                metadata_json="{}",
                input_json="{}",
                settings_json="{}",
                results_json="{}",
                created_at=project.metadata.created_at,
                updated_at=now,
            )
            self._session.add(record)
        record.name = project.metadata.name
        record.language = project.metadata.language
        record.metadata_json = to_json(project.metadata)
        record.input_json = to_json(
            {
                "impedance_points": project.impedance_points,
                "phasors": project.phasors,
                "source_data": project.source_data,
            }
        )
        record.settings_json = to_json(
            {
                "distance_zones": project.distance_zones,
                "psb_settings": project.psb_settings,
            }
        )
        record.results_json = to_json(results or {})
        record.updated_at = now
        self._session.commit()
        return record.id

    def delete(self, project_id: int) -> None:
        record = self._session.get(ProjectRecord, project_id)
        if record is not None:
            self._session.delete(record)
            self._session.commit()

    def export_bundle(self, project_id: int) -> dict[str, Any]:
        record = self._session.get(ProjectRecord, project_id)
        if record is None:
            msg = f"Project {project_id} was not found."
            raise KeyError(msg)
        return {
            "format": "REL-PSD project",
            "version": 1,
            "metadata": from_json(record.metadata_json),
            "input": from_json(record.input_json),
            "settings": from_json(record.settings_json),
            "results": from_json(record.results_json),
        }

    def import_bundle(self, bundle: dict[str, Any]) -> int:
        metadata_raw = bundle.get("metadata", {})
        project = self._bundle_to_project(bundle)
        project.metadata.name = str(metadata_raw.get("name", project.metadata.name))
        return self.save(project, results=bundle.get("results", {}))

    def load(self, project_id: int) -> ProjectData:
        record = self._session.get(ProjectRecord, project_id)
        if record is None:
            msg = f"Project {project_id} was not found."
            raise KeyError(msg)
        return self._record_to_project(record)

    def list_projects(self) -> list[ProjectRecord]:
        statement = select(ProjectRecord).order_by(ProjectRecord.updated_at.desc())
        return list(self._session.scalars(statement))

    def _bundle_to_project(self, bundle: dict[str, Any]) -> ProjectData:
        now = datetime.utcnow()
        metadata = dict(bundle.get("metadata", {}))
        metadata.setdefault("name", "Imported project")
        metadata.setdefault("author", "")
        metadata.setdefault("language", "uk")
        metadata.setdefault("created_at", now.isoformat())
        metadata.setdefault("updated_at", now.isoformat())
        input_raw = bundle.get("input", {})
        settings_raw = bundle.get("settings", {})
        record = ProjectRecord(
            name=str(metadata.get("name", "Imported project")),
            language=str(metadata.get("language", "uk")),
            metadata_json=to_json(metadata),
            input_json=to_json(input_raw),
            settings_json=to_json(settings_raw),
            results_json=to_json(bundle.get("results", {})),
            created_at=now,
            updated_at=now,
        )
        return self._record_to_project(record)

    def _record_to_project(self, record: ProjectRecord) -> ProjectData:
        metadata_raw = from_json(record.metadata_json)
        input_raw = from_json(record.input_json)
        settings_raw = from_json(record.settings_json)
        metadata = ProjectMetadata(
            name=str(metadata_raw["name"]),
            author=str(metadata_raw.get("author", "")),
            language=str(metadata_raw.get("language", "uk")),
            created_at=datetime.fromisoformat(str(metadata_raw["created_at"])),
            updated_at=datetime.fromisoformat(str(metadata_raw["updated_at"])),
        )
        impedance_points = [
            ImpedancePoint(
                name=str(item["name"]),
                resistance=float(item["resistance"]),
                reactance=float(item["reactance"]),
            )
            for item in input_raw.get("impedance_points", [])
        ]
        phasors = [
            Phasor(
                name=str(item["name"]),
                magnitude=float(item["magnitude"]),
                angle_deg=float(item["angle_deg"]),
            )
            for item in input_raw.get("phasors", [])
        ]
        source_data = input_raw.get("source_data", {})
        if not isinstance(source_data, dict):
            source_data = {}
        distance_zones = [
            DistanceZoneSettings(
                name=str(item["name"]),
                reach_ohm=float(item["reach_ohm"]),
                angle_deg=float(item["angle_deg"]),
                resistive_reach_ohm=float(item["resistive_reach_ohm"]),
                direction=ZoneDirection(str(item.get("direction", ZoneDirection.FORWARD))),
            )
            for item in settings_raw.get("distance_zones", [])
        ]
        psb_raw = settings_raw.get("psb_settings")
        psb_settings = (
            PsbSettings(
                inner_resistance_ohm=float(psb_raw["inner_resistance_ohm"]),
                inner_reactance_ohm=float(psb_raw["inner_reactance_ohm"]),
                outer_resistance_ohm=float(psb_raw["outer_resistance_ohm"]),
                outer_reactance_ohm=float(psb_raw["outer_reactance_ohm"]),
                angle_deg=float(psb_raw["angle_deg"]),
            )
            if psb_raw
            else None
        )
        return ProjectData(
            metadata=metadata,
            impedance_points=impedance_points,
            phasors=phasors,
            distance_zones=distance_zones,
            psb_settings=psb_settings,
            source_data=source_data,
        )
