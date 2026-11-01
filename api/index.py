"""Vercel entry point. Vercel serves the FastAPI app defined in app/main.py from this file.

The function runs in Mumbai (bom1, see vercel.json) because data.gov.in only accepts Indian IP addresses.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402,F401
