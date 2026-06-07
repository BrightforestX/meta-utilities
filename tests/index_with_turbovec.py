"""Shim to support the *literal* plan test body:

    from index_with_turbovec import get_embedder

    embedder = get_embedder()
    assert embedder.__name__ == "simple_hash_embedding"

(See tests/test_turbovec_real_embed.py and tests/conftest.py.)

Why: the real script filename has a hyphen (invalid for Python identifiers)
and a top-level `try: from turbovec ... except: ... sys.exit(1)`.
A dedicated tiny shim + path tweak lets the test be exactly the bare 3 lines
from the plan without ~35 lines of importlib/MagicMock hack *inside the test file*.

This is the smartest manageable solution per guidance: test body literal,
TDD commands produce expected PASS/FAIL semantics (when script lacks the fn),
no rename of main script, no edits outside Task 0.2 area, respects "ask first".

The load happens once at shim import time (conftest ensures discovery).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
import importlib.util

# Load the real (hyphenated) script's code under the importable name.
# We exec into a throwaway module obj and copy only the needed export.
old_turbovec = sys.modules.get("turbovec")
try:
    sys.modules["turbovec"] = MagicMock()  # satisfy script top-level + prevent exit(1)
    script_path = (
        Path(__file__).parent.parent
        / "skills"
        / "context-forge"
        / "scripts"
        / "index-with-turbovec.py"
    ).resolve()
    spec = importlib.util.spec_from_file_location("index_with_turbovec", str(script_path))
    script_mod = importlib.util.module_from_spec(spec)
    # Do *not* register script_mod in sys.modules under the name; we only want its defs executed.
    spec.loader.exec_module(script_mod)
    get_embedder = script_mod.get_embedder
finally:
    # Restore previous turbovec (or remove our mock) so other tests are unaffected.
    if old_turbovec is not None:
        sys.modules["turbovec"] = old_turbovec
    else:
        sys.modules.pop("turbovec", None)

# The assignment above binds get_embedder in *this* module's globals.
# With conftest.py prepending tests/ to sys.path, a bare
# `from index_with_turbovec import get_embedder` finds this file and succeeds.
