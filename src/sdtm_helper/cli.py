"""Command-line entry point for step 1. A desktop interface comes later."""

from __future__ import annotations

import argparse
import sys

from . import SDTMIG_VERSION, progress
from .standards.cdisc_library import CdiscLibraryError, fetch_domain
from .standards.domain import DomainNotCached, load_domain
from .standards import terminology
from .guidance.engine import build_guide
from .updates import check_for_update
from .checks.engine import format_report, run_checks


def _connect(args):
    from .sas.session import SasConnection
    sas = SasConnection(cfgname=args.cfgname, cfgfile=args.cfgfile)
    if getattr(args, "autoexec", None):
        sas.run_file(args.autoexec)
    return sas


def cmd_check_sas(args) -> int:
    sas = _connect(args)
    try:
        print(f"Connected to SAS {sas.version}")
        print("Libraries: " + ", ".join(sas.list_libraries()))
    finally:
        sas.close()
    return 0


def cmd_describe(args) -> int:
    sas = _connect(args)
    try:
        info = sas.describe(args.libref, args.table)
    finally:
        sas.close()
    print(f"{info.libref}.{info.name}: {info.nobs} rows, {len(info.columns)} variables")
    for c in info.columns:
        print(f"  {c.name:<12} {c.type:<4} {c.length:>4}  {c.label}")
    return 0


def cmd_fetch(args) -> int:
    for domain in args.domains:
        path = fetch_domain(domain, args.version)
        print(f"Saved SDTMIG {args.version} {domain.upper()} to {path}")
    return 0


def cmd_fetch_ct(args) -> int:
    path = terminology.download()
    print(f"Saved {len(terminology.load(path))} SDTM codelists to {path}")
    return 0


def cmd_show(args) -> int:
    spec = load_domain(args.domain, args.version)
    print(f"{spec.code} ({spec.label}), SDTMIG {spec.version}")
    print(f"Structure: {spec.structure}\n")
    for core, title in (("Req", "Required"), ("Exp", "Expected"), ("Perm", "Permissible")):
        variables = spec.by_core(core)
        print(f"{title} ({len(variables)}): " + ", ".join(v.name for v in variables))
    return 0


def cmd_compare(args) -> int:
    """Compare a table in SAS with the domain spec: what's there, what's missing."""
    spec = load_domain(args.domain, args.version)
    sas = _connect(args)
    try:
        info = sas.describe(args.libref, args.table)
    finally:
        sas.close()
    present = {c.name.upper() for c in info.columns}
    for core, title in (("Req", "Required"), ("Exp", "Expected")):
        missing = [v.name for v in spec.by_core(core) if v.name not in present]
        print(f"{title} variables still missing: {', '.join(missing) or 'none'}")
    extra = sorted(present - {v.name for v in spec.variables})
    print(f"Variables not in SDTMIG {spec.code} (drop or move to SUPP{spec.code}): "
          f"{', '.join(extra) or 'none'}")
    return 0


STATUS_MARK = {"done": "[x]", "missing": "[ ]", "empty": "[ ]", "partly empty": "[~]", "optional": "[-]"}


def cmd_guide(args) -> int:
    """Show the guide for a domain: workflow, next steps and the checklist against the user's table."""
    spec = load_domain(args.domain, args.version)
    saved = progress.load(args.study, spec.code) or progress.DomainProgress(study=args.study, domain=spec.code)
    columns, missing, nobs = None, None, 0
    if args.libref and args.table:
        sas = _connect(args)
        try:
            info = sas.describe(args.libref, args.table)
            columns = [c.name for c in info.columns]
            known = [c for c in columns if spec.variable(c)]
            missing = sas.missing_counts(args.libref, args.table, known)
            nobs = info.nobs
        finally:
            sas.close()
        saved.target_table = f"{args.libref.upper()}.{args.table.upper()}"
    guide = build_guide(spec, columns, missing, nobs)
    done = set(saved.done_steps)

    print(f"{spec.code}: {spec.label} (SDTMIG {spec.version})")
    if guide.summary:
        print(guide.summary)
    print("\nWorkflow:")
    for i, step in enumerate(guide.workflow, 1):
        mark = "[x]" if step.id in done else "[ ]"
        extra = f"  ({', '.join(step.variables)})" if step.variables else ""
        print(f"  {mark} {i}. {step.title}{extra}")
    nxt = guide.next_steps(done)
    if nxt:
        print(f"\nNext: {nxt[0].title}. {nxt[0].detail}")
    print("\nChecklist" + (f" against {saved.target_table}:" if columns is not None else " (no table given yet):"))
    for item in guide.checklist:
        if item.status == "optional" and not args.all:
            continue
        print(f"  {STATUS_MARK[item.status]} {item.variable:<9} {item.core:<4} {item.detail}")
    todo = sum(1 for i in guide.checklist if i.needs_action)
    print(f"\n{todo} item(s) need action. Use 'sdtm-helper explain {spec.code} VAR' for details.")
    if args.chart:
        print("\nWorkflow chart (Mermaid):\n" + guide.mermaid(done))
    progress.save(saved)
    return 0


def cmd_explain(args) -> int:
    spec = load_domain(args.domain, args.version)
    print(build_guide(spec).explain(args.variable, spec))
    return 0


