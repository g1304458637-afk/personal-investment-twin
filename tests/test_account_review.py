import asyncio
import copy
import json
import time
from types import SimpleNamespace

import pandas as pd
import pytest
from agents import ModelSettings, RunConfig
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
from openai.types.shared import Reasoning

from src.agents.account_review import run_account_review
from src.agents.account_review_sources import build_account_review_context
from src.agents.investment_coach import CoachModelRuntime
from src.agents.structured_finalizer import StructuredFinalizationUnavailable
from src.demo import showcase
from src.demo.showcase_runtime import _episode_mapping
from src.episodes.position_episode import build_position_episode_lifecycle
from toujing_core_runtime.account_review import AccountReviewService


class ScriptedModel(Model):
    """Offline SDK model; the real Agent loop executes the registered tools."""

    def __init__(self, script):
        self.script = iter(script)
        self.calls = 0
        self.requests = []

    async def get_response(self, *args, **kwargs):
        self.calls += 1
        self.requests.append(kwargs)
        step = next(self.script)
        if isinstance(step, tuple):
            name, arguments = step
            output = [ResponseFunctionToolCall(
                type="function_call", name=name, call_id=f"call-{self.calls}",
                arguments=json.dumps(arguments),
            )]
        else:
            text = step if isinstance(step, str) else json.dumps(step, ensure_ascii=False)
            output = [ResponseOutputMessage(
                id=f"message-{self.calls}", type="message", role="assistant", status="completed",
                content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
            )]
        return ModelResponse(output=output, usage=Usage(), response_id=f"response-{self.calls}")

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError
        yield


def runtime(model):
    return CoachModelRuntime(
        provider="deepseek", model_name="offline-scripted-model", model=model,
        model_settings=ModelSettings(tool_choice="required", reasoning=Reasoning(effort="none")),
        run_config=RunConfig(tracing_disabled=True),
    )


@pytest.fixture(scope="module")
def account_context():
    service = AccountReviewService(SimpleNamespace())
    params = {
        "scope_kind": "account", "subject_id": showcase.SUBJECT_ID,
        "account_id": showcase.ACCOUNT_ID, "data_mode": "synthetic_showcase",
    }
    context = service._source(params)
    service.close()
    return context


def script_for(choice):
    return [
        ("get_account_snapshot", {}),
        ("get_account_performance", {}),
        ("get_account_behavior", {}),
        ("get_account_self_history", {}),
        ("get_account_episode_index", {}),
        "已读取完整账户范围，候选仅使用已注册记录。",
        choice,
    ]


def test_account_context_needs_no_episode_and_uses_real_account_builders(account_context):
    assert account_context.scope == {
        "scope_kind": "account", "subject_id": showcase.SUBJECT_ID,
        "account_id": showcase.ACCOUNT_ID, "data_mode": "synthetic_showcase",
    }
    assert {record.kind for record in account_context.records.values()} == {
        "snapshot", "performance", "behavior", "self_history", "episode_index",
    }
    episode_ids = {
        item["episode_id"] for item in next(
            record.value["episodes"] for record in account_context.records.values()
            if record.kind == "episode_index"
        )
    }
    assert all(option.episode_id is None or option.episode_id in episode_ids
               for option in account_context.finding_options)
    performance = next(record for record in account_context.records.values() if record.kind == "performance")
    assert performance.method_id == "account_fixed_cash_twr_empyrical_v1"
    assert "period_return" in performance.value and "points" not in performance.value


def test_self_history_keeps_hhi_index_and_turnover_percentage_units_distinct():
    from src.agents.account_review_sources import _self_history_options
    window = {"window": "12m", "status": "complete", "current_value": .4321,
              "comparison_band": "within_historical_iqr", "valid_n": 8}
    record = SimpleNamespace(ref="unit-test", availability="complete", value={
        "default_window": "12m", "metrics": [
            {"metric_id": "portfolio_concentration_hhi", "windows": [window]},
            {"metric_id": "mean_daily_turnover", "windows": [window]},
        ]})
    concentration, turnover = _self_history_options(record)
    for locale in ("zh", "en"):
        assert "0.4321" in concentration.body[locale]
        assert "43.21%" not in concentration.body[locale]
        assert "43.21%" in turnover.body[locale]


