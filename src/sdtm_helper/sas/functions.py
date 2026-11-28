"""SAS functions and CALL routines: a short summary of the common ones, and a link to SAS's own documentation.

The summaries are short and written for this app; the SAS documentation is the reference.
NAMES also lists many other SAS function names, so the editor can tell a misspelt function
(CATZ for CATX) from a real one it has no summary for.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from urllib.parse import quote_plus

# SAS's Help Center has no URL that opens a function page by name, so the app opens a web
# search for the Help Center page (the approach SAS's own blog recommends), plus the reference's
# front page.
REFERENCE_URL = "https://documentation.sas.com/doc/en/lefunctionsref/9.4/titlepage.htm"


@dataclass(frozen=True)
class SasFunction:
    name: str
    syntax: str
    category: str
    summary: str
    sdtm: str = ""        # where it helps in SDTM mapping

    @property
    def is_call(self) -> bool:
        return self.name.startswith("CALL ")

    @property
    def doc_url(self) -> str:
        kind = "Routine" if self.is_call else "Function"
        return doc_url(self.name, kind)


def doc_url(name: str, kind: str = "Function") -> str:
    return "https://www.google.com/search?q=" + quote_plus(f'"SAS Help Center" "{name.upper()} {kind}" 9.4')


F = SasFunction
_LIST = [
    # character
    F("CAT", "CAT(item-1 <, ..., item-n>)", "Character", "Joins values without removing any blanks."),
    F("CATS", "CATS(item-1 <, ..., item-n>)", "Character", "Joins values after removing leading and trailing blanks."),
    F("CATT", "CATT(item-1 <, ..., item-n>)", "Character", "Joins values after removing trailing blanks."),
    F("CATX", "CATX(delimiter, item-1 <, ..., item-n>)", "Character",
      "Strips each value, then joins the non-missing ones with a delimiter between them.",
      'USUBJID = catx("-", STUDYID, SITEID, SUBJID) is the usual pattern.'),
    F("COMPRESS", "COMPRESS(source <, characters> <, modifiers>)", "Character",
      "Removes characters from a string: blanks by default, or the characters and classes you list (modifiers such as 'd' for digits, 'a' for letters, 'k' to keep instead)."),
    F("COMPBL", "COMPBL(source)", "Character", "Turns runs of blanks into a single blank."),
    F("STRIP", "STRIP(string)", "Character", "Removes leading and trailing blanks."),
    F("TRIM", "TRIM(string)", "Character", "Removes trailing blanks."),
    F("TRIMN", "TRIMN(string)", "Character", "Removes trailing blanks; returns an empty string for an all-blank value."),
    F("LEFT", "LEFT(string)", "Character", "Moves leading blanks to the end, so the text starts at the left."),
    F("RIGHT", "RIGHT(string)", "Character", "Moves trailing blanks to the start, so the text ends at the right."),
    F("UPCASE", "UPCASE(string)", "Character", "Converts letters to upper case.",
      "Controlled terminology submission values are mostly upper case, e.g. SEX, RACE."),
    F("LOWCASE", "LOWCASE(string)", "Character", "Converts letters to lower case."),
    F("PROPCASE", "PROPCASE(string <, delimiters>)", "Character", "Capitalises the first letter of each word."),
    F("SUBSTR", "SUBSTR(string, position <, length>)", "Character",
      "Extracts part of a string. On the left of = it replaces characters in place instead.",
      "Handy for partial ISO 8601 dates, e.g. the year part of a date."),
    F("SUBSTRN", "SUBSTRN(string, position <, length>)", "Character",
      "Like SUBSTR, but returns an empty string instead of a note when the position is out of range."),
    F("SCAN", "SCAN(string, n <, delimiters> <, modifiers>)", "Character",
      "Returns the nth word. A negative n counts from the end."),
    F("INDEX", "INDEX(source, excerpt)", "Character", "Position of the first occurrence of a string, or 0."),
    F("INDEXC", "INDEXC(source, characters)", "Character", "Position of the first of any of the listed characters, or 0."),
    F("INDEXW", "INDEXW(source, word <, delimiters>)", "Character", "Position of a whole word, or 0."),
    F("FIND", "FIND(string, substring <, modifiers> <, start>)", "Character",
      "Position of a substring, or 0. The 'i' modifier ignores case."),
    F("FINDW", "FINDW(string, word <, delimiters> <, modifiers> <, start>)", "Character", "Position of a whole word, or 0."),
    F("FINDC", "FINDC(string, characters <, modifiers> <, start>)", "Character", "Position of the first of any listed characters."),
    F("LENGTH", "LENGTH(string)", "Character", "Length without trailing blanks; 1 for a blank value."),
    F("LENGTHN", "LENGTHN(string)", "Character", "Length without trailing blanks; 0 for a blank value."),
    F("LENGTHC", "LENGTHC(string)", "Character", "Length including trailing blanks."),
    F("TRANWRD", "TRANWRD(source, target, replacement)", "Character", "Replaces every occurrence of a word or phrase."),
    F("TRANSLATE", "TRANSLATE(source, to-1, from-1 <, ...>)", "Character", "Replaces single characters (note: 'to' comes before 'from')."),
    F("TRANSTRN", "TRANSTRN(source, target, replacement)", "Character", "Like TRANWRD, but the replacement can be empty."),
    F("REVERSE", "REVERSE(string)", "Character", "Reverses the characters."),
    F("REPEAT", "REPEAT(string, n)", "Character", "Repeats a string n more times."),
    F("COUNTW", "COUNTW(string <, delimiters> <, modifiers>)", "Character", "Counts the words in a string."),
    F("COUNTC", "COUNTC(string, characters <, modifiers>)", "Character", "Counts the listed characters."),
    F("COUNT", "COUNT(string, substring <, modifiers>)", "Character", "Counts occurrences of a substring."),
    F("ANYDIGIT", "ANYDIGIT(string <, start>)", "Character", "Position of the first digit, or 0."),
    F("ANYALPHA", "ANYALPHA(string <, start>)", "Character", "Position of the first letter, or 0."),
    F("NOTDIGIT", "NOTDIGIT(string <, start>)", "Character", "Position of the first character that isn't a digit, or 0."),
    F("COALESCEC", "COALESCEC(value-1 <, ..., value-n>)", "Character", "First non-missing character value.",
      "e.g. an end date that falls back to the start date."),
    F("PRXMATCH", "PRXMATCH(regex, source)", "Character", "Position of the first match of a Perl regular expression, or 0."),
    F("PRXCHANGE", "PRXCHANGE(regex, times, source)", "Character", "Replaces text that matches a Perl regular expression ('s/old/new/')."),
    F("PRXPARSE", "PRXPARSE(regex)", "Character", "Compiles a Perl regular expression for the other PRX functions."),
    F("QUOTE", "QUOTE(string <, character>)", "Character", "Adds quotation marks around a value."),
    F("DEQUOTE", "DEQUOTE(string)", "Character", "Removes matching quotation marks."),
    F("CHAR", "CHAR(string, position)", "Character", "The single character at a position."),
    F("FIRST", "FIRST(string)", "Character", "The first character."),
    # missing values
    F("MISSING", "MISSING(value)", "Missing values", "1 if the value (character or numeric) is missing, else 0.",
      "Works for both types, so it is safer than comparing with . or ''."),
    F("CMISS", "CMISS(value-1 <, ..., value-n>)", "Missing values", "Counts missing values of either type."),
    F("NMISS", "NMISS(value-1 <, ..., value-n>)", "Missing values", "Counts missing numeric values."),
    F("COALESCE", "COALESCE(value-1 <, ..., value-n>)", "Missing values", "First non-missing numeric value."),
    F("CALL MISSING", "CALL MISSING(variable-1 <, ..., variable-n>)", "Missing values", "Sets variables of either type to missing."),
    # conversion
    F("PUT", "PUT(source, format.)", "Conversion", "Writes a value with a format and returns text.",
      "put(BRTHDT, e8601da.) turns a SAS date into ISO 8601 text (YYYY-MM-DD)."),
    F("PUTN", "PUTN(value, format)", "Conversion", "Like PUT, with the format given as a value, so it can vary by row."),
    F("PUTC", "PUTC(value, format)", "Conversion", "Character version of PUTN."),
    F("INPUT", "INPUT(source, informat.)", "Conversion", "Reads text with an informat and returns a value.",
      "input(RAWDATE, yymmdd10.) reads text into a SAS date; input(AGEC, best.) reads a number."),
    F("INPUTN", "INPUTN(source, informat)", "Conversion", "Like INPUT, with the informat given as a value."),
    F("INPUTC", "INPUTC(source, informat)", "Conversion", "Character version of INPUTN."),
    F("VVALUE", "VVALUE(variable)", "Conversion", "The formatted value of a variable."),
    # dates and times
    F("MDY", "MDY(month, day, year)", "Date and time", "Builds a SAS date from month, day and year."),
    F("DHMS", "DHMS(date, hour, minute, second)", "Date and time", "Builds a SAS datetime from a date and a time."),
    F("HMS", "HMS(hour, minute, second)", "Date and time", "Builds a SAS time."),
    F("TODAY", "TODAY()", "Date and time", "Today's date as a SAS date. DATE() is the same."),
    F("DATE", "DATE()", "Date and time", "Today's date as a SAS date."),
    F("DATETIME", "DATETIME()", "Date and time", "The current date and time as a SAS datetime."),
    F("TIME", "TIME()", "Date and time", "The current time of day."),
    F("DATEPART", "DATEPART(datetime)", "Date and time", "The date part of a SAS datetime."),
    F("TIMEPART", "TIMEPART(datetime)", "Date and time", "The time part of a SAS datetime."),
    F("YEAR", "YEAR(date)", "Date and time", "The year of a SAS date."),
    F("MONTH", "MONTH(date)", "Date and time", "The month (1 to 12) of a SAS date."),
    F("DAY", "DAY(date)", "Date and time", "The day of the month of a SAS date."),
    F("WEEKDAY", "WEEKDAY(date)", "Date and time", "Day of the week, 1 = Sunday."),
    F("QTR", "QTR(date)", "Date and time", "The quarter (1 to 4) of a SAS date."),
    F("HOUR", "HOUR(time or datetime)", "Date and time", "The hour."),
    F("MINUTE", "MINUTE(time or datetime)", "Date and time", "The minute."),
    F("SECOND", "SECOND(time or datetime)", "Date and time", "The second."),
    F("INTCK", "INTCK(interval, start, end <, method>)", "Date and time",
      "Counts interval boundaries between two dates ('year', 'month', 'day' ...). Use method 'c' for whole completed intervals.",
      "For AGE, intck('year', BRTHDT, RFSTDT, 'c') gives completed years."),
    F("INTNX", "INTNX(interval, start, increment <, alignment>)", "Date and time", "Moves a date by a number of intervals."),
    F("YRDIF", "YRDIF(start, end <, basis>)", "Date and time", "Difference in years, with fractions. Basis 'AGE' gives age."),
    F("DATDIF", "DATDIF(start, end, basis)", "Date and time", "Difference in days with a day-count basis such as 'ACT/ACT'."),
    F("ANYDTDTE", "INPUT(source, ANYDTDTE.)", "Date and time",
      "An informat, not a function: reads dates written in many layouts. Check the results, it can guess the order wrongly."),
    # numbers
    F("SUM", "SUM(value-1 <, ..., value-n>)", "Numeric", "Sum of the non-missing values (missing only if all are missing)."),
    F("MEAN", "MEAN(value-1 <, ..., value-n>)", "Numeric", "Mean of the non-missing values."),
    F("MIN", "MIN(value-1 <, ..., value-n>)", "Numeric", "Smallest non-missing value. In PROC SQL with one argument it summarises a column."),
    F("MAX", "MAX(value-1 <, ..., value-n>)", "Numeric", "Largest non-missing value. In PROC SQL with one argument it summarises a column."),
    F("N", "N(value-1 <, ..., value-n>)", "Numeric", "Counts the non-missing numeric values."),
    F("ROUND", "ROUND(value <, unit>)", "Numeric", "Rounds to the nearest unit (1 by default, e.g. 0.01 for two decimals)."),
    F("INT", "INT(value)", "Numeric", "The integer part (drops the fraction)."),
    F("FLOOR", "FLOOR(value)", "Numeric", "Largest integer not above the value."),
    F("CEIL", "CEIL(value)", "Numeric", "Smallest integer not below the value."),
    F("ABS", "ABS(value)", "Numeric", "Absolute value."),
    F("MOD", "MOD(value, divisor)", "Numeric", "Remainder of a division."),
    F("SQRT", "SQRT(value)", "Numeric", "Square root."),
    F("LOG", "LOG(value)", "Numeric", "Natural logarithm."),
    F("LOG10", "LOG10(value)", "Numeric", "Base-10 logarithm."),
    F("EXP", "EXP(value)", "Numeric", "e raised to a power."),
    F("STD", "STD(value-1, value-2 <, ...>)", "Numeric", "Standard deviation of the non-missing values."),
    F("RANUNI", "RANUNI(seed)", "Numeric", "A random number between 0 and 1 (RAND('uniform') is the newer form)."),
    F("RAND", "RAND(distribution <, parameters>)", "Numeric", "A random number from a distribution, e.g. RAND('uniform')."),
    F("IFN", "IFN(condition, value-if-true, value-if-false <, value-if-missing>)", "Numeric", "Picks one of two numbers by a condition."),
    F("IFC", "IFC(condition, text-if-true, text-if-false <, text-if-missing>)", "Character", "Picks one of two texts by a condition."),
    F("WHICHC", "WHICHC(value, item-1 <, ..., item-n>)", "Character", "Position of the first item equal to the value, or 0."),
    F("WHICHN", "WHICHN(value, item-1 <, ..., item-n>)", "Numeric", "Numeric version of WHICHC."),
    # data step helpers
    F("LAG", "LAG<n>(value)", "Data step", "The value from the previous call (not necessarily the previous row, if called conditionally)."),
    F("DIF", "DIF<n>(value)", "Data step", "Value minus its LAG."),
    F("SYMGET", "SYMGET(macro-variable-name)", "Macro", "The value of a macro variable while the step runs."),
    F("CALL SYMPUTX", "CALL SYMPUTX(macro-variable, value <, scope>)", "Macro", "Stores a value in a macro variable, stripped of blanks."),
    F("CALL SYMPUT", "CALL SYMPUT(macro-variable, value)", "Macro", "Stores a value in a macro variable."),
    F("CALL SORTC", "CALL SORTC(variable-1 <, ..., variable-n>)", "Data step", "Sorts the values of character variables within a row."),
    F("CALL SORTN", "CALL SORTN(variable-1 <, ..., variable-n>)", "Data step", "Sorts the values of numeric variables within a row."),
    F("DIM", "DIM(array)", "Data step", "The number of elements in an array."),
    F("VNAME", "VNAME(variable)", "Data step", "The name of a variable, e.g. of an array element."),
    F("VLABEL", "VLABEL(variable)", "Data step", "The label of a variable."),
    F("VTYPE", "VTYPE(variable)", "Data step", "'C' or 'N'."),
    F("VLENGTH", "VLENGTH(variable)", "Data step", "The length of a variable."),
    F("EXIST", "EXIST(data-set)", "Data set", "1 if a data set exists."),
    F("OPEN", "OPEN(data-set)", "Data set", "Opens a data set for the other data set functions."),
    F("ATTRN", "ATTRN(data-set-id, attribute)", "Data set", "A numeric attribute such as 'NOBS'."),
    F("VARNUM", "VARNUM(data-set-id, variable)", "Data set", "The position of a variable in a data set, or 0."),
    F("CLOSE", "CLOSE(data-set-id)", "Data set", "Closes a data set opened with OPEN."),
    # macro functions (used with %)
    F("%SYSFUNC", "%SYSFUNC(function(arguments) <, format>)", "Macro", "Runs a data step function in macro code."),
    F("%SCAN", "%SCAN(text, n <, delimiters>)", "Macro", "Macro version of SCAN."),
    F("%SUBSTR", "%SUBSTR(text, position <, length>)", "Macro", "Macro version of SUBSTR."),
    F("%UPCASE", "%UPCASE(text)", "Macro", "Macro version of UPCASE."),
    F("%STR", "%STR(text)", "Macro", "Quotes text so special characters such as ; are not acted on."),
    F("%EVAL", "%EVAL(expression)", "Macro", "Integer arithmetic and comparisons in macro code."),
    F("%SYSEVALF", "%SYSEVALF(expression <, conversion>)", "Macro", "Arithmetic with decimals in macro code."),
]
FUNCTIONS: dict[str, SasFunction] = {f.name: f for f in _LIST}

# Other SAS function names the summaries don't cover, used only to recognise real functions.
_MORE = """
ADDR ADDRLONG ALLCOMB ALLPERM ANYALNUM ANYCNTRL ANYFIRST ANYGRAPH ANYLOWER ANYNAME ANYPRINT ANYPUNCT ANYSPACE
ANYUPPER ANYXDIGIT ARCOS ARCOSH ARSIN ARSINH ARTANH ATAN ATAN2 ATTRC BAND BETA BETAINV BLSHIFT BNOT BOR
BRSHIFT BXOR BYTE CDF CEILZ CEXIST CHOOSEC CHOOSEN CINV COLLATE COMB COMPARE COMPGED COMPLEV COMPOUND
CONSTANT CONVX COS COSH CSS CUROBS CV DACCDB DATDIF DCLOSE DCREATE DEPDB DEVIANCE DINFO DIVIDE DNUM DOPEN
DOPTNAME DOPTNUM DREAD DROPNOTE DSNAME DUR ERF ERFC EUCLID EXIST FACT FAPPEND FCLOSE FCOL FDELETE FETCH
FETCHOBS FEXIST FGET FILEEXIST FILENAME FILEREF FINANCE FINFO FINV FIPNAME FIPNAMEL FIPSTATE FLOORZ FNONCT
FNOTE FOPEN FOPTNAME FOPTNUM FPOINT FPOS FPUT FREAD FREWIND FRLEN FSEP FUZZ FWRITE GAMINV GAMMA GEODIST
GEOMEAN GEOMEANZ GETOPTION GETVARC GETVARN HARMEAN HARMEANZ HBOUND HTMLDECODE HTMLENCODE IBESSEL INTCINDEX
INTCYCLE INTFIT INTFMT INTGET INTINDEX INTSEAS INTSHIFT INTTEST INTZ IORCMSG IQR IRR JBESSEL JULDATE
JULDATE7 KURTOSIS LARGEST LBOUND LEXCOMB LEXPERM LFACT LGAMMA LIBNAME LIBREF LOG1PX LOG2 LOGBETA LOGCDF
LOGISTIC LOGPDF LOGSDF MAD MARGRCLPRC MD5 MEDIAN MODZ MOPEN MORT MSPLINT MVALID NETPV NLITERAL NORMAL NOTALNUM
NOTALPHA NOTCNTRL NOTFIRST NOTGRAPH NOTLOWER NOTNAME NOTPRINT NOTPUNCT NOTSPACE NOTUPPER NOTXDIGIT NPV
NVALID NWKDOM ORDINAL PATHNAME PCTL PDF PEEK PEEKC PEEKCLONG PEEKLONG PERM POINT POISSON PROBBETA PROBBNML
PROBCHI PROBF PROBGAM PROBHYPR PROBIT PROBMC PROBNEGB PROBNORM PROBT PRXPAREN PRXPOSN PTRLONGADD PUTN RANBIN
RANCAU RANEXP RANGAM RANGE RANK RANNOR RANPOI RANTBL RANTRI RENAME REWIND RMS SAVING SCANQ SDF SECOND SIGN
SIN SINH SKEWNESS SLEEP SMALLEST SOAPWEB SOUNDEX SPEDIS SQUANTILE STDERR STFIPS STNAME STNAMEL STRIP SUBPAD
SUMABS SYMEXIST SYMGLOBL SYMLOCAL SYSEXIST SYSGET SYSMSG SYSPARM SYSPROCESSID SYSPROCESSNAME SYSPROD SYSRC
SYSTEM TAN TANH TINV TNONCT TRANSLATE TRIGAMMA TRUNC TSO UNIFORM UNIQUE UPDATE URLDECODE URLENCODE USS
UUIDGEN VAR VARFMT VARINFMT VARLABEL VARLEN VARNAME VARRAY VARRAYX VARTYPE VERIFY VFORMAT VFORMATD VFORMATN
VFORMATW VINARRAY VINFORMAT VLABELX VLENGTHX VNAMEX VTYPEX VVALUEX WEEK YEARCUTOFF YIELDP YRDIF YYQ
ZIPCITY ZIPFIPS ZIPNAME ZIPNAMEL ZIPSTATE COALESCE KSTRIP KUPCASE KLOWCASE KSCAN KSUBSTR KINDEX KCOMPRESS
KLENGTH KTRIM KLEFT KRIGHT KCVT KTRANSLATE KCOUNT DATEJUL NLDATE NLDATM NLTIME TZONEOFF TZONEID
"""
NAMES: set[str] = {f.name for f in _LIST if not f.name.startswith(("CALL ", "%"))} | set(_MORE.split())
CALL_ROUTINES = {f.name[5:] for f in _LIST if f.is_call} | {
    "STREAMINIT", "SCAN", "SET", "SYMPUTN", "EXECUTE", "SYSTEM", "LABEL", "VNAME", "CATX", "CATS", "CATT",
    "PRXCHANGE", "PRXFREE", "PRXNEXT", "PRXPOSN", "PRXSUBSTR", "RANUNI", "RANNOR", "SLEEP", "ALLPERM", "LEXPERM",
    "COMPCOST", "POKE", "MODULE"}
# Words that are followed by ( in SAS code but are not functions.
NOT_FUNCTIONS = {"IF", "IN", "WHILE", "UNTIL", "AND", "OR", "NOT", "WHEN", "SELECT", "DO", "THEN", "ELSE", "ON",
                 "VALUES", "OUTPUT", "RETURN", "EQ", "NE", "GT", "LT", "GE", "LE", "CASE", "AS", "BY", "FROM",
                 "WHERE", "HAVING", "KEEP", "DROP", "RENAME", "LABEL", "LENGTH", "FORMAT", "INFORMAT", "OBS",
                 "FIRSTOBS", "CONTAINS", "EXISTS", "ANY", "ALL", "SOME", "COUNT", "DISTINCT", "CALCULATED", "INTO",
                 "TABLE", "VIEW", "CREATE", "INSERT", "JOIN", "ARRAY", "PUT", "INPUT", "FREQ", "AVG", "NMISS"}


def find(name: str) -> SasFunction | None:
    key = " ".join(name.strip().upper().split())
    if key.startswith("CALL") and not key.startswith("CALL "):
        key = "CALL " + key[4:].strip()
    return FUNCTIONS.get(key) or FUNCTIONS.get(key.lstrip("%")) or FUNCTIONS.get("%" + key)


def search(text: str, limit: int = 40) -> list[SasFunction]:
    """Functions whose name starts with the text, then those whose name or summary contains it."""
    q = text.strip().upper()
    if not q:
        return list(_LIST)[:limit]
    starts = [f for f in _LIST if f.name.lstrip("%").startswith(q.lstrip("%")) or f.name == q]
    contains = [f for f in _LIST if f not in starts and (q in f.name or q.lower() in f.summary.lower()
                                                           or q.lower() in f.category.lower())]
    return (starts + contains)[:limit]


def is_known(name: str) -> bool:
    return name.upper() in NAMES


def closest(name: str) -> list[str]:
    """The known functions a misspelt name most likely means (CATZ -> CATS, CATT, CATX); empty if none."""
    name = name.upper()
    matches = difflib.get_close_matches(name, sorted(NAMES), n=6, cutoff=0.7)
    same = sorted(m for m in matches if len(m) == len(name))
    if same:
        return same[:3]
    return matches[:1] if matches and difflib.SequenceMatcher(None, name, matches[0]).ratio() >= 0.8 else []
