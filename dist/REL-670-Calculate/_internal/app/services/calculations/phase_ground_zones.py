"""Phase-ground distance zone polygon formulas for PSD graphs."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan, isclose, pi, tan

from app.models.protection import DistanceZonePolygon


@dataclass(frozen=True)
class PhaseGroundStageInput:
    name: str
    is_forward: bool
    x1: float
    r1: float
    x0: float
    r0: float
    rpff: float
    rfpe: float
    arg_neg_res_deg: float
    arg_dir_deg: float


@dataclass(frozen=True)
class PhaseGroundStageHelpers:
    res1_deg: float
    d32: int
    b33: float


def phase_ground_zone_polygon(stage: PhaseGroundStageInput) -> DistanceZonePolygon:
    """Build phase-ground zone polygon points. TODO: verify against RET670 manual."""
    return DistanceZonePolygon(name=stage.name, points=phase_ground_zone_points(stage))


def phase_ground_zone_points(
    stage: PhaseGroundStageInput,
) -> tuple[tuple[float, float], ...]:
    """Build phase-ground points by checked spreadsheet logic. TODO: verify docs."""
    helpers = phase_ground_stage_helpers(stage)
    direction_sign = 1.0 if stage.is_forward else -1.0

    condition_met = helpers.d32 == 1
    x_equivalent = (2.0 * stage.x1 + stage.x0) / 3.0
    r_equivalent = (2.0 * stage.r1 + stage.r0) / 3.0
    c_prime_x = (
        -tan((stage.arg_neg_res_deg - 90.0) * pi / 180.0) * stage.x1
        if condition_met
        else 0.0
    )
    d_x = 0.0 if condition_met else -stage.rfpe
    d_y = 0.0 if condition_met else x_equivalent
    d_prime_x = helpers.b33 if helpers.d32 == 0 else 0.0
    d_prime_y = (
        (1.0 / tan((stage.arg_neg_res_deg - 90.0) * pi / 180.0)) * stage.rfpe
        if helpers.d32 == 0
        else 0.0
    )

    base_points = (
        (0.0, 0.0),
        (stage.rfpe, -stage.rfpe * tan(stage.arg_dir_deg * pi / 180.0)),
        (stage.rfpe, 0.0),
        (r_equivalent + stage.rfpe, x_equivalent),
        (0.0, x_equivalent),
        (c_prime_x, x_equivalent),
        (d_x, d_y),
        (d_prime_x, d_prime_y),
        (0.0, 0.0),
    )
    return tuple(
        (direction_sign * x_value, direction_sign * y_value)
        for x_value, y_value in base_points
    )


def phase_ground_stage_helpers(stage: PhaseGroundStageInput) -> PhaseGroundStageHelpers:
    """Return RES1/D32/B33 helpers from spreadsheet logic. TODO: verify docs."""
    x_equivalent = (2.0 * stage.x1 + stage.x0) / 3.0
    res1 = phase_ground_res1_deg(x_equivalent, stage.rpff, stage.rfpe)
    d32 = 1 if res1 > stage.arg_neg_res_deg else 0
    b33 = 0.0 if d32 == 1 else -stage.rpff / 2.0
    return PhaseGroundStageHelpers(res1_deg=res1, d32=d32, b33=b33)


def phase_ground_res1_deg(x_equivalent: float, rpff: float, rfpe: float) -> float:
    """Return RES1 helper angle. TODO: verify spreadsheet mapping by RET670 docs."""
    condition_reference = -rpff / 2.0
    angle_reference = -rfpe
    if not isclose(condition_reference, 0.0, abs_tol=1e-12):
        if isclose(angle_reference, 0.0, abs_tol=1e-12):
            return -90.0 if x_equivalent < 0 else 90.0
        angle = atan(x_equivalent / angle_reference) * 180.0 / pi
        return angle if angle_reference > 0 else angle + 180.0
    return -90.0 if x_equivalent < 0 else 90.0


def phase_ground_zone_polygons(
    stages: list[PhaseGroundStageInput],
) -> list[DistanceZonePolygon]:
    """Build polygons for all complete phase-ground stages."""
    return [phase_ground_zone_polygon(stage) for stage in stages]