def test_account_builders_cut_off_future_executions_and_prices_once():
    _, frame, market, instruments = _episode_mapping(showcase.SUBJECT_ID)
    cutoff = pd.Timestamp("2025-06-30 23:59:00")
    lifecycle = build_position_episode_lifecycle(
        frame, market, subject_id=showcase.SUBJECT_ID, account_id=showcase.ACCOUNT_ID,
        as_of=cutoff, init_cash=showcase.INITIAL_CASH, data_tier="synthetic",
        calculation_code_version="account_review_cutoff_test_v1",
    )
    adversarial_frame = frame.copy(deep=True)
    adversarial_market = market.copy(deep=True)
    adversarial_frame.loc[adversarial_frame.event_time > cutoff, "executed_quantity"] = 1_000_000_000.0
    adversarial_market.loc[
        pd.to_datetime(adversarial_market.date) > cutoff.normalize(), "close"
    ] = 1_000_000_000.0
    display_names = {
        str(item.instrument_id): item.display_name or item.local_symbol
        for item in instruments.values()
    }
    common = dict(
        subject_id=showcase.SUBJECT_ID, account_id=showcase.ACCOUNT_ID,
        data_mode="synthetic_showcase", as_of=cutoff,
        init_cash=showcase.INITIAL_CASH, data_tier="synthetic", currency="CNY",
        lifecycle=lifecycle, display_names=display_names, source_refs=("cutoff-test",),
    )
    actual = build_account_review_context(adversarial_frame, adversarial_market, **common)
    expected = build_account_review_context(
        frame.loc[frame.event_time <= cutoff].copy(),
        market.loc[pd.to_datetime(market.date) <= cutoff.normalize()].copy(),
        **common,
    )
    actual_by_kind = {record.kind: record.value for record in actual.records.values()}
    expected_by_kind = {record.kind: record.value for record in expected.records.values()}
    assert actual_by_kind == expected_by_kind
    assert actual_by_kind["snapshot"]["valuation_date"] == "2025-06-30"
    assert all(item["opened_at"] <= cutoff.isoformat()
               for item in actual_by_kind["episode_index"]["episodes"])


def test_agent_calls_all_readonly_tools_and_only_composes_backend_options(account_context):
    selected = [account_context.finding_options[1].id, account_context.finding_options[2].id]
    model = ScriptedModel(script_for({"finding_ids": selected, "guide_ids": ["pretrade-allocation"]}))
    result = asyncio.run(run_account_review("从全账户看发生了什么？", account_context, runtime=runtime(model)))
    assert set(result["executed_tools"]) == {
        "get_account_snapshot", "get_account_performance", "get_account_behavior",
        "get_account_self_history", "get_account_episode_index",
    }
    expected = {item.id: item.public() for item in account_context.finding_options}
    assert result["answer"]["findings"] == [expected[item] for item in selected]
    assert result["answer"]["guide_ids"] == ["pretrade-allocation"]
    assert account_context.retrieved == set()


def test_model_cannot_select_an_unregistered_finding_id(account_context):
    invalid = {"finding_ids": ["account_finding_not_registered"], "guide_ids": []}
    model = ScriptedModel(script_for(invalid) + [invalid])
    with pytest.raises(StructuredFinalizationUnavailable, match="schema_validation"):
        asyncio.run(run_account_review("分析账户", account_context, runtime=runtime(model)))


def test_missing_completed_tool_receipt_rejects_answer(account_context):
    option = account_context.finding_options[0]
    script = script_for({"finding_ids": [option.id], "guide_ids": []})
    del script[3]  # no self-history call
    model = ScriptedModel(script)
    with pytest.raises(ValueError, match="required_account_tools_not_executed"):
        asyncio.run(run_account_review("分析账户", account_context, runtime=runtime(model)))


def test_invalid_scope_is_rejected_before_desktop_credentials(monkeypatch):
    service = AccountReviewService(SimpleNamespace())
    called = []
    monkeypatch.setattr("toujing_core_runtime.model_service.desktop_runtime", lambda key: called.append(key))
    with pytest.raises(ValueError, match="unregistered_showcase_scope"):
        service.start({
            "scope_kind": "account", "subject_id": "OTHER", "account_id": "OTHER",
            "data_mode": "synthetic_showcase", "allow_model_review": True,
            "question": "分析", "_desktop_model_key": "secret",
        })
    assert called == []
    with pytest.raises(ValueError, match="does_not_accept_episode"):
        service.context({
            "scope_kind": "account", "subject_id": showcase.SUBJECT_ID,
            "account_id": showcase.ACCOUNT_ID, "data_mode": "synthetic_showcase",
            "episode_id": "invented",
        })
    service.close()


