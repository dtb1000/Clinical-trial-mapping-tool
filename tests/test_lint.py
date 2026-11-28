"""The quick check behind the squiggly underlines, SAS log messages, and the function lookup."""
from sdtm_helper.sas import functions, lint

BROKEN = """data work.dm;
  set raw.dm
  STUDYID = "LORNA";
  DOMAIN = "DM"
  USUBJID = catz("-", STUDYID, SUBJID);
  if SEX == "Male" then do;
    SEX = "M";
  if (AGE > 18 then AGEU = "YEARS";
run;
"""

CLEAN = """libname raw "~/lorna";
%let study = LORNA;
data work.dm(keep=STUDYID USUBJID SEX);
  length STUDYID $5 USUBJID $20;
  set raw.dm(where=(age > 18)) end=last;
  by subjid;
  STUDYID = "&study";
  USUBJID = catx("-", STUDYID, SITEID,
                 SUBJID);
  if upcase(SEX) in ("WOMAN", "FEMALE") then
    SEX = "F";
  else if missing(SEX) then do;
    SEX = "U";
  end;
  call missing(AGEU);
  rfstdtc = put(input(RAWDATE, yymmdd10.), e8601da.);
run;

proc sql;
  create table work.ae as
  select a.*, d.RFSTDTC, count(*) as N
  from raw.ae(where=(aeser = 'Y')) as a left join work.dm as d
  on a.subjid = d.subjid
  where a.aeterm ne ''
  group by a.subjid;
quit;
"""


def messages(text):
    return {(p.line + 1, p.message.split("?")[0].split(".")[0]) for p in lint.check(text)}


def test_clean_program_has_no_problems():
    assert lint.check(CLEAN) == []


def test_broken_program():
    found = {(p.line + 1, p.severity, p.message) for p in lint.check(BROKEN)}
    text = "\n".join(f"{line} {sev} {msg}" for line, sev, msg in sorted(found))
    assert "2 error Missing semicolon?" in text            # set raw.dm  (next line is an assignment)
    assert "4 error Missing semicolon?" in text            # DOMAIN = "DM"
    assert "5 warning catz isn't a SAS function. Did you mean CATS, CATT or CATX?" in text
    assert "6 error SAS compares with = or EQ, not ==." in text
    assert "6 error This DO has no END." in text
    assert "8 error This ( isn't closed before the end of the statement." in text


def test_unclosed_quote_comment_and_last_step():
    assert any("never closed" in p.message for p in lint.check("data x;\n  a = 'it's here';\nrun;"))
    assert any("comment is never closed" in p.message for p in lint.check("/* start\ndata x; run;"))
    last = lint.check("data x;\n  set y;\n")
    assert last and "no RUN;" in last[0].message and last[0].severity == lint.WARNING
    assert any("no QUIT;" in p.message for p in lint.check("proc sql;\n  create table x as select * from y;\n"))


def test_set_options_and_macro_calls_are_fine():
    assert lint.check("data x;\n  set y\n    end=eof nobs=n;\nrun;") == []
    assert lint.check("data ts;\n  %rec(A, 1)\n  %rec(B, 2)\nrun;") == []


LOG = """1          data work.dm;
2            set raw.dm;
3            USUBJID = catx("-" STUDYID, SUBJID);
                                ________
                                22
ERROR 22-322: Syntax error, expecting one of the following: !, !!, &, *, **, +, ',', -, /.
4            AGEU = "YEARS";
5          run;
NOTE: Variable SUBJID is uninitialized.
NOTE: The SAS System stopped processing this step because of errors.
"""
CODE = """data work.dm;
  set raw.dm;
  USUBJID = catx("-" STUDYID, SUBJID);
  AGEU = "YEARS";
run;"""


def test_sas_log_messages_land_on_the_right_place():
    problems = lint.from_log(LOG, CODE, start_line=10)
    syntax, uninit = problems
    assert (syntax.line, syntax.col, syntax.length, syntax.severity) == (12, 21, 8, lint.ERROR)
    assert CODE.split("\n")[2][21:28] == "STUDYID"
    assert syntax.message.startswith("Syntax error") and syntax.source == "SAS"
    assert (uninit.line, uninit.severity) == (12, lint.WARNING) and "SUBJID" in uninit.message


def test_sandbox_lines_are_ignored():
    log = "1    data work._sdtmh_in1 / view=work._sdtmh_in1;\nERROR: File WORK._SDTMH_IN1.DATA does not exist.\n"
    assert lint.from_log(log, "data x; set y; run;") == []


def test_function_lookup():
    catx = functions.find("catx")
    assert catx.syntax.startswith("CATX(delimiter") and "USUBJID" in catx.sdtm
    assert "SAS+Help+Center" in catx.doc_url and "CATX+Function" in catx.doc_url
    assert functions.find("call missing").doc_url.endswith("CALL+MISSING+Routine%22+9.4")
    assert functions.find("%sysfunc").name == "%SYSFUNC"
    assert [f.name for f in functions.search("intc")][:1] == ["INTCK"]
    assert any(f.name == "YRDIF" for f in functions.search("date"))
    assert functions.is_known("VERIFY") and not functions.is_known("CATZ")
    assert functions.closest("UPCSE") == ["UPCASE"]
    assert functions.closest("RFSTDTC") == []
