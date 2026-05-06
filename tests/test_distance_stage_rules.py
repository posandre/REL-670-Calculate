import pytest

from app.services.calculations.distance_stage_rules import (
    arg_dir_default,
    arg_neg_res_by_direction,
    compensated_load_angle_deg,
    load_angle_deg,
)


def test_direction_angle_defaults() -> None:
    assert arg_neg_res_by_direction(is_forward=True) == 115.0
    assert arg_neg_res_by_direction(is_forward=False) == -65.0
    assert arg_dir_default() == 15.0


def test_load_angle_formula() -> None:
    assert load_angle_deg(r1=2.0, x1=2.0) == pytest.approx(45.0)
    assert load_angle_deg(r1=1.0, x1=3.0) == pytest.approx(71.5650512)


def test_compensated_load_angle_formula() -> None:
    result = compensated_load_angle_deg(r1=3.0, x1=6.0, r0=6.0, x0=12.0)

    assert result == pytest.approx(63.4349488)
