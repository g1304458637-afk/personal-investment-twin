"""Offline integration checks for control-lane liveness and SQLite ownership."""
from __future__ import annotations

import io
import json
import re
import threading
import pytest
from pathlib import Path
from queue import Queue

from toujing_core_runtime import protocol


def request(identifier, method, params=None):
    return {"protocol_version": "1", "request_id": identifier,
            "method": method, "params": {} if params is None else params}


def test_health_overtakes_blocked_work_and_queue_is_bounded(monkeypatch):
    started, release, healthy = threading.Event(), threading.Event(), threading.Event()
    inputs = Queue()
    output = io.StringIO()

    class Input:
        def __iter__(self):
            while (item := inputs.get()) is not None:
                yield json.dumps(item) + "\n"

    class Output:
        def write(self, line):
            output.write(line)
            if json.loads(line).get("request_id") == "health":
                healthy.set()

        def flush(self):
            pass

    def slow(params):
        started.set()
        assert release.wait(10)
        return {"done": True}

    monkeypatch.setitem(protocol._METHODS, "test.slow", slow)
    monkeypatch.setitem(protocol._METHODS, "test.fast", lambda p: {"done": True})
    runner = threading.Thread(target=protocol.run, args=(Input(), Output()))
    runner.start()
    try:
        inputs.put(request("slow", "test.slow"))
        assert started.wait(5)
        for index in range(64):
            inputs.put(request(f"fast-{index}", "test.fast"))
        inputs.put(request("health", "runtime.health"))
        assert healthy.wait(5), "health must answer while data worker is blocked"
        before_release = [json.loads(line) for line in output.getvalue().splitlines()]
        assert not any(item["request_id"] == "slow" for item in before_release)
        assert any(item["error"] and item["error"]["code"] == "runtime_busy"
                   for item in before_release)
    finally:
        release.set()
        inputs.put(request("stop", "runtime.shutdown"))
        runner.join(10)
    assert not runner.is_alive()
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(responses) == 67
    accepted = [item["request_id"] for item in responses if item["ok"]]
    assert accepted[-1] == "stop"
    assert accepted.index("slow") < accepted.index("fast-0") < accepted.index("fast-62")


def test_real_sqlite_product_is_created_used_and_closed_on_owner_worker(tmp_path):
    payloads = [request("first", "account.list"), request("second", "account.list"),
                request("stop", "runtime.shutdown")]
    output = io.StringIO()
    protocol.run(io.StringIO("".join(json.dumps(p) + "\n" for p in payloads)),
                 output, db_path=str(tmp_path / "account.sqlite3"))
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [item["request_id"] for item in responses] == ["first", "second", "stop"]
    assert all(item["ok"] for item in responses), responses
    assert responses[0]["result"]["accounts"] == []


def test_queued_write_expires_and_invalid_shutdown_does_not_block_health(monkeypatch):
    started, release, health = threading.Event(), threading.Event(), threading.Event()
    inputs, output, writes = Queue(), io.StringIO(), []
    clock = [1000]
    monkeypatch.setattr(protocol.time, "time_ns", lambda: clock[0] * 1_000_000)

    class Input:
        def __iter__(self):
            while (item := inputs.get()) is not None:
                yield json.dumps(item) + "\n"

    class Output:
        def write(self, line):
            output.write(line)
            if json.loads(line).get("request_id") == "health":
                health.set()

        def flush(self):
            pass

    def slow(params):
        started.set()
        assert release.wait(10)
        return {}

    monkeypatch.setitem(protocol._METHODS, "test.slow", slow)
    monkeypatch.setitem(protocol._METHODS, "test.write", lambda p: writes.append(p) or {})
    runner = threading.Thread(target=protocol.run, args=(Input(), Output()))
    runner.start()
    try:
        inputs.put(request("slow", "test.slow"))
        assert started.wait(5)
        inputs.put({**request("write", "test.write"), "deadline_unix_ms": 1500})
        inputs.put(request("invalid-stop", "runtime.shutdown", {"unexpected": True}))
        inputs.put(request("health", "runtime.health"))
        assert health.wait(5), "an invalid shutdown must not block the control lane"
        clock[0] = 2000
    finally:
        release.set()
        inputs.put(request("stop", "runtime.shutdown"))
        runner.join(10)
    assert not runner.is_alive()
    responses = {item["request_id"]: item for item in map(json.loads, output.getvalue().splitlines())}
    assert responses["invalid-stop"]["error"]["code"] == "invalid_params"
    assert responses["write"]["error"]["code"] == "request_expired"
    assert writes == []


