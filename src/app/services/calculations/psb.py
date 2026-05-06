from __future__ import annotations

from app.models.protection import PsbCharacteristic, PsbSettings


def _rectangle(resistance: float, reactance: float) -> tuple[tuple[float, float], ...]:
    return (
        (-resistance, -reactance),
        (resistance, -reactance),
        (resistance, reactance),
        (-resistance, reactance),
        (-resistance, -reactance),
    )


def calculate_psb_characteristic(settings: PsbSettings) -> PsbCharacteristic:
    """Calculate baseline inner/outer PSB operating polygons.

    The present implementation intentionally exposes a conservative rectangular
    placeholder. RET670 Power Swing Blocking can depend on selected measuring
    principle, delta impedance timing, load encroachment, and setting group.
    TODO: Replace or specialize this geometry after verification against RET670 TRM.
    """
    values = (
        settings.inner_resistance_ohm,
        settings.inner_reactance_ohm,
        settings.outer_resistance_ohm,
        settings.outer_reactance_ohm,
    )
    if any(value <= 0 for value in values):
        msg = "PSB resistance and reactance limits must be positive."
        raise ValueError(msg)
    if settings.inner_resistance_ohm >= settings.outer_resistance_ohm:
        msg = "Inner PSB resistance must be smaller than outer resistance."
        raise ValueError(msg)
    if settings.inner_reactance_ohm >= settings.outer_reactance_ohm:
        msg = "Inner PSB reactance must be smaller than outer reactance."
        raise ValueError(msg)

    return PsbCharacteristic(
        inner_polygon=_rectangle(settings.inner_resistance_ohm, settings.inner_reactance_ohm),
        outer_polygon=_rectangle(settings.outer_resistance_ohm, settings.outer_reactance_ohm),
    )
