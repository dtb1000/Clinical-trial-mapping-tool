"""Maintainer script: build the standards bundle from the text of the SDTMIG PDF.

    python scripts/extract_sdtmig_text.py path/to/SDTMIG_v3.4.txt --version 3.4

Use a text export of the PDF (for example from `pdftotext -layout`-free text or the
"Save as text" option of a PDF reader). The script reads each domain's
specification table and keeps only the facts the app needs: variable names,
labels, types, controlled terminology or format, roles and Core. CDISC's notes
text is NOT copied into the bundle.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "sdtm_helper" / "data"

HEADER = re.compile(r"^([a-z]{2,8})\.xpt, (.+?) — (.+?)\. (.*)$")
ROLES = ["Grouping Qualifier", "Record Qualifier", "Synonym Qualifier", "Variable Qualifier",
         "Result Qualifier", "Identifier", "Topic", "Timing", "Rule"]
ROLE_RE = re.compile(r"\b(" + "|".join(ROLES) + r")\b")
CORE_END = re.compile(r"(?:^|[\s.\")\]]|(?<=[a-z]))(Req|Exp|Perm)$")
VAR_START = re.compile(r"^([A-Z][A-Z0-9]{0,7}) (.*)$")
NOISE = re.compile(
    r"^(Name|Variable Label Type Controlled Terms,|Codelist or|Format1|Format|"
    r"Role CDISC Notes Core|CDISC Study Data Tabulation Model.*|©.*|\d{4}-\d{2}-\d{2}|"
    r"Variable Label Type Controlled Terms, Codelist or Format1 Role CDISC Notes Core)$")
SECTION_END = re.compile(r"^(\d* ?In this column|.* – Assumptions|.*Assumptions for .*)")
CODELIST = re.compile(r"\(([A-Z][A-Z0-9]{1,15})\)")


def split_record(text: str) -> dict | None:
    m = VAR_START.match(text)
    if not m:
        return None
    name, rest = m.groups()
    t = re.search(r"\b(Char|Num)\b", rest)
    if not t:
        return None
    label = rest[: t.start()].strip()
    after = rest[t.end():].strip()
    r = ROLE_RE.search(after)
    if not r:
        return None
    ct = after[: r.start()].strip()
    core = CORE_END.search(after).group(1)
    var = {"name": name, "label": label, "simpleDatatype": t.group(1), "role": r.group(1), "core": core}
    codelists = CODELIST.findall(ct)
    if codelists:
        var["_links"] = {"codelist": [{"href": f"/mdr/root/ct/sdtmct/codelists/{c}"} for c in codelists]}
    fmt = CODELIST.sub("", ct).replace("*", "").strip(" ;,")
    if fmt:
        var["describedValueDomain"] = fmt
    return var


START = re.compile(r"^([A-Z][A-Z0-9]{0,7}) (.{1,45}?) (Char|Num)\b")


def _is_header_variable(lines: list[str], i: int) -> bool:
    """'Variable' alone on a line is a repeated table header only when 'Name' or 'Label' follows."""
    if lines[i].strip() != "Variable":
        return False
    nxt = next((l.strip() for l in lines[i + 1:i + 3] if l.strip()), "")
    return nxt.startswith(("Name", "Label", "Variable Label"))


def looks_like_start(lines: list[str], i: int) -> bool:
    """A row starts with NAME, a short label, then Char or Num, possibly wrapped over a few lines.

    This rejects lines of notes that continue after a page break and happen to begin with a variable name.
    """
    if not VAR_START.match(lines[i].strip()):
        return False
    parts, j = [], i
    while j < len(lines) and len(parts) < 5:
        line = lines[j].strip()
        j += 1
        if not line or NOISE.match(line) or _is_header_variable(lines, j - 1):
            continue
        parts.append(line)
    return bool(START.match(" ".join(parts)))


def parse(lines: list[str]) -> dict[str, dict]:
    domains: dict[str, dict] = {}
    i = 0
    while i < len(lines):
        h = HEADER.match(lines[i].strip())
        if not h:
            i += 1
            continue
        code, label, klass, structure = h.groups()
        structure = structure.rsplit(", Tabulation", 1)[0].strip()
        i += 1
        variables, buf = [], []
        while i < len(lines):
            line = lines[i].strip()
            if HEADER.match(line) or SECTION_END.match(line):
                break
            i += 1
            if not line or NOISE.match(line) or _is_header_variable(lines, i - 1):
                continue
            if not buf and not looks_like_start(lines, i - 1):
                continue
            buf.append(line)
            if CORE_END.search(line):
                rec = split_record(" ".join(buf))
                if rec:
                    rec["ordinal"] = str(len(variables) + 1)
                    variables.append(rec)
                buf = []
        if variables and code.upper() not in domains:
            domains[code.upper()] = {
                "name": code.upper(), "label": label, "class": klass,
                "datasetStructure": structure, "datasetVariables": variables,
            }
    return domains


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("text_file")
    ap.add_argument("--version", default="3.4")
    args = ap.parse_args()
    lines = Path(args.text_file).read_text(encoding="utf-8", errors="replace").splitlines()
    domains = parse(lines)
    out = DATA / f"sdtmig-{args.version.replace('.', '-')}"
    out.mkdir(parents=True, exist_ok=True)
    for code, d in sorted(domains.items()):
        (out / f"{code}.json").write_text(json.dumps(d, indent=2), encoding="utf-8")
        print(f"  {code:<8} {len(d['datasetVariables']):>3} variables")
    manifest = {"sdtmig_version": args.version, "source": "extracted from the SDTMIG PDF text",
                "built_on": date.today().isoformat(), "verified_by": None, "verified_on": None,
                "domains": sorted(domains)}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved {len(domains)} domains to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
