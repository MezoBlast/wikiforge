"""pytest configuration: make the curator-side helper modules importable.

The WikiForge Python helpers live in .forge/lib/ (not a package on PYTHONPATH).
Tests import them by bare name (`import ingest_helpers`), so put that directory
on sys.path before collection.
"""
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent / ".forge" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
