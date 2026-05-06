from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models.electrical import ImpedancePoint, Phasor
from app.models.protection import DistanceZoneSettings, PsbSettings


@dataclass
class ProjectMetadata:
    name: str
    author: str = ""
    language: str = "uk"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ProjectData:
    metadata: ProjectMetadata
    impedance_points: list[ImpedancePoint] = field(default_factory=list)
    phasors: list[Phasor] = field(default_factory=list)
    distance_zones: list[DistanceZoneSettings] = field(default_factory=list)
    psb_settings: PsbSettings | None = None
    source_data: dict[str, Any] = field(default_factory=dict)
