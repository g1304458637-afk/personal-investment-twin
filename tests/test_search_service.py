"""Offline Bocha/quotes protocol boundary. No live network or Keychain writes."""
import json

from toujing_core_runtime.protocol import handle_request, _METHODS, SUPPORTED_METHODS


def test_search_and_quotes_are_private_stdio_methods_not_product_allowlist():
    assert "search.test_connection" in _METHODS
    assert "quotes.status" in _METHODS
    assert "search.test_connection" not in SUPPORTED_METHODS
    assert "quotes.status" not in SUPPORTED_METHODS


def test_quotes_status_is_offline_and_does_not_require_params(monkeypatch):
    monkeypatch.setattr("toujing_core_runtime.quote_status.quotes_status", lambda: {
        "available": False, "provider": "akshare", "license": "MIT",
        "disclaimer": "research_background_not_sla"})
    response, _ = handle_request({"protocol_version": "1", "request_id": "q", "method": "quotes.status",
                                  "params": {}}, _METHODS)
    assert response["ok"] is True
    assert response["result"]["provider"] == "akshare"
    assert response["result"]["available"] is False


def test_quotes_status_is_available_when_akshare_imports():
    from toujing_core_runtime.quote_status import quotes_status
    status = quotes_status()
    assert status["available"] is True
    assert status["provider"] == "akshare"
    assert "traceback" not in json.dumps(status).lower()


def test_search_test_rejects_custom_query_and_redacts_failures(monkeypatch, capsys):
    monkeypatch.setattr("toujing_core_runtime.search_service.bocha_web_search",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("search_authentication_failed")))
    response, _ = handle_request({"protocol_version": "1", "request_id": "s",
                                  "method": "search.test_connection",
                                  "params": {"_desktop_bocha_key": "secret-test-key"}}, _METHODS)
    assert response["ok"] is True
    assert response["result"] == {"connected": False, "reason": "search_authentication_failed"}
    assert "secret-test-key" not in json.dumps(response)
    failed, _ = handle_request({"protocol_version": "1", "request_id": "bad",
                                "method": "search.test_connection",
                                "params": {"_desktop_bocha_key": "secret-test-key", "query": "我的账户"}}, _METHODS)
    assert failed["ok"] is False
    dumped = json.dumps(failed)
    assert "secret-test-key" not in dumped
    assert "我的账户" not in dumped
    assert "secret-test-key" not in capsys.readouterr().out
