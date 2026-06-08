"""Shared pytest fixtures and path setup."""
import sys
from pathlib import Path

# Make project root importable so tests can `import agent`, `import utils.X`, etc.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
