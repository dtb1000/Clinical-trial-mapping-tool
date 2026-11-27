# Standards bundle

`sdtmig-3-4/` holds the SDTMIG v3.4 domain metadata that ships with the app, one JSON file per
domain plus `manifest.json`. It is built by the maintainer with
`scripts/build_standards_bundle.py` and their own CDISC Library API key, so users need no key.

Until the bundle is built, the app falls back to anything the user downloaded with
`sdtm-helper fetch-standards`.
