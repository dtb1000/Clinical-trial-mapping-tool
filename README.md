# SDTM Helper

A guide for SAS clinical programmers who map clinical trial data to CDISC SDTM.

SDTM Helper **does not write your mapping programs**. You write every line of SAS yourself. The app reads the standards and the tables you have loaded in SAS, then tells you what each domain needs, tracks what is left to do, and runs light checks when you finish.

Targets: **SDTMIG v3.4** and **SDTM v2.0**, with SAS 9.4 through SAS OnDemand for Academics (SAS 9.4 Desktop support is planned).

## Plan

| Step | What it delivers | Status |
|---|---|---|
| 1. Foundation | SAS connection through SASPy, local SDTMIG and controlled terminology, saved progress | Done |
| 2. Domain guidance (DM first) | You choose the domain; the app explains each variable (for example ISO 8601 dates, how RFSTDTC is derived), shows a checklist of what is missing and a workflow chart, and saves your progress | In progress |
| 3. P21-lite checks | Small, fixable conformance checks at the end of each domain, run as SAS code | Planned |
| 4. More domains and a Windows app | AE, CM, EX, VS, LB and others; installer for Windows; SAS 9.4 Desktop | Planned |

## Getting started

1. Follow [docs/saspy-setup-windows.md](docs/saspy-setup-windows.md) to connect to SAS OnDemand for Academics.
2. Download the controlled terminology (no key needed): `sdtm-helper fetch-ct`
3. Tell the app which domain you are mapping, and point it at the table you are building:

   ```
   sdtm-helper guide DM FINAL DM --study LORNA --autoexec path\to\libname.sas
   sdtm-helper explain DM RFSTDTC
   sdtm-helper step DM identifiers --study LORNA
   sdtm-helper guide DM --study LORNA --chart
   ```

   `guide` shows the workflow, your next step and a checklist of required and expected variables that are missing or empty. `step` ticks off a workflow step; progress is saved and picked up next time. `--chart` prints the workflow as a Mermaid flowchart.

## Where the standards come from

- **Controlled terminology** comes from the public NCI EVS release files, so it needs no account.
- **SDTMIG variable metadata** ships with the app in `src/sdtm_helper/data/`. The CDISC Library API only serves SDTMIG to CDISC members, so the files are hand-built from SDTMIG v3.4 and verified against the published guide (see `src/sdtm_helper/data/README.md`). A maintainer with membership can replace them with `scripts/build_standards_bundle.py`. The app checks GitHub for newer releases and reminds the user to update.

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
