"""Hostile-protocol gate: every runtime method must answer malformed params
with a typed error — never an escaping exception, and a NaN payload must
never reach the allow_nan=False serializer outside the handler (that would
kill the sidecar process for every later request)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.fuzz_protocol import run_suite


def test_hostile_protocol_corpus_stays_inside_the_boundary():
    total, failures, core_errors = run_suite()
    assert total > 400
    assert failures == 0
    # Handlers either accept or raise typed errors; a bare core_error means a
    # malformed param reached an unguarded code path.
    assert core_errors == 0
