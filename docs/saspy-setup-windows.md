# Connecting SDTM Helper to SAS OnDemand for Academics (Windows)

> Using the desktop app? Its **Settings** dialog writes this configuration for you and asks for your password when you connect, so you can skip steps 5 and 6.

SDTM Helper talks to SAS through **SASPy**, a free library from SAS Institute. You do this setup once. It takes about 15 minutes.

You will need:

- Your SAS OnDemand for Academics (ODA) user ID and password
- Python 3.10 or newer
- Java 8 or newer (SASPy uses it to talk to the SAS server)

## 1. Install Python

1. Download Python from <https://www.python.org/downloads/windows/>.
2. Run the installer and tick **Add python.exe to PATH** on the first screen.
3. Open **Command Prompt** and check it works:

   ```
   python --version
   ```

## 2. Install Java

1. Download a Java runtime, for example Eclipse Temurin from <https://adoptium.net/>. The default LTS version is fine.
2. Install it with the default options.
3. In Command Prompt, find where `java.exe` lives:

   ```
   where java
   ```

   Copy the full path it prints (for example `C:\Program Files\Eclipse Adoptium\jre-21...\bin\java.exe`). You need it in step 5.

## 3. Install SDTM Helper and SASPy

From the folder where you cloned this repository:

```
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

This installs SASPy and the other libraries the app needs.

## 4. Find your ODA home region

1. Sign in at <https://welcome.oda.sas.com/>.
2. On the dashboard, look for your **home region** (for example "Europe 1" or "United States 2").

## 5. Create your SASPy configuration

1. Copy `config\sascfg_personal.example.py` to `config\sascfg_personal.py`.
2. Open the new file and:
   - set `"java"` to the path from step 2;
   - set `"iomhost"` to the pair of servers for your home region (the list is in the file).

`config\sascfg_personal.py` is listed in `.gitignore`, so it will never be pushed to GitHub.

## 6. Store your ODA login safely

SASPy reads your login from a file called `_authinfo` in your Windows home folder, so the password is never typed into code.

1. Open Notepad.
2. Type one line, replacing the placeholders with your own details:

   ```
   oda user YOUR_ODA_USER_ID password YOUR_ODA_PASSWORD
   ```

3. Save it as `C:\Users\<your Windows name>\_authinfo`. In the Save dialog choose **All files** so Notepad does not add `.txt`.

Keep this file private. Do not put it inside the repository folder.

## 7. Test the connection

```
sdtm-helper check-sas
```

If it works you will see the SAS version and your libraries, for example:

```
Connected to SAS 9.04.01M8...
Libraries: MAPS, SASHELP, SASUSER, WORK
```

ODA only knows about your own libraries (such as `RAW` or `FINAL`) after a `libname` statement runs in the same session. The app will run your `libname` program for you once you point it at the file; for now you can test with:

```
sdtm-helper check-sas --autoexec path\to\00_libname.sas
```

## Troubleshooting

| Message | What to do |
|---|---|
| `No SAS process attached` or a Java error | Check the `java` path in `sascfg_personal.py` and that `java -version` works. |
| `Connection refused` or a timeout | Check that `iomhost` matches your home region. Some work or university networks block port 8591; try a home network. |
| Asked for a user ID and password every time | Check that `_authinfo` is in your home folder, has no `.txt` ending, and starts with `oda`. |
| `Configuration Definition oda not found` | Check that `config\sascfg_personal.py` exists and contains `SAS_config_names = ["oda"]`. |

SASPy's own documentation for ODA is at <https://sassoftware.github.io/saspy/configuration.html#iom-using-java>.
