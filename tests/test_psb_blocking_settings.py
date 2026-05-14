import pytest

from app.services.calculations.psb_blocking_settings import (
    PsbLoadCutInput,
    PsbStageSettingInput,
    _round_setting,
    psb_blocking_settings,
)


def test_psb_blocking_settings_uses_directional_extremes() -> None:
    result = psb_blocking_settings(
        [
            PsbStageSettingInput(
                name="1",
                is_forward=True,
                x1=10.0,
                r1=5.0,
                x0=16.0,
                r0=8.0,
                rfpp=4.0,
                rfpe=3.0,
                arg_neg_res_deg=115.0,
                arg_dir_deg=15.0,
                load_angle_deg=63.4349488,
                time_sec=2.5,
            ),
            PsbStageSettingInput(
                name="2",
                is_forward=False,
                x1=8.0,
                r1=4.0,
                x0=14.0,
                r0=7.0,
                rfpp=6.0,
                rfpe=5.0,
                arg_neg_res_deg=-65.0,
                arg_dir_deg=15.0,
                load_angle_deg=63.4349488,
                time_sec=2.5,
            ),
            PsbStageSettingInput(
                name="3",
                is_forward=True,
                x1=100.0,
                r1=50.0,
                x0=160.0,
                r0=80.0,
                rfpp=40.0,
                rfpe=30.0,
                arg_neg_res_deg=115.0,
                arg_dir_deg=15.0,
                load_angle_deg=63.4349488,
                time_sec=2.6,
            ),
        ],
        sensitivity_factor=1.1,
    )

    assert result.forward is not None
    assert result.reverse is not None
    assert result.forward.x1 == 10.0
    assert result.forward.x0 == 16.0
    assert result.forward.rfpp == 4.0
    assert result.forward.rfpe == 3.0
    assert result.reverse.x1 == 8.0
    assert result.reverse.x0 == 14.0
    assert result.reverse.rfpp == 6.0
    assert result.reverse.rfpe == 5.0
    assert result.arg_dir_deg == 15.0
    assert result.arg_neg_res_deg == -65.0
    assert result.arg_dir_fw_deg == 15.0
    assert result.arg_neg_res_fw_deg == 115.0
    assert result.arg_dir_rv_deg == 15.0
    assert result.arg_neg_res_rv_deg == -65.0
    assert result.load_angle_fw_candidates == (("1", 63.4349488),)
    assert result.load_angle_rv_candidates == (("2", 63.4349488),)
    assert result.load_angle_candidates == (("1", 63.4349488), ("2", 63.4349488))
    assert result.included_forward_stage_names == ("1",)
    assert result.included_reverse_stage_names == ("2",)

    assert result.x1_in_fw == 14.0
    assert result.r1f_in_fw == 6.0
    assert result.x1_in_rv == 11.0
    assert result.r1f_in_rv == 7.0
    assert result.r1l_in == 7.0


def test_psb_setting_rounding_is_upward() -> None:
    assert _round_setting(12.0) == 12.0
    assert _round_setting(12.01) == 13.0
    assert _round_setting(12.49) == 13.0


def test_psb_blocking_settings_uses_direction_specific_angles() -> None:
    result = psb_blocking_settings(
        [
            PsbStageSettingInput(
                name="Fw",
                is_forward=True,
                x1=10.0,
                r1=5.0,
                x0=10.0,
                r0=5.0,
                rfpp=10.0,
                rfpe=5.0,
                arg_neg_res_deg=100.0,
                arg_dir_deg=30.0,
                load_angle_deg=60.0,
                time_sec=2.5,
            ),
            PsbStageSettingInput(
                name="Rv",
                is_forward=False,
                x1=10.0,
                r1=5.0,
                x0=10.0,
                r0=5.0,
                rfpp=10.0,
                rfpe=5.0,
                arg_neg_res_deg=120.0,
                arg_dir_deg=45.0,
                load_angle_deg=60.0,
                time_sec=2.5,
            ),
        ],
        sensitivity_factor=1.0,
    )

    assert result.arg_dir_fw_deg == 30.0
    assert result.arg_neg_res_fw_deg == 100.0
    assert result.arg_dir_rv_deg == 45.0
    assert result.arg_neg_res_rv_deg == 120.0
    assert result.x1_in_fw_reverse_intersection_phase == pytest.approx(2.8867513)
    assert result.x1_in_rv_forward_intersection_phase == pytest.approx(5.0)


