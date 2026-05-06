from __future__ import annotations

from pathlib import Path

from matplotlib.figure import Figure


SUPPORTED_EXPORT_FILTER = "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)"


def export_figure(figure: Figure, path: Path) -> None:
    """Export a Matplotlib figure to an engineering-friendly vector or raster format."""
    figure.savefig(path, bbox_inches="tight", dpi=300)
