"""Offline real-ledger AI boundary: exact facts, scope, source changes, tool receipts."""
import asyncio
from dataclasses import asdict
import json

import pytest
from agents.tool_context import ToolContext

from src.agents.account_conversation import (
    ConversationAnswer, ConversationError, conversation_tools, get_account_ledger_activity, validate_answer,
)
from src.agents.account_review_sources import compose_account_answer
from src.agents.account_conversation_sources import knowledge_record
from toujing_core_runtime.account_review import AccountReviewService
from toujing_core_runtime.product import ProductRuntime
from tests.test_real_account_ledger import SCOPE, OPEN, INITIAL, SEC, commit, row, quote

PARAMS = {**SCOPE, "scope_kind": "account", "data_mode": "real_user"}


@pytest.fixture
def account(tmp_path):
    runtime = ProductRuntime(tmp_path / "test.sqlite3")
    commit(runtime, "opening", opening=OPEN, records=[INITIAL])
    service = AccountReviewService(runtime)
    yield runtime, service
    service.close()
    runtime.close()


def record(context, kind):
    return next(r for r in (*context.records.values(), *context.conversation_records.values()) if r.kind == kind)


def test_ledger_context_uses_projection_not_legacy_and_keeps_flow_basis(account, monkeypatch):
    runtime, service = account
    monkeypatch.setattr(runtime, "_lifecycle", lambda _: pytest.fail("legacy replay must not run"))
    commit(runtime, "events", records=[row("deposit", "in", "2025-01-02", amount="500")])
    context, _ = service._source_with_fingerprint(PARAMS)
    assert record(context, "snapshot").value["equity"] == "11700"
    performance = record(context, "performance").value
    assert performance["period_pnl"] == "0" and performance["net_contributions"] == "500"
    assert performance["time_weighted_return"] is None
    assert record(context, "snapshot").value["positions"][0]["unrealized_pnl"] == "200"
    assert "缺少" in knowledge_record(context, "performance").value["content"]
    assert service.context(PARAMS)["projection_kind"] == "account_ledger.v1"
    context.retrieved.update(context.records)
    answer = compose_account_answer([context.finding_options[0].id], [], context)
    assert "11700" in answer["summary"]["zh"]


def test_actions_missing_prices_zero_cash_and_no_invented_returns(account):
    runtime, service = account
    commit(runtime, "events", records=[row("split", "split", "2025-01-02", ratio="2")])
    context = service._source(PARAMS)
    assert record(context, "snapshot").value["equity"] is None
    assert record(context, "performance").value["period_pnl"] is None
    assert "split" in json.dumps(record(context, "ledger_activity").value)
    assert not {"get_hypothetical_trade_impact", "get_owned_period_comparison", "get_owned_same_stock_comparison"} & {t.name for t in conversation_tools(context)}
    assert "get_account_ledger_activity" in {t.name for t in conversation_tools(context)}
    context.retrieved.update(context.records)
    assert "暂不可用" in compose_account_answer([context.finding_options[0].id], [], context)["summary"]["zh"]


def test_episode_scope_keeps_opening_action_sources_but_no_account_journal(account):
    runtime, service = account
    commit(runtime, "events", records=[row("split", "split", "2025-01-02", ratio="2")])
    context = service._source(PARAMS)
    episode_id = record(context, "episode_index").value["episodes"][0]["episode_id"]
    focused = service._source({**PARAMS, "scope_kind": "episode", "episode_id": episode_id})
    detail = record(focused, "episode_detail")
    assert {e["event_type"] for e in detail.value["operations"]} == {"opening_position", "split"}
    assert set(detail.underlying_refs) == {"open", "split"}
    assert not {"snapshot", "ledger_journal", "ledger_activity"} & {r.kind for r in (*focused.records.values(), *focused.conversation_records.values())}
    with pytest.raises(ValueError, match="owned_episode_unavailable"):
        service._source({**PARAMS, "scope_kind": "episode", "episode_id": "foreign"})


