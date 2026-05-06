import pytest

from app.services.calculations.phase_ground_zones import (
    PhaseGroundStageInput,
    phase_ground_stage_helpers,
    phase_ground_zone_polygon,
)


def test_forward_phase_ground_zone_points() -> None:
    zone = phase_ground_zone_polygon(
        PhaseGroundStageInput(
            name="1 ступінь",
            is_forward=True,
            x1=10.0,
            r1=5.0,
            x0=16.0,
            r0=8.0,
            rpff=4.0,
            rfpe=3.0,
            arg_neg_res_deg=115.0,
            arg_dir_deg=15.0,
        )
    )

    assert zone.points[0] == (0.0, 0.0)
    assert zone.points[1] == pytest.approx((3.0, -0.8038476))
    assert zone.points[2] == pytest.approx((3.0, 0.0))
    assert zone.points[3] == pytest.approx((9.0, 12.0))
    assert zone.points[4] == pytest.approx((0.0, 12.0))
    assert zone.points[5] == pytest.approx((0.0, 12.0))
    assert zone.points[6] == pytest.approx((-3.0, 12.0))
    assert zone.points[7] == pytest.approx((-2.0, 6.4335207))
    assert zone.points[8] == (0.0, 0.0)


def test_reverse_phase_ground_zone_points_are_mirrored() -> None:
    zone = phase_ground_zone_polygon(
        PhaseGroundStageInput(
            name="2 ступінь",
            is_forward=False,
            x1=10.0,
            r1=5.0,
            x0=16.0,
            r0=8.0,
            rpff=4.0,
            rfpe=3.0,
            arg_neg_res_deg=115.0,
            arg_dir_deg=15.0,
        )
    )

    assert zone.points[1] == pytest.approx((-3.0, 0.8038476))
    assert zone.points[3] == pytest.approx((-9.0, -12.0))
    assert zone.points[7] == pytest.approx((2.0, -6.4335207))


def test_phase_ground_helper_values() -> None:
    helpers = phase_ground_stage_helpers(
        PhaseGroundStageInput(
            name="1 ступінь",
            is_forward=True,
            x1=10.0,
            r1=5.0,
            x0=16.0,
            r0=8.0,
            rpff=4.0,
            rfpe=3.0,
            arg_neg_res_deg=115.0,
            arg_dir_deg=15.0,
        )
    )

    assert helpers.res1_deg == pytest.approx(104.0362435)
    assert helpers.d32 == 0
    assert helpers.b33 == -2.0
