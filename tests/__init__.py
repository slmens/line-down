import sys
from pathlib import Path

# collectors run as plain scripts, so tests import them the same way
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "collectors"), str(ROOT / "pipelines")]
