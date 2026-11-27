"""Smoke test of the desktop window, offscreen. Skipped where PySide6 isn't installed."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # PySide6 or its system libraries missing
    pytest.skip("PySide6 not available", allow_module_level=True)

from fake_sas import FakeSASsession  # noqa: E402
from sdtm_helper.sas.session import SasConnection  # noqa: E402
from test_checks import DM, read  # noqa: E402


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("SDTM_HELPER_HOME", str(tmp_path))
    from sdtm_helper.app.window import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    yield w
    w.close()


def test_window_opens_on_dm_and_switches_domain(window):
    assert window.ws.domain == "DM"
    assert window.variables.count() == len(window.ws.spec.variables)
    assert "Step 1" in window.editor.toPlainText()
    window.domain.setCurrentIndex(window.domain.findData("AE"))
    assert window.ws.domain == "AE"
    assert window.table.text() == "FINAL.AE"


def test_checks_and_workflow_in_window(window):
    window.sas = SasConnection(session=FakeSASsession({"FINAL.DM": read("lorna_dm.csv", DM)}))
    window.ws.sas = window.sas
    window.show_guide(window.ws.refresh("FINAL.DM"))
    window.show_report(window.ws.run_checks("FINAL.DM"))
    assert window.findings.topLevelItemCount() >= 1
    assert "No errors" in window.checks_summary.text()
    window.toggle_step("load", True)
    assert "load" in window.ws.done
