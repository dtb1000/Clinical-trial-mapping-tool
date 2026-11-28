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
    w = MainWindow(check_online=False)
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


def test_problems_are_underlined_listed_and_explained(window):
    from PySide6.QtGui import QTextCharFormat
    from test_lint import BROKEN
    window.editor.setPlainText(BROKEN)
    window.check_code()
    assert "Problems (" in window.bottom.tabText(1)
    assert window.problems_view.topLevelItemCount() >= 6
    layout = window.editor.document().findBlockByNumber(5).layout()     # if SEX == "Male"
    underlined = [r for r in layout.formats() if r.format.underlineStyle() == QTextCharFormat.WaveUnderline]
    assert underlined
    assert window.problem_at(5, 9).message == "SAS compares with = or EQ, not ==."
    window._go_to_problem(window.problems_view.topLevelItem(0))
    assert window.editor.textCursor().blockNumber() == window.all_problems()[0].line
    window.editor.setPlainText("data x;\n  set y;\nrun;\n")
    window.check_code()
    assert window.bottom.tabText(1) == "Problems"


def test_sas_errors_stay_until_their_line_changes(window):
    from test_lint import CODE, LOG
    window.editor.setPlainText(CODE)
    window.add_sas_problems(LOG, CODE, 0)
    window.check_code()
    assert any(p.source == "SAS" for p in window.all_problems())
    window.editor.setPlainText(CODE.replace('catx("-" STUDYID', 'catx("-", STUDYID'))
    window.check_code()
    assert not any(p.source == "SAS" for p in window.all_problems())


def test_function_lookup_and_f1(window):
    from PySide6.QtGui import QTextCursor
    window.show_function("intck")
    assert "INTCK(interval" in window.func_text.toPlainText()
    assert "SAS+Help+Center" in window.func_text.toHtml()
    window.show_function("catz")
    assert "Did you mean CATS, CATT, CATX?" in window.func_text.toPlainText()
    window.editor.setPlainText("data x;\n  call missing(a);\nrun;")
    cursor = window.editor.textCursor()
    cursor.setPosition(window.editor.toPlainText().index("missing") + 2)
    window.editor.setTextCursor(cursor)
    window.lookup_word()
    assert "CALL MISSING(" in window.func_text.toPlainText()


def _settle(window, until=lambda: False):
    """Let background work finish and its signals reach the window."""
    import time
    window.pool.waitForDone(5000)
    end = time.time() + 3
    while time.time() < end and not until():
        QApplication.processEvents()
        time.sleep(0.01)


def test_menus_hold_every_feature(window):
    menus = {m.title().replace("&", ""): [a.text() for a in m.actions() if a.text()]
             for m in (a.menu() for a in window.menuBar().actions())}
    assert {"File", "SAS", "View", "Standards", "Help"} <= set(menus)
    assert "Saved work…" in menus["File"] and "Run ▶" in menus["SAS"] and "Follow my code" in menus["SAS"]
    assert "Download controlled terminology" in menus["Standards"]
    assert any("SAS function" in t for t in menus["Help"])
    assert "SAS functions" in menus["View"] and "Problems" in menus["View"]
    window.follow_action.setChecked(False)
    assert not window.preview.follow.isChecked()


def test_saved_work_reopens_a_domain(window):
    from sdtm_helper.app.window import SavedWorkDialog
    from sdtm_helper import progress
    window.editor.setPlainText("/* my AE work */")
    window.domain.setCurrentIndex(window.domain.findData("AE"))      # saves DM, opens AE
    window.save()
    dlg = SavedWorkDialog(progress.list_saved())
    assert dlg.table.rowCount() >= 2
    row = next(r for r in range(dlg.table.rowCount()) if dlg.table.item(r, 1).text() == "AE")
    dlg._pick(row, 0)
    assert dlg.choice == (window.ws.study, "AE")


def test_terminology_download_and_update_reminder(window, monkeypatch):
    from sdtm_helper import updates
    from sdtm_helper.standards import terminology
    monkeypatch.setattr(terminology, "download", lambda: terminology.cache_path())
    monkeypatch.setattr(terminology, "load", lambda path=None: {"C66731": object()})
    window.download_ct(quiet=True)
    _settle(window, lambda: "Downloaded" in window.statusBar().currentMessage())
    assert "Downloaded 1 SDTM codelists" in window.statusBar().currentMessage()
    monkeypatch.setattr(updates, "check_for_update",
                        lambda: "A newer version (v9.9.9) is available with updated standards: https://example.org/r")
    window.check_updates(quiet=True)
    _settle(window, lambda: bool(window.update_label.text()))
    assert "newer version" in window.update_label.text()


def test_copy_workflow_as_mermaid(window):
    window.copy_mermaid()
    assert QApplication.clipboard().text().startswith("flowchart TD")
