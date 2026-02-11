import sys
from pathlib import Path


PYTHON_AGENT_DIR = Path(__file__).resolve().parent.parent
if str(PYTHON_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_AGENT_DIR))
