"""Hostile-input gate: the ingestion/market parsers must answer every
malformed, truncated, mutated or oversized input with a typed ValueError —
never an AttributeError, IndexError, pandas exception or anything else that
would escape as an unexplained failure instead of a per-row issue code."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.fuzz_parsers import run_suite


def test_hostile_csv_corpus_produces_typed_errors_only():
    total, crashes = run_suite()
    assert total > 500
    assert crashes == 0
