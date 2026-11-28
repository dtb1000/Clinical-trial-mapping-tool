"""Everything the desktop window does, without any Qt code, so it can be tested.

A Workspace is one study and one domain: the user's SAS program, the target
table, the guide for the domain, the latest checklist and check report, and
saved progress. It talks to SAS only through SasConnection.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import SDTMIG_VERSION, progress
from ..checks.engine import CheckReport, run_checks
from ..guidance.engine import DomainGuide, build_guide
from ..sas.session import SasConnection, TableInfo
from ..standards import terminology
from ..standards.domain import DomainSpec, bundle_manifest, load_domain


def available_domains(version: str = SDTMIG_VERSION) -> list[tuple[str, str]]:
    """(code, label) for every domain in the standards bundle, DM first."""
    manifest = bundle_manifest(version) or {"domains": []}
    out = []
    for code in manifest["domains"]:
        try:
            out.append((code, load_domain(code, version).label))
        except FileNotFoundError:
            continue
    out.sort(key=lambda d: (d[0] != "DM", d[0]))
    return out


def split_table(text: str) -> tuple[str, str]:
    """'final.dm' -> ('FINAL', 'DM'); a bare name means the WORK library."""
    text = text.strip().upper()
    if "." in text:
        lib, _, table = text.partition(".")
        return lib, table
    return "WORK", text


@dataclass
class Preview:
    table: str
    info: TableInfo
    rows: "object"        # pandas DataFrame with the first rows

    @property
    def shown(self) -> int:
        return len(self.rows)


@dataclass
class Workspace:
    study: str
    domain: str
    version: str = SDTMIG_VERSION
    sas: SasConnection | None = None
    spec: DomainSpec = field(init=False)
    guide: DomainGuide = field(init=False)
    state: progress.DomainProgress = field(init=False)
    report: CheckReport | None = None

    def __post_init__(self):
        self.domain = self.domain.upper()
        self.spec = load_domain(self.domain, self.version)
        self.state = progress.load(self.study, self.domain) or progress.DomainProgress(
            study=self.study, domain=self.domain)
        self.guide = build_guide(self.spec)

    # -- program and progress -------------------------------------------
    @property
    def program(self) -> str:
        return self.state.program or self.starter_program()

    def starter_program(self) -> str:
        """An empty program with the workflow as comments: a place to start, not mapping code."""
        lines = [f"/* {self.spec.code}: {self.spec.label} (SDTMIG {self.spec.version}) */",
                 f"/* Study: {self.study} */", ""]
        for i, step in enumerate(self.guide.workflow, 1):
            lines.append(f"/* Step {i}: {step.title} */")
            if step.variables:
                lines.append(f"/*   {', '.join(step.variables)} */")
            lines.append("")
        return "\n".join(lines)

    def save(self, program: str | None = None, table: str | None = None) -> None:
        if program is not None:
            self.state.program = program
        if table is not None:
            self.state.target_table = table.strip().upper()
        progress.save(self.state)

    def toggle_step(self, step_id: str, done: bool) -> None:
        if done:
            self.state.mark_done(step_id)
        else:
            self.state.done_steps = [s for s in self.state.done_steps if s != step_id]
        progress.save(self.state)

    @property
    def done(self) -> set[str]:
        return set(self.state.done_steps)

    # -- talking to SAS ---------------------------------------------------
    def submit(self, code: str) -> str:
        if self.sas is None:
            raise RuntimeError("Not connected to SAS.")
        return self.sas.submit(code)

    def refresh(self, table: str | None = None) -> DomainGuide:
        """Rebuild the checklist against the target table, if it exists yet."""
        table = (table or self.state.target_table or "").strip()
        columns, missing, nobs = None, None, 0
        if table and self.sas is not None:
            lib, name = split_table(table)
            try:
                info = self.sas.describe(lib, name)
            except LookupError:
                info = None
            if info is not None:
                columns = [c.name for c in info.columns]
                known = [c for c in columns if self.spec.variable(c)]
                missing = self.sas.missing_counts(lib, name, known) if known else {}
                nobs = info.nobs
        self.guide = build_guide(self.spec, columns, missing, nobs)
        if table:
            self.save(table=table)
        return self.guide

    def tables(self, extra_libs: tuple[str, ...] = ("WORK",)) -> list[str]:
        """LIB.TABLE names to offer in the preview picker: WORK, the target library and any others given."""
        if self.sas is None:
            return []
        libs = list(dict.fromkeys([split_table(self.state.target_table or "WORK.X")[0], *extra_libs]))
        out = []
        for lib in libs:
            try:
                out += [f"{lib}.{t}" for t in self.sas.list_tables(lib)]
            except Exception:  # library not assigned yet
                continue
        return out

    def preview(self, table: str, rows: int = 200) -> Preview | None:
        """The first rows of any table, for the live preview next to the editor. None if it doesn't exist yet."""
        if self.sas is None or not table.strip():
            return None
        lib, name = split_table(table)
        try:
            info = self.sas.describe(lib, name)
        except LookupError:
            return None
        return Preview(f"{lib}.{name}", info, self.sas.fetch(lib, name, obs=rows))

    def follow(self, program: str, pos: int, rows: int = 200):
        """Run a sandboxed copy of the step under the cursor and mark what it does to its tables."""
        if self.sas is None:
            raise RuntimeError("Not connected to SAS.")
        from .follow import follow
        return follow(self.sas, program, pos, rows)

    def run_checks(self, table: str | None = None, dm_table: str | None = None) -> CheckReport:
        if self.sas is None:
            raise RuntimeError("Not connected to SAS.")
        table = (table or self.state.target_table).strip()
        if not table:
            raise ValueError("Enter the table you are building, e.g. FINAL.DM.")
        lib, name = split_table(table)
        info = self.sas.describe(lib, name)
        df = self.sas.fetch(lib, name)
        dm = None
        if self.domain != "DM":
            dm_lib, dm_name = split_table(dm_table or f"{lib}.DM")
            try:
                dm = self.sas.fetch(dm_lib, dm_name)
            except Exception:  # DM not built yet: run without cross-domain checks
                dm = None
        try:
            codelists = terminology.load()
        except FileNotFoundError:
            codelists = None
        self.report = run_checks(self.spec, df, info, codelists, dm)
        if self.report.passed:
            self.toggle_step("check", True)
        return self.report
