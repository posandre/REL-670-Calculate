from __future__ import annotations

from math import isclose, tan, pi

from app.services.calculations.phs_selector_settings import (
    PhsStageInput,
    phs_selector_settings,
)
from app.services.calculations.psb_blocking_settings import PsbLoadCutInput


def test_phs_selector_calculates_core_settings_without_psd() -> None:
    stage = PhsStageInput(
        name="1 ступінь",
        x1=10.0,
        r1=4.0,
        x0=16.0,
        r0=6.0,
        rfpp=8.0,
        rfpe=6.0,
        arg_dir_deg=15.0,
        arg_neg_res_deg=115.0,
        load_angle_ground_deg=50.0,
    )

    result = phs_selector_settings(
        stage,
        1.1,
        PsbLoadCutInput(
            r_load_fw=30.0,
            x_load_fw=10.0,
            r_load_rv=20.0,
            x_load_rv=8.0,
            rejection_factor=0.85,
            delta_phi_deg=4.0,
        ),
        None,
        use_psd_zone=False,
    )

    assert isclose(result.x0, 17.6)
    assert isclose(result.inblock_pp, 20.0)
    assert isclose(result.inblock_pe, 20.0)
    assert result.x1 == max(
        result.x1_ground_fault,
        result.x1_three_phase_q1,
        result.x1_three_phase_q4,
    )
    assert result.rffw_pp == max(
        result.rffw_pp_two_phase,
        result.rffw_pp_three_phase,
    )
    expected_rfrv_pe = 1.1 * (10.0 + (16.0 - 10.0) / 3.0) * tan((115.0 - 90.0) * pi / 180.0)
    assert isclose(result.rfrv_pe, expected_rfrv_pe)
    expected_rffw_pe = 1.1 * 2.0 * (
        (6.0 + 2.0 * 4.0) / 3.0
        + 6.0
        - (16.0 + 2.0 * 10.0) / (3.0 * tan(60.0 * pi / 180.0))
    )
    assert isclose(result.rffw_pe, expected_rffw_pe)
    assert result.rffw_pe_angle_branch == "low_angle"
    assert isclose(result.rld_fw, 25.5)
    assert isclose(result.rld_rv, 17.0)
    assert result.rld_fw_psd is None
    assert result.rld_rv_psd is None
    assert result.arg_ld is not None
