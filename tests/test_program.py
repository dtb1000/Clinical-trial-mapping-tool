"""Reading the user's SAS program to follow the step under the cursor, and the sandboxed copy."""
import pandas as pd

from fake_sas import FakeSASsession
from sdtm_helper.app.follow import follow
from sdtm_helper.sas import program as sp
from sdtm_helper.sas.session import SasConnection

PROGRAM = """libname raw "~/lorna";
/* DM: demographics */
data final.dm(keep=studyid usubjid sex country);
  set raw.dm(where=(age > 18) rename=(gender=sexc));
  studyid = "LORNA";
  usubjid = catx("-", studyid, subjid);
  if sexc = "Male" then sex = "M";
  else sex = "F";
  if country = 'X' then delete;
run;

proc sql;
  create table work.ae as
  select a.subjid, a.aeterm as AETERM_RAW, upcase(a.aeterm) as AEDECOD length=200, d.rfstdtc
  from raw.ae a left join final.dm as d on a.subjid = d.subjid
  where a.aeser = 'Y'
  order by a.subjid;
  select * from raw.vs;
quit;
"""


def at(text):
    return PROGRAM.index(text)


def test_steps_and_cursor():
    kinds = [s.kind for s in sp.steps(PROGRAM)]
    assert kinds == ["global", "data", "sql"]
    assert sp.step_at(PROGRAM, at("studyid =")).kind == "data"
    assert sp.step_at(PROGRAM, at("run;") + 5).kind == "data"      # blank line after run; still that step
    assert sp.step_at(PROGRAM, at("libname")).kind == "global"


def test_data_step_plan():
    step = sp.step_at(PROGRAM, at("studyid ="))
    plan = sp.analyse(PROGRAM, step)
    assert plan.title == "DATA step making final.dm"
    assert [r.name for r in plan.inputs] == ["raw.dm"]
    assert plan.rename == {"GENDER": "SEXC"}
    assert "age > 18" in plan.filters and "not (country = 'X')" in plan.filters
    assert plan.assigned["USUBJID"] == 'catx("-", studyid, subjid)'
    assert plan.assigned["SEX"] == '"M"'
    assert {"SUBJID", "SEXC", "STUDYID"} <= plan.used_cols
    assert "CATX" not in plan.used_cols


def test_data_step_sandbox_reads_work_copies_only():
    step = sp.step_at(PROGRAM, at("studyid ="))
    code = sp.sandbox(PROGRAM, step, sp.analyse(PROGRAM, step), rows=50)
    assert "set raw.dm(obs=50); _sdtmh_r1 = _n_;" in code
    assert "data work._sdtmh_out1(keep=_sdtmh_r1 studyid" in code
    assert "set work._sdtmh_in1(where=(age > 18)" in code
    assert "final.dm" not in code.lower()          # the user's table is never written
    assert code.rstrip().endswith("run;")


def test_sql_plan_and_sandbox():
    step = sp.step_at(PROGRAM, at("upcase"))
    plan = sp.analyse(PROGRAM, step, at("upcase"))
    assert [(r.name, r.alias) for r in plan.inputs] == [("raw.ae", "a"), ("final.dm", "d")]
    assert plan.rename == {"AETERM": "AETERM_RAW"}
    assert plan.assigned == {"AEDECOD": "upcase(a.aeterm)"}
    assert plan.filters == ["a.aeser = 'Y'"] and plan.join_cols == {"SUBJID"}
    code = sp.sandbox(PROGRAM, step, plan)
    assert ", a._sdtmh_r1, d._sdtmh_r2 from work._sdtmh_in1 a left join work._sdtmh_in2 as d" in code
    assert "create table work._sdtmh_out1 as" in code and "select * from raw.vs" not in code


def test_plain_select_gets_an_alias_and_output():
    pos = at("raw.vs")
    step = sp.step_at(PROGRAM, pos)
    code = sp.sandbox(PROGRAM, step, sp.analyse(PROGRAM, step, pos))
    assert "create table work._sdtmh_out1 as select * from work._sdtmh_in1 as VS;" in code


def test_half_typed_and_unsafe_steps():
    plan = sp.analyse("data x; set raw.dm(where=(age", sp.steps("data x; set raw.dm(where=(age")[0])
    assert [r.name for r in plan.inputs] == ["raw.dm"]
    unsafe = "data _null_; set raw.dm; call execute('proc delete data=raw.dm; run;'); run;"
    assert sp.analyse(unsafe, sp.steps(unsafe)[0]).problem
    for sql in ("proc sql; select max(age) into :maxage from raw.dm; quit;",
                "proc sql; create table x as select * from dictionary.columns; quit;",
                "proc sql; create table x as select a from raw.a union select a from raw.b; quit;"):
        assert sp.analyse(sql, sp.steps(sql)[0], 12).problem, sql
    proc = "proc sort data=raw.dm; by subjid; run;"
    assert sp.analyse(proc, sp.steps(proc)[0]).problem


def test_follow_marks_rows_and_columns():
    raw = pd.DataFrame({"SUBJID": ["001", "002", "003"], "GENDER": ["Male", "Female", "Male"],
                        "AGE": [30.0, 12.0, 45.0], "COUNTRY": ["PL", "PL", "X"]})
    view = raw.assign(_sdtmh_r1=[1.0, 2.0, 3.0])
    out = pd.DataFrame({"STUDYID": ["LORNA"], "USUBJID": ["LORNA-001"], "SEX": ["M"], "COUNTRY": ["PL"],
                        "_sdtmh_r1": [1.0]})
    fake = FakeSASsession({"RAW.DM": raw, "WORK._SDTMH_IN1": view, "WORK._SDTMH_OUT1": out})
    res = follow(SasConnection(session=fake), PROGRAM, at("studyid ="))
    assert not res.message, res.message
    src, made = res.tables
    assert src.name == "raw.dm" and src.kept_rows == {0}
    assert src.status["GENDER"] == "drop" and "→ SEXC" in src.words["GENDER"] and src.status["AGE"] == "drop" and src.status["COUNTRY"] == "keep"
    assert "where" in src.words["AGE"] and "used" in src.words["GENDER"]
    assert src.new_columns == ["STUDYID", "USUBJID", "SEX"]
    assert src.formulas["USUBJID"] == 'catx("-", studyid, subjid)'
    assert src.rows["USUBJID"][0] == "LORNA-001" and src.rows["USUBJID"][1:].isna().all()
    assert "keeps 1 of 3 rows" in "".join(t for t, _ in src.summary)
    assert made.role == "output" and list(made.rows.columns) == ["STUDYID", "USUBJID", "SEX", "COUNTRY"]
    assert not any("final.dm" in c.lower() for c in fake.submitted)


def test_follow_says_when_an_input_is_missing():
    fake = FakeSASsession({"RAW.AE": pd.DataFrame({"SUBJID": ["1"]})})
    res = follow(SasConnection(session=fake), PROGRAM, at("upcase"))
    assert "FINAL.DM doesn't exist yet" in res.message and not fake.submitted
