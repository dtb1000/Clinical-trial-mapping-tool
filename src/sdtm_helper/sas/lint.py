"""Find problems in the user's SAS program, for squiggly underlines in the editor.

Two sources:
- `check(program)`: a quick check in Python as you type. It catches what is easy to get wrong
  and easy to spot: unclosed comments, quotes and brackets, a missing semicolon, DO without END,
  a misspelt function name, == or != instead of SAS operators, and a last step without RUN.
- `from_log(log, code, start_line)`: SAS's own errors and warnings from a run, placed on the line
  (and where SAS marks it, the column) of the code they belong to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import functions
from .program import mask, steps

ERROR, WARNING = "error", "warning"


@dataclass(frozen=True)
class Problem:
    line: int          # 0-based line in the editor
    col: int           # 0-based column
    length: int
    severity: str      # error or warning
    message: str
    source: str = "check"   # "check" (as you type) or "SAS" (from the log)


def _pos(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset)
    col = offset - (text.rfind("\n", 0, offset) + 1)
    return line, col


def _at(text: str, offset: int, length: int, severity: str, message: str) -> Problem:
    line, col = _pos(text, offset)
    return Problem(line, col, max(1, length), severity, message)


# -- the quick check ---------------------------------------------------------------

STARTS_STATEMENT = {"data", "set", "merge", "run", "quit", "proc", "keep", "drop", "length", "format",
                    "label", "retain", "libname", "%let", "array", "rename", "by", "infile", "input"}
SET_OPTIONS = {"end", "nobs", "point", "key", "indsname", "open", "cur", "unique", "curobs"}
SQL_STARTS = {"run", "quit", "proc", "data", "create", "libname", "%let"}


def check(program: str) -> list[Problem]:
    out: list[Problem] = []
    out += _unclosed(program)
    masked = mask(program)
    for step in steps(program):
        for s in step.statements:
            if s.comment:
                continue
            out += _brackets(program, s)
            out += _operators(program, s)
            out += _missing_semicolon(program, s, step.kind)
            out += _functions(program, s)
        if step.kind == "data":
            out += _do_end(program, step)
    out += _last_step(program, masked)
    return sorted(set(out), key=lambda p: (p.line, p.col))


def _unclosed(program: str) -> list[Problem]:
    out, i, n = [], 0, len(program)
    while i < n:
        if program.startswith("/*", i):
            j = program.find("*/", i + 2)
            if j < 0:
                return out + [_at(program, i, 2, ERROR, "This comment is never closed with */, so everything after it is ignored.")]
            i = j + 2
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
            if j >= n:
                return out + [_at(program, i, 1, ERROR, f"This {'quote' if ch == chr(39) else 'double quote'} is never closed.")]
            i = j + 1
            continue
        i += 1
    return out


def _brackets(program: str, s) -> list[Problem]:
    out, stack = [], []
    for i, ch in enumerate(s.masked):
        if ch == "(":
            stack.append(i)
        elif ch == ")":
            if stack:
                stack.pop()
            else:
                out.append(_at(program, s.start + i, 1, ERROR, "This ) has no matching (."))
    for i in stack:
        out.append(_at(program, s.start + i, 1, ERROR, "This ( isn't closed before the end of the statement."))
    return out


def _operators(program: str, s) -> list[Problem]:
    out = []
    for m in re.finditer(r"==|!=", s.masked):
        hint = "= or EQ" if m.group() == "==" else "^= or NE"
        out.append(_at(program, s.start + m.start(), 2, ERROR, f"SAS compares with {hint}, not {m.group()}."))
    return out


def _missing_semicolon(program: str, s, kind: str) -> list[Problem]:
    """A statement that runs into a line that starts a new statement has lost its semicolon."""
    lines = s.masked.split("\n")
    if len(lines) < 2 or not s.masked.strip():
        return []
    starts = SQL_STARTS if kind == "sql" else STARTS_STATEMENT
    offset = 0
    first_kw = s.keyword
    if first_kw.startswith("%") or re.search(r"%\w+\s*\(", s.masked):
        return []                   # macro calls don't need a semicolon
    conditional = bool(re.search(r"\b(then|else|when|do)\b", lines[0], re.I)) or first_kw in ("if", "else", "when", "select")
    seen_text = bool(lines[0].strip())
    for k, line in enumerate(lines[1:], 1):
        offset += len(lines[k - 1]) + 1
        word = re.match(r"\s*(%?\w+)\s*(=?)", line)
        inside = s.masked[:offset].count("(") > s.masked[:offset].count(")")
        if not word or not seen_text or inside:     # still inside brackets, e.g. data set options
            seen_text = seen_text or bool(line.strip())
            continue
        w = word.group(1).lower()
        new_statement = w in starts and not (w == "by" and kind == "sql")
        reading = first_kw in ("set", "merge", "update") and w not in SET_OPTIONS
        assignment = (kind == "data" and word.group(2) == "=" and not conditional
                      and (reading or ("=" in s.masked[:offset] and first_kw not in (
                          "rename", "label", "format", "length", "attrib", "data", "set", "merge", "update",
                          "proc", "where", "by"))))
        if (new_statement and not (w in ("keep", "drop", "rename", "format", "length", "label") and first_kw == "data")) or assignment:
            prev = s.masked[:offset - 1].rstrip()
            return [_at(program, s.start + len(prev) - 1 if prev else s.start, 1, ERROR,
                        f"Missing semicolon? The next line starts a new statement ({word.group(1)}).")]
        if re.search(r"\b(then|else|when|do)\b", line, re.I):
            conditional = True
    return []


FUNC_CALL = re.compile(r"(?<![\w.&%$])([A-Za-z_]\w*)\s*\(")


def _functions(program: str, s) -> list[Problem]:
    if s.keyword in ("data", "set", "merge", "update", "proc", "libname", "array", "create", "options",
                     "title", "footnote", "ods", "filename", "%macro", "%let", "%put", "length", "format", "label"):
        return []
    arrays = set()
    out = []
    for m in FUNC_CALL.finditer(s.masked):
        name = m.group(1).upper()
        if (name in functions.NOT_FUNCTIONS or functions.is_known(name) or name in arrays
                or s.masked[max(0, m.start() - 5):m.start()].lower().strip().endswith("call")):
            continue
        before = s.masked[:m.start()].rstrip()
        if before.endswith(("from", "join")) or re.search(r"\b(from|join)\s*$", before, re.I):
            continue                                             # a table with data set options
        guesses = functions.closest(name)
        if guesses:
            options = guesses[0] if len(guesses) == 1 else ", ".join(guesses[:-1]) + " or " + guesses[-1]
            out.append(_at(program, s.start + m.start(1), len(name), WARNING,
                           f"{m.group(1)} isn't a SAS function. Did you mean {options}?"))
    return out


def _do_end(program: str, step) -> list[Problem]:
    stack, out = [], []
    for s in step.statements:
        if s.comment:
            continue
        if re.match(r"\s*(select)\b", s.masked, re.I) or re.search(r"\b(then|else)\s+do\b|^\s*do\b", s.masked, re.I):
            stack.append(s)
        elif s.keyword == "end":
            if stack:
                stack.pop()
            else:
                out.append(_at(program, s.start + len(s.masked) - len(s.masked.lstrip()), 3, ERROR,
                               "This END has no DO or SELECT to close."))
    for s in stack:
        m = re.search(r"\bdo\b|\bselect\b", s.masked, re.I)
        out.append(_at(program, s.start + (m.start() if m else 0), 2, ERROR, "This DO has no END."
                       if not m or m.group().lower() == "do" else "This SELECT has no END."))
    return out


def _last_step(program: str, masked: str) -> list[Problem]:
    all_steps = steps(program)
    if not all_steps:
        return []
    last = all_steps[-1]
    if last.kind not in ("data", "sql", "proc"):
        return []
    ends = [s.keyword for s in last.statements if not s.comment]
    want = "quit" if last.kind == "sql" else "run"
    if "quit" in ends or "run" in ends and last.kind != "sql":
        return []
    if re.search(rf"\b{want}\s*;\s*$", last.statements[-1].masked, re.I):
        return []                   # e.g. macro calls without semicolons, then RUN;
    first = last.statements[0]
    at = first.start + len(first.masked) - len(first.masked.lstrip())
    word = re.match(r"\s*\w+", first.masked)
    return [_at(program, at, len(word.group().strip()) if word else 4, WARNING,
                f"This step has no {want.upper()}; at the end, so SAS won't run it yet.")]


# -- SAS's own messages ---------------------------------------------------------------

ECHO = re.compile(r"^\s*(\d+)(?:\s+!)?\s{1,}(.*\S)?\s*$")
UNDERLINE = re.compile(r"^[ _]*_[ _]*$")
VARIABLE = re.compile(r"(?:Variable|column|Column)s?\s+(?:named\s+)?([A-Za-z_]\w*)\b|were not found[^:]*:\s*([A-Za-z_]\w*)", re.I)


def from_log(log: str, code: str, start_line: int = 0) -> list[Problem]:
    """ERROR and WARNING lines from a SAS log, placed in the editor.

    code is what was submitted and start_line where it starts in the editor (for a selection).
    SAS echoes each source line with a number; an underline below it marks the column of the
    error. Messages without a position are placed on the variable they name, if it is in the code,
    or on the last echoed line.
    """
    code_lines = code.split("\n")
    out: list[Problem] = []
    last_line: int | None = None
    marks: list[tuple[int, int]] = []
    echo_text, echo_at = "", 0
    search_from = 0
    for raw in log.splitlines():
        if UNDERLINE.match(raw) and echo_text:
            marks = [(m.start() - echo_at, len(m.group())) for m in re.finditer(r"_+", raw)]
            continue
        sev = ERROR if raw.startswith("ERROR") else WARNING if raw.startswith("WARNING") else None
        if raw.startswith("NOTE: Variable") and "uninitialized" in raw:
            sev = WARNING           # usually a misspelt or dropped variable
        if sev is None:
            if raw.startswith(("NOTE", "      ")) and not ECHO.match(raw):
                continue
            m = ECHO.match(raw)
            if m and m.group(2):
                text = m.group(2).strip()
                found = _find_line(code_lines, text, search_from)
                if found is not None:
                    last_line, search_from = found, found
                    echo_text, echo_at = text, raw.index(m.group(2).strip())
                    marks = []
                elif "_sdtmh_" not in text.lower():
                    echo_text = ""
            continue
        message = re.sub(r"^(ERROR|WARNING|NOTE)( \d+-\d+)?:\s*", "", raw).strip()
        if "_sdtmh_" in message.lower() or not message:
            continue
        if marks and last_line is not None:
            col, length = marks.pop(0)
            indent = len(code_lines[last_line]) - len(code_lines[last_line].lstrip())
            out.append(Problem(start_line + last_line, max(0, indent + col), length, sev, message, "SAS"))
            continue
        var = VARIABLE.search(message)
        placed = None
        if var:
            name = (var.group(1) or var.group(2)).upper()
            for i, line in enumerate(code_lines):
                hit = re.search(rf"\b{re.escape(name)}\b", line, re.I)
                if hit:
                    placed = Problem(start_line + i, hit.start(), len(name), sev, message, "SAS")
                    break
        if placed is None and last_line is not None:
            line = code_lines[last_line]
            indent = len(line) - len(line.lstrip())
            placed = Problem(start_line + last_line, indent, max(1, len(line.strip())), sev, message, "SAS")
        if placed is None:
            placed = Problem(-1, 0, 0, sev, message, "SAS")
        out.append(placed)
    return out


def _find_line(code_lines: list[str], text: str, start: int) -> int | None:
    for rng in (range(start, len(code_lines)), range(0, start)):
        for i in rng:
            if code_lines[i].strip() == text:
                return i
    return None
