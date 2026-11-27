"""Build the guide for one domain: explanations, a checklist and the workflow.

Inputs are the SDTMIG spec for the domain (from the standards bundle), the
curated tips in this folder, and optionally what the user's SAS table looks
like right now. The output is guidance only; no SAS code is generated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..standards.domain import DomainSpec

HERE = Path(__file__).resolve().parent


@dataclass
class ChecklistItem:
    variable: str
    label: str
    core: str
    status: str        # "missing", "empty", "partly empty", "done" or "optional"
    detail: str = ""

    @property
    def needs_action(self) -> bool:
        return self.status in ("missing", "empty") or (self.status == "partly empty" and self.core == "Req")


@dataclass
class WorkflowStep:
    id: str
    title: str
    detail: str
    after: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)


@dataclass
class DomainGuide:
    domain: str
    summary: str
    general_tips: dict[str, str]
    tips: dict[str, str]
    workflow: list[WorkflowStep]
    checklist: list[ChecklistItem]

    def explain(self, variable: str, spec: DomainSpec) -> str:
        """Everything the app knows about one variable, for the user to read."""
        var = spec.variable(variable)
        if var is None:
            return f"{variable.upper()} is not a {spec.code} variable in SDTMIG {spec.version}."
        lines = [f"{var.name}: {var.label}",
                 f"Core: {var.core}   Role: {var.role}   Type: {var.datatype}"]
        if var.codelists:
            lines.append("Controlled terminology: " + ", ".join(var.codelists))
        if var.is_iso8601:
            lines.append("Format: " + self.general_tips.get("iso8601", "ISO 8601"))
        if var.description:
            lines.append("SDTMIG notes: " + var.description)
        if var.name in self.tips:
            lines.append("Tip: " + self.tips[var.name])
        return "\n".join(lines)

    def mermaid(self, done: set[str] | None = None) -> str:
        """The workflow as a Mermaid flowchart, with finished steps marked."""
        done = done or set()
        lines = ["flowchart TD"]
        for step in self.workflow:
            mark = " ✓" if step.id in done else ""
            lines.append(f'    {step.id}["{step.title}{mark}"]')
        for step in self.workflow:
            for parent in step.after:
                lines.append(f"    {parent} --> {step.id}")
        if done:
            lines.append("    classDef done fill:#d4edda,stroke:#2e7d32")
            lines.append("    class " + ",".join(sorted(done)) + " done")
        return "\n".join(lines)

    def next_steps(self, done: set[str]) -> list[WorkflowStep]:
        """Steps whose prerequisites are all finished but which are not finished themselves."""
        return [s for s in self.workflow if s.id not in done and all(p in done for p in s.after)]


def _read(name: str) -> dict:
    path = HERE / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_tips(domain: str, klass: str = "") -> dict:
    """Merge the domain's own tips over the shared tips for its observation class."""
    general, own = _read("general"), _read(domain.lower())
    workflow = (own.get("workflow") or general.get("workflows", {}).get(klass)
                or general.get("generic_workflow", []))
    return {
        "domain": domain.upper(),
        "summary": own.get("summary", ""),
        "workflow": workflow,
        "general_tips": {**general.get("general_tips", {}), **own.get("general_tips", {})},
        "variables": own.get("variables", {}),
        "shared_variables": general.get("variables", {}),
    }


def tip_for(name: str, domain: str, tips: dict) -> dict | None:
    """Domain tip first, then a shared tip for the exact name, then the shared --SUFFIX tip."""
    name = name.upper()
    if name in tips["variables"]:
        return tips["variables"][name]
    shared = tips["shared_variables"]
    if name in shared:
        return shared[name]
    if name.startswith(domain.upper()):
        return shared.get("--" + name[len(domain):])
    return None


def build_checklist(spec: DomainSpec, columns: list[str] | None = None,
                    missing: dict[str, int] | None = None, nobs: int = 0) -> list[ChecklistItem]:
    """Compare the spec with the user's table. Without a table, everything Req/Exp is 'missing'."""
    present = {c.upper() for c in (columns or [])}
    missing = {k.upper(): v for k, v in (missing or {}).items()}
    items = []
    for var in spec.variables:
        if var.name not in present:
            status = "optional" if var.core == "Perm" else "missing"
            detail = "" if var.core == "Perm" else f"{var.name} is {'required' if var.required else 'expected'} but not in your table yet."
        else:
            n_missing = missing.get(var.name, 0)
            if nobs and n_missing >= nobs:
                status = "empty"
                detail = f"{var.name} exists but every row is empty."
                if var.core == "Exp":
                    detail += " Expected variables may be empty only when the data were not collected or do not apply."
                if var.core == "Perm":
                    status = "optional"
                    detail = f"{var.name} is permissible and entirely empty; consider dropping it."
            elif n_missing:
                status = "partly empty"
                detail = f"{n_missing} of {nobs} rows are empty."
                if var.required:
                    detail += " Required variables must never be empty."
            else:
                status = "done"
                detail = ""
        items.append(ChecklistItem(var.name, var.label, var.core, status, detail))
    return items


def build_guide(spec: DomainSpec, columns: list[str] | None = None,
                missing: dict[str, int] | None = None, nobs: int = 0) -> DomainGuide:
    tips = load_tips(spec.code, spec.klass)
    step_ids = {s["id"] for s in tips["workflow"]}
    var_tips: dict[str, str] = {}
    by_step: dict[str, list[str]] = {}
    names = [v.name for v in spec.variables] + [n for n in tips["variables"] if not spec.variable(n)]
    for name in names:
        info = tip_for(name, spec.code, tips)
        if not info:
            continue
        var_tips[name] = info.get("tip", "")
        step = info.get("step", "")
        if step not in step_ids:      # shared tips name steps that a domain's own workflow may not have
            fallbacks = ["dates"] if step == "timing" else ["qualifiers", "tests", "content"]
            step = next((f for f in fallbacks if f in step_ids), "")
        if step:
            by_step.setdefault(step, []).append(name)
    workflow = [WorkflowStep(variables=by_step.get(s["id"], []), **s) for s in tips["workflow"]]
    return DomainGuide(
        domain=spec.code,
        summary=tips["summary"],
        general_tips=tips["general_tips"],
        tips=var_tips,
        workflow=workflow,
        checklist=build_checklist(spec, columns, missing, nobs),
    )
