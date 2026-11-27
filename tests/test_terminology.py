from pathlib import Path

from sdtm_helper.standards import terminology

FIXTURE = Path(__file__).parent / "fixtures" / "ct_sample.txt"


def test_parse_codelist_and_terms():
    cls = terminology.load(FIXTURE)
    sex = cls["C66731"]
    assert sex.submission_name == "SEX"
    assert not sex.extensible
    assert sex.allows("M") and not sex.allows("MALE")


def test_lookup_by_submission_name():
    cls = terminology.load(FIXTURE)
    assert terminology.by_submission_name(cls, "sex").code == "C66731"
    assert terminology.by_submission_name(cls, "NY") is None
