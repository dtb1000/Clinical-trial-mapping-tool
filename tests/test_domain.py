import json
from pathlib import Path

from sdtm_helper.standards.domain import load_domain, parse_domain

FIXTURE = Path(__file__).parent / "fixtures" / "dm_sample.json"


def test_parse_orders_variables_and_reads_core():
    spec = parse_domain(json.loads(FIXTURE.read_text()))
    assert spec.code == "DM"
    assert [v.name for v in spec.variables][:3] == ["STUDYID", "DOMAIN", "USUBJID"]
    assert [v.name for v in spec.by_core("Req")] == ["STUDYID", "DOMAIN", "USUBJID", "SEX"]


def test_codelists_and_iso_dates():
    spec = parse_domain(json.loads(FIXTURE.read_text()))
    assert spec.variable("sex").codelists == ["C66731"]
    assert spec.variable("RFSTDTC").is_iso8601
    assert not spec.variable("SEX").is_iso8601


def test_load_from_path():
    assert load_domain("DM", path=FIXTURE).label == "Demographics"
