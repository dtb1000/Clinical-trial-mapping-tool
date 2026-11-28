"""Follow the step under the cursor, the way SQLens follows a query (no Qt here, so it can be tested).

The user's own DATA step or PROC SQL statement runs as a sandboxed copy on the first rows
of each table it reads (see sas.program.sandbox). The result says, for each table the step
reads, which rows reach the output, which columns are kept, dropped or renamed, which
columns the filters and new columns use, and the values the new columns will get.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..sas import program as sasprog
from ..sas.session import SasConnection, TableInfo
from .workspace import split_table

ROW = sasprog.ROW


@dataclass
class FollowedTable:
    name: str                       # as written in the program, e.g. raw.dm
    role: str                       # "input" or "output"
    rows: object                    # pandas DataFrame, row-number columns removed
    info: TableInfo | None = None   # the real table's metadata (for inputs: the original table)
    total: int | None = None        # rows in the real table
    kept_rows: set[int] | None = None          # 0-based positions that reach the output; None = unknown
    new_columns: list[str] = field(default_factory=list)   # columns added on the right (inputs) or made by the step
    words: dict[str, list[str]] = field(default_factory=dict)  # column (upper) -> how the step uses it
    status: dict[str, str] = field(default_factory=dict)       # column (upper) -> keep, drop, rename, new
    summary: list[tuple[str, str]] = field(default_factory=list)  # (text, mark) pieces
    formulas: dict[str, str] = field(default_factory=dict)       # new column -> your expression

    @property
    def shown(self) -> int:
        return len(self.rows)


@dataclass
class FollowResult:
    title: str = ""
    tables: list[FollowedTable] = field(default_factory=list)
    message: str = ""               # why nothing is shown, or the SAS error
    error: bool = False
    step_start: int = -1
    step_end: int = -1
    plan: sasprog.StepPlan | None = None
    log: str = ""                   # SAS's log of the sandboxed run, for squiggly underlines


def follow(sas: SasConnection, program: str, pos: int, rows: int = 200) -> FollowResult:
    step = sasprog.step_at(program, pos)
    if step is None:
        return FollowResult(message="Put the cursor in a DATA step or a PROC SQL step to follow it.")
    plan = sasprog.analyse(program, step, pos)
    res = FollowResult(title=plan.title, step_start=step.start, step_end=step.end, plan=plan)
    if plan.problem:
        res.message = plan.problem
        return res
    if not plan.inputs and not plan.outputs:
        res.message = "This step doesn't read or make a table yet."
        return res

    infos: dict[str, TableInfo | None] = {}
    for key in sasprog.input_keys(plan):
        lib, name = split_table(key)
        try:
            infos[key] = sas.describe(lib, name)
        except LookupError:
            res.message = (f"{key} doesn't exist yet. Run the steps that make it first "
                           "(select them and press F3).")
            return res
        except ValueError:           # a macro variable in the name: let SAS resolve it
            infos[key] = None

    log = sas.submit(sasprog.sandbox(program, step, plan, rows))
    res.log = log
    errors = [ln for ln in log.splitlines() if ln.startswith("ERROR")]
    if errors:
        res.error = True
        res.message = "SAS can't run this step yet: " + " ".join(errors[:2])
        return res

    keys = sasprog.input_keys(plan)
    out_df = None
    if plan.outputs or plan.kind == "sql":
        try:
            out_df = sas.fetch("WORK", "_SDTMH_OUT1")
        except Exception:
            out_df = None
    out_cols = [] if out_df is None else [c for c in out_df.columns if not _is_row(c)]
    out_upper = {c.upper() for c in out_cols}
    in_frames = {}
    for i, key in enumerate(keys, 1):
        in_frames[key] = sas.fetch("WORK", f"_SDTMH_IN{i}")
    all_in = {c.upper() for df in in_frames.values() for c in df.columns if not _is_row(c)}
    renamed_to = set(plan.rename.values())
    new_cols = [c for c in out_cols if c.upper() not in all_in and c.upper() not in renamed_to]
    back = {v: k for k, v in plan.rename.items()}     # new name -> old name

    for i, key in enumerate(keys, 1):
        df = in_frames[key]
        ref = next(r for r in plan.inputs if r.key == key)
        rowcol = _find(df.columns, f"{ROW}{i}")
        cols = [c for c in df.columns if not _is_row(c)]
        view = df[cols].reset_index(drop=True)
        kept = None
        out_row = _find(out_df.columns, f"{ROW}{i}") if out_df is not None else None
        if out_row is not None and rowcol is not None:
            reached = out_df.dropna(subset=[out_row]).copy()
            reached[out_row] = reached[out_row].astype(int)
            kept = {int(v) - 1 for v in reached[out_row]}
            first = reached.drop_duplicates(out_row).set_index(out_row)
            positions = df[rowcol].astype(int).tolist()
            for c in new_cols:
                view[c] = [first[c].get(p) if p in first.index else None for p in positions]
        table = FollowedTable(ref.name, "input", view, infos.get(key),
                              infos[key].nobs if infos.get(key) else None, kept, list(new_cols) if kept is not None else [])
        used = _used_names(plan, back)
        for c in cols:
            u = c.upper()
            words = []
            if u in plan.rename:
                target = plan.rename[u]
                table.status[u] = "rename" if target in out_upper else ("drop" if out_df is not None else "")
                words.append(f"→ {target}")
            elif out_df is None:
                table.status[u] = ""
            elif u in out_upper:
                table.status[u] = "keep"
                words.append("select" if plan.kind == "sql" else "keep")
            else:
                table.status[u] = "drop"
                words.append("drop")
            for label, group in (("where", plan.filter_cols), ("used", used), ("by", set(plan.by)),
                                 ("join", plan.join_cols), ("group by", plan.group_by), ("order by", plan.order_by)):
                if u in group or (plan.rename.get(u) in group):
                    words.append(label)
            table.words[u] = words
        for c in table.new_columns:
            table.status[c.upper()] = "new"
            expr = plan.assigned.get(c.upper())
            table.words[c.upper()] = ["new"]
            if expr:
                table.formulas[c.upper()] = expr
        table.summary = _summary(plan, table, len(cols), len(keys) > 1)
        res.tables.append(table)

    if out_df is not None:
        out_name = plan.outputs[0].name if plan.outputs else "the result"
        view = out_df[out_cols].head(rows).reset_index(drop=True)
        try:
            out_info = sas.describe("WORK", "_SDTMH_OUT1")
        except Exception:
            out_info = None
        table = FollowedTable(out_name, "output", view, out_info, out_info.nobs if out_info else len(out_df))
        table.new_columns = list(new_cols)
        for c in out_cols:
            u = c.upper()
            if c in new_cols:
                table.status[u] = "new"
                expr = plan.assigned.get(u)
                table.words[u] = ["new"]
                if expr:
                    table.formulas[u] = expr
            elif u in renamed_to:
                table.status[u] = "rename"
                table.words[u] = [f"from {back[u]}"]
                table.status[u] = "rename"
            else:
                table.words[u] = []
        n = len(out_df)
        table.summary = [(f"Your step makes {n} row{'s' if n != 1 else ''} and {len(out_cols)} columns "
                          f"from the first {rows} rows of each input. ", ""),
                         (f"{len(new_cols)} new column{'s' if len(new_cols) != 1 else ''}.", "new")]
        res.tables.append(table)
    return res


def _is_row(col) -> bool:
    return str(col).lower().startswith(ROW)


def _find(columns, name: str):
    return next((c for c in columns if str(c).lower() == name.lower()), None)


def _used_names(plan: sasprog.StepPlan, back: dict[str, str]) -> set[str]:
    used = set(plan.used_cols)
    return used | {back[u] for u in used if u in back}


def _summary(plan: sasprog.StepPlan, t: FollowedTable, ncols: int, several: bool) -> list[tuple[str, str]]:
    verb = "FROM" if plan.kind == "sql" else "SET"
    total = f" of {t.total}" if t.total is not None and t.total > t.shown else ""
    parts = [(f"{verb} reads {'the first ' if total else ''}{t.shown}{total} rows. ", "")]
    if t.kept_rows is not None:
        what = "WHERE/IF" if plan.kind == "data" else ("WHERE and the join" if several else "WHERE")
        if plan.filters or several:
            parts.append((f"{what} keeps {len(t.kept_rows)} of {t.shown} rows.", "removed"))
        else:
            parts.append((f"All {t.shown} rows reach the output.", "kept"))
        parts.append((" ", ""))
    kept = sum(1 for s in t.status.values() if s in ("keep", "rename"))
    if any(t.status.values()):
        parts.append((f"{kept} of {ncols} columns go to the output.", "keep"))
        parts.append((" ", ""))
    if t.new_columns:
        n = len(t.new_columns)
        parts.append((f"{n} new column{'s' if n != 1 else ''}.", "new"))
    return parts
