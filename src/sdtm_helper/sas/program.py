"""Read the user's SAS program well enough to follow it, the way SQLens follows a query.

This never writes mapping code. It reads the DATA step or PROC SQL statement under
the cursor and works out which tables it reads and makes, which columns it keeps,
drops, renames or creates, and which columns its filters use. `sandbox` then wraps
the user's own step, unchanged apart from table names, so it reads the first rows
of each input from WORK and writes to WORK, and never touches the user's tables.

The reader is forgiving: half-typed code gives a partial answer, never an error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

NAME = re.compile(r"[A-Za-z_&][\w&.]*")
IDENT = re.compile(r"(?<![\w.&%'\"])(?:[A-Za-z_]\w*\.)?([A-Za-z_]\w*)\b(?!\s*\()(?!\.)")
KEYWORDS = {
    "AND", "OR", "NOT", "IN", "EQ", "NE", "GT", "LT", "GE", "LE", "THEN", "ELSE", "DO", "END", "IF",
    "IS", "NULL", "MISSING", "LIKE", "BETWEEN", "AS", "CASE", "WHEN", "CALCULATED", "DISTINCT", "ON",
    "DESCENDING", "ASC", "DESC", "TO", "BY", "WHILE", "UNTIL", "OTHERWISE", "CONTAINS", "ALSO",
}
UNSAFE_DATA = re.compile(r"(file\s|x\s*['\"])", re.I)
SQL_CLAUSES = re.compile(r"\b(from|where|group\s+by|having|order\s+by)\b", re.I)
JOIN = re.compile(r"\b(?:(?:left|right|full|inner|cross|natural)\s+(?:outer\s+)?)?join\b", re.I)
ROW = "_sdtmh_r"


def mask(program: str) -> str:
    """The program with comment and string contents blanked, same length, so offsets still line up."""
    out = list(program)
    i, n = 0, len(program)

    def blank(a, b):
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        if program.startswith("/*", i):
            j = program.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
            continue
        ch = program[i]
        if ch in "'\"":
            j = i + 1
            while j < n:
                if program[j] == ch:
                    if j + 1 < n and program[j + 1] == ch:
                        j += 2
                        continue
                    break
                j += 1
            blank(i + 1, j)
            i = j + 1
            continue
        i += 1
    return "".join(out)


@dataclass
class Statement:
    start: int
    end: int
    text: str
    masked: str
    comment: bool = False

    @property
    def keyword(self) -> str:
        m = re.match(r"\s*(%?\w+)", self.masked)
        return m.group(1).lower() if m else ""

    @property
    def body_offset(self) -> int:
        """Offset just after the first word."""
        m = re.match(r"\s*%?\w+", self.masked)
        return m.end() if m else 0


@dataclass
class Step:
    kind: str                 # data, sql, proc or global
    start: int
    end: int
    statements: list[Statement] = field(default_factory=list)


def statements(program: str) -> list[Statement]:
    masked = mask(program)
    out, start = [], 0
    for i, ch in enumerate(masked):
        if ch == ";":
            out.append(Statement(start, i + 1, program[start:i + 1], masked[start:i + 1]))
            start = i + 1
    if program[start:].strip():
        out.append(Statement(start, len(program), program[start:], masked[start:]))
    for s in out:
        lead = s.masked.lstrip()
        if lead.startswith("*") or lead.startswith("%*"):
            s.comment = True
            s.masked = re.sub(r"[^\n]", " ", s.masked)
    return out


def steps(program: str) -> list[Step]:
    result: list[Step] = []
    cur: Step | None = None
    for s in statements(program):
        if s.comment or not s.masked.strip(" \n\t;"):
            if cur is not None:
                cur.statements.append(s)
                cur.end = s.end
            continue
        kw = s.keyword
        starts = (kw == "data" and not re.match(r"\s*data\s*=", s.masked, re.I)) or kw == "proc"
        if starts:
            if cur is not None:
                result.append(cur)
            kind = "data" if kw == "data" else ("sql" if re.match(r"\s*proc\s+sql\b", s.masked, re.I) else "proc")
            cur = Step(kind, s.start, s.end, [s])
            continue
        if cur is None:
            result.append(Step("global", s.start, s.end, [s]))
            continue
        cur.statements.append(s)
        cur.end = s.end
        if kw == "quit" or (kw == "run" and cur.kind != "sql"):
            result.append(cur)
            cur = None
    if cur is not None:
        result.append(cur)
    return result


def step_at(program: str, pos: int) -> Step | None:
    """The step the cursor is in. A cursor on the blank lines after a step still means that step."""
    all_steps = steps(program)
    for i, st in enumerate(all_steps):
        if st.start <= pos <= st.end:
            if i > 0 and not program[st.start:pos].strip():
                return all_steps[i - 1]
            return st
    return all_steps[-1] if all_steps and pos >= all_steps[-1].end else None


# -- data set references ----------------------------------------------------------

@dataclass
class DsRef:
    name: str            # as written, e.g. raw.dm
    start: int           # span of the name in the program
    end: int
    options: str = ""    # "(keep=... where=(...))" including the parentheses
    opt_start: int = -1
    opt_end: int = -1
    alias: str = ""

    @property
    def key(self) -> str:
        return self.name.upper() if "." in self.name else f"WORK.{self.name.upper()}"

    @property
    def member(self) -> str:
        return self.name.split(".")[-1].upper()

    def option(self, name: str) -> str:
        """The value of one data set option, e.g. option('keep') -> 'a b c'."""
        m = re.search(rf"\b{name}\s*=\s*", self.options, re.I)
        if not m:
            return ""
        rest = self.options[m.end():]
        if rest.startswith("("):
            depth = 0
            for i, ch in enumerate(rest):
                depth += ch == "("
                depth -= ch == ")"
                if depth == 0:
                    return rest[1:i]
            return rest[1:]
        stop = re.search(r"\b\w+\s*=|\)\s*$", rest)
        return rest[:stop.start()] if stop else rest


def _close_paren(text: str, i: int) -> int:
    depth = 0
    for e in range(i, len(text)):
        if text[e] == "(":
            depth += 1
        elif text[e] == ")":
            depth -= 1
            if depth == 0:
                return e + 1
    return len(text)


def ds_list(stmt: Statement, after: int) -> list[DsRef]:
    """Data set names (with options) in a DATA, SET or MERGE statement."""
    m, out, i = stmt.masked, [], after
    while i < len(m):
        ch = m[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "/;":
            break
        mm = NAME.match(m, i)
        if not mm:
            i += 1
            continue
        k = mm.end()
        while k < len(m) and m[k].isspace():
            k += 1
        if k < len(m) and m[k] == "=":          # end=eof, nobs=n: not a data set
            k += 1
            while k < len(m) and m[k].isspace():
                k += 1
            mv = re.compile(r"[\w.&]+").match(m, k)
            i = mv.end() if mv else k + 1
            continue
        ref = DsRef(stmt.text[mm.start():mm.end()], stmt.start + mm.start(), stmt.start + mm.end())
        i = mm.end()
        if k < len(m) and m[k] == "(":
            e = _close_paren(m, k)
            ref.options, ref.opt_start, ref.opt_end = stmt.text[k:e], stmt.start + k, stmt.start + e
            i = e
        out.append(ref)
    return out


def idents(text: str) -> set[str]:
    """Names that may be columns in an expression (function names and keywords left out)."""
    return {m.group(1).upper() for m in IDENT.finditer(text)} - KEYWORDS


def names(text: str) -> list[str]:
    return [n.upper() for n in re.findall(r"[A-Za-z_]\w*", text)]


# -- what a step does -------------------------------------------------------------

@dataclass
class StepPlan:
    kind: str                                   # data or sql
    statement: Statement | None = None          # for SQL, the statement followed
    outputs: list[DsRef] = field(default_factory=list)
    inputs: list[DsRef] = field(default_factory=list)
    keep: set[str] = field(default_factory=set)
    drop: set[str] = field(default_factory=set)
    rename: dict[str, str] = field(default_factory=dict)
    filters: list[str] = field(default_factory=list)
    filter_cols: set[str] = field(default_factory=set)
    assigned: dict[str, str] = field(default_factory=dict)   # new column -> expression
    used_cols: set[str] = field(default_factory=set)
    by: list[str] = field(default_factory=list)
    join_cols: set[str] = field(default_factory=set)
    group_by: set[str] = field(default_factory=set)
    order_by: set[str] = field(default_factory=set)
    selected: set[str] = field(default_factory=set)
    select_all: bool = False
    distinct: bool = False
    problem: str = ""

    @property
    def title(self) -> str:
        made = ", ".join(o.name for o in self.outputs) or "no table"
        if self.kind == "sql":
            return f"PROC SQL making {made}"
        return f"DATA step making {made}"


def analyse(program: str, step: Step, pos: int | None = None) -> StepPlan:
    if step.kind in ("data", "sql"):
        plan = _analyse_data(step) if step.kind == "data" else _analyse_sql(step, pos)
        if not plan.problem:
            _check_inputs(plan)
        return plan
    return StepPlan(step.kind, problem="Put the cursor in a DATA step or a PROC SQL step to follow it.")


def _add_filter(plan: StepPlan, masked: str, text: str | None = None) -> None:
    """masked is used to find column names; text (same offsets, strings intact) is what is shown."""
    if masked.strip():
        plan.filters.append(" ".join((text if text is not None else masked).split()).rstrip(";"))
        plan.filter_cols |= idents(masked)


def _analyse_data(step: Step) -> StepPlan:
    plan = StepPlan("data")
    first = step.statements[0]
    if re.search(r"/\s*view\s*=", first.masked, re.I):
        plan.problem = "This DATA step makes a view, which isn't previewed."
    plan.outputs = [d for d in ds_list(first, first.body_offset) if d.member not in ("_NULL_",)]
    for s in step.statements[1:]:
        if s.comment:
            continue
        kw, off = s.keyword, s.body_offset
        body, orig = s.masked[off:].rstrip(";"), s.text[off:].rstrip(";")
        if UNSAFE_DATA.match(s.masked.strip()) or re.search(r"\bcall\s+(execute|system)\b", s.masked, re.I):
            plan.problem = "This step writes files or runs commands, so it isn't run as a preview."
        if kw in ("set", "merge", "update"):
            plan.inputs += ds_list(s, s.body_offset)
        elif kw == "modify":
            plan.problem = "MODIFY changes a table in place, so it isn't run as a preview."
        elif kw == "keep":
            plan.keep |= set(names(body))
        elif kw == "drop":
            plan.drop |= set(names(body))
        elif kw == "rename":
            plan.rename.update({a.upper(): b.upper() for a, b in re.findall(r"(\w+)\s*=\s*(\w+)", body)})
        elif kw == "where":
            lead = re.match(r"\s*((same\s+and|also)\b)?", body, re.I).end()
            _add_filter(plan, body[lead:], orig[lead:])
        elif kw == "by":
            plan.by += [n for n in names(body) if n not in KEYWORDS]
        elif kw == "if":
            then = re.search(r"\bthen\b", body, re.I)
            if not then:
                _add_filter(plan, body, orig)                # subsetting IF
            else:
                rest = body[then.end():]
                if re.match(r"\s*delete\b", rest, re.I):
                    _add_filter(plan, body[:then.start()], "not (" + orig[:then.start()].strip() + ")")
                _assignment(plan, s, off + then.end())
                plan.used_cols |= idents(body[:then.start()])
        elif kw == "else":
            _assignment(plan, s, off)
        elif kw in ("length", "format", "informat", "label", "attrib", "retain", "array", "call", "output",
                    "do", "end", "run", "return", "delete", "stop", "select", "when", "otherwise", "put",
                    "input", "datalines", "cards", "infile"):
            if kw == "when":
                m = re.search(r"\)\s*", body)
                if m:
                    _assignment(plan, s, off + m.end())
        else:
            _assignment(plan, s, 0)
    for ref in plan.inputs:
        _add_filter(plan, ref.option("where"))
        plan.rename.update({a.upper(): b.upper() for a, b in re.findall(r"(\w+)\s*=\s*(\w+)", ref.option("rename"))})
    return plan


ASSIGN = re.compile(r"\s*([A-Za-z_]\w*)\s*=(?!=)(.*)$", re.S)


def _assignment(plan: StepPlan, s: Statement, start: int) -> None:
    m = ASSIGN.match(s.masked, start)
    if m and m.group(1).upper() not in KEYWORDS:
        expr = s.text[m.start(2):m.end(2)].strip().rstrip(";")
        plan.assigned.setdefault(m.group(1).upper(), " ".join(expr.split()))
        plan.used_cols |= idents(m.group(2))


def _split_top(text: str, sep: str = ",") -> list[tuple[int, str]]:
    """Split on a separator outside parentheses; (offset, piece) pairs."""
    out, depth, last = [], 0, 0
    for i, ch in enumerate(text):
        depth += ch == "("
        depth -= ch == ")"
        if ch == sep and depth == 0:
            out.append((last, text[last:i]))
            last = i + 1
    out.append((last, text[last:]))
    return out


def _depths(text: str) -> list[int]:
    depth, out = 0, []
    for ch in text:
        if ch == ")":
            depth -= 1
        out.append(depth)
        if ch == "(":
            depth += 1
    return out


def _analyse_sql(step: Step, pos: int | None) -> StepPlan:
    plan = StepPlan("sql")
    candidates = [s for s in step.statements if s.keyword in ("create", "select")]
    if not candidates:
        plan.problem = "Write a CREATE TABLE … AS SELECT statement to follow it."
        return plan
    stmt = next((s for s in candidates if pos is not None and s.start <= pos <= s.end), candidates[0])
    plan.statement = stmt
    m = stmt.masked
    create = re.match(r"\s*create\s+table\s+", m, re.I)
    if create:
        out = ds_list(stmt, create.end())[:1]
        plan.outputs = out
        sel = re.search(r"\bas\s+select\b", m, re.I)
        if not sel:
            plan.problem = "Only CREATE TABLE … AS SELECT statements are followed. Run this one with F3."
            return plan
        sel_start = sel.end()
    else:
        sel_start = re.match(r"\s*select\b", m, re.I).end()
    if re.search(r"\binto\s*:", m, re.I):
        plan.problem = "SELECT … INTO :macro-variable isn't previewed. Run it with F3."
        return plan
    if re.search(r"\b(union|except|intersect|outer\s+union)\b", m, re.I):
        plan.problem = "Queries with UNION, EXCEPT or INTERSECT aren't followed yet. Run them with F3."
        return plan
    depth = _depths(m)
    clauses = [(c.start(), c.end(), re.sub(r"\s+", " ", c.group(1).lower()))
               for c in SQL_CLAUSES.finditer(m, sel_start) if depth[c.start()] == 0]
    bounds = [(sel_start, "select")] + [(e, k) for _s, e, k in clauses]
    starts = [sel_start] + [s for s, _e, _k in clauses] + [len(m.rstrip().rstrip(";"))]
    parts = {}
    for i, (b, k) in enumerate(bounds):
        parts[k] = (b, m[b:starts[i + 1]])
    if "from" not in parts:
        plan.problem = "Add a FROM clause to follow this query."
        return plan
    if re.search(r"\bselect\b", parts["from"][1], re.I):
        plan.problem = "Queries that read from a subquery aren't followed yet."
        return plan

    # select list
    sel_off, sel_text = parts["select"]
    if re.match(r"\s*distinct\b", sel_text, re.I):
        plan.distinct = True
        sel_text = re.sub(r"^\s*distinct\b", lambda x: " " * len(x.group(0)), sel_text, flags=re.I)
    for _off, item in _split_top(sel_text):
        item = re.sub(r"(\s+(label|format|length|informat)\s*=\s*\S+)+\s*$", "", item, flags=re.I)
        plain = re.match(r"\s*(?:(\w+)\.)?(\w+|\*)\s*$", item)
        if plain:
            if plain.group(2) == "*":
                plan.select_all = True
            else:
                plan.selected.add(plain.group(2).upper())
            continue
        named = re.match(r"(?s)\s*(.*?)\s+as\s+(\w+)\s*$", item, re.I)
        if named:
            expr, new = named.group(1), named.group(2).upper()
            col = re.match(r"\s*(?:\w+\.)?(\w+)\s*$", expr)
            if col and col.group(1).upper() not in KEYWORDS:
                plan.rename[col.group(1).upper()] = new
                plan.selected.add(col.group(1).upper())
            else:
                at = sel_off + _off + item.find(expr)
                plan.assigned[new] = " ".join(stmt.text[at:at + len(expr)].split())
                plan.used_cols |= idents(expr)

    # tables and joins
    from_off, from_text = parts["from"]
    pieces = [p for _o, chunk in _split_top(from_text) for p in JOIN.split(chunk)]
    cursor = 0
    for piece in pieces:
        found = from_text.find(piece, cursor)
        cursor = found + len(piece)
        on = re.search(r"\bon\b", piece, re.I)
        if on:
            plan.join_cols |= idents(piece[on.end():])
        head = piece[:on.start()] if on else piece
        t = re.match(r"\s*([A-Za-z_&][\w&.]*)", head)
        if not t:
            continue
        absolute = stmt.start + from_off + found
        ref = DsRef(stmt.text[from_off + found + t.start(1):from_off + found + t.end(1)],
                    absolute + t.start(1), absolute + t.end(1))
        rest = head[t.end():]
        if rest.lstrip().startswith("("):
            k = t.end() + (len(rest) - len(rest.lstrip()))
            e = _close_paren(head, k)
            ref.options = stmt.text[from_off + found + k:from_off + found + e]
            ref.opt_start, ref.opt_end = absolute + k, absolute + e
            rest = head[e:]
        alias = re.match(r"\s*(?:as\s+)?([A-Za-z_]\w*)\s*$", rest, re.I)
        if alias:
            ref.alias = alias.group(1)
        plan.inputs.append(ref)
        _add_filter(plan, ref.option("where"))
    for clause in ("where", "having"):
        if clause in parts:
            off, text = parts[clause]
            _add_filter(plan, text, stmt.text[off:off + len(text)])
    if "group by" in parts:
        plan.group_by = idents(parts["group by"][1])
    if "order by" in parts:
        plan.order_by = idents(parts["order by"][1])
    for c in clauses:
        if c[2] == "from":
            plan._from_at = stmt.start + c[0]  # type: ignore[attr-defined]
    return plan


# -- the sandboxed copy ---------------------------------------------------------------

def _check_inputs(plan: StepPlan) -> None:
    if any(r.name.upper().startswith("DICTIONARY.") for r in plan.inputs):
        plan.problem = "DICTIONARY tables aren't previewed. Run this step with F3."


def input_keys(plan: StepPlan) -> list[str]:
    """Each distinct input, in order, as LIB.MEMBER."""
    return list(dict.fromkeys(r.key for r in plan.inputs))


def sandbox(program: str, step: Step, plan: StepPlan, rows: int = 200) -> str:
    """The user's own step, reading the first `rows` rows of each input from WORK views and
    writing to WORK._SDTMH_OUTn. Each view adds a row number (_sdtmh_r1, _sdtmh_r2, …) so the
    preview can tell which input rows reached the output. Nothing else in the step changes."""
    keys = input_keys(plan)
    index = {k: i + 1 for i, k in enumerate(keys)}
    rowvars = " ".join(f"{ROW}{i}" for i in index.values())
    lines = ["proc datasets lib=work nolist nowarn; delete _sdtmh_in: _sdtmh_out: / memtype=all; quit;"]
    for ref in {r.key: r for r in plan.inputs}.values():
        i = index[ref.key]
        lines.append(f"data work._sdtmh_in{i} / view=work._sdtmh_in{i}; "
                     f"set {ref.name}(obs={int(rows)}); {ROW}{i} = _n_; run;")
    edits: list[tuple[int, int, str]] = []      # program offsets
    for ref in plan.inputs:
        i = index[ref.key]
        new = f"work._sdtmh_in{i}"
        if plan.kind == "sql" and not ref.alias:
            alias_at = ref.opt_end if ref.opt_end > 0 else ref.end
            edits.append((alias_at, alias_at, f" as {ref.member}"))
        edits.append((ref.start, ref.end, new))
        _keep_rows(ref, f"{ROW}{i}", edits)
    for j, ref in enumerate(plan.outputs, 1):
        edits.append((ref.start, ref.end, f"work._sdtmh_out{j}"))
        _keep_rows(ref, rowvars, edits)

    if plan.kind == "data":
        a, b = step.start, step.end
        for s in step.statements[1:]:
            if s.keyword == "keep" and rowvars:
                at = s.start + s.body_offset
                edits.append((at, at, f" {rowvars}"))
        tail = "" if re.search(r"\brun\s*;\s*$", mask(program[a:b]), re.I) else "\nrun;"
    else:
        stmt = plan.statement
        a, b = stmt.start, stmt.end
        if not plan.outputs:
            sel = re.match(r"\s*select\b", stmt.masked, re.I)
            at = stmt.start + sel.start() + len(sel.group(0)) - len("select")
            edits.append((at, at, "create table work._sdtmh_out1 as "))
        if not (plan.select_all or plan.distinct or plan.group_by):
            cols = "".join(f", {r.alias or r.member}.{ROW}{index[r.key]}"
                           for r in {r.key: r for r in plan.inputs}.values())
            at = getattr(plan, "_from_at", None)
            if at is not None:
                edits.append((at, at, f"{cols} "))
        tail = "" if stmt.masked.rstrip().endswith(";") else ";"
    text = program[a:b]
    for start, end, new in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        if a <= start <= b:
            text = text[:start - a] + new + text[end - a:]
    if plan.kind == "sql":
        lines += ["proc sql;", text.strip() + tail, "quit;"]
    else:
        lines.append(text.strip() + tail)
    return "\n".join(lines)


def _keep_rows(ref: DsRef, rowvars: str, edits: list) -> None:
    if not ref.options or not rowvars:
        return
    m = re.search(r"\bkeep\s*=\s*\(?", ref.options, re.I)
    if m:
        at = ref.opt_start + m.end()
        edits.append((at, at, f"{rowvars} "))
