import json

from sdtm_helper.standards.domain import BUNDLE_DIR, bundle_manifest, load_domain


def test_every_bundled_domain_loads_and_is_well_formed():
    manifest = bundle_manifest("3.4")
    assert manifest and manifest["domains"]
    for code in manifest["domains"]:
        spec = load_domain(code, "3.4")
        assert spec.code == code
        names = [v.name for v in spec.variables]
        assert len(names) == len(set(names)), f"duplicate variables in {code}"
        assert names[0] == "STUDYID", code
        for v in spec.variables:
            assert v.core in ("Req", "Exp", "Perm"), (code, v.name)
            assert v.datatype in ("Char", "Num"), (code, v.name)
            assert len(v.name) <= 8 and len(v.label) <= 40, (code, v.name)


def test_all_domains_from_the_guide_are_bundled():
    domains = bundle_manifest("3.4")["domains"]
    assert len(domains) >= 60
    for code in ("AE", "CM", "DM", "DS", "EX", "LB", "MH", "VS", "TA", "TS"):
        assert code in domains


def test_dm_core_values():
    dm = load_domain("DM", "3.4")
    assert [v.name for v in dm.by_core("Req")] == ["STUDYID", "DOMAIN", "USUBJID", "SUBJID", "SITEID", "SEX", "COUNTRY"]
    assert dm.variable("SEX").codelists == ["SEX"]
    assert dm.variable("RFCSTDTC").core == "Perm"
    assert len(dm.variables) == 32
