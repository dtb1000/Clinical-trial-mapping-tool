"""A stand-in for saspy.SASsession backed by pandas DataFrames, for tests and screenshots."""

import pandas as pd


class _Data:
    def __init__(self, df):
        self._df = df

    def to_df(self):
        return self._df


class FakeSASsession:
    sasver = "9.04.01M7 (fake)"

    def __init__(self, tables: dict[str, pd.DataFrame], lengths: dict[str, int] | None = None):
        self.tables = {k.upper(): v for k, v in tables.items()}   # "FINAL.DM" -> DataFrame
        self.submitted: list[str] = []
        self._missing = None

    def submit(self, code):
        self.submitted.append(code)
        if "_sdtmh_missing" in code:
            lib_table = code.split(" from ")[-1].split(";")[0].strip().upper()
            df = self.tables[lib_table]
            self._missing = pd.DataFrame([{c: int(df[c].isna().sum() + (df[c].astype(str).str.strip() == "").sum())
                                           for c in df.columns}])
        return {"LOG": "NOTE: The SAS System used:\n" + "\n".join(f"  {l}" for l in code.splitlines()[:3])}

    def sasdata(self, table, libref, dsopts=None):
        table, libref = table.upper(), libref.upper()
        where = (dsopts or {}).get("where", "")
        if (libref, table) == ("WORK", "_SDTMH_MISSING"):
            return _Data(self._missing)
        if libref == "SASHELP" and table == "VLIBNAM":
            return _Data(pd.DataFrame({"libname": sorted({k.split(".")[0] for k in self.tables})}))
        if libref == "SASHELP" and table in ("VTABLE", "VCOLUMN"):
            lib = where.split("libname='")[1].split("'")[0]
            mem = where.split("memname='")[1].split("'")[0] if "memname=" in where else None
            if table == "VTABLE":
                rows = [{"memname": k.split(".")[1], "nobs": len(v)} for k, v in self.tables.items()
                        if k.split(".")[0] == lib and (mem is None or k.split(".")[1] == mem)]
                return _Data(pd.DataFrame(rows, columns=["memname", "nobs"]))
            df = self.tables.get(f"{lib}.{mem}")
            rows = [] if df is None else [
                {"name": c, "type": "num" if pd.api.types.is_numeric_dtype(df[c]) else "char",
                 "length": 8 if pd.api.types.is_numeric_dtype(df[c]) else int(max(1, df[c].astype(str).str.len().max())),
                 "label": "", "format": "", "varnum": i + 1} for i, c in enumerate(df.columns)]
            return _Data(pd.DataFrame(rows, columns=["name", "type", "length", "label", "format", "varnum"]))
        return _Data(self.tables[f"{libref}.{table}"])

    def endsas(self):
        pass
