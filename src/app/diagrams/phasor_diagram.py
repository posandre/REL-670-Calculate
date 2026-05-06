from __future__ import annotations

from matplotlib.axes import Axes

from app.models.electrical import Phasor
from app.services.calculations.phasors import phasor_to_complex


def plot_phasors(axis: Axes, phasors: list[Phasor], labels: dict[str, str]) -> None:
    axis.clear()
    axis.set_title(labels["title"])
    axis.set_xlabel(labels["real_axis"])
    axis.set_ylabel(labels["imag_axis"])
    axis.axhline(0.0, color="#7a8491", linewidth=0.8)
    axis.axvline(0.0, color="#7a8491", linewidth=0.8)
    axis.grid(True, which="both", linestyle="--", linewidth=0.5, alpha=0.55)
    axis.set_aspect("equal", adjustable="datalim")

    for phasor in phasors:
        value = phasor_to_complex(phasor)
        axis.arrow(
            0.0,
            0.0,
            value.real,
            value.imag,
            head_width=max(phasor.magnitude * 0.035, 0.05),
            length_includes_head=True,
            linewidth=1.6,
        )
        axis.annotate(
            phasor.name,
            (value.real, value.imag),
            textcoords="offset points",
            xytext=(5, 5),
        )

    if phasors:
        limit = max(phasor.magnitude for phasor in phasors) * 1.2
        axis.set_xlim(-limit, limit)
        axis.set_ylim(-limit, limit)
