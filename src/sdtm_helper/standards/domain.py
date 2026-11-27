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
    )


def load_domain(domain: str, version: str = SDTMIG_VERSION, path: Path | None = None) -> DomainSpec:
    path = path or cache_path(domain, version)
    if not path.exists():
        raise DomainNotCached(
            f"SDTMIG {version} {domain.upper()} is not downloaded yet. "
            f"Run: sdtm-helper fetch-standards {domain.upper()}"
        )
    return parse_domain(json.loads(path.read_text(encoding="utf-8")), version)
