# Standards bundle

`sdtmig-3-4/` holds the SDTMIG v3.4 domain metadata that ships with the app: one JSON file per
domain, plus `manifest.json`. Users need no CDISC account.

## How it is built

The CDISC Library API only serves SDTMIG content to CDISC members, so for now the files are
**hand-built**. Each file holds only the facts the app needs: variable names, labels, types,
Core (Req/Exp/Perm), roles, and controlled terminology codelist codes. The files don't copy
CDISC's notes text. The app's own explanations live in `guidance/<domain>.json`.

The files use the same JSON shape as the CDISC Library API. If a maintainer has membership,
`scripts/build_standards_bundle.py` can overwrite them with the official content without any
other change.

## Verifying a domain

Check each variable against the domain's specification table in the published SDTMIG v3.4.
Then set `verified_by` and `verified_on` in `manifest.json`. `tests/test_bundle.py` checks the
files are well formed.
