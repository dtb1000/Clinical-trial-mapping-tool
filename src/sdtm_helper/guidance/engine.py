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


def load_tips(domain: str) -> dict:
    path = HERE / f"{domain.lower()}.json"
    if not path.exists():
        return {"domain": domain.upper(), "summary": "", "workflow": [], "variables": {}, "general_tips": {}}
    return json.loads(path.read_text(encoding="utf-8"))


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
    tips = load_tips(spec.code)
    by_step: dict[str, list[str]] = {}
    for name, info in tips.get("variables", {}).items():
        by_step.setdefault(info.get("step", ""), []).append(name)
    workflow = [WorkflowStep(variables=by_step.get(s["id"], []), **s) for s in tips.get("workflow", [])]
    return DomainGuide(
        domain=spec.code,
        summary=tips.get("summary", ""),
        general_tips=tips.get("general_tips", {}),
        tips={k: v.get("tip", "") for k, v in tips.get("variables", {}).items()},
        workflow=workflow,
        checklist=build_checklist(spec, columns, missing, nobs),
    )
