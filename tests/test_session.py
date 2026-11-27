import pandas as pd
import pytest

from sdtm_helper.sas.session import SasConnection


class FakeData:
    def __init__(self, df):
        self._df = df

    def to_df(self):
        return self._df


class FakeSas:
    """Stands in for saspy.SASsession so tests run without SAS."""
    sasver = "9.04.01M8"

    def __init__(self):
        self.where = []

    def sasdata(self, table, libref, dsopts=None):
        self.where.append((dsopts or {}).get("where"))
        if table == "vcolumn":
            return FakeData(pd.DataFrame([
                {"name": "USUBJID", "type": "char", "length": 20, "label": "", "format": "", "varnum": 2},
                {"name": "STUDYID", "type": "char", "length": 8, "label": "Study", "format": "", "varnum": 1},
            ]))
        if table == "vtable":
            return FakeData(pd.DataFrame([{"memname": "DM", "nobs": 120}]))
        return FakeData(pd.DataFrame({"libname": ["WORK", "RAW "]}))


def test_describe_reads_metadata_in_order():
    sas = SasConnection(session=FakeSas())
    info = sas.describe("final", "dm")
    assert info.nobs == 120
    assert [c.name for c in info.columns] == ["STUDYID", "USUBJID"]
    assert info.column("usubjid").length == 20


def test_rejects_unsafe_names():
    sas = SasConnection(session=FakeSas())
    with pytest.raises(ValueError):
        sas.describe("final", "dm' or '1'='1")


def test_list_libraries():
    assert SasConnection(session=FakeSas()).list_libraries() == ["RAW", "WORK"]


class FakeSasWithMissing(FakeSas):
    def submit(self, code):
        self.code = code
        return {"LOG": ""}

    def sasdata(self, table, libref, dsopts=None):
        if table == "_sdtmh_missing":
            return FakeData(pd.DataFrame([{"SEX": 2.0, "RACE": 0.0}]))
        return super().sasdata(table, libref, dsopts)


def test_missing_counts():
    fake = FakeSasWithMissing()
    counts = SasConnection(session=fake).missing_counts("final", "dm", ["sex", "race"])
    assert counts == {"SEX": 2, "RACE": 0}
    assert "sum(missing(SEX)) as SEX" in fake.code and "from FINAL.DM" in fake.code
