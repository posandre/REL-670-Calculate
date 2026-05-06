from __future__ import annotations

from app.models.protection import DistanceZoneSettings, PsbSettings
from app.validation.validators import validate_distance_zone, validate_psb_settings


def test_distance_zone_validation_reports_required_fields() -> None:
    issues = validate_distance_zone(
        DistanceZoneSettings(name="", reach_ohm=-1.0, angle_deg=0.0, resistive_reach_ohm=0.0)
    )

    assert {issue.message_key for issue in issues} == {
        "validation.zone_name_required",
        "validation.positive_reach",
        "validation.positive_resistance",
    }


def test_psb_validation_reports_inner_outer_issue() -> None:
    issues = validate_psb_settings(
        PsbSettings(
            inner_resistance_ohm=10.0,
            inner_reactance_ohm=20.0,
            outer_resistance_ohm=8.0,
            outer_reactance_ohm=16.0,
            angle_deg=75.0,
        )
    )

    assert "validation.psb_inner_outer" in {issue.message_key for issue in issues}
