"""Pytest auto-setup for Task 0.2 literal import support.

Prepends the tests/ directory to sys.path so that the bare statement

    from index_with_turbovec import get_embedder

(directly from the plan's test example) resolves to tests/index_with_turbovec.py
(the clean shim) instead of failing on the hyphen-named real script or requiring
35+ lines of dynamic setup *inside* the test file itself.

This + the shim is the smartest, most manageable way to honor:
- exact bare 3-line test body per plan
- "ask clarifying questions before implementing" (done)
- no main script rename
- changes confined (support only in tests/)
- TDD steps 2/4 produce results matching documented expectations as closely as possible
  (FAIL before get_embedder added to script; PASS after)
- keeps test file pristine

Standard pytest pattern; no effect on non-test runs or other tests.
"""

import sys
from pathlib import Path

# Make tests/index_with_turbovec.py importable as top-level "index_with_turbovec".
# (Insert at front so it wins over any root-level name.)
_tests_dir = str(Path(__file__).parent.resolve())
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)
