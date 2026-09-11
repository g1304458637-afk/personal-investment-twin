"""No network, no model secrets. Research-method integration and evidence boundaries."""
import asyncio
import json

import pytest
from test_account_review import account_context
from test_public_research import _invoke, _context, FakeQuotes
from test_dsa_conversation import configured, response
from src.agents.account_conversation import CONVERSATION_TOOLS, ConversationAnswer, validate_answer, ConversationError
from src.agents.dsa_conversation import run_dsa_conversation
from src.agents.stock_research_methods import METHODS, read_stock_research_method, research_method_record


def test_methods_registered_distinct_and_not_stock_signals(account_context):
    account_context = _context(account_context)
    assert read_stock_research_method in CONVERSATION_TOOLS
    refs = []
    for method in METHODS:
        result = _invoke(read_stock_research_method, account_context, method=method)
        record = result["records"][0]
        refs.append(record["ref"])
        assert result["status"] == "complete"
        assert record["kind"] == "knowledge"
        assert "research_method_not_signal" in record["tags"]
        assert "089d9d26" in record["value"]["sources"][0]
        assert record["ref"] in account_context.retrieved
        status = result["records"][1]
        assert status["kind"] == "research_status"
        assert status["value"]["search_enabled"] is True
        assert status["as_of"].startswith("2026-09-08")
    assert len(set(refs)) == len(METHODS)


def test_method_cannot_be_promoted_to_stock_fact(account_context):
    account_context = _context(account_context)
    result = _invoke(read_stock_research_method, account_context, method="events")
    record = result["records"][0]
    answer = ConversationAnswer.model_validate({"paragraphs": [{"kind": "fact",
        "text": {"zh": "这只股票已经充分反映利好。", "en": "The positive event is already fully priced in."},
        "refs": [record["ref"]]}], "guides": []})
    with pytest.raises(ConversationError, match="fact_source_required") as error:
        validate_answer(answer, {record["ref"]: record}, [record["ref"]])
    assert error.value.details["paragraph_index"] == 0
    assert error.value.details["read_fact_refs"] == []
    assert "do not only relabel" in error.value.details["rule"]
    with pytest.raises(ConversationError, match="unread_reference"):
        validate_answer(answer, {record["ref"]: record}, [])


def test_research_loop_reads_method_and_actual_quotes_without_account_tools(monkeypatch, account_context):
    context = _context(account_context, quotes=FakeQuotes(), enabled=False)
    probe = _context(account_context, quotes=FakeQuotes(), enabled=False)
    method, status = _invoke(read_stock_research_method, probe, method="price_volume")["records"]
    from src.agents.public_research import read_public_daily_ohlcv
    quote = _invoke(read_public_daily_ohlcv, probe, security_id="SZSE:000001",
        start_date="2026-09-01", end_date="2026-09-05", adjust="qfq")["records"][0]
    answer = {"paragraphs": [
        {"kind": "fact", "text": {"zh": "SZSE:000001公开日线收盘10.2 CNY。", "en": "SZSE:000001 public daily close was 10.2 CNY."}, "refs": [quote["ref"]]},
        {"kind": "concept", "text": {"zh": "对照同一口径的价格和量能，放量本身不等于吸筹。", "en": "Compare price and volume on a consistent basis; higher volume alone is not accumulation."}, "refs": [method["ref"]]},
    ], "guides": []}
    rt, client, model = configured(monkeypatch, [
        response(calls=[("method", "read_stock_research_method", {"method": "price_volume"})]),
        response(calls=[("quotes", "read_public_daily_ohlcv", {"security_id": "SZSE:000001", "start_date": "2026-09-01", "end_date": "2026-09-05", "adjust": "qfq"})]),
        response("Use the actual quote and distinguish the general method.")], [answer, {"issues": []}])
    result = asyncio.run(run_dsa_conversation("研究这只股票的量价", context, runtime=rt))
    assert set(result["executed_tools"]) == {"read_stock_research_method", "read_public_daily_ohlcv"}
    assert set(result["read_refs"]) == {method["ref"], status["ref"], quote["ref"]}
    assert set(result["research_read_refs"]) == {method["ref"], status["ref"]}
    assert result["verification"] == "receipts_and_grounding_review_v1"
    assert not context.retrieved  # local research copy only
    first = client.responses.create.call_args_list[0].kwargs
    request = json.loads(first["input"][1]["content"])
    assert request["research_date"].startswith("2026-09-08")
    assert all(r["tools"] == [] for r in model.requests)
    # Verify the actual Python answer through the same TS projection as the UI.
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    client_context = {"version": "account_review_context_v1", "scope": context.scope,
        "source_fingerprint": "test-fingerprint", "finding_options": [],
        "conversation_version": "account_conversation_answer_v2", "record_refs": list(context.records)}
    wire = {**result, "inference_id": "test-inference", "invalidated": False, "source_fingerprint": "test-fingerprint"}
    script = """import {projectAccountAnswer} from './apps/desktop/src/data/agentChat.ts';
let input=''; for await (const part of process.stdin) input+=part;
const {result, context}=JSON.parse(input);
if (!projectAccountAnswer(result, context, 'zh-CN')) process.exit(1);
"""
    subprocess.run(["node", "--input-type=module", "-e", script], cwd=root,
        input=json.dumps({"result": wire, "context": client_context}), text=True, check=True, capture_output=True)


def test_methods_refuse_access_after_cancel(account_context):
    account_context = _context(account_context)
    account_context.access_allowed = lambda: False
    # SDK may serialize a tool exception, but no record may enter the read set.
    try:
        result = _invoke(read_stock_research_method, account_context, method="overview")
    except (ConversationError, json.JSONDecodeError):
        pass
    assert not account_context.retrieved


def test_today_volume_is_not_a_completed_session(account_context):
    import pandas as pd
    from src.agents.public_research import read_public_daily_ohlcv, reset_public_caches
    reset_public_caches()
    ctx = _context(account_context, quotes=FakeQuotes(bars=pd.DataFrame([
        {"日期": "2026-09-08", "开盘": 10, "最高": 11, "最低": 9, "收盘": 10, "成交量": 100}])) )
    result = _invoke(read_public_daily_ohlcv, ctx, security_id="SZSE:000001",
        start_date="2026-09-08", end_date="2026-09-08", adjust="qfq")
    assert result["records"][0]["value"]["latest_bar_may_be_in_progress"] is True
    record = result["records"][0]
    answer = ConversationAnswer.model_validate({"paragraphs": [{"kind": "fact",
        "text": {"zh": "最新收盘10元。", "en": "Latest close is 10."}, "refs": [record["ref"]]}], "guides": []})
    with pytest.raises(ConversationError, match="unconfirmed_close_claim"):
        validate_answer(answer, {record["ref"]: record}, [record["ref"]])