@pytest.mark.parametrize("deadline", [None, True, -1, [], 1.5, float("nan")])
def test_invalid_deadline_is_a_structured_error(deadline):
    response, _ = protocol.handle_request({**request("bad", "runtime.health"), "deadline_unix_ms": deadline})
    assert response["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("method", [[], {}, None, 23])
def test_malformed_method_cannot_stop_the_reader(method):
    output = io.StringIO()
    payloads = [request("bad", method), request("health", "runtime.health"),
                request("stop", "runtime.shutdown")]
    protocol.run(io.StringIO("".join(json.dumps(p) + "\n" for p in payloads)), output)
    responses = {item["request_id"]: item for item in map(json.loads, output.getvalue().splitlines())}
    assert responses["bad"]["error"]["code"] == "unknown_method"
    assert responses["health"]["ok"] and responses["stop"]["ok"]


def test_python_product_registry_matches_rust_frontend_boundary(tmp_path):
    root = Path(__file__).resolve().parents[1]
    rust = (root / "apps/desktop/src-tauri/src/runtime.rs").read_text()
    block = rust.split("const PRODUCT_METHODS: &[&str] = &[")[1].split("];", 1)[0]
    rust_methods = set(re.findall(r'"([a-z_.]+)"', block))
    methods, product = protocol._product_methods(str(tmp_path / "registry.sqlite3"))
    try:
        assert set(methods) == set(protocol.PRODUCT_METHODS) == rust_methods
        assert "strategy_teaching.explain" in methods
    finally:
        product.close()


def test_teaching_dispatch_reaches_existing_implementation_without_network(tmp_path, monkeypatch):
    from src.agents import strategy_teaching

    seen = []
    monkeypatch.setattr(strategy_teaching, "explain_report",
                        lambda params: seen.append(params) or {"status": "available", "texts": ["fixture"]})
    methods, product = protocol._product_methods(str(tmp_path / "teaching.sqlite3"))
    try:
        params = {"report": {"schema_version": "strategy_simulation.v1"}, "focus": "entry"}
        response, stop = protocol.handle_request(request("teaching", "strategy_teaching.explain", params), methods)
        assert response["ok"] and not stop
        assert response["result"]["texts"] == ["fixture"]
        assert seen == [params]
        invalid, _ = protocol.handle_request(request("bad", "strategy_teaching.explain", []), methods)
        assert invalid["error"]["code"] == "invalid_params"
    finally:
        product.close()


def test_company_wait_does_not_block_account_owner_lane(monkeypatch, tmp_path):
    """A slow external company model must not hold the account SQLite worker."""
    started,release,account_done=threading.Event(),threading.Event(),threading.Event()
    inputs,output=Queue(),io.StringIO()
    original=protocol._product_methods
    def product_methods(path):
        methods,product=original(path)
        def company(_params):
            started.set()
            assert release.wait(10)
            return {'status':'ANSWERED'}
        methods['company_research.chat']=company
        return methods,product
    monkeypatch.setattr(protocol,'_product_methods',product_methods)
    class Input:
        def __iter__(self):
            while (item:=inputs.get()) is not None:yield json.dumps(item)+'\n'
    class Output:
        def write(self,line):
            output.write(line)
            if json.loads(line)['request_id']=='account':account_done.set()
        def flush(self):pass
    runner=threading.Thread(target=protocol.run,args=(Input(),Output()),kwargs={'db_path':str(tmp_path/'independent.sqlite3')})
    runner.start()
    try:
        inputs.put(request('company','company_research.chat',{}));assert started.wait(5)
        inputs.put(request('account','account.list'))
        assert account_done.wait(5),'Account read waited behind an external company model'
        before=[json.loads(line) for line in output.getvalue().splitlines()]
        assert before[0]['request_id']=='account' and before[0]['ok']
    finally:
        release.set();inputs.put(request('stop','runtime.shutdown'));runner.join(10)
    assert not runner.is_alive()
    responses=[json.loads(line) for line in output.getvalue().splitlines()]
    assert responses[-1]['request_id']=='stop'


@pytest.mark.parametrize('invalid', [
    {'params': {'unexpected': True}},
    {'protocol_version': 'unsupported'},
    {'deadline_unix_ms': 1},
])
def test_invalid_shutdown_keeps_company_and_account_lanes_available(monkeypatch, tmp_path, invalid):
    monkeypatch.setattr(protocol.CompanyResearchClient, 'call', lambda *_args: {'application': 'company-operating-twin'})
    messages = [{**request('invalid', 'runtime.shutdown'), **invalid},
                request('company', 'company_research.status'), request('account', 'account.list'),
                request('stop', 'runtime.shutdown')]
    output = io.StringIO()
    protocol.run(io.StringIO(''.join(json.dumps(message) + '\n' for message in messages)), output,
                 db_path=str(tmp_path / 'shutdown-contract.sqlite3'))
    replies = {item['request_id']: item for item in map(json.loads, output.getvalue().splitlines())}
    assert not replies['invalid']['ok']
    assert all(replies[key]['ok'] for key in ('company', 'account', 'stop'))


def test_shutdown_expiring_after_reader_validation_keeps_company_lane_available(monkeypatch, tmp_path):
    # Accepted while reading, expired by the time the account worker executes it.
    clock = iter([1000_000_000, 2000_000_000])
    monkeypatch.setattr(protocol.time, 'time_ns', lambda: next(clock))
    monkeypatch.setattr(protocol.CompanyResearchClient, 'call', lambda *_args: {'application': 'company-operating-twin'})
    messages = [{**request('expired', 'runtime.shutdown'), 'deadline_unix_ms': 1500},
                request('company', 'company_research.status'), request('stop', 'runtime.shutdown')]
    output = io.StringIO()
    protocol.run(io.StringIO(''.join(json.dumps(message) + '\n' for message in messages)), output,
                 db_path=str(tmp_path / 'expired-shutdown.sqlite3'))
    replies = {item['request_id']: item for item in map(json.loads, output.getvalue().splitlines())}
    assert replies['expired']['error']['code'] == 'request_expired'
    assert replies['company']['ok'] and replies['stop']['ok']
