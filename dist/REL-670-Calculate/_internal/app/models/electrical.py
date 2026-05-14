from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComplexValue:
    real: float
    imag: float

    @property
    def as_complex(self) -> complex:
        return complex(self.real, self.imag)


@dataclass(frozen=True)
class Phasor:
    name: str
    magnitude: float
    angle_deg: float


@dataclass(frozen=True)
class ImpedancePoint:
    name: str
    resistance: float
    reactance: float
