# SDTM Helper

A guide for SAS clinical programmers who map clinical trial data to CDISC SDTM.

SDTM Helper **does not write your mapping programs**. You write every line of SAS yourself. The app reads the standards and the tables you have loaded in SAS, then tells you what each domain needs, tracks what is left to do, and runs light checks when you finish.

Targets: **SDTMIG v3.4** and **SDTM v2.0**, with SAS 9.4 through SAS OnDemand for Academics (SAS 9.4 Desktop support is planned).

## Plan

| Step | What it delivers | Status |
|---|---|---|
| 1. Foundation | SAS connection through SASPy, local SDTMIG and controlled terminology, saved progress | Done |
| 2. Domain guidance (DM first) | You choose the domain; the app explains each variable (for example ISO 8601 dates, how RFSTDTC is derived), shows a checklist of what is missing and a workflow chart, and saves your progress | Done |
| 3. P21-lite checks | Small, fixable conformance checks at the end of each domain | Done |
| 4a. Guidance for all domains | Shared workflows and tips for Events, Interventions and Findings domains, plus specific tips for AE, MH, DS, CM, EX, VS and LB | Done |
| 4b. Windows app | Desktop window with SAS editor and guide panel, Windows installer, SAS 9.4 on your PC | Done |

## The desktop app

![SDTM Helper window](docs/images/app-live-preview.png)

The window has your SAS program with a **live table preview** beside it, the SAS log underneath, and the guide on the right (F9 hides it for more room).

- **Table preview**: the first 200 rows of the table you are building, or any other table (pick WORK or intermediate tables from the list). It refreshes after every run. Red headers are Required variables, shaded cells are empty Required values, grey headers aren't in the domain; hover a header for its label and Core. Tick **Live** to re-run your program automatically about 2 seconds after you stop typing.

The guide tabs:

- **Guide**: every variable of the domain, with its Core status, format, terminology and tips. Click one to read about it.
- **Checklist**: what is still missing or empty in the table you are building. It refreshes after each run (F5).
- **Workflow**: the order to work in, as a chart. Click a step to tick it off; blue is what to do next.
- **Checks**: the P21-lite report (F6), each finding with a suggested fix.

Pick your study and domain at the top and type the table you are building (e.g. `FINAL.DM`). **Run** (F3) submits your program, or just the selected lines, to SAS. Your program and ticked steps are saved per study and domain (Ctrl+S, and automatically when you switch or close).

### Install on Windows

1. Install Java (for example Eclipse Temurin from <https://adoptium.net/>).
2. Download `SDTM-Helper-Setup-<version>.exe` from the [Releases](https://github.com/dtb1000/Clinical-trial-mapping-tool/releases) page and run it.
3. Open SDTM Helper, click **Settings**, choose *SAS OnDemand for Academics* (with your home region and user ID) or *SAS 9.4 installed on this PC*, and check the Java path. Optionally pick your libname program to run after connecting.
4. Click **Connect**. For ODA the app asks for your password each time and never stores it.

To run it from source instead: `pip install -e .[app]`, then `sdtm-helper-app` (or `python -m sdtm_helper.app`).

### Making a release

Push a tag such as `v0.2.0`. GitHub Actions runs the tests on Windows, builds the app with PyInstaller, wraps it in an Inno Setup installer and attaches it to a new release. Every pull request also builds the installer as a downloadable artifact.

## Command line

The same features are available as commands, which is handy for scripting.

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

   When the domain is finished, run the P21-lite checks (add `--dm FINAL.DM` for other domains, to check subjects and study days against DM):

   ```
   sdtm-helper check DM FINAL DM --study LORNA --autoexec path\to\libname.sas
   sdtm-helper check AE FINAL AE --dm FINAL.DM --study LORNA --autoexec path\to\libname.sas
   ```

   `guide` shows the workflow, your next step and a checklist of required and expected variables that are missing or empty. `step` ticks off a workflow step; progress is saved and picked up next time. `--chart` prints the workflow as a Mermaid flowchart.

## What P21-lite checks

Errors, warnings and notices, each with a suggested fix:

- Required or expected variables missing; required variables empty; variables that aren't in the domain (move them to SUPP--)
- Variable names over 8 characters, labels over 40, character lengths over 200, wrong type, labels that differ from SDTMIG, variable order
- ISO 8601 dates and durations (partial dates allowed), DOMAIN value, controlled terminology (after `fetch-ct`)
- One record per subject in DM, --SEQ unique within USUBJID, start after end
- DM rules: AGEU with AGE, DTHFL only "Y", ARMNRS when ARMCD is empty
- AE: serious events have a seriousness criterion. Findings: every result has a standard result, --STRESN matches --STRESC, no results on NOT DONE records
- Class variables the SDTM model allows (e.g. TAETORD in DS) are noted, not flagged as errors
- Against DM: every USUBJID exists in DM, --DY matches the date and RFSTDTC, no study day 0

The checks read your table through SASPy and never change it. They are a quick first pass, not a replacement for Pinnacle 21.

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
