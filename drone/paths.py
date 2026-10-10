"""Bundled resources and persistent files have separate roots."""
from pathlib import Path
import sys

RESOURCE_ROOT=Path(__file__).resolve().parents[1]
USER_ROOT=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else RESOURCE_ROOT
SAVE_DIR=USER_ROOT/'save'
