from sdtm_helper.settings import AppSettings, load_settings, save_settings


def test_settings_round_trip_and_sascfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SDTM_HELPER_HOME", str(tmp_path))
    s = AppSettings(connection="oda", oda_region="United States 2", java_path=r"C:\Java\bin\java.exe", oda_user="u1")
    save_settings(s)
    again = load_settings()
    assert again.oda_region == "United States 2" and again.oda_user == "u1"
    cfg = {}
    exec((tmp_path / "sascfg_personal.py").read_text(), cfg)
    assert cfg["SAS_config_names"] == ["oda", "winlocal"]
    assert cfg["oda"]["iomhost"] == ["odaws01-usw2-2.oda.sas.com", "odaws02-usw2-2.oda.sas.com"]
    assert cfg["oda"]["java"] == r"C:\Java\bin\java.exe"
    assert "password" not in (tmp_path / "settings.json").read_text().lower()
