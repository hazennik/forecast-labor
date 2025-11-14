"""
Root conftest.py - Sets up Python path before any test modules are imported.
This file is discovered by pytest before tests/ subdirectory conftest.
"""

import sys
from pathlib import Path

# Ensure /app is in Python path for all imports
_project_root = Path(__file__).parent.absolute()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Verify key modules can be imported
try:
    import etl
    import features
    import seasonal
except ImportError as e:
    print(f"WARNING: Could not import required modules: {e}")
    print(f"sys.path: {sys.path}")

