import pandas as pd
import pytest

from fake_sas import FakeSASsession
from sdtm_helper.app.workspace import Workspace, available_domains, split_table
from sdtm_helper.sas.session import SasConnection
from test_checks import DM, read


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SDTM_HELPER_HOME", str(tmp_path))


def test_domains_and_tables():
    codes = [c for c, _ in available_domains()]
    assert codes[0] == "DM" and "AE" in codes and len(codes) >= 60
    assert split_table("final.dm") == ("FINAL", "DM")
    assert split_table("dm") == ("WORK", "DM")


def test_starter_program_is_comments_only():
    ws = Workspace("LORNA", "DM")
    text = ws.program
    assert "Step 1: Load the data" in text
    assert all(l.startswith("/*") or not l.strip() for l in text.splitlines())


def test_program_and_steps_are_saved_and_restored():
    ws = Workspace("LORNA", "AE")
    ws.save("data final.ae; run;", "final.ae")
    ws.toggle_step("load", True)
    again = Workspace("LORNA", "AE")
    assert again.program == "data final.ae; run;"
    assert again.state.target_table == "FINAL.AE"
    assert again.done == {"load"}


def test_refresh_and_checks_through_sas():
    dm = read("lorna_dm.csv", DM)
    sas = SasConnection(session=FakeSASsession({"FINAL.DM": dm.drop(columns=["COUNTRY"])}))
    ws = Workspace("LORNA", "DM", sas=sas)
    guide = ws.refresh("FINAL.DM")
    status = {i.variable: i.status for i in guide.checklist}
    assert status["COUNTRY"] == "missing" and status["USUBJID"] == "done"
    report = ws.run_checks("FINAL.DM")
    assert not report.passed and any(f.check == "REQ-MISSING" for f in report.findings)
    assert "check" not in ws.done


def test_clean_table_ticks_the_check_step():
    sas = SasConnection(session=FakeSASsession({"FINAL.DM": read("lorna_dm.csv", DM)}))
    ws = Workspace("LORNA", "DM", sas=sas)
    assert ws.run_checks("FINAL.DM").passed
    assert "check" in ws.done
