import pytest

from app.services.calculations.phase_phase_zones import (
    PhasePhaseStageInput,
    forward_res1_deg,
    phase_phase_stage_helpers,
    phase_phase_zone_polygon,
)


def test_forward_phase_phase_zone_points() -> None:
    zone = phase_phase_zone_polygon(
        PhasePhaseStageInput(
            name="1 ступінь",
            is_forward=True,
            x1=10.0,
            r1=5.0,
            rpff=4.0,
            arg_neg_res_deg=115.0,
            arg_dir_deg=15.0,
        )
    )

    assert zone.points[0] == (0.0, 0.0)
    assert zone.points[1] == pytest.approx((2.0, -0.5358984))
    assert zone.points[2] == pytest.approx((2.0, 0.0))
    assert zone.points[3] == pytest.approx((7.0, 10.0))
    assert zone.points[4] == pytest.approx((0.0, 10.0))
    assert zone.points[5] == pytest.approx((-2.0, 10.0))
    assert zone.points[6] == pytest.approx((-2.0, 10.0))
    assert zone.points[7] == pytest.approx((-2.0, 4.2890138))
    assert zone.points[8] == (0.0, 0.0)


def test_reverse_phase_phase_zone_points() -> None:
    zone = phase_phase_zone_polygon(
        PhasePhaseStageInput(
            name="2 ступінь",
            is_forward=False,
            x1=10.0,
            r1=5.0,
            rpff=4.0,
            arg_neg_res_deg=-65.0,
            arg_dir_deg=15.0,
        )
    )

    assert zone.points[0] == (0.0, 0.0)
    assert zone.points[1] == pytest.approx((-2.0, 0.5358984))
    assert zone.points[2] == pytest.approx((-2.0, 0.0))
    assert zone.points[3] == pytest.approx((-7.0, -10.0))
    assert zone.points[4] == pytest.approx((0.0, -10.0))
    assert zone.points[5] == pytest.approx((4.6630766, -10.0))
    assert zone.points[6] == pytest.approx((0.0, 0.0))
    assert zone.points[7] == pytest.approx((0.0, 0.0))
    assert zone.points[8] == (0.0, 0.0)


def test_forward_res1_helper() -> None:
    assert forward_res1_deg(x1=10.0, rpff=4.0) == pytest.approx(101.3099325)
    assert forward_res1_deg(x1=-10.0, rpff=0.0) == -90.0
    assert forward_res1_deg(x1=10.0, rpff=0.0) == 90.0


def test_phase_phase_helper_values() -> None:
    helpers = phase_phase_stage_helpers(
        PhasePhaseStageInput(
            name="1 ступінь",
            is_forward=True,
            x1=10.0,
            r1=5.0,
            rpff=4.0,
            arg_neg_res_deg=115.0,
            arg_dir_deg=15.0,
        )
    )

    assert helpers.res1_deg == pytest.approx(101.3099325)
    assert helpers.d32 == 0
    assert helpers.b33 == -2.0
