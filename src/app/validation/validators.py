from __future__ import annotations

from dataclasses import dataclass

from app.models.protection import DistanceZoneSettings, PsbSettings


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    message_key: str


def validate_distance_zone(settings: DistanceZoneSettings) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not settings.name.strip():
        issues.append(ValidationIssue("name", "validation.zone_name_required"))
    if settings.reach_ohm <= 0:
        issues.append(ValidationIssue("reach_ohm", "validation.positive_reach"))
    if settings.resistive_reach_ohm <= 0:
        issues.append(ValidationIssue("resistive_reach_ohm", "validation.positive_resistance"))
    return issues


def validate_psb_settings(settings: PsbSettings) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if settings.inner_resistance_ohm <= 0 or settings.outer_resistance_ohm <= 0:
        issues.append(ValidationIssue("resistance", "validation.positive_resistance"))
    if settings.inner_reactance_ohm <= 0 or settings.outer_reactance_ohm <= 0:
        issues.append(ValidationIssue("reactance", "validation.positive_reactance"))
    if settings.inner_resistance_ohm >= settings.outer_resistance_ohm:
        issues.append(ValidationIssue("inner_resistance_ohm", "validation.psb_inner_outer"))
    if settings.inner_reactance_ohm >= settings.outer_reactance_ohm:
        issues.append(ValidationIssue("inner_reactance_ohm", "validation.psb_inner_outer"))
    return issues
