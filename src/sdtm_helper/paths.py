"""Where the app keeps its local files (standards cache, saved progress)."""

import os
from pathlib import Path


def app_home() -> Path:
    """Base folder for local app data. Override with SDTM_HELPER_HOME."""
    override = os.environ.get("SDTM_HELPER_HOME")
    base = Path(override) if override else Path.home() / ".sdtm_helper"
    base.mkdir(parents=True, exist_ok=True)
    return base


def standards_dir() -> Path:
    path = app_home() / "standards"
    path.mkdir(parents=True, exist_ok=True)
    return path


def progress_dir() -> Path:
    path = app_home() / "progress"
    path.mkdir(parents=True, exist_ok=True)
    return path
