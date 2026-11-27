import json
from pathlib import Path

from sdtm_helper.guidance.engine import build_guide
from sdtm_helper.standards.domain import parse_domain

SPEC = parse_domain(json.loads((Path(__file__).parent / "fixtures" / "dm_sample.json").read_text()))


def status(guide, name):
    return next(i for i in guide.checklist if i.variable == name).status


def test_checklist_against_table():
    guide = build_guide(SPEC, columns=["STUDYID", "DOMAIN", "USUBJID", "SEX", "RFSTDTC"],
                        missing={"SEX": 3, "RFSTDTC": 10}, nobs=10)
    assert status(guide, "STUDYID") == "done"
    assert status(guide, "RACE") == "missing"
    assert status(guide, "SEX") == "partly empty"
    assert status(guide, "RFSTDTC") == "empty"
    assert status(guide, "DMDTC") == "optional"
    assert next(i for i in guide.checklist if i.variable == "SEX").needs_action


def test_no_table_lists_required_and_expected_as_missing():
    guide = build_guide(SPEC)
    assert status(guide, "USUBJID") == "missing"
    assert status(guide, "DMDTC") == "optional"


def test_workflow_order_and_next_steps():
    guide = build_guide(SPEC)
    assert guide.workflow[0].id == "load"
    assert [s.id for s in guide.next_steps(set())] == ["load"]
    after_ids = [s.id for s in guide.next_steps({"load", "inspect", "identifiers"})]
    assert after_ids == ["demographics", "arms"]
    assert "RFSTDTC" in next(s for s in guide.workflow if s.id == "dates").variables


def test_explain_combines_sdtmig_and_tips():
    text = build_guide(SPEC).explain("RFSTDTC", SPEC)
    assert "ISO 8601" in text and "Tip:" in text and "Core: Exp" in text
    assert "C66731" in build_guide(SPEC).explain("SEX", SPEC)


def test_mermaid_marks_done_steps():
    chart = build_guide(SPEC).mermaid({"load"})
    assert chart.startswith("flowchart TD")
    assert "load --> inspect" in chart and "class load done" in chart


def test_every_tip_points_to_a_real_step():
    guide = build_guide(SPEC)
    steps = {s.id for s in guide.workflow}
    tips = json.loads((Path(__file__).parents[1] / "src/sdtm_helper/guidance/dm.json").read_text())
    assert all(v["step"] in steps for v in tips["variables"].values())
