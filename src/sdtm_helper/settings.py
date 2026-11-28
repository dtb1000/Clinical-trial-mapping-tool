"""App settings and the SASPy configuration file the app writes for the user.

Users of the Windows app never edit Python files: the Settings dialog stores
their choices here and writes a sascfg_personal.py into the app's folder.
Passwords are never stored by the app.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from .paths import app_home

ODA_REGIONS = {
    "United States 1": ["odaws01-usw2.oda.sas.com", "odaws02-usw2.oda.sas.com"],
    "United States 2": ["odaws01-usw2-2.oda.sas.com", "odaws02-usw2-2.oda.sas.com"],
    "Europe 1": ["odaws01-euw1.oda.sas.com", "odaws02-euw1.oda.sas.com"],
    "Asia Pacific 1": ["odaws01-apse1.oda.sas.com", "odaws02-apse1.oda.sas.com"],
    "Asia Pacific 2": ["odaws01-apse1-2.oda.sas.com", "odaws02-apse1-2.oda.sas.com"],
}
CONNECTIONS = {"oda": "SAS OnDemand for Academics", "winlocal": "SAS 9.4 installed on this PC"}


@dataclass
class AppSettings:
    connection: str = "oda"          # "oda" or "winlocal"
    oda_region: str = "Europe 1"
    java_path: str = ""
    oda_user: str = ""               # user ID only; the password is asked at each connect
    autoexec: str = ""               # the user's own libname program
    last_study: str = ""
    last_domain: str = "DM"
    last_table: str = ""

    @property
    def cfgfile(self) -> Path:
        return app_home() / "sascfg_personal.py"


def settings_file() -> Path:
    return app_home() / "settings.json"


def load_settings() -> AppSettings:
    path = settings_file()
    if not path.exists():
        return AppSettings(java_path=find_java())
    data = json.loads(path.read_text(encoding="utf-8"))
    known = AppSettings.__dataclass_fields__
    return AppSettings(**{k: v for k, v in data.items() if k in known})


def save_settings(settings: AppSettings) -> Path:
    path = settings_file()
    path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    write_sascfg(settings)
    return path


def find_java() -> str:
    found = shutil.which("java")
    return found or ""


def write_sascfg(settings: AppSettings) -> Path:
    """Write the SASPy configuration for both connection types."""
    hosts = ODA_REGIONS.get(settings.oda_region, ODA_REGIONS["Europe 1"])
    java = settings.java_path or "java"
    text = (
        "# Written by SDTM Helper's Settings dialog. Edit the settings in the app instead.\n"
        "SAS_config_names = ['oda', 'winlocal']\n\n"
        f"oda = {{'java': {java!r}, 'iomhost': {hosts!r}, 'iomport': 8591,\n"
        "       'authkey': 'oda', 'encoding': 'utf-8'}\n\n"
        f"winlocal = {{'java': {java!r}, 'encoding': 'windows-1252'}}\n"
    )
    path = settings.cfgfile
    path.write_text(text, encoding="utf-8")
    return path
