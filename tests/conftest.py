"""Make the repository's scripts importable from tests, wherever pytest is run from."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
