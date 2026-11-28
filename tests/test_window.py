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
    w.pool.waitForDone(5000)
    w.deleteLater()            # destroy the widgets before Python tears Qt down at exit
    app.sendPostedEvents(None, 0)
    app.processEvents()


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


def test_table_preview_shows_rows_and_marks_columns(window):
    from PySide6.QtCore import Qt
    dm = read("lorna_dm.csv", DM)
    dm.loc[0, "SEX"] = None
    dm["EXTRA"] = "x"
    window.sas = SasConnection(session=FakeSASsession({"FINAL.DM": dm}))
    window.ws.sas = window.sas
    preview = window.ws.preview("FINAL.DM", rows=20)
    window.preview.show_preview(preview, window.ws.spec, "FINAL.DM")
    model = window.preview.model
    assert model.rowCount() == 20 and "300 rows" in window.preview.info.text()
    sex = list(dm.columns).index("SEX")
    assert model.data(model.index(0, sex), Qt.BackgroundRole) is not None      # empty Required value shaded
    extra = list(dm.columns).index("EXTRA")
    assert "Not a DM variable" in model.headerData(extra, Qt.Horizontal, Qt.ToolTipRole)
    window.preview.show_preview(None, window.ws.spec, "FINAL.XX")
    assert "doesn't exist yet" in window.preview.info.text()


def test_follow_needs_a_connection(window):
    assert window.preview.follow.isChecked()
    window.follow_now()
    assert "Connect to SAS" in window.preview.info.text()


def test_follow_marks_the_step_under_the_cursor(window):
    import pandas as pd
    from PySide6.QtCore import Qt
    from test_program import PROGRAM
    raw = pd.DataFrame({"SUBJID": ["001", "002"], "GENDER": ["Male", "Female"], "AGE": [30.0, 12.0],
                        "COUNTRY": ["PL", "PL"]})
    out = pd.DataFrame({"STUDYID": ["LORNA"], "USUBJID": ["LORNA-001"], "SEX": ["M"], "COUNTRY": ["PL"],
                        "_sdtmh_r1": [1.0]})
    fake = FakeSASsession({"RAW.DM": raw, "WORK._SDTMH_IN1": raw.assign(_sdtmh_r1=[1.0, 2.0]),
                           "WORK._SDTMH_OUT1": out})
    window.sas = window.ws.sas = SasConnection(session=fake)
    result = window.ws.follow(PROGRAM, PROGRAM.index("studyid ="))
    window.preview.show_follow(result, window.ws.spec)
    window._mark_step(result)
    assert window.preview.list.count() == 2
    model = window.preview.model
    assert model.headerData(1, Qt.Vertical) == "✕ 2"                       # AGE 12 removed by WHERE
    assert model.data(model.index(1, 0), Qt.FontRole).strikeOut()
    cols = list(model.df.columns)
    assert "new" in model.headerData(cols.index("USUBJID"), Qt.Horizontal)
    assert "catx" in model.headerData(cols.index("USUBJID"), Qt.Horizontal, Qt.ToolTipRole)
    assert "drop" in model.headerData(cols.index("AGE"), Qt.Horizontal)
    assert "keeps 1 of 2 rows" in window.preview.info.text()
    window.preview.list.setCurrentRow(1)
    assert list(model.df.columns) == ["STUDYID", "USUBJID", "SEX", "COUNTRY"]
    assert window.editor.extraSelections()
