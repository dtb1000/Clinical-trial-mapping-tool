"""A thin wrapper around SASPy.

The app only reads from SAS here: it lists libraries and tables and describes
a table's variables so it can compare them against SDTMIG. The user's own SAS
code is submitted unchanged (Follow my code runs a copy of one step with only its table
names pointed at WORK, see sas/program.py); the app never generates mapping code.
"""

from __future__ import annotations

import functools
import threading
from dataclasses import dataclass, field
from pathlib import Path


def _locked(method):
    """One SAS call at a time: the window follows your code in the background while you run it."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


@dataclass
class ColumnInfo:
    name: str
    type: str          # "char" or "num"
    length: int
    label: str = ""
    format: str = ""


@dataclass
class TableInfo:
    libref: str
    name: str
    nobs: int
    columns: list[ColumnInfo] = field(default_factory=list)

    def column(self, name: str) -> ColumnInfo | None:
        name = name.upper()
        return next((c for c in self.columns if c.name.upper() == name), None)


class SasConnection:
    """Open one SAS session through SASPy and answer questions about its data."""

    def __init__(self, cfgname: str = "oda", cfgfile: str | None = None, session=None, **login):
        """login may hold omruser/omrpw for ODA, so the app can ask for the password instead of a file."""
        self._lock = threading.RLock()
        if session is not None:          # used by tests
            self._sas = session
            return
        import saspy  # imported here so the rest of the app works without SAS

        if cfgfile is None:
            from ..paths import app_home
            candidates = [Path(__file__).resolve().parents[3] / "config" / "sascfg_personal.py",
                          app_home() / "sascfg_personal.py"]
            cfgfile = next((str(p) for p in candidates if p.exists()), None)
        login = {k: v for k, v in login.items() if v}
        self._sas = saspy.SASsession(cfgname=cfgname, cfgfile=cfgfile, **login)

    # -- running the user's own code ---------------------------------------
    @_locked
    def submit(self, code: str) -> str:
        """Submit the user's own SAS code unchanged and return the log."""
        return self._sas.submit(code).get("LOG", "")

    @_locked
    def run_file(self, path: str | Path) -> str:
        """Submit a SAS program the user wrote (for example their libname file). Returns the log."""
        code = Path(path).read_text(encoding="utf-8")
        result = self._sas.submit(code)
        return result.get("LOG", "")

    # -- reading metadata ---------------------------------------------------
    @property
    def version(self) -> str:
        return str(getattr(self._sas, "sasver", "unknown"))

    @_locked
    def list_libraries(self) -> list[str]:
        df = self._sas.sasdata("vlibnam", "sashelp").to_df()
        return sorted({str(v).strip().upper() for v in df["libname"]})

    @_locked
    def list_tables(self, libref: str) -> list[str]:
        libref = _safe_name(libref)
        df = self._sas.sasdata(
            "vtable", "sashelp", dsopts={"where": f"libname='{libref}'"}
        ).to_df()
        return sorted(str(v).strip().upper() for v in df["memname"])

    @_locked
    def describe(self, libref: str, table: str) -> TableInfo:
        libref, table = _safe_name(libref), _safe_name(table)
        where = f"libname='{libref}' and memname='{table}'"
        cols = self._sas.sasdata("vcolumn", "sashelp", dsopts={"where": where}).to_df()
        tab = self._sas.sasdata("vtable", "sashelp", dsopts={"where": where}).to_df()
        if tab.empty:
            raise LookupError(f"{libref}.{table} was not found in the SAS session")
        nobs = int(tab["nobs"].iloc[0])
        columns = [
            ColumnInfo(
                name=str(r["name"]).strip(),
                type=str(r["type"]).strip(),
                length=int(r["length"]),
                label=_text(r.get("label")),
                format=_text(r.get("format")),
            )
            for _, r in cols.sort_values("varnum").iterrows()
        ]
        return TableInfo(libref=libref, name=table, nobs=nobs, columns=columns)

    @_locked
    def fetch(self, libref: str, table: str, obs: int | None = None):
        """Read a table (or its first `obs` rows) into a pandas DataFrame (read-only)."""
        libref, table = _safe_name(libref), _safe_name(table)
        dsopts = {"obs": int(obs)} if obs else None
        return self._sas.sasdata(table, libref, dsopts=dsopts).to_df()

    @_locked
    def missing_counts(self, libref: str, table: str, variables: list[str]) -> dict[str, int]:
        """Count empty values per variable, so the checklist can say what still needs filling.

        This is read-only: it creates one small summary table in WORK and reads it back.
        """
        libref, table = _safe_name(libref), _safe_name(table)
        names = [_safe_name(v) for v in variables]
        if not names:
            return {}
        sums = ",\n    ".join(f"sum(missing({n})) as {n}" for n in names)
        log = self._sas.submit(
            f"proc sql;\n  create table work._sdtmh_missing as\n  select\n    {sums}\n"
            f"  from {libref}.{table};\nquit;"
        )
        df = self._sas.sasdata("_sdtmh_missing", "work").to_df()
        if df is None or df.empty:
            raise RuntimeError("Could not count missing values. SAS log:\n" + log.get("LOG", ""))
        row = df.iloc[0]
        return {n: int(row[n] or 0) for n in names}

    @_locked
    def close(self) -> None:
        self._sas.endsas()


def _safe_name(name: str) -> str:
    """SAS names are letters, digits and underscores; reject anything else before it reaches a WHERE clause."""
    cleaned = name.strip().upper()
    if not cleaned or not all(ch.isalnum() or ch == "_" for ch in cleaned):
        raise ValueError(f"Not a valid SAS name: {name!r}")
    return cleaned


def _text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text
