from pathlib import Path

import pandas as pd
import pytest

from sdtm_helper.checks.engine import ERROR, is_iso8601, run_checks, study_day
from sdtm_helper.standards import terminology
from sdtm_helper.standards.domain import load_domain

FIX = Path(__file__).parent / "fixtures"
DM = load_domain("DM", "3.4")
AE = load_domain("AE", "3.4")


def read(name: str, spec) -> pd.DataFrame:
    """Read a LORNA CSV the way SASPy would hand it over: Char as text (empty = NaN), Num as numbers."""
    df = pd.read_csv(FIX / name, dtype=str, keep_default_na=False).replace("", pd.NA)
    for v in spec.variables:
        if v.datatype == "Num" and v.name in df:
            df[v.name] = pd.to_numeric(df[v.name])
    return df


def checks(report, severity=ERROR):
    return {f.check for f in report.findings if f.severity == severity}


@pytest.mark.parametrize("value,ok", [
    ("2023-01-04", True), ("2023-01", True), ("2023", True), ("2023-01-04T09:30", True),
    ("2023-01-04T09:30:15.5", True), ("2023---15", True), ("2023-01-04/2023-02-01", True),
    ("04/01/2023", False), ("2023-1-4", False), ("2023-01-04 09:30", False), ("UNK", False),
])
def test_iso8601(value, ok):
    assert is_iso8601(value) is ok


def test_iso_duration_only_where_allowed():
    assert is_iso8601("P3D", allow_duration=True)
    assert not is_iso8601("P3D")


def test_study_day_has_no_day_zero():
    assert study_day("2023-01-04", "2023-01-04") == 1
    assert study_day("2023-01-03", "2023-01-04") == -1
    assert study_day("2023-01-10", "2023-01-04") == 7
    assert study_day("2023-01", "2023-01-04") is None
    assert study_day("04/01/2023", "2023-01-04") is None


def test_lorna_dm_has_no_errors():
    report = run_checks(DM, read("lorna_dm.csv", DM))
    assert report.passed, [f.message for f in report.findings if f.severity == ERROR]


def test_lorna_ae_against_dm_has_no_errors():
    report = run_checks(AE, read("lorna_ae.csv", AE), dm=read("lorna_dm.csv", DM))
    assert report.passed, [f.message for f in report.findings if f.severity == ERROR]


def test_broken_dm_is_caught():
    df = read("lorna_dm.csv", DM)
    df.loc[0, "SEX"] = pd.NA                    # required value empty
    df.loc[1, "RFSTDTC"] = "04/01/2023"         # not ISO 8601
    df.loc[2, "DTHFL"] = "N"                    # DTHFL must be Y or empty
    df.loc[3, "AGEU"] = pd.NA                   # AGE without units
    df.loc[4, "USUBJID"] = df.loc[5, "USUBJID"] # duplicate subject
    df.loc[6, "DOMAIN"] = "XX"
    df.loc[7, "DMDY"] = 0
    df["EXTRA"] = "x"                           # not an SDTM variable
    df = df.drop(columns=["COUNTRY"])           # required variable gone
    report = run_checks(DM, df)
    assert {"REQ-NULL", "ISO8601", "DM-DTHFL", "DM-AGEU", "DM-ONE-PER-SUBJECT", "DOMAIN-VALUE",
            "NONSTANDARD", "REQ-MISSING", "DY-ZERO"} <= checks(report)
    assert not report.passed


def test_ae_cross_domain_problems():
    ae, dm = read("lorna_ae.csv", AE), read("lorna_dm.csv", DM)
    ae.loc[0, "USUBJID"] = "LORNA-SITE999-SUBJ999"
    ae.loc[1, "AESEQ"] = ae.loc[2, "AESEQ"]
    ae.loc[2, "USUBJID"] = ae.loc[1, "USUBJID"]
    ae.loc[3, "AESTDY"] = ae.loc[3, "AESTDY"] + 5
    ae.loc[4, "AEENDTC"] = "2000-01-01"
    report = run_checks(AE, ae, dm=dm)
    assert {"USUBJID-NOT-IN-DM", "SEQ-UNIQUE", "DY-CALC", "START-AFTER-END"} <= checks(report)


def test_controlled_terminology():
    cl = terminology.load(FIX / "ct_sample.txt")
    df = read("lorna_dm.csv", DM)
    assert "CT" not in checks(run_checks(DM, df, codelists=cl))
    df.loc[0, "SEX"] = "Female"
    report = run_checks(DM, df, codelists=cl)
    ct = [f for f in report.findings if f.check == "CT"]
    assert ct and ct[0].severity == ERROR and ct[0].examples == ["Female"]


def test_ct_skipped_notice_without_terminology():
    assert "CT-SKIPPED" in checks(run_checks(DM, read("lorna_dm.csv", DM)), "Notice")
