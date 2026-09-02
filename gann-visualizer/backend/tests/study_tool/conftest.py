"""
Makes scripts/ importable as bare top-level modules (e.g. `import
build_gann_corpus`), matching the pattern the test suite already uses for
importing `study_tool` directly. Resolved relative to this file rather than
hardcoded, so it points at whichever checkout (worktree or permanent) the
tests are actually running from.
"""
import os
import sys

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCRIPTS_DIR = os.path.join(_BACKEND_DIR, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
