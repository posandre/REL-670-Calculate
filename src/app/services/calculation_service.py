from __future__ import annotations

from dataclasses import dataclass

from app.models.protection import DistanceZonePolygon, PsbCharacteristic
from app.models.project import ProjectData
from app.services.calculations.distance_zones import calculate_distance_zones
from app.services.calculations.psb import calculate_psb_characteristic


@dataclass(frozen=True)
class CalculationResult:
    distance_zones: list[DistanceZonePolygon]
    psb_characteristic: PsbCharacteristic | None


class CalculationService:
    def calculate(self, project: ProjectData) -> CalculationResult:
        zones = calculate_distance_zones(project.distance_zones)
        psb = (
            calculate_psb_characteristic(project.psb_settings)
            if project.psb_settings is not None
            else None
        )
        return CalculationResult(distance_zones=zones, psb_characteristic=psb)