@pytest.mark.parametrize("field", ["episode_id", "data_mode", "share_id", "compare_pair"])
def test_malformed_external_scope_metadata_is_a_value_error(field):
    service = AccountReviewService(SimpleNamespace())
    params = {
        "scope_kind": "account", "subject_id": showcase.SUBJECT_ID,
        "account_id": showcase.ACCOUNT_ID, "data_mode": "synthetic_showcase",
        field: ["malformed"],
    }
    with pytest.raises(ValueError):
        service.context(params)
    service.close()


def test_real_source_fingerprint_includes_valuation_driving_account_config():
    class Repo:
        def __init__(self, initial_cash):
            self.initial_cash = initial_cash

        def list_accounts(self):
            return [{"subject_id": "S", "account_id": "A", "initial_cash": self.initial_cash}]

        def executions(self, subject, account):
            return ()

        def prices(self, subject, account):
            return ()

    params = {"scope_kind": "account", "subject_id": "S", "account_id": "A", "data_mode": "real_user"}
    first = AccountReviewService(SimpleNamespace(repo=Repo(100_000)))
    second = AccountReviewService(SimpleNamespace(repo=Repo(200_000)))
    assert first._source_fingerprint(params) != second._source_fingerprint(params)
    first.close()
    second.close()


def test_poll_rejects_future_account_facts_with_source_fingerprint(monkeypatch, account_context):
    import toujing_core_runtime.account_review as account_runtime

    service = AccountReviewService(SimpleNamespace())
    option = account_context.finding_options[0]

    async def fake_run(question, context, **kwargs):
        await asyncio.sleep(0.02)
        return {
            "version": "evidence_grounded_account_review_v1", "scope": context.scope,
            "answer": {"version": "account_review_answer_v1", "summary": {"zh": "摘要", "en": "Summary"},
                       "findings": [option.public()], "guide_ids": []},
        }

    monkeypatch.setattr("toujing_core_runtime.account_review.run_account_review", fake_run)
    monkeypatch.setattr("toujing_core_runtime.model_service.desktop_runtime", lambda key: object())
    params = {
        "scope_kind": "account", "subject_id": showcase.SUBJECT_ID,
        "account_id": showcase.ACCOUNT_ID, "data_mode": "synthetic_showcase",
        "allow_model_review": True, "question": "分析", "_desktop_model_key": "ephemeral",
    }
    started = service.start(params)
    original_fingerprint = account_runtime.showcase_source_fingerprint
    monkeypatch.setattr("toujing_core_runtime.account_review.showcase_source_fingerprint", lambda *args: "future-facts")
    poll_params = {**{key: params[key] for key in ("scope_kind", "subject_id", "account_id", "data_mode")},
                   "job_id": started["job_id"]}
    polled = service.poll(poll_params)
    assert polled == {"status": "stale", "reason": "account_facts_changed", "result": None}
    monkeypatch.setattr("toujing_core_runtime.account_review.showcase_source_fingerprint", original_fingerprint)
    assert service.poll(poll_params) == polled
    assert service.completed == {}
    service.close()


def test_completed_result_echoes_the_context_source_fingerprint(monkeypatch, account_context):
    service = AccountReviewService(SimpleNamespace())
    context = copy.copy(account_context)
    monkeypatch.setattr(service, "_source_with_fingerprint", lambda params: (context, "bound-fingerprint"))
    monkeypatch.setattr(service, "_source_fingerprint", lambda params: "bound-fingerprint")
    monkeypatch.setattr("toujing_core_runtime.model_service.desktop_runtime", lambda key: object())

    async def fake_run(question, current, **kwargs):
        return {
            "version": "evidence_grounded_account_review_v1", "scope": current.scope,
            "answer": {"version": "account_review_answer_v1", "summary": {"zh": "摘要", "en": "Summary"},
                       "findings": [current.finding_options[0].public()], "guide_ids": []},
        }

    monkeypatch.setattr("toujing_core_runtime.account_review.run_account_review", fake_run)
    params = {
        "scope_kind": "account", "subject_id": showcase.SUBJECT_ID,
        "account_id": showcase.ACCOUNT_ID, "data_mode": "synthetic_showcase",
        "allow_model_review": True, "question": "分析", "_desktop_model_key": "ephemeral",
    }
    started = service.start(params)
    poll_params = {**{key: params[key] for key in ("scope_kind", "subject_id", "account_id", "data_mode")},
                   "job_id": started["job_id"]}
    result = None
    for _ in range(100):
        response = service.poll(poll_params)
        if response["status"] == "complete":
            result = response["result"]
            break
        time.sleep(0.005)
    assert result is not None
    assert result["source_fingerprint"] == "bound-fingerprint"
    assert result["scope"] == account_context.scope
    service.close()


