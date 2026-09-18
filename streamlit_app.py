"""Run with: python -m streamlit run streamlit_app.py."""

import sys
from pathlib import Path

# AppTest and some hosting launchers execute an entrypoint with its directory
# as the only script path.  Add the repository root explicitly so the package
# imports work in the same way as ``python -m streamlit run`` from the root.
_REPOSITORY_ROOT = str(Path(__file__).resolve().parent)
if _REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, _REPOSITORY_ROOT)

from src.dashboard.app import main

main()
