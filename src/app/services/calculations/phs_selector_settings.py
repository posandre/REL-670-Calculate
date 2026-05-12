"""Phase selector setting formulas for the PHS module."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, atan, cos, degrees, pi, sin, sqrt, tan

from app.services.calculations.psb_blocking_settings import PsbBlockingResult, PsbLoadCutInput

STANDARD_INBLOCK_PP = 20.0
STANDARD_INBLOCK_PE = 20.0


@dataclass(frozen=True)
class PhsStageInput:
    name: str
    x1: float
    r1: float
    x0: float
    r0: float
    rfpp: float
    rfpe: float
    arg_dir_deg: float
    arg_neg_res_deg: float
    load_angle_ground_deg: float | None


@dataclass(frozen=True)
class PhsSelectorResult:
    phs_sensitivity_factor: float
    stage: PhsStageInput
    use_psd_zone: bool
    inblock_pp: float
    inblock_pe: float
    x1_ground_fault: float
    x1_three_phase_q1: float
    x1_three_phase_q4: float
    x1: float
    x0: float
    rfrv_pe: float
    rfrv_pe_angle_branch: str
    rffw_pp_two_phase: float
    rffw_pp_three_phase: float
    rffw_pp: float
    rfrv_pp: float
    rffw_pe_angle_branch: str
    rffw_pe: float
    rld_fw_load: float | None
    rld_rv_load: float | None
    arg_ld_load: float | None
    arg_ld_fw_psd: float | None
    arg_ld_rv_psd: float | None
    rld_fw_psd: float | None
    rld_rv_psd: float | None
    rld_fw: float | None
    rld_rv: float | None
    arg_ld: float | None


def phs_selector_settings(
    stage: PhsStageInput,
    phs_sensitivity_factor: float,
    load_cut: PsbLoadCutInput | None,
    psd_result: PsbBlockingResult | None,
    *,
    use_psd_zone: bool,
) -> PhsSelectorResult:
    """Calculate PHS selector settings. TODO: verify formulas by RET670 docs."""
    x1_ground_fault = round(phs_sensitivity_factor * stage.x1)
    x1_three_phase_q1 = round(phs_sensitivity_factor * (stage.x1 * 2.0 / sqrt(3.0)))
    x1_three_phase_q4 = round(phs_sensitivity_factor * (
        stage.rfpp
        / (2.0 * _cos_deg(stage.arg_dir_deg))
        * _sin_deg(30.0 + stage.arg_dir_deg)
    ))
    x1 = ceil(max(x1_ground_fault, x1_three_phase_q1, x1_three_phase_q4))
    x0 = ceil(phs_sensitivity_factor * stage.x0)
    rfrv_pe = ceil(
        phs_sensitivity_factor
        * _compensated_x(stage.x1, stage.x0)
        * _tan_deg(stage.arg_neg_res_deg - 90.0)
    )
    rfrv_pe_angle_branch = "direction_intersection"
    rffw_pp_two_phase = (
        phs_sensitivity_factor * stage.rfpp
        if (stage.load_angle_ground_deg or 0.0) > 60.0
        else phs_sensitivity_factor
        * (2.0 * stage.r1 + stage.rfpp - stage.x1 / _tan_deg(60.0))
    )
    rffw_pp_three_phase = (
        phs_sensitivity_factor * (2.0 * stage.r1 + stage.rfpp) * 2.0 / sqrt(3.0)
    )
    rffw_pp = ceil(max(rffw_pp_two_phase, rffw_pp_three_phase))
    rfrv_pp = rffw_pp
    if (stage.load_angle_ground_deg or 0.0) > 60.0:
        rffw_pe = ceil(phs_sensitivity_factor * stage.rfpe)
        rffw_pe_angle_branch = "high_angle"
    else:
        rffw_pe = phs_sensitivity_factor * 2.0 * (
            (stage.r0 + 2.0 * stage.r1) / 3.0
            + stage.rfpe
            - (stage.x0 + 2.0 * stage.x1) / (3.0 * _tan_deg(60.0))
        )
        rffw_pe_angle_branch = "low_angle"

    rld_fw_load = _multiply(_field(load_cut, "rejection_factor"), _field(load_cut, "r_load_fw"))
    rld_rv_load = _multiply(_field(load_cut, "rejection_factor"), _field(load_cut, "r_load_rv"))
    arg_ld_load = _add(
        _max_or_none(
            [
                _load_angle(_field(load_cut, "r_load_fw"), _field(load_cut, "x_load_fw")),
                _load_angle(_field(load_cut, "r_load_rv"), _field(load_cut, "x_load_rv")),
            ]
        ),
        _field(load_cut, "delta_phi_deg"),
    )

    arg_ld_fw_psd = None
    arg_ld_rv_psd = None
    rld_fw_psd = None
    rld_rv_psd = None
    if use_psd_zone and psd_result is not None and psd_result.arg_ld_deg is not None:
        tan_arg_ld_psd = _tan_deg(psd_result.arg_ld_deg)
        if psd_result.kld_fw not in (None, 0.0):
            arg_ld_fw_psd = degrees(atan(tan_arg_ld_psd / psd_result.kld_fw))
        if psd_result.kld_rv not in (None, 0.0):
            arg_ld_rv_psd = degrees(atan(tan_arg_ld_psd / psd_result.kld_rv))
        rld_fw_psd = _multiply(psd_result.kld_fw, psd_result.rld_out_fw)
        rld_rv_psd = _multiply(psd_result.kld_rv, psd_result.rld_out_rv)

    rld_fw = _min_or_none([rld_fw_load, rld_fw_psd])
    rld_rv = _min_or_none([rld_rv_load, rld_rv_psd])
    arg_ld = _min_or_none([arg_ld_load, arg_ld_fw_psd, arg_ld_rv_psd])

    return PhsSelectorResult(
        phs_sensitivity_factor=phs_sensitivity_factor,
        stage=stage,
        use_psd_zone=use_psd_zone,
        inblock_pp=STANDARD_INBLOCK_PP,
        inblock_pe=STANDARD_INBLOCK_PE,
        x1_ground_fault=x1_ground_fault,
        x1_three_phase_q1=x1_three_phase_q1,
        x1_three_phase_q4=x1_three_phase_q4,
        x1=x1,
        x0=x0,
        rfrv_pe=rfrv_pe,
        rfrv_pe_angle_branch=rfrv_pe_angle_branch,
        rffw_pp_two_phase=rffw_pp_two_phase,
        rffw_pp_three_phase=rffw_pp_three_phase,
        rffw_pp=rffw_pp,
        rfrv_pp=rfrv_pp,
        rffw_pe_angle_branch=rffw_pe_angle_branch,
        rffw_pe=rffw_pe,
        rld_fw_load=rld_fw_load,
        rld_rv_load=rld_rv_load,
        arg_ld_load=arg_ld_load,
        arg_ld_fw_psd=arg_ld_fw_psd,
        arg_ld_rv_psd=arg_ld_rv_psd,
        rld_fw_psd=rld_fw_psd,
        rld_rv_psd=rld_rv_psd,
        rld_fw=rld_fw,
        rld_rv=rld_rv,
        arg_ld=arg_ld,
    )


def _field(load_cut: PsbLoadCutInput | None, name: str) -> float | None:
    return getattr(load_cut, name) if load_cut is not None else None


def _compensated_x(x1: float, x0: float) -> float:
    return x1 + (x0 - x1) / 3.0


def _tan_deg(angle_deg: float) -> float:
    return tan(angle_deg * pi / 180.0)


def _cos_deg(angle_deg: float) -> float:
    return cos(angle_deg * pi / 180.0)


def _sin_deg(angle_deg: float) -> float:
    return sin(angle_deg * pi / 180.0)


def _load_angle(r_value: float | None, x_value: float | None) -> float | None:
    if r_value in (None, 0.0) or x_value is None:
        return None
    return abs(degrees(atan(x_value / r_value)))


def _add(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left + right


def _multiply(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left * right


def _max_or_none(values: list[float | None]) -> float | None:
    complete_values = [value for value in values if value is not None]
    return max(complete_values) if complete_values else None


def _min_or_none(values: list[float | None]) -> float | None:
    complete_values = [value for value in values if value is not None]
    return min(complete_values) if complete_values else None