def test_only_latest_account_conversation_head_can_continue(monkeypatch, account_context):
    service = AccountReviewService(SimpleNamespace())
    monkeypatch.setattr(service, "_source_with_fingerprint",
                        lambda params: (copy.copy(account_context), "conversation-fingerprint"))
    monkeypatch.setattr(service, "_source_fingerprint", lambda params: "conversation-fingerprint")
    credential_calls = []
    monkeypatch.setattr("toujing_core_runtime.model_service.desktop_runtime",
                        lambda key: credential_calls.append(key) or object())
    received_conversations = []

    async def fake_run(question, current, *, conversation_context=None, **kwargs):
        received_conversations.append(copy.deepcopy(conversation_context))
        return {
            "version": "evidence_grounded_account_review_v1", "scope": current.scope,
            "answer": {"version": "account_review_answer_v1", "summary": {"zh": "摘要", "en": "Summary"},
                       "findings": [current.finding_options[0].public()], "guide_ids": []},
        }

    monkeypatch.setattr("toujing_core_runtime.account_review.run_account_review", fake_run)
    base = {
        "scope_kind": "account", "subject_id": showcase.SUBJECT_ID,
        "account_id": showcase.ACCOUNT_ID, "data_mode": "synthetic_showcase",
        "allow_model_review": True, "_desktop_model_key": "ephemeral",
    }
    poll_scope = {key: base[key] for key in ("scope_kind", "subject_id", "account_id", "data_mode")}

    def complete(question, previous=None):
        started = service.start({**base, "question": question, "previous_inference_id": previous})
        for _ in range(100):
            response = service.poll({**poll_scope, "job_id": started["job_id"]})
            if response["status"] == "complete":
                return response["result"]
            time.sleep(0.005)
        raise AssertionError("account review did not complete")

    first = complete("A")
    second = complete("B", first["inference_id"])
    assert received_conversations[0] is None
    assert [turn["user_question"] for turn in received_conversations[1]["history"]] == ["A"]
    assert service.completed[first["inference_id"]]["result"]["invalidated"] is True
    assert service.completed[first["inference_id"]]["result"]["replaced_by"] == second["inference_id"]
    visible = service.context(poll_scope)["inferences"]
    old = next(item for item in visible if item["inference_id"] == first["inference_id"])
    assert old["invalidated"] is True and old["replaced_by"] == second["inference_id"]

    before = len(credential_calls)
    with pytest.raises(ValueError, match="account_previous_inference_not_latest"):
        service.start({**base, "question": "old branch", "previous_inference_id": first["inference_id"]})
    assert len(credential_calls) == before  # rejected before model construction

    third_start = service.start({**base, "question": "C", "previous_inference_id": second["inference_id"]})
    assert third_start["status"] == "running"
    assert len(credential_calls) == before + 1
    service.close()


def test_followup_is_owned_fingerprinted_and_bounded_to_three_turns(account_context):
    service = AccountReviewService(SimpleNamespace())
    fingerprint = "f" * 64
    scope = account_context.scope
    previous_id = None
    expected = []
    for index in range(5):
        inference_id = f"account_inference_{index}"
        answer = {
            "version": "account_review_answer_v1", "summary": {"zh": "摘要", "en": "Summary"},
            "findings": [account_context.finding_options[0].public()], "guide_ids": [],
        }
        history = [] if previous_id is None else service._history(
            previous_id, scope=scope, source_fingerprint=fingerprint)
        service.completed[inference_id] = {
            "scope": copy.deepcopy(scope), "source_fingerprint": fingerprint,
            "question": f"q{index}", "history": history,
            "result": {"answer": answer},
        }
        previous_id = inference_id
        expected.append(f"q{index}")
    history = service._history(previous_id, scope=scope, source_fingerprint=fingerprint)
    assert [turn["user_question"] for turn in history] == expected[-3:]
    with pytest.raises(ValueError, match="unavailable"):
        service._history(previous_id, scope={**scope, "account_id": "OTHER"}, source_fingerprint=fingerprint)
    with pytest.raises(ValueError, match="stale"):
        service._history(previous_id, scope=scope, source_fingerprint="changed")
    service.close()
