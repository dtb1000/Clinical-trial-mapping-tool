"""The SDTMIG rules for a single domain, read from the local cache.

The user always names the domain they are working on, so the app loads only
that domain's content instead of the whole implementation guide.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .. import SDTMIG_VERSION
from .cdisc_library import cache_path

CORE_ORDER = {"Req": 0, "Exp": 1, "Perm": 2}


@dataclass
class Variable:
    name: str
    label: str
    core: str                 # "Req", "Exp" or "Perm"
    role: str = ""
    datatype: str = ""        # "Char" or "Num"
    description: str = ""     # the CDISC Notes column
    value_domain: str = ""    # for example "ISO 8601 datetime or interval"
    codelists: list[str] = field(default_factory=list)   # e.g. ["C66731"]

    @property
    def required(self) -> bool:
        return self.core == "Req"

    @property
    def is_iso8601(self) -> bool:
        return "iso 8601" in self.value_domain.lower() or self.name.endswith(("DTC", "DUR"))


@dataclass
class DomainSpec:
    code: str
    label: str
    structure: str
    description: str
    version: str
    variables: list[Variable]
    klass: str = ""           # observation class, e.g. "Events" or "Findings"

    def variable(self, name: str) -> Variable | None:
        name = name.upper()
        return next((v for v in self.variables if v.name == name), None)

    def by_core(self, core: str) -> list[Variable]:
        return [v for v in self.variables if v.core == core]


class DomainNotCached(FileNotFoundError):
    pass


def parse_domain(data: dict, version: str = SDTMIG_VERSION) -> DomainSpec:
    """Turn a CDISC Library dataset response into a DomainSpec."""
    variables = []
    for raw in sorted(data.get("datasetVariables", []), key=lambda v: int(v.get("ordinal", 0))):
        links = raw.get("_links", {}) or {}
        codelist_links = links.get("codelist", []) or []
        if isinstance(codelist_links, dict):
            codelist_links = [codelist_links]
        codelists = [link["href"].rstrip("/").rsplit("/", 1)[-1]
                     for link in codelist_links if link.get("href")]
        variables.append(Variable(
            name=raw.get("name", "").upper(),
            label=raw.get("label", ""),
            core=raw.get("core", ""),
            role=raw.get("role", ""),
            datatype=raw.get("simpleDatatype", ""),
            description=raw.get("description", ""),
            value_domain=raw.get("describedValueDomain", ""),
            codelists=codelists,
        ))
    return DomainSpec(
        code=data.get("name", "").upper(),
        label=data.get("label", ""),
        structure=data.get("datasetStructure", ""),
        description=data.get("description", ""),
        version=version,
        variables=variables,
        klass=data.get("class", "") or _class_from_link(data),
    )


def _class_from_link(data: dict) -> str:
    """The CDISC Library API gives the class as a link title rather than a field."""
    link = (data.get("_links", {}) or {}).get("parentClass", {}) or {}
    return link.get("title", "") if isinstance(link, dict) else ""


BUNDLE_DIR = Path(__file__).resolve().parents[1] / "data"


def bundled_path(domain: str, version: str = SDTMIG_VERSION) -> Path:
    return BUNDLE_DIR / f"sdtmig-{version.replace('.', '-')}" / f"{domain.upper()}.json"


def bundle_manifest(version: str = SDTMIG_VERSION) -> dict | None:
    path = BUNDLE_DIR / f"sdtmig-{version.replace('.', '-')}" / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_domain(domain: str, version: str = SDTMIG_VERSION, path: Path | None = None) -> DomainSpec:
    """Load a domain from an explicit path, else the bundle shipped with the app, else the user's own download."""
    if path is None:
        candidates = [bundled_path(domain, version), cache_path(domain, version)]
        path = next((p for p in candidates if p.exists()), None)
    if path is None or not path.exists():
        raise DomainNotCached(
            f"SDTMIG {version} {domain.upper()} is not in the app's standards bundle yet. "
            f"Update the app, or run: sdtm-helper fetch-standards {domain.upper()}"
        )
    return parse_domain(json.loads(path.read_text(encoding="utf-8")), version)
