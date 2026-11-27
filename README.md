# SDTM Helper

A guide for SAS clinical programmers who map clinical trial data to CDISC SDTM.

SDTM Helper **does not write your mapping programs**. You write every line of SAS yourself. The app reads the standards and the tables you have loaded in SAS, then tells you what each domain needs, tracks what is left to do, and runs light checks when you finish.

Targets: **SDTMIG v3.4** and **SDTM v2.0**, with SAS 9.4 through SAS OnDemand for Academics (SAS 9.4 Desktop support is planned).

## Plan

| Step | What it delivers | Status |
|---|---|---|
| 1. Foundation | SAS connection through SASPy, local SDTMIG and controlled terminology, saved progress | In progress |
| 2. Domain guidance (DM first) | You choose the domain; the app explains each variable (for example ISO 8601 dates, how RFSTDTC is derived), shows a checklist of what is missing and a workflow chart, and saves your progress | Planned |
| 3. P21-lite checks | Small, fixable conformance checks at the end of each domain, run as SAS code | Planned |
| 4. More domains and a Windows app | AE, CM, EX, VS, LB and others; installer for Windows; SAS 9.4 Desktop | Planned |

## Getting started

1. Follow [docs/saspy-setup-windows.md](docs/saspy-setup-windows.md) to connect to SAS OnDemand for Academics.
2. Download the standards:

   ```
   sdtm-helper fetch-ct                  # controlled terminology from NCI EVS, no key needed
   set CDISC_API_KEY=your-key            # your own CDISC Library key
   sdtm-helper fetch-standards DM AE     # SDTMIG v3.4 variable metadata
   ```

3. Try it on a table:

   ```
   sdtm-helper check-sas --autoexec path\to\libname.sas
   sdtm-helper show-domain DM
   sdtm-helper compare DM FINAL DM --autoexec path\to\libname.sas
   ```

## Where the standards come from

- **Controlled terminology** comes from the public NCI EVS release files, so it needs no account.
- **SDTMIG variable metadata** comes from the CDISC Library API, which needs each user's own API key from a CDISC account. A shared key cannot be shipped in an open-source app.

Downloaded files are cached in `%USERPROFILE%\.sdtm_helper\standards`, and saved work in `%USERPROFILE%\.sdtm_helper\progress`.

## Development

```
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
pytest
```

The tests do not need SAS or a CDISC key.

Test data: the [LORNA Clinical Trial](https://github.com/dtb1000/LORNA-Clinical-Trial) project has raw data, SAS mapping programs and validated SDTM datasets that work well with this app.
