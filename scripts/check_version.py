"""Fail a release before publication if its Git tag disagrees with the app."""
from pathlib import Path
import os
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cesoir import __version__

if not re.fullmatch(r"\d+\.\d+\.\d+", __version__):
    raise SystemExit("La version de l'application doit avoir le format X.Y.Z.")
if os.environ.get("REF_TYPE") == "tag" and os.environ.get("REF_NAME") != f"v{__version__}":
    raise SystemExit(f"Le tag doit être v{__version__}, comme cesoir/__init__.py.")
print(f"Version vérifiée : {__version__}")
