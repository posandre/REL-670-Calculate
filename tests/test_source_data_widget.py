import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from app.localization.translator import Translator
from app.ui.widgets.source_data_widget import SourceDataWidget


def test_source_data_widget_starts_with_dynamic_stage_headers() -> None:
    app = QApplication.instance() or QApplication([])
    widget = SourceDataWidget(Translator())

    assert widget.settings_table.horizontalHeaderItem(1).text() == "1 ступінь"
    assert app is not None


def test_source_data_widget_converts_secondary_delta_r_to_primary() -> None:
    app = QApplication.instance() or QApplication([])
    widget = SourceDataWidget(Translator())
    widget.ktc_primary.setText("500")
    widget.ktc_secondary.setText("5")
    widget.ktn_primary.setText("100000")
    widget.ktn_secondary.setText("100")
    widget.delta_r_fw_rv.setText("1")

    assert widget.delta_r_primary_value() == pytest.approx(10.0)
    assert app is not None
