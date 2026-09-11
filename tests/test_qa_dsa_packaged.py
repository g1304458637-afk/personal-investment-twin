"""Packaged QA mirrors desktop deadlines and cannot accept stale IPC replies."""

import pytest

from scripts.qa_dsa_packaged import decode_response, request_timeout


def test_separate_startup_context_and_service_deadlines():
    assert request_timeout("runtime.handshake") == 90
    assert request_timeout("review.context") == 300
    for method in ("quotes.status", "review.start", "review.poll", "runtime.shutdown"):
        assert request_timeout(method) == 30


def test_receipt_matches_exact_request():
    assert decode_response('{"request_id":"qa-2","ok":true}', "qa-2")["ok"]


@pytest.mark.parametrize("line", ['{"request_id":"qa-1","ok":true}', '{}', '[]'])
def test_stale_or_missing_receipt_is_not_a_shutdown_success(line):
    with pytest.raises(RuntimeError, match="packaged_response_mismatch"):
        decode_response(line, "qa-2")
