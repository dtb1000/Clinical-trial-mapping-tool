"""Tell the user when a newer release of the app (and so of its standards bundle) exists."""

from __future__ import annotations

import requests

from . import __version__

RELEASES_URL = "https://api.github.com/repos/dtb1000/Clinical-trial-mapping-tool/releases/latest"


def _as_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for piece in version.lstrip("vV").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def check_for_update(current: str = __version__, session: requests.Session | None = None) -> str | None:
    """Return a reminder message if GitHub has a newer release, else None. Never raises on network errors."""
    http = session or requests.Session()
    try:
        response = http.get(RELEASES_URL, timeout=10, headers={"Accept": "application/vnd.github+json"})
        if response.status_code != 200:
            return None
        release = response.json()
    except (requests.RequestException, ValueError):
        return None
    latest = release.get("tag_name", "")
    if latest and _as_tuple(latest) > _as_tuple(current):
        return (f"A newer version ({latest}) is available with updated standards: "
                f"{release.get('html_url', '')}")
    return None
