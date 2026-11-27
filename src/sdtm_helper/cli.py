"""Command-line entry point for step 1. A desktop interface comes later."""

from __future__ import annotations

import argparse
import sys

from . import SDTMIG_VERSION, progress
from .standards.cdisc_library import CdiscLibraryError, fetch_domain
from .standards.domain import DomainNotCached, load_domain
from .standards import terminology


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

    p = sub.add_parser("progress", help="List saved work")
    p.set_defaults(func=cmd_progress)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (CdiscLibraryError, FileNotFoundError, LookupError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
