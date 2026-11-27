# Copy this file to config/sascfg_personal.py and edit it.
# config/sascfg_personal.py is in .gitignore, so it is never committed.
# Your ODA user ID and password do NOT go here; they go in your _authinfo file
# (see docs/saspy-setup-windows.md).

SAS_config_names = ["oda"]

oda = {
    # Full path to java.exe. Find it with:  where java   (in Command Prompt)
    "java": r"C:\Program Files\Eclipse Adoptium\jre-21.0.5.11-hotspot\bin\java.exe",

    # Pick the pair for your ODA home region (shown on the ODA dashboard):
    #   United States 1: odaws01-usw2.oda.sas.com,   odaws02-usw2.oda.sas.com
    #   United States 2: odaws01-usw2-2.oda.sas.com, odaws02-usw2-2.oda.sas.com
    #   Europe 1:        odaws01-euw1.oda.sas.com,   odaws02-euw1.oda.sas.com
    #   Asia Pacific 1:  odaws01-apse1.oda.sas.com,  odaws02-apse1.oda.sas.com
    #   Asia Pacific 2:  odaws01-apse1-2.oda.sas.com, odaws02-apse1-2.oda.sas.com
    "iomhost": ["odaws01-euw1.oda.sas.com", "odaws02-euw1.oda.sas.com"],
    "iomport": 8591,

    # Tells SASPy to read the "oda" line from your _authinfo file.
    "authkey": "oda",
    "encoding": "utf-8",
}
