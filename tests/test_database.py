from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from app.database.project_repository import ProjectRepository
from app.database.session import create_session_factory, create_sqlite_engine, initialize_database
from app.models.electrical import ImpedancePoint, Phasor
from app.models.project import ProjectData, ProjectMetadata
from app.models.protection import DistanceZoneSettings, PsbSettings


def test_project_repository_save_and_load(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine = create_sqlite_engine(tmp_path / "projects.sqlite")
    initialize_database(engine)
    session_factory = create_session_factory(engine)

    project = ProjectData(
        metadata=ProjectMetadata(name="Unit Test", author="QA"),
        impedance_points=[ImpedancePoint("Z1", 1.0, 2.0)],
        phasors=[Phasor("UA", 1.0, 0.0)],
        distance_zones=[DistanceZoneSettings("Zone 1", 8.0, 75.0, 2.5)],
        psb_settings=PsbSettings(5.0, 10.0, 8.0, 16.0, 75.0),
        source_data={
            "protection_type": 1,
            "settings": {"X1": ["1", "2", "3", "4", "5"]},
        },
    )

    with session_factory() as session:
        repository = ProjectRepository(session)
        project_id = repository.save(project, results={"ok": True})
        loaded = repository.load(project_id)

    assert loaded.metadata.name == "Unit Test"
    assert loaded.impedance_points[0].reactance == 2.0
    assert loaded.distance_zones[0].name == "Zone 1"
    assert loaded.psb_settings is not None
    assert loaded.psb_settings.outer_reactance_ohm == 16.0
    assert loaded.source_data["protection_type"] == 1
    assert loaded.source_data["settings"]["X1"][2] == "3"


def test_project_repository_manages_multiple_projects(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine = create_sqlite_engine(tmp_path / "projects.sqlite")
    initialize_database(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        repository = ProjectRepository(session)
        first_id = repository.save(ProjectData(metadata=ProjectMetadata(name="First")))
        second_id = repository.save(ProjectData(metadata=ProjectMetadata(name="Second")))

        projects = repository.list_projects()
        bundle = repository.export_bundle(first_id)
        imported_id = repository.import_bundle(bundle)
        repository.delete(second_id)

        names = [project.name for project in repository.list_projects()]

    assert len(projects) == 2
    assert first_id != second_id
    assert imported_id not in {first_id, second_id}
    assert "First" in names
    assert "Second" not in names
