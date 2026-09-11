"""Offline credential-boundary tests. Values below are invalid synthetic sentinels."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from toujing_core_runtime import model_service as service
from toujing_core_runtime.protocol import handle_request, _METHODS


@pytest.mark.parametrize("key", [None, "", "x y", "x\n", "秘密", "x" * 513])
def test_invalid_or_deleted_key_never_uses_environment(key, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "old-terminal-test-sentinel")
    with pytest.raises(ValueError, match="^model_not_configured$"):
        service.desktop_runtime(key, factory=lambda **_: pytest.fail("must not call factory"))


def test_explicit_key_uses_existing_factory_without_global_environment_change(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "old-terminal-test-sentinel")
    import os
    observed = []
    sentinel = object()
    def factory(**kwargs):
        observed.append(kwargs)
        return sentinel
    assert service.desktop_runtime("test-only-value", factory) is sentinel
    assert observed == [{"environment": {"DEEPSEEK_API_KEY": "test-only-value"}}]
    assert os.environ["DEEPSEEK_API_KEY"] == "old-terminal-test-sentinel"


def test_factory_failure_does_not_echo_secret():
    def bad(**kwargs):
        raise RuntimeError(str(kwargs))
    with pytest.raises(ValueError) as error:
        service.desktop_runtime("test-only-value", bad)
    assert str(error.value) == "model_configuration_failed"
    assert error.value.__suppress_context__


def test_connection_probe_uses_same_runtime_no_tools_or_account_and_closes(monkeypatch):
    client = SimpleNamespace(close=AsyncMock())
    runtime = SimpleNamespace(model=SimpleNamespace(_get_client=lambda: client),
                              model_settings=SimpleNamespace(reasoning={"effort": "none"}),
                              run_config=object())
    monkeypatch.setattr(service, "desktop_runtime", lambda key: runtime)
    agents = []
    def agent(**kwargs):
        agents.append(kwargs)
        return object()
    monkeypatch.setattr(service, "Agent", agent)
    run = AsyncMock(return_value=SimpleNamespace(final_output="OK"))
    monkeypatch.setattr(service.Runner, "run", run)
    assert service.test_connection({"_desktop_model_key": "test-only-value"}) == {"connected": True, "reason": None}
    assert agents[0]["model"] is runtime.model
    assert agents[0]["tools"] == []
    assert agents[0]["model_settings"].reasoning.effort == "none"
    assert run.call_args.args[1] == "Connection check"
    assert run.call_args.kwargs["max_turns"] == 1
    client.close.assert_awaited_once()


@pytest.mark.parametrize("exception,reason", [(RuntimeError("test-only-secret"), "model_connection_failed"),
                                                (TimeoutError("test-only-secret"), "model_connection_timeout")])
def test_provider_errors_never_reach_stdout_stderr_or_response(monkeypatch, capsys, exception, reason):
    monkeypatch.setattr(service, "_probe", AsyncMock(side_effect=exception))
    response, _ = handle_request({"protocol_version": "1", "request_id": "test", "method": "model.test_connection",
                                 "params": {"_desktop_model_key": "test-only-secret"}}, _METHODS)
    assert response["result"] == {"connected": False, "reason": reason}
    assert "test-only-secret" not in json.dumps(response)
    assert capsys.readouterr() == ("", "")


def test_test_connection_rejects_custom_prompts_or_endpoints():
    with pytest.raises(ValueError, match="invalid_model_test_request"):
        service.test_connection({"_desktop_model_key": "test", "prompt": "private account", "base_url": "http://other"})


def test_failed_test_still_closes_client(monkeypatch):
    client = SimpleNamespace(close=AsyncMock())
    runtime = SimpleNamespace(model=SimpleNamespace(_get_client=lambda: client), model_settings=SimpleNamespace(reasoning=None), run_config=None)
    monkeypatch.setattr(service, "desktop_runtime", lambda key: runtime)
    monkeypatch.setattr(service, "Agent", lambda **kwargs: object())
    monkeypatch.setattr(service.Runner, "run", AsyncMock(side_effect=RuntimeError("test-only-secret")))
    assert service.test_connection({"_desktop_model_key": "test"})["connected"] is False
    client.close.assert_awaited_once()
