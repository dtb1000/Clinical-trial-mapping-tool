"""Save and resume a user's work on a domain.

Progress is a small JSON file per study and domain in ~/.sdtm_helper/progress.
It records which source tables the user is mapping from, which target table
they are building, and which checklist items they have ticked off.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import SDTMIG_VERSION
from .paths import progress_dir


@dataclass
class DomainProgress:
    study: str
    domain: str
    sdtmig_version: str = SDTMIG_VERSION
    source_tables: list[str] = field(default_factory=list)   # e.g. ["RAW.SUBJECTS"]
    target_table: str = ""                                    # e.g. "FINAL.DM"
    done_steps: list[str] = field(default_factory=list)       # workflow steps ticked off
    notes: dict[str, str] = field(default_factory=dict)       # per-variable notes
    updated_at: str = ""

    def mark_done(self, step: str) -> None:
        if step not in self.done_steps:
            self.done_steps.append(step)


def _file(study: str, domain: str) -> Path:
    safe_study = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in study)
    return progress_dir() / f"{safe_study}_{domain.upper()}.json"


def save(progress: DomainProgress) -> Path:
    progress.domain = progress.domain.upper()
    progress.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = _file(progress.study, progress.domain)
    path.write_text(json.dumps(asdict(progress), indent=2), encoding="utf-8")
    return path


def load(study: str, domain: str) -> DomainProgress | None:
    path = _file(study, domain)
    if not path.exists():
        return None
    return DomainProgress(**json.loads(path.read_text(encoding="utf-8")))


def list_saved() -> list[DomainProgress]:
    return [DomainProgress(**json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(progress_dir().glob("*.json"))]
