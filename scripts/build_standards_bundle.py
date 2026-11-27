"""Maintainer script: download every SDTMIG domain once and save it as the app's standards bundle.

Run this with YOUR CDISC Library API key whenever CDISC publishes an update,
then commit the result and publish a new release. App users never need a key.

    set CDISC_API_KEY=your-key
    python scripts/build_standards_bundle.py --version 3.4

Check CDISC's terms of use for redistributing Library content before a public release.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdtm_helper.standards.cdisc_library import DEFAULT_BASE, _version_slug  # noqa: E402

DATA = ROOT / "src" / "sdtm_helper" / "data"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="3.4")
    args = parser.parse_args()

    key = os.environ.get("CDISC_API_KEY")
    if not key:
        print("Set CDISC_API_KEY first.", file=sys.stderr)
        return 1
    base = (os.environ.get("CDISC_API_BASE") or DEFAULT_BASE).rstrip("/")
    slug = _version_slug(args.version)
    http = requests.Session()
    http.headers.update({"api-key": key, "Accept": "application/json"})

    index = http.get(f"{base}/mdr/sdtmig/{slug}/datasets", timeout=60)
    index.raise_for_status()
    links = index.json().get("_links", {}).get("datasets", [])
    domains = sorted(link["href"].rstrip("/").rsplit("/", 1)[-1] for link in links)
    if not domains:
        print("The API returned no datasets; check the version and key.", file=sys.stderr)
        return 1

    out = DATA / f"sdtmig-{slug}"
    out.mkdir(parents=True, exist_ok=True)
    for code in domains:
        response = http.get(f"{base}/mdr/sdtmig/{slug}/datasets/{code}", timeout=60)
        response.raise_for_status()
        (out / f"{code}.json").write_text(json.dumps(response.json(), indent=2), encoding="utf-8")
        print(f"  {code}")

    manifest = {
        "sdtmig_version": args.version,
        "built_on": date.today().isoformat(),
        "source": f"{base}/mdr/sdtmig/{slug}",
        "domains": domains,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved {len(domains)} domains to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
