from __future__ import annotations

from app.models.electrical import ComplexValue


def calculate_impedance(voltage: complex, current: complex) -> ComplexValue:
    """Calculate impedance Z = U / I using complex voltage and current phasors."""
    if abs(current) == 0:
        msg = "Current must be non-zero to calculate impedance."
        raise ZeroDivisionError(msg)
    impedance = voltage / current
    return ComplexValue(real=impedance.real, imag=impedance.imag)


def impedance_from_rx(resistance: float, reactance: float) -> complex:
    """Represent impedance on the R-X plane as a complex number."""
    return complex(resistance, reactance)


def primary_to_secondary_impedance(
    primary_impedance_ohm: complex,
    voltage_transformer_ratio: float,
    current_transformer_ratio: float,
) -> complex:
    """Convert primary impedance to relay secondary impedance.

    Formula: Zsec = Zpri * CTR / VTR, where ratios are primary/secondary.
    TODO: Verify naming and sign convention against the RET670 project standard.
    """
    if voltage_transformer_ratio <= 0 or current_transformer_ratio <= 0:
        msg = "Transformer ratios must be positive."
        raise ValueError(msg)
    return primary_impedance_ohm * current_transformer_ratio / voltage_transformer_ratio


def secondary_to_primary_impedance(
    secondary_impedance_ohm: complex,
    voltage_transformer_ratio: float,
    current_transformer_ratio: float,
) -> complex:
    """Convert relay secondary impedance to primary impedance.

    Formula: Zpri = Zsec * VTR / CTR, inverse of primary_to_secondary_impedance.
    TODO: Verify ratio convention against the RET670 documentation used by the utility.
    """
    if voltage_transformer_ratio <= 0 or current_transformer_ratio <= 0:
        msg = "Transformer ratios must be positive."
        raise ValueError(msg)
    return secondary_impedance_ohm * voltage_transformer_ratio / current_transformer_ratio