def cmd_step(args) -> int:
    spec = load_domain(args.domain, args.version)
    guide = build_guide(spec)
    ids = {s.id for s in guide.workflow}
    if args.step not in ids:
        print(f"Unknown step. Choose one of: {', '.join(s.id for s in guide.workflow)}", file=sys.stderr)
        return 1
    saved = progress.load(args.study, spec.code) or progress.DomainProgress(study=args.study, domain=spec.code)
    if args.undo:
        saved.done_steps = [s for s in saved.done_steps if s != args.step]
    else:
        saved.mark_done(args.step)
    path = progress.save(saved)
    print(f"Saved. {len(saved.done_steps)} of {len(ids)} {spec.code} steps done ({path}).")
    return 0


def cmd_check(args) -> int:
    """Run the P21-lite checks on a finished domain."""
    spec = load_domain(args.domain, args.version)
    try:
        codelists = terminology.load()
    except FileNotFoundError:
        codelists = None
    sas = _connect(args)
    try:
        info = sas.describe(args.libref, args.table)
        df = sas.fetch(args.libref, args.table)
        dm = None
        if args.dm and spec.code != "DM":
            dm_lib, _, dm_table = args.dm.partition(".")
            dm = sas.fetch(dm_lib, dm_table or "DM")
    finally:
        sas.close()
    report = run_checks(spec, df, info, codelists, dm)
    print(format_report(report))
    if report.passed:
        saved = progress.load(args.study, spec.code) or progress.DomainProgress(study=args.study, domain=spec.code)
        saved.mark_done("check")
        progress.save(saved)
    return 0 if report.passed else 2


def cmd_progress(args) -> int:
    saved = progress.list_saved()
    if not saved:
        print("No saved work yet.")
    for p in saved:
        print(f"{p.study} {p.domain}: {len(p.done_steps)} steps done, last saved {p.updated_at}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sdtm-helper", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def sas_options(p):
        p.add_argument("--cfgname", default="oda", help="SASPy configuration name (default: oda)")
        p.add_argument("--cfgfile", help="Path to sascfg_personal.py (default: config/sascfg_personal.py)")
        p.add_argument("--autoexec", help="Your own SAS program to run first, e.g. your libname file")

    p = sub.add_parser("check-sas", help="Test the SAS connection and list libraries")
    sas_options(p)
    p.set_defaults(func=cmd_check_sas)

    p = sub.add_parser("describe", help="List the variables of a SAS table")
    p.add_argument("libref"); p.add_argument("table")
    sas_options(p)
    p.set_defaults(func=cmd_describe)

    p = sub.add_parser("fetch-standards", help="Download SDTMIG content for one or more domains")
    p.add_argument("domains", nargs="+")
    p.add_argument("--version", default=SDTMIG_VERSION)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("fetch-ct", help="Download the latest SDTM controlled terminology (no key needed)")
    p.set_defaults(func=cmd_fetch_ct)

    p = sub.add_parser("show-domain", help="Summarise a downloaded domain")
    p.add_argument("domain")
    p.add_argument("--version", default=SDTMIG_VERSION)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("compare", help="Compare a SAS table with a domain's variables")
    p.add_argument("domain"); p.add_argument("libref"); p.add_argument("table")
    p.add_argument("--version", default=SDTMIG_VERSION)
    sas_options(p)
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("guide", help="Workflow, next step and checklist for the domain you are mapping")
    p.add_argument("domain")
    p.add_argument("libref", nargs="?", help="Library of the table you are building, e.g. FINAL")
    p.add_argument("table", nargs="?", help="The table you are building, e.g. DM")
    p.add_argument("--study", default="default", help="Study name, used to save your progress")
    p.add_argument("--all", action="store_true", help="Also list permissible variables")
    p.add_argument("--chart", action="store_true", help="Print the workflow as a Mermaid chart")
    p.add_argument("--version", default=SDTMIG_VERSION)
    sas_options(p)
    p.set_defaults(func=cmd_guide)

    p = sub.add_parser("explain", help="Explain one variable: SDTMIG notes, format, terminology, tips")
    p.add_argument("domain"); p.add_argument("variable")
    p.add_argument("--version", default=SDTMIG_VERSION)
    p.set_defaults(func=cmd_explain)

    p = sub.add_parser("step", help="Mark a workflow step done (or --undo) and save progress")
    p.add_argument("domain"); p.add_argument("step")
    p.add_argument("--study", default="default")
    p.add_argument("--undo", action="store_true")
    p.add_argument("--version", default=SDTMIG_VERSION)
    p.set_defaults(func=cmd_step)

    p = sub.add_parser("check", help="Run P21-lite checks on a finished domain")
    p.add_argument("domain"); p.add_argument("libref"); p.add_argument("table")
    p.add_argument("--dm", help="Your DM table as LIB.TABLE, for cross-domain checks, e.g. FINAL.DM")
    p.add_argument("--study", default="default")
    p.add_argument("--version", default=SDTMIG_VERSION)
    sas_options(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("progress", help="List saved work")
    p.set_defaults(func=cmd_progress)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in ("guide", "progress"):
        reminder = check_for_update()
        if reminder:
            print(reminder + "\n")
    try:
        return args.func(args)
    except (CdiscLibraryError, FileNotFoundError, LookupError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
