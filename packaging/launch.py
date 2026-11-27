"""Entry point for the Windows build (PyInstaller)."""
import sys

from sdtm_helper.app.window import main

if __name__ == "__main__":
    sys.exit(main())
