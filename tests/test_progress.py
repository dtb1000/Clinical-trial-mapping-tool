from sdtm_helper import progress


def test_save_and_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("SDTM_HELPER_HOME", str(tmp_path))
    p = progress.DomainProgress(study="LORNA", domain="dm", source_tables=["RAW.SUBJECTS"])
    p.mark_done("load-data")
    p.mark_done("load-data")
    progress.save(p)

    again = progress.load("LORNA", "DM")
    assert again.done_steps == ["load-data"]
    assert again.source_tables == ["RAW.SUBJECTS"]
    assert again.updated_at
    assert progress.load("LORNA", "AE") is None
