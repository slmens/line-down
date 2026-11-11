import sys
from pathlib import Path

# collectors run as plain scripts, so tests import them the same way
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collectors"))
