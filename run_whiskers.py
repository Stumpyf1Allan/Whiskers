#!/usr/bin/env python3
"""Double-click entry point: python run_whiskers.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from folio.main import main  # noqa: E402

sys.exit(main())