def test_reconciliation_and_void_invalidate_context_and_expose_stale_state(account):
    runtime, service = account
    before = service.context(PARAMS)["source_fingerprint"]
    statement = {"statement_id": "s", "source_ref": "broker", "as_of": "2025-01-01", "currency": "CNY",
                 "positions_complete": True, "cash": "10000", "positions": [{**SEC, "quantity": "100"}]}
    commit(runtime, "statement", statement=statement)
    assert service.context(PARAMS)["source_fingerprint"] != before
    commit(runtime, "void", target_event_id="open", reason="incorrect")
    assert record(service._source(PARAMS), "ledger_reconciliation").value["runs"][0]["stale"] is True
    assert not record(service._source(PARAMS), "episode_index").value["episodes"]


def test_tools_produce_auditable_records_and_numeric_validator_rejects_invention(account):
    _, service = account
    context = service._source(PARAMS)
    context.records.update(context.conversation_records)
    tool_context = ToolContext(context, tool_name=get_account_ledger_activity.name,
                               tool_call_id="offline-ledger", tool_arguments="{}")
    raw = asyncio.run(get_account_ledger_activity.on_invoke_tool(tool_context, "{}"))
    payload = json.loads(raw)
    assert {r["kind"] for r in payload["records"]} == {"ledger_activity", "ledger_journal", "ledger_reconciliation"}
    assert {r["ref"] for r in payload["records"]} <= context.retrieved
    snap = record(context, "snapshot")
    answer = ConversationAnswer.model_validate({"paragraphs": [{"kind":"fact", "text":{"zh":"现金 999999 CNY", "en":"Cash 999999 CNY"}, "refs":[snap.ref]}], "guides":[]})
    with pytest.raises(ConversationError, match="number_not_in_sources"):
        validate_answer(answer, {snap.ref: asdict(snap)}, [snap.ref])


def test_zero_cash_account_with_no_trades(tmp_path):
    runtime = ProductRuntime(tmp_path / "zero.sqlite3")
    service = AccountReviewService(runtime)
    try:
        commit(runtime, "opening", opening={**OPEN, "initial_cash":"0"}, records=[])
        context = service._source(PARAMS)
        assert record(context, "snapshot").value["equity"] == "0"
        assert record(context, "episode_index").value["episodes"] == []
        with pytest.raises(ValueError):
            service._source({**PARAMS, "account_id":"other"})
    finally:
        service.close()
        runtime.close()


def test_raw_price_value_and_observation_provenance_remain_bound(account, monkeypatch):
    runtime, service = account
    before = service.context(PARAMS)["source_fingerprint"]
    observation = quote("2025-01-02", 13)
    monkeypatch.setattr(runtime.repo, "prices", lambda subject, account: (observation,))
    context = service._source(PARAMS)
    snap = record(context, "snapshot")
    assert snap.value["equity"] == "11300"
    assert observation.observation_id in snap.underlying_refs
    assert service.context(PARAMS)["source_fingerprint"] != before


def test_offline_dsa_turn_reads_ledger_and_passes_receipts_and_grounding(account, monkeypatch):
    from test_dsa_conversation import configured, response
    from src.agents.dsa_conversation import run_dsa_conversation

    _, service = account
    context = service._source(PARAMS)
    snap = record(context, "snapshot")
    answer = {"paragraphs":[{"kind":"fact", "text":{"zh":"当前现金为 10000 CNY。", "en":"Current cash is 10000 CNY."}, "refs":[snap.ref]}], "guides":[]}
    runtime, client, _ = configured(monkeypatch, [
        response(calls=[("s", "get_account_snapshot", {}), ("l", "get_account_ledger_activity", {})]),
        response("Use read ledger records only."),
    ], [answer, {"issues":[]}])
    result = asyncio.run(run_dsa_conversation("现在现金有多少？", context, runtime=runtime))
    assert result["verification"] == "receipts_and_grounding_review_v1"
    assert result["answer"]["paragraphs"] == answer["paragraphs"]
    assert snap.ref in result["read_refs"]
    offered = {tool["name"] for tool in client.responses.create.call_args_list[0].kwargs["tools"]}
    assert "get_account_ledger_activity" in offered
    assert "get_hypothetical_trade_impact" not in offered
