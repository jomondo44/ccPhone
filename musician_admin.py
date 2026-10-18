#!/usr/bin/env python3
"""Launcher: `python musician_admin.py` starts the app and opens the browser."""
import sys

from indie_admin.server import main

if __name__ == "__main__":
    sys.exit(main())
