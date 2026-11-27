"""CDISC SDTM Controlled Terminology, downloaded from NCI EVS. No API key needed.

NCI EVS publishes the current SDTM terminology as a tab-delimited file at
https://evs.nci.nih.gov/ftp1/CDISC/SDTM/ (updated each quarter). The app keeps
a local copy and refreshes it on request.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

import requests

from ..paths import standards_dir

CT_URL = "https://evs.nci.nih.gov/ftp1/CDISC/SDTM/SDTM%20Terminology.txt"


@dataclass
class Codelist:
    code: str                 # e.g. C66731
    name: str                 # e.g. Sex
    submission_name: str      # e.g. SEX
    extensible: bool
    terms: dict[str, str] = field(default_factory=dict)   # submission value -> NCI preferred term

    def allows(self, value: str) -> bool:
        return value in self.terms


def cache_path() -> Path:
    return standards_dir() / "sdtm_ct.txt"


def download(url: str = CT_URL, session: requests.Session | None = None) -> Path:
    http = session or requests.Session()
    response = http.get(url, timeout=120)
    response.raise_for_status()
    path = cache_path()
    path.write_bytes(response.content)
    return path


def parse(text: str) -> dict[str, Codelist]:
    """Parse the EVS file. Rows with no 'Codelist Code' are codelist headers."""
    codelists: dict[str, Codelist] = {}
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    rows = list(reader)
    for row in rows:
        if not row.get("Codelist Code"):
            codelists[row["Code"]] = Codelist(
                code=row["Code"],
                name=row.get("Codelist Name", ""),
                submission_name=row.get("CDISC Submission Value", ""),
                extensible=row.get("Codelist Extensible (Yes/No)", "").strip().lower() == "yes",
            )
    for row in rows:
        parent = row.get("Codelist Code")
        if parent and parent in codelists:
            codelists[parent].terms[row["CDISC Submission Value"]] = row.get("NCI Preferred Term", "")
    return codelists


def load(path: Path | None = None) -> dict[str, Codelist]:
    path = path or cache_path()
    if not path.exists():
        raise FileNotFoundError("Controlled terminology not downloaded yet. Run: sdtm-helper fetch-ct")
    return parse(path.read_text(encoding="utf-8-sig"))
