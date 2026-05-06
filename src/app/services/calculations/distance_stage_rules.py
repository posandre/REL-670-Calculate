"""Controlled formulas for distance protection stage table defaults."""

import math


FORWARD_ARG_NEG_RES_DEG = 115.0
REVERSE_ARG_NEG_RES_DEG = -65.0
ARG_DIR_DEG = 15.0


def arg_neg_res_by_direction(is_forward: bool) -> float:
    """Return ArgNegRes by stage direction. TODO: verify constants by RET670 docs."""
    return FORWARD_ARG_NEG_RES_DEG if is_forward else REVERSE_ARG_NEG_RES_DEG


def arg_dir_default() -> float:
    """Return default ArgDir. TODO: verify constant by RET670 docs."""
    return ARG_DIR_DEG


def load_angle_deg(r1: float, x1: float) -> float | None:
    """Return Фл = atan(X1 / R1) in degrees. TODO: verify formula by RET670 docs."""
    if r1 == 0:
        return None
    return math.degrees(math.atan(x1 / r1))


def compensated_load_angle_deg(
    r1: float,
    x1: float,
    r0: float,
    x0: float,
) -> float | None:
    """Return Флк by zero-sequence compensated formula. TODO: verify by RET670 docs."""
    denominator = r1 + ((r0 - r1) / 3)
    if denominator == 0:
        return None
    numerator = x1 + ((x0 - x1) / 3)
    return math.degrees(math.atan(numerator / denominator))
