"""Phase-phase distance zone polygon formulas for PSD graphs."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan, isclose, pi, tan

from app.models.protection import DistanceZonePolygon


@dataclass(frozen=True)
class PhasePhaseStageInput:
    name: str
    is_forward: bool
    x1: float
    r1: float
    rpff: float
    arg_neg_res_deg: float
    arg_dir_deg: float


@dataclass(frozen=True)
class PhasePhaseStageHelpers:
    res1_deg: float
    d32: int
    b33: float


def phase_phase_zone_polygon(stage: PhasePhaseStageInput) -> DistanceZonePolygon:
    """Build phase-phase zone polygon points. TODO: verify against RET670 manual."""
    return DistanceZonePolygon(name=stage.name, points=phase_phase_zone_points(stage))


def phase_phase_zone_points(
    stage: PhasePhaseStageInput,
) -> tuple[tuple[float, float], ...]:
    """Build phase-phase points by checked spreadsheet logic. TODO: verify docs."""
    helpers = phase_phase_stage_helpers(stage)
    direction_sign = 1.0 if stage.is_forward else -1.0

    condition_met = helpers.d32 == 1
    c_prime_x = (
        -tan((stage.arg_neg_res_deg - 90.0) * pi / 180.0) * stage.x1
        if condition_met
        else -stage.rpff / 2.0
    )
    d_x = 0.0 if condition_met else -stage.rpff / 2.0
    d_y = 0.0 if condition_met else stage.x1
    d_prime_x = helpers.b33 if helpers.d32 == 0 else 0.0
    d_prime_y = (
        (1.0 / tan((stage.arg_neg_res_deg - 90.0) * pi / 180.0)) * (stage.rpff / 2.0)
        if helpers.d32 == 0
        else 0.0
    )

    base_points = (
        (0.0, 0.0),
        (stage.rpff / 2.0, -stage.rpff / 2.0 * tan(stage.arg_dir_deg * pi / 180.0)),
        (stage.rpff / 2.0, 0.0),
        (stage.r1 + stage.rpff / 2.0, stage.x1),
        (0.0, stage.x1),
        (c_prime_x, stage.x1),
        (d_x, d_y),
        (d_prime_x, d_prime_y),
        (0.0, 0.0),
    )
    return tuple((direction_sign * x_value, direction_sign * y_value) for x_value, y_value in base_points)


def phase_phase_stage_helpers(stage: PhasePhaseStageInput) -> PhasePhaseStageHelpers:
    """Return RES1/D32/B33 helpers from spreadsheet logic. TODO: verify docs."""
    res1 = res1_deg(stage.x1, -stage.rpff / 2.0)
    d32 = 1 if res1 > stage.arg_neg_res_deg else 0
    b33 = -stage.rpff / 2.0 if d32 == 0 else 0.0
    return PhasePhaseStageHelpers(res1_deg=res1, d32=d32, b33=b33)


def res1_deg(x_reach: float, resistive_reference: float) -> float:
    """Return RES1 helper angle. TODO: verify spreadsheet mapping by RET670 docs."""
    if not isclose(resistive_reference, 0.0, abs_tol=1e-12):
        angle = atan(x_reach / resistive_reference) * 180.0 / pi
        return angle if resistive_reference > 0 else angle + 180.0
    return -90.0 if x_reach < 0 else 90.0


def forward_res1_deg(x1: float, rpff: float) -> float:
    """Return RES1 helper angle. TODO: verify spreadsheet mapping by RET670 docs."""
    return res1_deg(x1, -rpff / 2.0)


def phase_phase_zone_polygons(
    stages: list[PhasePhaseStageInput],
) -> list[DistanceZonePolygon]:
    """Build polygons for all complete phase-phase stages."""
    return [phase_phase_zone_polygon(stage) for stage in stages]
