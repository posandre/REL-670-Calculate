from __future__ import annotations

from matplotlib.axes import Axes

from app.models.electrical import ImpedancePoint
from app.models.protection import DistanceZonePolygon, PsbCharacteristic


def configure_rx_axes(axis: Axes, labels: dict[str, str]) -> None:
    axis.set_title(labels["title"])
    axis.set_xlabel(labels["r_axis"])
    axis.set_ylabel(labels["x_axis"])
    axis.axhline(0.0, color="#7a8491", linewidth=0.8)
    axis.axvline(0.0, color="#7a8491", linewidth=0.8)
    axis.grid(True, which="both", linestyle="--", linewidth=0.5, alpha=0.55)
    axis.set_aspect("equal", adjustable="datalim")


def plot_rx_diagram(
    axis: Axes,
    impedance_points: list[ImpedancePoint],
    zones: list[DistanceZonePolygon],
    psb: PsbCharacteristic | None,
    labels: dict[str, str],
) -> None:
    axis.clear()
    configure_rx_axes(axis, labels)

    for zone in zones:
        xs = [point[0] for point in zone.points]
        ys = [point[1] for point in zone.points]
        axis.plot(xs, ys, linewidth=1.8, label=zone.name)

    if psb is not None:
        outer_x = [point[0] for point in psb.outer_polygon]
        outer_y = [point[1] for point in psb.outer_polygon]
        inner_x = [point[0] for point in psb.inner_polygon]
        inner_y = [point[1] for point in psb.inner_polygon]
        axis.plot(outer_x, outer_y, color="#8b5cf6", linewidth=1.6, label=labels["psb_outer"])
        axis.plot(inner_x, inner_y, color="#ef4444", linewidth=1.6, label=labels["psb_inner"])

    if impedance_points:
        axis.plot(
            [point.resistance for point in impedance_points],
            [point.reactance for point in impedance_points],
            marker="o",
            color="#0f766e",
            linewidth=1.4,
            label=labels["trajectory"],
        )
        for point in impedance_points:
            axis.annotate(
                point.name,
                (point.resistance, point.reactance),
                textcoords="offset points",
                xytext=(5, 5),
            )

    handles, legend_labels = axis.get_legend_handles_labels()
    if handles and legend_labels:
        axis.legend(loc="best")