def test_psb_blocking_settings_reports_load_angle_min_candidates() -> None:
    result = psb_blocking_settings(
        [
            PsbStageSettingInput(
                name="1",
                is_forward=True,
                x1=10.0,
                r1=5.0,
                x0=10.0,
                r0=5.0,
                rfpp=4.0,
                rfpe=2.0,
                arg_neg_res_deg=115.0,
                arg_dir_deg=15.0,
                load_angle_deg=60.0,
                time_sec=2.5,
            ),
            PsbStageSettingInput(
                name="2",
                is_forward=False,
                x1=8.0,
                r1=4.0,
                x0=8.0,
                r0=4.0,
                rfpp=4.0,
                rfpe=2.0,
                arg_neg_res_deg=-65.0,
                arg_dir_deg=15.0,
                load_angle_deg=50.9925,
                time_sec=2.5,
            ),
        ],
        sensitivity_factor=1.0,
    )

    assert result.load_angle_candidates == (("1", 60.0), ("2", 50.9925))
    assert result.load_angle_deg == 50.9925
    assert result.load_angle_fw_candidates == (("1", 60.0),)
    assert result.load_angle_rv_candidates == (("2", 50.9925),)
    assert result.load_angle_fw_deg == 60.0
    assert result.load_angle_rv_deg == 50.9925


def test_psb_blocking_settings_uses_forward_load_angle_for_forward_r1l() -> None:
    result = psb_blocking_settings(
        [
            PsbStageSettingInput(
                name="Fw",
                is_forward=True,
                x1=30.0,
                r1=5.0,
                x0=30.0,
                r0=5.0,
                rfpp=4.0,
                rfpe=2.0,
                arg_neg_res_deg=115.0,
                arg_dir_deg=15.0,
                load_angle_deg=65.0,
                time_sec=2.5,
            ),
            PsbStageSettingInput(
                name="Rv",
                is_forward=False,
                x1=8.0,
                r1=4.0,
                x0=8.0,
                r0=4.0,
                rfpp=4.0,
                rfpe=2.0,
                arg_neg_res_deg=-65.0,
                arg_dir_deg=15.0,
                load_angle_deg=50.0,
                time_sec=2.5,
            ),
        ],
        sensitivity_factor=1.0,
    )

    assert result.x1_in_fw == 30.0
    assert result.load_angle_fw_deg == 65.0
    assert result.load_angle_rv_deg == 50.0
    assert result.r1l_in_fw == pytest.approx(30.0 / 2.1445069)


def test_psb_blocking_settings_includes_stages_with_default_zero_time() -> None:
    result = psb_blocking_settings(
        [
            PsbStageSettingInput(
                name="1",
                is_forward=True,
                x1=10.0,
                r1=5.0,
                x0=16.0,
                r0=8.0,
                rfpp=4.0,
                rfpe=3.0,
                arg_neg_res_deg=115.0,
                arg_dir_deg=15.0,
                load_angle_deg=63.4349488,
                time_sec=0.0,
            )
        ],
        sensitivity_factor=1.1,
    )

    assert result.included_forward_stage_names == ("1",)
    assert result.forward is not None
    assert result.forward.x1 == 10.0


def test_psb_blocking_settings_calculates_load_cutout_settings() -> None:
    result = psb_blocking_settings(
        [
            PsbStageSettingInput(
                name="Fw",
                is_forward=True,
                x1=10.0,
                r1=5.0,
                x0=16.0,
                r0=8.0,
                rfpp=4.0,
                rfpe=3.0,
                arg_neg_res_deg=115.0,
                arg_dir_deg=15.0,
                load_angle_deg=63.4349488,
                time_sec=2.5,
            ),
            PsbStageSettingInput(
                name="Rv",
                is_forward=False,
                x1=8.0,
                r1=4.0,
                x0=14.0,
                r0=7.0,
                rfpp=6.0,
                rfpe=5.0,
                arg_neg_res_deg=-65.0,
                arg_dir_deg=15.0,
                load_angle_deg=63.4349488,
                time_sec=2.5,
            ),
        ],
        sensitivity_factor=1.1,
        load_cut=PsbLoadCutInput(
            r_load_fw=100.0,
            x_load_fw=20.0,
            r_load_rv=80.0,
            x_load_rv=60.0,
            rejection_factor=0.85,
            delta_phi_deg=4.0,
            delta_r_secondary=1.0,
            delta_r_primary=10.0,
        ),
    )

    assert result.rld_out_fw_load == pytest.approx(85.0)
    assert result.rld_in_fw_load == pytest.approx(75.0)
    assert result.rld_in_fw == pytest.approx(6.0)
    assert result.rld_out_fw == pytest.approx(16.0)
    assert result.rld_out_rv_load == pytest.approx(68.0)
    assert result.rld_in_rv == pytest.approx(7.0)
    assert result.rld_out_rv == pytest.approx(17.0)
    assert result.kld_fw == pytest.approx(6.0 / 16.0)
    assert result.kld_rv == pytest.approx(7.0 / 17.0)
    assert result.arg_ld_fw_base_deg == pytest.approx(11.309932, rel=1e-6)
    assert result.arg_ld_rv_base_deg == pytest.approx(36.869897, rel=1e-6)
    assert result.arg_ld_deg == pytest.approx(40.869897, rel=1e-6)
