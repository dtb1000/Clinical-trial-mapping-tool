"""P21-lite: small, fixable conformance checks for one finished domain.

These catch the everyday mistakes before a full Pinnacle 21 run: missing or
empty required variables, wrong types and lengths, badly formed ISO 8601 dates,
values outside controlled terminology, duplicate keys and subjects missing
from DM. They do not replace Pinnacle 21 and they never change the data.

The checks read the dataset as a pandas DataFrame (SASPy fetches it from SAS),
plus the table's SAS metadata, so they can be tested without SAS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from ..sas.session import TableInfo
from ..standards.domain import DomainSpec
from ..standards.terminology import Codelist, by_submission_name

ERROR, WARNING, NOTICE = "Error", "Warning", "Notice"
SEVERITY_ORDER = {ERROR: 0, WARNING: 1, NOTICE: 2}

_D = r"\d{4}(-\d{2}(-\d{2}(T\d{2}(:\d{2}(:\d{2}(\.\d+)?)?)?)?)?)?"
# Partial dates with unknown middle parts use hyphens, e.g. "2023---15" or "2023-05-15T-:30".
_D_MISSING = r"(\d{4}|-)(-(\d{2}|-)(-(\d{2}|-)(T(\d{2}|-)(:(\d{2}|-)(:\d{2}(\.\d+)?)?)?)?)?)?"
_DUR = r"-?P(\d+(\.\d+)?Y)?(\d+(\.\d+)?M)?(\d+(\.\d+)?W)?(\d+(\.\d+)?D)?(T(\d+(\.\d+)?H)?(\d+(\.\d+)?M)?(\d+(\.\d+)?S)?)?"
ISO_DATETIME = re.compile(rf"^({_D}|{_D_MISSING})$")
ISO_DURATION = re.compile(rf"^{_DUR}$")


@dataclass
class Finding:
    check: str            # short id, e.g. "REQ-MISSING"
    severity: str
    message: str
    variable: str = ""
    count: int = 0
    examples: list[str] = field(default_factory=list)
    fix: str = ""


@dataclass
class CheckReport:
    domain: str
    nobs: int
    findings: list[Finding]

    def by_severity(self, severity: str) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]

    @property
    def passed(self) -> bool:
        return not self.by_severity(ERROR)


# -- helpers --------------------------------------------------------------

def _blank(series: pd.Series) -> pd.Series:
    """True where a value is missing: NaN, None, or an all-space string."""
    as_text = series.astype("string").str.strip()
    return series.isna() | (as_text == "") | as_text.isna()


def _examples(values, limit: int = 3) -> list[str]:
    seen = []
    for v in values:
        s = str(v)
        if s not in seen:
            seen.append(s)
        if len(seen) == limit:
            break
    return seen


def is_iso8601(value: str, allow_duration: bool = False) -> bool:
    value = value.strip()
    if allow_duration and ISO_DURATION.match(value) and value not in ("P", "-P"):
        return True
    if "/" in value:                                   # interval: start/end, either may be a duration
        parts = value.split("/")
        return len(parts) == 2 and all(
            ISO_DATETIME.match(p) or (ISO_DURATION.match(p) and p not in ("P", "-P")) for p in parts)
    return bool(ISO_DATETIME.match(value))


def _iso_to_date(value) -> pd.Timestamp | None:
    """Date part of a complete ISO 8601 date, else None."""
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}", value.strip()):
        return None
    try:
        return pd.Timestamp(value.strip()[:10])
    except ValueError:
        return None


def study_day(dtc, rfstdtc) -> int | None:
    """SDTM study day: no day 0, the day of RFSTDTC is day 1."""
    d, r = _iso_to_date(dtc), _iso_to_date(rfstdtc)
    if d is None or r is None:
        return None
    diff = (d - r).days
    return diff + 1 if diff >= 0 else diff


GENERAL_CLASSES = ("Events", "Interventions", "Findings", "Findings About")
_POOLS: dict[tuple[str, str], set[str]] = {}


def _generic(name: str, code: str) -> str:
    return "--" + name[len(code):] if name.startswith(code) and len(name) > len(code) else name


def class_variable_pool(spec: DomainSpec) -> set[str]:
    """Variables the SDTM model lets you add to a domain of this class.

    Built from the bundled SDTMIG: every variable used by any domain of the same
    class, plus identifiers and timing variables used by any general-class domain.
    """
    key = (spec.version, spec.klass)
    if key in _POOLS:
        return _POOLS[key]
    from ..standards.domain import bundle_manifest, load_domain
    pool: set[str] = set()
    manifest = bundle_manifest(spec.version)
    if spec.klass in GENERAL_CLASSES and manifest:
        for code in manifest["domains"]:
            try:
                other = load_domain(code, spec.version)
            except FileNotFoundError:
                continue
            same = other.klass == spec.klass or {other.klass, spec.klass} <= {"Findings", "Findings About"}
            for v in other.variables:
                if same or (other.klass in GENERAL_CLASSES and v.role in ("Identifier", "Timing")):
                    pool.add(_generic(v.name, other.code))
    _POOLS[key] = pool
    return pool


# -- the checks -----------------------------------------------------------

def check_structure(spec: DomainSpec, info: TableInfo | None, df: pd.DataFrame) -> list[Finding]:
    out: list[Finding] = []
    present = {c.upper() for c in df.columns}
    for var in spec.variables:
        if var.name in present:
            continue
        if var.core == "Req":
            out.append(Finding("REQ-MISSING", ERROR, f"Required variable {var.name} is not in the dataset.",
                               var.name, fix=f"Add {var.name} ({var.label})."))
        elif var.core == "Exp":
            out.append(Finding("EXP-MISSING", WARNING, f"Expected variable {var.name} is not in the dataset.",
                               var.name, fix="Add it, left empty if the data were not collected; explain in the reviewer's guide."))
    pool = class_variable_pool(spec)
    for name in df.columns:
        if spec.variable(name) is None and _generic(name.upper(), spec.code) in pool:
            out.append(Finding("CLASS-VARIABLE", NOTICE,
                               f"{name.upper()} is not listed in SDTMIG {spec.code} but is a {spec.klass} class variable, "
                               "which the SDTM model allows you to add.", name.upper(),
                               fix="Fine if it is needed; check the SDTM model's usage restrictions."))
        elif spec.variable(name) is None:
            out.append(Finding("NONSTANDARD", ERROR, f"{name.upper()} is not a {spec.code} variable in SDTMIG {spec.version}.",
                               name.upper(), fix=f"Drop it, or move it to SUPP{spec.code} if the data must be submitted."))
        if len(name) > 8:
            out.append(Finding("NAME-LENGTH", ERROR, f"Variable name {name} is longer than 8 characters.", name.upper()))

    if info is not None:
        unlabelled: list[str] = []
        for col in info.columns:
            var = spec.variable(col.name)
            if col.label and len(col.label) > 40:
                out.append(Finding("LABEL-LENGTH", ERROR, f"Label of {col.name} is longer than 40 characters.", col.name.upper()))
            if col.type == "char" and col.length > 200:
                out.append(Finding("CHAR-LENGTH", ERROR, f"{col.name} has length {col.length}; the maximum is 200.",
                                   col.name.upper(), fix="Split long text into extra variables or SUPP records."))
            if var is None:
                continue
            sas_type = "Num" if col.type == "num" else "Char"
            if var.datatype and sas_type != var.datatype:
                out.append(Finding("TYPE", ERROR, f"{var.name} is {sas_type} but SDTMIG says {var.datatype}.", var.name,
                                   fix="Recreate the variable with the right type."))
            if col.label and var.label and col.label.strip().lower() != var.label.strip().lower():
                out.append(Finding("LABEL", WARNING, f"{var.name} label is \"{col.label}\"; SDTMIG uses \"{var.label}\".", var.name))
            elif not col.label:
                unlabelled.append(var.name)

        if unlabelled:
            out.append(Finding("LABEL", WARNING, f"{len(unlabelled)} variable(s) have no label: {', '.join(unlabelled)}.",
                               count=len(unlabelled),
                               fix="Add the SDTMIG labels, e.g. with a LABEL statement or ATTRIB in the final DATA step."))
        order = [c.name.upper() for c in info.columns if spec.variable(c.name)]
        expected = [v.name for v in spec.variables if v.name in order]
        if order != expected:
            out.append(Finding("ORDER", NOTICE, "Variables are not in SDTMIG order.",
                               fix="Reorder with a RETAIN or LENGTH statement before SET: " + " ".join(expected)))
    return out


def check_values(spec: DomainSpec, df: pd.DataFrame, codelists: dict[str, Codelist] | None) -> list[Finding]:
    out: list[Finding] = []
    nobs = len(df)
    cols = {c.upper(): c for c in df.columns}
    for var in spec.variables:
        if var.name not in cols:
            continue
        s = df[cols[var.name]]
        blank = _blank(s)
        n_blank = int(blank.sum())

        if var.core == "Req" and n_blank:
            out.append(Finding("REQ-NULL", ERROR, f"Required variable {var.name} is empty in {n_blank} of {nobs} records.",
                               var.name, n_blank, fix="Required variables must be populated on every record."))
        if var.core == "Perm" and nobs and n_blank == nobs:
            out.append(Finding("PERM-EMPTY", NOTICE, f"Permissible variable {var.name} is empty on every record.",
                               var.name, fix="Consider dropping it."))

        filled = s[~blank].astype(str).str.strip()
        if filled.empty:
            continue

        if var.name.endswith(("DTC", "DUR")) or var.is_iso8601:
            allow_dur = var.name.endswith("DUR") or "duration" in var.value_domain.lower()
            bad = filled[~filled.map(lambda v: is_iso8601(v, allow_dur))]
            if len(bad):
                out.append(Finding("ISO8601", ERROR, f"{var.name} has {len(bad)} value(s) that are not valid ISO 8601.",
                                   var.name, len(bad), _examples(bad),
                                   fix="Use YYYY-MM-DD or YYYY-MM-DDThh:mm:ss; keep partial dates partial, e.g. 2023-05."))

        if var.name == "DOMAIN":
            bad = filled[filled != spec.code]
            if len(bad):
                out.append(Finding("DOMAIN-VALUE", ERROR, f"DOMAIN should be \"{spec.code}\" on every record.",
                                   var.name, len(bad), _examples(bad)))

        if codelists and var.codelists:
            lists = [cl for cl in (by_submission_name(codelists, n) for n in var.codelists) if cl]
            if lists:
                allowed = set().union(*(cl.terms for cl in lists))
                bad = filled[~filled.isin(allowed)]
                if len(bad):
                    extensible = any(cl.extensible for cl in lists)
                    names = ", ".join(cl.submission_name for cl in lists)
                    out.append(Finding("CT", WARNING if extensible else ERROR,
                                       f"{var.name} has {len(bad)} value(s) not in the {names} codelist"
                                       + (" (extensible)." if extensible else "."),
                                       var.name, len(bad), _examples(bad),
                                       fix="Recode to the CDISC submission value; match case exactly."
                                           + (" New terms are allowed in extensible codelists but must be documented." if extensible else "")))
    return out


def check_keys(spec: DomainSpec, df: pd.DataFrame) -> list[Finding]:
    out: list[Finding] = []
    cols = {c.upper(): c for c in df.columns}
    if spec.code == "DM" and "USUBJID" in cols:
        dup = df[cols["USUBJID"]][df[cols["USUBJID"]].duplicated(keep=False)]
        if len(dup):
            out.append(Finding("DM-ONE-PER-SUBJECT", ERROR, f"DM must have one record per subject; {dup.nunique()} USUBJID value(s) repeat.",
                               "USUBJID", len(dup), _examples(dup)))
    seq = f"{spec.code}SEQ"
    if seq in cols and "USUBJID" in cols:
        dup = df[df.duplicated([cols["USUBJID"], cols[seq]], keep=False)]
        if len(dup):
            out.append(Finding("SEQ-UNIQUE", ERROR, f"{seq} is not unique within USUBJID ({len(dup)} records).", seq, len(dup),
                               _examples(dup[cols["USUBJID"]] + " / " + dup[cols[seq]].astype(str)),
                               fix=f"Derive {seq} after sorting, e.g. with BY USUBJID and a counter reset at FIRST.USUBJID."))
    st, en = f"{spec.code}STDTC", f"{spec.code}ENDTC"
    if st in cols and en in cols:
        s, e = df[cols[st]].map(_iso_to_date), df[cols[en]].map(_iso_to_date)
        mask = s.notna() & e.notna() & (s > e)
        if mask.any():
            out.append(Finding("START-AFTER-END", ERROR, f"{st} is after {en} on {int(mask.sum())} record(s).", st, int(mask.sum()),
                               _examples(df.loc[mask, cols["USUBJID"]] if "USUBJID" in cols else df.index[mask])))
    return out


def check_dm_rules(df: pd.DataFrame) -> list[Finding]:
    """A few DM-specific rules that trip people up."""
    out: list[Finding] = []
    c = {k.upper(): k for k in df.columns}

    def col(name):
        return df[c[name]] if name in c else None

    age, ageu = col("AGE"), col("AGEU")
    if age is not None and ageu is not None:
        bad = (~_blank(age) & _blank(ageu)).sum()
        if bad:
            out.append(Finding("DM-AGEU", ERROR, f"AGEU is empty on {bad} record(s) where AGE is filled.", "AGEU", int(bad)))
        bad = (_blank(age) & ~_blank(ageu)).sum()
        if bad:
            out.append(Finding("DM-AGEU", WARNING, f"AGEU is filled on {bad} record(s) where AGE is empty.", "AGEU", int(bad)))
    dthfl = col("DTHFL")
    if dthfl is not None:
        vals = dthfl[~_blank(dthfl)].astype(str).str.strip()
        bad = vals[vals != "Y"]
        if len(bad):
            out.append(Finding("DM-DTHFL", ERROR, "DTHFL must be \"Y\" or empty (never \"N\").", "DTHFL", len(bad), _examples(bad)))
        dthdtc = col("DTHDTC")
        if dthdtc is not None:
            bad = (~_blank(dthdtc) & _blank(dthfl)).sum()
            if bad:
                out.append(Finding("DM-DTHFL", ERROR, f"DTHDTC is filled but DTHFL is empty on {bad} record(s).", "DTHFL", int(bad)))
    armcd, armnrs = col("ARMCD"), col("ARMNRS")
    if armcd is not None:
        nrs_blank = _blank(armnrs) if armnrs is not None else pd.Series(True, index=df.index)
        bad = (_blank(armcd) & nrs_blank).sum()
        if bad:
            out.append(Finding("DM-ARMNRS", ERROR, f"ARMCD is empty on {bad} record(s) but ARMNRS gives no reason.", "ARMNRS", int(bad)))
        bad = (~_blank(armcd) & ~nrs_blank).sum()
        if bad:
            out.append(Finding("DM-ARMNRS", ERROR, f"ARMNRS is filled on {bad} record(s) that have an ARMCD.", "ARMNRS", int(bad)))
    rfst, rfx = col("RFSTDTC"), col("RFXSTDTC")
    if rfst is not None and rfx is not None:
        differ = (~_blank(rfst) & ~_blank(rfx) & (rfst.astype(str) != rfx.astype(str))).sum()
        if differ:
            out.append(Finding("DM-RFSTDTC", NOTICE, f"RFSTDTC differs from RFXSTDTC on {differ} record(s).", "RFSTDTC", int(differ),
                               fix="Fine if your reference start is not first dose (e.g. randomisation); document the rule."))
    return out


def check_ae_rules(df: pd.DataFrame) -> list[Finding]:
    out: list[Finding] = []
    c = {k.upper(): k for k in df.columns}
    if "AESER" not in c:
        return out
    criteria = [n for n in ("AESDTH", "AESHOSP", "AESLIFE", "AESDISAB", "AESCONG", "AESMIE", "AESCAN", "AESOD") if n in c]
    if not criteria:
        return out
    serious = (df[c["AESER"]].astype("string").str.strip() == "Y").fillna(False).astype(bool)
    any_y = pd.Series(False, index=df.index)
    for n in criteria:
        any_y |= (df[c[n]].astype("string").str.strip() == "Y").fillna(False).astype(bool)
    bad = serious & ~any_y
    if bad.any():
        out.append(Finding("AE-SERIOUS", WARNING, f"AESER is \"Y\" on {int(bad.sum())} record(s) with no seriousness criterion set to \"Y\".",
                           "AESER", int(bad.sum()),
                           _examples(df.loc[bad, c["USUBJID"]]) if "USUBJID" in c else [],
                           fix="Set the criterion that applies (" + ", ".join(criteria) + ")."))
    flagged = ~serious & any_y
    if flagged.any():
        out.append(Finding("AE-SERIOUS", ERROR, f"A seriousness criterion is \"Y\" on {int(flagged.sum())} record(s) where AESER is not \"Y\".",
                           "AESER", int(flagged.sum())))
    return out


def check_findings(spec: DomainSpec, df: pd.DataFrame) -> list[Finding]:
    """Result consistency for Findings domains."""
    out: list[Finding] = []
    c = {k.upper(): k for k in df.columns}
    p = spec.code

    def col(suffix):
        return df[c[p + suffix]] if p + suffix in c else None

    orres, stresc, stresn, stat = col("ORRES"), col("STRESC"), col("STRESN"), col("STAT")
    if orres is not None and stresc is not None:
        bad = (~_blank(orres) & _blank(stresc)).sum()
        if bad:
            out.append(Finding("STRESC-MISSING", ERROR, f"{p}STRESC is empty on {bad} record(s) that have {p}ORRES.", p + "STRESC", int(bad),
                               fix=f"Every collected result needs a standardised {p}STRESC."))
    if stresc is not None and stresn is not None:
        as_num = pd.to_numeric(stresc, errors="coerce")
        num = pd.to_numeric(stresn, errors="coerce")
        missing_n = (as_num.notna() & num.isna()).sum()
        if missing_n:
            out.append(Finding("STRESN-MISSING", ERROR, f"{p}STRESN is empty on {missing_n} record(s) where {p}STRESC is numeric.",
                               p + "STRESN", int(missing_n)))
        differ = (as_num.notna() & num.notna() & ((as_num - num).abs() > 1e-9)).sum()
        if differ:
            out.append(Finding("STRESN-DIFFERS", ERROR, f"{p}STRESN does not equal {p}STRESC on {differ} record(s).", p + "STRESN", int(differ)))
    if stat is not None and orres is not None:
        notdone = stat.astype("string").str.strip() == "NOT DONE"
        bad = (notdone.fillna(False) & ~_blank(orres)).sum()
        if bad:
            out.append(Finding("NOT-DONE-RESULT", ERROR, f"{p}ORRES has a value on {bad} record(s) marked {p}STAT = \"NOT DONE\".",
                               p + "ORRES", int(bad)))
    return out


def check_against_dm(spec: DomainSpec, df: pd.DataFrame, dm: pd.DataFrame) -> list[Finding]:
    """Cross-domain checks that need DM: subjects exist in DM, and study days match RFSTDTC."""
    out: list[Finding] = []
    c = {k.upper(): k for k in df.columns}
    d = {k.upper(): k for k in dm.columns}
    if "USUBJID" not in c or "USUBJID" not in d:
        return out
    known = set(dm[d["USUBJID"]].astype(str).str.strip())
    subj = df[c["USUBJID"]].astype(str).str.strip()
    orphans = subj[~subj.isin(known)]
    if spec.code != "DM" and len(orphans):
        out.append(Finding("USUBJID-NOT-IN-DM", ERROR, f"{orphans.nunique()} subject(s) are not in DM.", "USUBJID",
                           len(orphans), _examples(orphans), fix="Check the USUBJID rule is the same in every domain."))
    if "RFSTDTC" not in d:
        return out
    ref = dict(zip(dm[d["USUBJID"]].astype(str).str.strip(), dm[d["RFSTDTC"]]))
    for var in spec.variables:
        if not var.name.endswith("DY") or var.name not in c:
            continue
        dtc = var.name[:-2] + "DTC"
        if dtc not in c:
            continue
        dy = pd.to_numeric(df[c[var.name]], errors="coerce")
        zero = (dy == 0).sum()
        if zero:
            out.append(Finding("DY-ZERO", ERROR, f"{var.name} is 0 on {zero} record(s); there is no study day 0.", var.name, int(zero)))
        expected = [study_day(x, ref.get(u)) for x, u in zip(df[c[dtc]], subj)]
        wrong = [(u, int(a), e) for u, a, e in zip(subj, dy, expected) if e is not None and pd.notna(a) and int(a) != e]
        if wrong:
            out.append(Finding("DY-CALC", ERROR, f"{var.name} does not match {dtc} and DM.RFSTDTC on {len(wrong)} record(s).",
                               var.name, len(wrong), [f"{u}: {a}, expected {e}" for u, a, e in wrong[:3]],
                               fix="Study day = date - RFSTDTC + 1 on or after RFSTDTC, date - RFSTDTC before it."))
    return out


def run_checks(spec: DomainSpec, df: pd.DataFrame, info: TableInfo | None = None,
               codelists: dict[str, Codelist] | None = None, dm: pd.DataFrame | None = None) -> CheckReport:
    findings = check_structure(spec, info, df) + check_values(spec, df, codelists) + check_keys(spec, df)
    if spec.code == "DM":
        findings += check_dm_rules(df)
    if spec.code == "AE":
        findings += check_ae_rules(df)
    if spec.klass.startswith("Findings"):
        findings += check_findings(spec, df)
    if spec.code == "DM":
        dm = df if dm is None else dm
    if dm is not None:
        findings += check_against_dm(spec, df, dm)
    if codelists is None:
        findings.append(Finding("CT-SKIPPED", NOTICE, "Controlled terminology not checked: run 'sdtm-helper fetch-ct' first."))
    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.check, f.variable))
    return CheckReport(spec.code, len(df), findings)


def format_report(report: CheckReport) -> str:
    lines = [f"P21-lite checks for {report.domain} ({report.nobs} records)",
             f"{len(report.by_severity(ERROR))} error(s), {len(report.by_severity(WARNING))} warning(s), "
             f"{len(report.by_severity(NOTICE))} notice(s)", ""]
    for f in report.findings:
        lines.append(f"[{f.severity}] {f.check}: {f.message}")
        if f.examples:
            lines.append("    e.g. " + "; ".join(f.examples))
        if f.fix:
            lines.append("    Fix: " + f.fix)
    if report.passed:
        lines.append("\nNo errors. Ready to export to XPT; run Pinnacle 21 for full validation.")
    return "\n".join(lines)
