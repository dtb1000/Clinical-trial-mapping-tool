"""Download SDTMIG content for one domain from the CDISC Library API and cache it.

You need a CDISC Library API key (from your CDISC account at
https://api.developer.library.cdisc.org/). Set it in the environment variable
CDISC_API_KEY. The key is never written to disk by this app.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from .. import SDTMIG_VERSION
from ..paths import standards_dir

DEFAULT_BASE = "https://api.library.cdisc.org/api"


class CdiscLibraryError(RuntimeError):
    pass


def _version_slug(version: str) -> str:
    return version.replace(".", "-")          # "3.4" -> "3-4", as the API expects


def cache_path(domain: str, version: str = SDTMIG_VERSION) -> Path:
    folder = standards_dir() / f"sdtmig-{_version_slug(version)}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{domain.upper()}.json"


def fetch_domain(domain: str, version: str = SDTMIG_VERSION, *, api_key: str | None = None,
                 base_url: str | None = None, session: requests.Session | None = None) -> Path:
    """Fetch one SDTMIG dataset (for example DM) and save the raw JSON to the local cache."""
    api_key = api_key or os.environ.get("CDISC_API_KEY")
    if not api_key:
        raise CdiscLibraryError(
            "No CDISC Library API key. Set the CDISC_API_KEY environment variable first."
        )
    base_url = (base_url or os.environ.get("CDISC_API_BASE") or DEFAULT_BASE).rstrip("/")
    url = f"{base_url}/mdr/sdtmig/{_version_slug(version)}/datasets/{domain.upper()}"
    http = session or requests.Session()
    response = http.get(url, headers={"api-key": api_key, "Accept": "application/json"}, timeout=60)
    if response.status_code == 401:
        raise CdiscLibraryError("The CDISC Library rejected the API key (401).")
    if response.status_code == 404:
        raise CdiscLibraryError(f"SDTMIG {version} has no dataset called {domain.upper()}.")
    response.raise_for_status()

    data = response.json()
    data["_sdtm_helper"] = {"source": url, "sdtmig_version": version}
    path = cache_path(domain, version)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path
