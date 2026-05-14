"""Power swing blocking setting formulas for the PSD settings table."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan, ceil, degrees, pi, tan

DEFAULT_MAX_BLOCKING_STAGE_TIME_SEC = 2.5


@dataclass(frozen=True)
class PsbStageSettingInput:
    name: str
    is_forward: bool
    x1: float
    r1: float
    x0: float
    r0: float
    rfpp: float
    rfpe: float
    arg_neg_res_deg: float
    arg_dir_deg: float
    load_angle_deg: float | None
    time_sec: float | None
    compensated_load_angle_deg: float | None = None


@dataclass(frozen=True)
class PsbDirectionExtremes:
    x1: float
    x0: float
    rfpp: float
    rfpe: float


@dataclass(frozen=True)
class PsbLoadCutInput:
    r_load_fw: float | None = None
    x_load_fw: float | None = None
    r_load_rv: float | None = None
    x_load_rv: float | None = None
    rejection_factor: float | None = None
    delta_phi_deg: float | None = None
    delta_r_secondary: float | None = None
    delta_r_primary: float | None = None


@dataclass(frozen=True)
class PsbBlockingResult:
    sensitivity_factor: float
    forward: PsbDirectionExtremes | None
    reverse: PsbDirectionExtremes | None
    included_forward_stage_names: tuple[str, ...]
    included_reverse_stage_names: tuple[str, ...]
    arg_dir_deg: float | None
    arg_neg_res_deg: float | None
    arg_dir_fw_deg: float | None
    arg_neg_res_fw_deg: float | None
    arg_dir_rv_deg: float | None
    arg_neg_res_rv_deg: float | None
    load_angle_deg: float | None
    load_angle_candidates: tuple[tuple[str, float], ...]
    load_angle_fw_deg: float | None
    load_angle_rv_deg: float | None
    load_angle_fw_candidates: tuple[tuple[str, float], ...]
    load_angle_rv_candidates: tuple[tuple[str, float], ...]
    x1_in_fw_coverage_phase: float | None
    x1_in_fw_coverage_ground: float | None
    x1_in_fw_reverse_intersection_phase: float | None
    x1_in_fw_reverse_intersection_ground: float | None
    x1_in_fw: float | None
    r1f_in_fw_coverage_phase: float | None
    r1f_in_fw_coverage_ground: float | None
    r1f_in_fw_reverse_intersection_phase: float | None
    r1f_in_fw_reverse_intersection_ground: float | None
    r1f_in_fw: float | None
    x1_in_rv_coverage_phase: float | None
    x1_in_rv_coverage_ground: float | None
    x1_in_rv_forward_intersection_phase: float | None
    x1_in_rv_forward_intersection_ground: float | None
    x1_in_rv: float | None
    r1f_in_rv_coverage_phase: float | None
    r1f_in_rv_coverage_ground: float | None
    r1f_in_rv_forward_intersection_phase: float | None
    r1f_in_rv_forward_intersection_ground: float | None
    r1f_in_rv: float | None
    r1l_in_fw: float | None
    r1l_in_rv: float | None
    r1l_in: float | None
    load_cut: PsbLoadCutInput | None
    rld_out_fw_load: float | None
    rld_out_rv_load: float | None
    rld_in_fw_load: float | None
    rld_in_rv_load: float | None
    rld_in_fw: float | None
    rld_in_rv: float | None
    rld_out_fw: float | None
    rld_out_rv: float | None
    kld_fw: float | None
    kld_rv: float | None
    arg_ld_fw_base_deg: float | None
    arg_ld_rv_base_deg: float | None
    arg_ld_selected_deg: float | None
    arg_ld_deg: float | None


def psb_blocking_settings(
    stages: list[PsbStageSettingInput],
    sensitivity_factor: float,
    load_cut: PsbLoadCutInput | None = None,
    *,
    max_stage_time_sec: float = DEFAULT_MAX_BLOCKING_STAGE_TIME_SEC,
) -> PsbBlockingResult:
    """Calculate PSD blocking settings. TODO: verify formulas by RET670 docs."""
    included_stages = [
        stage
        for stage in stages
        if stage.time_sec is not None and stage.time_sec <= max_stage_time_sec
    ]
    forward_stages = [stage for stage in included_stages if stage.is_forward]
    reverse_stages = [stage for stage in included_stages if not stage.is_forward]
    forward = _direction_extremes(forward_stages)
    reverse = _direction_extremes(reverse_stages)
    arg_dir_fw = _min_or_none([stage.arg_dir_deg for stage in forward_stages])
    arg_neg_res_fw = _min_or_none([stage.arg_neg_res_deg for stage in forward_stages])
    arg_dir_rv = _min_or_none([stage.arg_dir_deg for stage in reverse_stages])
    arg_neg_res_rv = _min_or_none([stage.arg_neg_res_deg for stage in reverse_stages])
    load_angle_fw_candidates = _load_angle_candidates(forward_stages)
    load_angle_rv_candidates = _load_angle_candidates(reverse_stages)
    load_angle_candidates = load_angle_fw_candidates + load_angle_rv_candidates
    load_angle_fw = _min_or_none([value for _, value in load_angle_fw_candidates])
    load_angle_rv = _min_or_none([value for _, value in load_angle_rv_candidates])
    load_angle = _min_or_none([value for _, value in load_angle_candidates])
    if load_angle_fw is None:
        load_angle_fw = load_angle
    if load_angle_rv is None:
        load_angle_rv = load_angle

    fw_coverage_x_phase = _multiply(sensitivity_factor, forward.x1 if forward else None)
    fw_coverage_x_ground = _multiply(
        sensitivity_factor,
        _compensated_x(forward.x1, forward.x0) if forward else None,
    )
    fw_coverage_r_phase = _multiply(
        sensitivity_factor,
        forward.rfpp / 2.0 if forward else None,
    )
    fw_coverage_r_ground = _multiply(sensitivity_factor, forward.rfpe if forward else None)
    fw_reverse_x_phase = _multiply(
        sensitivity_factor,
        _multiply(reverse.rfpp / 2.0, _tan_deg(arg_dir_fw)) if reverse else None,
    )
    fw_reverse_x_ground = _multiply(
        sensitivity_factor,
        _multiply(reverse.rfpe, _tan_deg(arg_dir_fw)) if reverse else None,
    )
    fw_reverse_r_phase = _multiply(
        sensitivity_factor,
        _multiply(reverse.x1, _tan_deg((arg_neg_res_fw or 0.0) - 90.0))
        if reverse and arg_neg_res_fw is not None
        else None,
    )
    fw_reverse_r_ground = _multiply(
        sensitivity_factor,
        _multiply(
            _compensated_x(reverse.x1, reverse.x0),
            _tan_deg((arg_neg_res_fw or 0.0) - 90.0),
        )
        if reverse and arg_neg_res_fw is not None
        else None,
    )
    x1_in_fw = _round_setting(
        _max_or_none(
            [fw_coverage_x_phase, fw_coverage_x_ground, fw_reverse_x_phase, fw_reverse_x_ground]
        )
    )
    r1f_in_fw = _round_setting(
        _max_or_none(
            [fw_coverage_r_phase, fw_coverage_r_ground, fw_reverse_r_phase, fw_reverse_r_ground]
        )
    )

    rv_coverage_x_phase = _multiply(sensitivity_factor, reverse.x1 if reverse else None)
    rv_coverage_x_ground = _multiply(
        sensitivity_factor,
        _compensated_x(reverse.x1, reverse.x0) if reverse else None,
    )
    rv_coverage_r_phase = _multiply(
        sensitivity_factor,
        reverse.rfpp / 2.0 if reverse else None,
    )
    rv_coverage_r_ground = _multiply(sensitivity_factor, reverse.rfpe if reverse else None)
    rv_forward_x_phase = _multiply(
        sensitivity_factor,
        _multiply(forward.rfpp / 2.0, _tan_deg(arg_dir_rv)) if forward else None,
    )
    rv_forward_x_ground = _multiply(
        sensitivity_factor,
        _multiply(forward.rfpe, _tan_deg(arg_dir_rv)) if forward else None,
    )
    rv_forward_r_phase = _multiply(
        sensitivity_factor,
        _multiply(forward.x1, _tan_deg((arg_neg_res_rv or 0.0) - 90.0))
        if forward and arg_neg_res_rv is not None
        else None,
    )
    rv_forward_r_ground = _multiply(
        sensitivity_factor,
        _multiply(
            _compensated_x(forward.x1, forward.x0),
            _tan_deg((arg_neg_res_rv or 0.0) - 90.0),
        )
        if forward and arg_neg_res_rv is not None
        else None,
    )
    x1_in_rv = _round_setting(
        _max_or_none(
            [rv_coverage_x_phase, rv_coverage_x_ground, rv_forward_x_phase, rv_forward_x_ground]
        )
    )
    r1f_in_rv = _round_setting(
        _max_or_none(
            [rv_coverage_r_phase, rv_coverage_r_ground, rv_forward_r_phase, rv_forward_r_ground]
        )
    )

    r1l_in_fw = _divide_by_tan(x1_in_fw, load_angle_fw)
    r1l_in_rv = _divide_by_tan(x1_in_rv, load_angle_rv)
    r1l_in = _round_setting(_max_or_none([r1l_in_fw, r1l_in_rv]))
    load_cut_result = _calculate_load_cut(load_cut, r1f_in_fw, r1f_in_rv)

    return PsbBlockingResult(
        sensitivity_factor=sensitivity_factor,
        forward=forward,
        reverse=reverse,
        included_forward_stage_names=tuple(stage.name for stage in forward_stages),
        included_reverse_stage_names=tuple(stage.name for stage in reverse_stages),
        arg_dir_deg=arg_dir_rv,
        arg_neg_res_deg=arg_neg_res_rv,
        arg_dir_fw_deg=arg_dir_fw,
        arg_neg_res_fw_deg=arg_neg_res_fw,
        arg_dir_rv_deg=arg_dir_rv,
        arg_neg_res_rv_deg=arg_neg_res_rv,
        load_angle_deg=load_angle,
        load_angle_candidates=load_angle_candidates,
        load_angle_fw_deg=load_angle_fw,
        load_angle_rv_deg=load_angle_rv,
        load_angle_fw_candidates=load_angle_fw_candidates,
        load_angle_rv_candidates=load_angle_rv_candidates,
        x1_in_fw_coverage_phase=fw_coverage_x_phase,
        x1_in_fw_coverage_ground=fw_coverage_x_ground,
        x1_in_fw_reverse_intersection_phase=fw_reverse_x_phase,
        x1_in_fw_reverse_intersection_ground=fw_reverse_x_ground,
        x1_in_fw=x1_in_fw,
        r1f_in_fw_coverage_phase=fw_coverage_r_phase,
        r1f_in_fw_coverage_ground=fw_coverage_r_ground,
        r1f_in_fw_reverse_intersection_phase=fw_reverse_r_phase,
        r1f_in_fw_reverse_intersection_ground=fw_reverse_r_ground,
        r1f_in_fw=r1f_in_fw,
        x1_in_rv_coverage_phase=rv_coverage_x_phase,
        x1_in_rv_coverage_ground=rv_coverage_x_ground,
        x1_in_rv_forward_intersection_phase=rv_forward_x_phase,
        x1_in_rv_forward_intersection_ground=rv_forward_x_ground,
        x1_in_rv=x1_in_rv,
        r1f_in_rv_coverage_phase=rv_coverage_r_phase,
        r1f_in_rv_coverage_ground=rv_coverage_r_ground,
        r1f_in_rv_forward_intersection_phase=rv_forward_r_phase,
        r1f_in_rv_forward_intersection_ground=rv_forward_r_ground,
        r1f_in_rv=r1f_in_rv,
        r1l_in_fw=r1l_in_fw,
        r1l_in_rv=r1l_in_rv,
        r1l_in=r1l_in,
        load_cut=load_cut,
        rld_out_fw_load=load_cut_result["rld_out_fw_load"],
        rld_out_rv_load=load_cut_result["rld_out_rv_load"],
        rld_in_fw_load=load_cut_result["rld_in_fw_load"],
        rld_in_rv_load=load_cut_result["rld_in_rv_load"],
        rld_in_fw=load_cut_result["rld_in_fw"],
        rld_in_rv=load_cut_result["rld_in_rv"],
        rld_out_fw=load_cut_result["rld_out_fw"],
        rld_out_rv=load_cut_result["rld_out_rv"],
        kld_fw=load_cut_result["kld_fw"],
        kld_rv=load_cut_result["kld_rv"],
        arg_ld_fw_base_deg=load_cut_result["arg_ld_fw_base_deg"],
        arg_ld_rv_base_deg=load_cut_result["arg_ld_rv_base_deg"],
        arg_ld_selected_deg=load_cut_result["arg_ld_selected_deg"],
        arg_ld_deg=load_cut_result["arg_ld_deg"],
    )


def _calculate_load_cut(
    load_cut: PsbLoadCutInput | None,
    r1f_in_fw: float | None,
    r1f_in_rv: float | None,
) -> dict[str, float | None]:
    if load_cut is None:
        return _empty_load_cut_result()

    delta_r_primary = load_cut.delta_r_primary
    rld_out_fw_load = _multiply(load_cut.rejection_factor, load_cut.r_load_fw)
    rld_out_rv_load = _multiply(load_cut.rejection_factor, load_cut.r_load_rv)
    rld_in_fw_load = _subtract(rld_out_fw_load, delta_r_primary)
    rld_in_rv_load = _subtract(rld_out_rv_load, delta_r_primary)
    # TODO: Verify load cut selectivity rule against RET670 documentation.
    rld_in_fw = _min_or_none([r1f_in_fw, rld_in_fw_load])
    rld_in_rv = _min_or_none([r1f_in_rv, rld_in_rv_load])
    rld_out_fw = _add(rld_in_fw, delta_r_primary)
    rld_out_rv = _add(rld_in_rv, delta_r_primary)
    kld_fw = _divide(rld_in_fw, rld_out_fw)
    kld_rv = _divide(rld_in_rv, rld_out_rv)
    arg_ld_fw_base = _load_cut_angle(load_cut.r_load_fw, load_cut.x_load_fw)
    arg_ld_rv_base = _load_cut_angle(load_cut.r_load_rv, load_cut.x_load_rv)
    arg_ld_selected = _add(
        _max_or_none([arg_ld_fw_base, arg_ld_rv_base]),
        load_cut.delta_phi_deg,
    )
    arg_ld = max(arg_ld_selected, 30.0) if arg_ld_selected is not None else None
    return {
        "rld_out_fw_load": rld_out_fw_load,
        "rld_out_rv_load": rld_out_rv_load,
        "rld_in_fw_load": rld_in_fw_load,
        "rld_in_rv_load": rld_in_rv_load,
        "rld_in_fw": rld_in_fw,
        "rld_in_rv": rld_in_rv,
        "rld_out_fw": rld_out_fw,
        "rld_out_rv": rld_out_rv,
        "kld_fw": kld_fw,
        "kld_rv": kld_rv,
        "arg_ld_fw_base_deg": arg_ld_fw_base,
        "arg_ld_rv_base_deg": arg_ld_rv_base,
        "arg_ld_selected_deg": arg_ld_selected,
        "arg_ld_deg": arg_ld,
    }


def _empty_load_cut_result() -> dict[str, float | None]:
    return {
        "rld_out_fw_load": None,
        "rld_out_rv_load": None,
        "rld_in_fw_load": None,
        "rld_in_rv_load": None,
        "rld_in_fw": None,
        "rld_in_rv": None,
        "rld_out_fw": None,
        "rld_out_rv": None,
        "kld_fw": None,
        "kld_rv": None,
        "arg_ld_fw_base_deg": None,
        "arg_ld_rv_base_deg": None,
        "arg_ld_selected_deg": None,
        "arg_ld_deg": None,
    }


def _load_angle_candidates(
    stages: list[PsbStageSettingInput],
) -> tuple[tuple[str, float], ...]:
    return tuple(
        (stage.name, stage.load_angle_deg)
        for stage in stages
        if stage.load_angle_deg is not None and stage.load_angle_deg > 0
    )


def _direction_extremes(stages: list[PsbStageSettingInput]) -> PsbDirectionExtremes | None:
    if not stages:
        return None
    return PsbDirectionExtremes(
        x1=max(stage.x1 for stage in stages),
        x0=max(stage.x0 for stage in stages),
        rfpp=max(stage.rfpp for stage in stages),
        rfpe=max(stage.rfpe for stage in stages),
    )


def _compensated_x(x1: float, x0: float) -> float:
    return x1 + (x0 - x1) / 3.0


def _tan_deg(angle_deg: float | None) -> float | None:
    if angle_deg is None:
        return None
    return tan(angle_deg * pi / 180.0)


def _divide_by_tan(value: float | None, angle_deg: float | None) -> float | None:
    tangent = _tan_deg(angle_deg)
    if value is None or tangent in (None, 0.0):
        return None
    return value / tangent


def _load_cut_angle(r_value: float | None, x_value: float | None) -> float | None:
    if r_value in (None, 0.0) or x_value is None:
        return None
    return abs(degrees(atan(x_value / r_value)))


def _add(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left + right


def _subtract(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _divide(left: float | None, right: float | None) -> float | None:
    if left is None or right in (None, 0.0):
        return None
    return left / right


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


def _round_setting(value: float | None) -> float | None:
    """Round selected setting upward to integer. TODO: verify policy by RET670 docs."""
    if value is None:
        return None
    return float(ceil(value))
