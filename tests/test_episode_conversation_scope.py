from __future__ import annotations

import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
from agents.tool_context import ToolContext

from src.agents.account_conversation import CONVERSATION_TOOLS, get_investment_details
from src.agents.account_conversation import run_account_conversation
from src.agents.episode_conversation import EPISODE_TOOL_NAMES, focus_episode_context
from src.agents.account_review_sources import PREPARED_HHI_HISTORY_ATTRIBUTE
from src.agents.owned_analysis_tools import MATERIALIZER_ATTRIBUTE, hypothetical_trade_impact
from src.demo import showcase
from src.demo.showcase_runtime import _episode_mapping, _lifecycle
from toujing_core_runtime.account_review import AccountReviewService, _scope
from toujing_core_runtime.product import ProductRuntime
from test_account_review import ScriptedModel, runtime as scripted_runtime


@pytest.fixture(scope="module")
def episode_source():
    identities, frame, market, instruments = _episode_mapping(showcase.SUBJECT_ID)
    lifecycle = _lifecycle(frame, market, subject_id=showcase.SUBJECT_ID)
    selected = lifecycle.episodes[0]
    canonical = selected.episode_id
    display = str(identities[canonical]["display_episode_id"])
    return canonical, display, selected, lifecycle


def _params(scope_kind: str, episode_id: str | None = None) -> dict[str, object]:
    return {
        "scope_kind": scope_kind,
        "subject_id": showcase.SUBJECT_ID,
        "account_id": showcase.ACCOUNT_ID,
        "data_mode": "synthetic_showcase",
        **({"episode_id": episode_id} if episode_id is not None else {}),
    }


def _episode_rows(context):
    rows = []
    for record in (*context.records.values(), *context.conversation_records.values()):
        if isinstance(record.value, dict):
            rows.extend(record.value.get("episodes", ()))
    return rows


def _walk(value):
    yield value
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk(child)


def test_scope_requires_an_explicit_kind_and_episode_identity():
    account = _scope(_params("account"))
    assert account == {
        "scope_kind": "account",
        "subject_id": showcase.SUBJECT_ID,
        "account_id": showcase.ACCOUNT_ID,
        "data_mode": "synthetic_showcase",
    }
    with pytest.raises(ValueError, match="scope_kind_required"):
        _scope({"subject_id": showcase.SUBJECT_ID, "account_id": showcase.ACCOUNT_ID})
    with pytest.raises(ValueError, match="episode_id_required"):
        _scope(_params("episode"))
    with pytest.raises(ValueError, match="does_not_accept_episode_id"):
        _scope(_params("account", "unexpected"))


def test_focused_context_accepts_canonical_and_display_ids_but_rejects_foreign(episode_source):
    canonical, display, _, _ = episode_source
    service = AccountReviewService(SimpleNamespace())
    try:
        canonical_context = service._source(_params("episode", canonical))
        display_context = service._source(_params("episode", display))
        assert canonical_context.scope["episode_id"] == canonical
        assert display_context.scope["episode_id"] == display
        assert _episode_rows(canonical_context) == _episode_rows(display_context)
        assert {row["episode_id"] for row in _episode_rows(canonical_context)} == {canonical}
        with pytest.raises(ValueError, match="owned_episode_unavailable"):
            service._source(_params("episode", "foreign-account-episode"))
    finally:
        service.close()


def test_focused_context_excludes_account_records_and_private_owned_sources(episode_source):
    canonical, _, selected, lifecycle = episode_source
    service = AccountReviewService(SimpleNamespace())
    try:
        account = service._source(_params("account"))
        focused = service._source(_params("episode", canonical))
        assert hasattr(account, MATERIALIZER_ATTRIBUTE)
        assert not hasattr(focused, MATERIALIZER_ATTRIBUTE)
        assert not hasattr(focused, PREPARED_HHI_HISTORY_ATTRIBUTE)
        assert focused.finding_options == ()
        assert {record.kind for record in focused.records.values()} == {
            "episode_index", "episode_results",
        }
        assert {record.kind for record in focused.conversation_records.values()} == {
            "episode_detail",
        }
        forbidden = {"snapshot", "performance", "performance_path", "behavior", "self_history", "allocation"}
        assert not forbidden & {
            record.kind for record in (*focused.records.values(), *focused.conversation_records.values())
        }

        # Opaque execution provenance is still account data. A focused read may
        # bind the selected episode's operations, never IDs from another episode.
        selected_execution_ids = set(selected.execution_refs)
        exposed_execution_ids = {
            ref
            for record in (*focused.records.values(), *focused.conversation_records.values())
            for ref in record.underlying_refs
            if ":execution:" in ref
        }
        assert exposed_execution_ids <= selected_execution_ids
        other_instrument_ids = {
            item.instrument_id for item in lifecycle.episodes
            if item.instrument_id != selected.instrument_id
        }
        assert not any(
            instrument_id in ref
            for record in (*focused.records.values(), *focused.conversation_records.values())
            for ref in record.underlying_refs
            for instrument_id in other_instrument_ids
        )
        all_value_items = tuple(
            item
            for record in (*focused.records.values(), *focused.conversation_records.values())
            for item in _walk(record.value)
        )
        assert "provenance" not in all_value_items
        assert "underlying_refs" not in all_value_items
        foreign_value_refs = {
            ref
            for episode in lifecycle.episodes if episode.episode_id != canonical
            for ref in episode.execution_refs
        } | other_instrument_ids
        assert not any(
            isinstance(item, str) and foreign_ref in item
            for item in all_value_items
            for foreign_ref in foreign_value_refs
        )
    finally:
        service.close()


def test_display_id_can_read_the_already_focused_episode_detail(episode_source):
    _, display, _, _ = episode_source
    service = AccountReviewService(SimpleNamespace())
    try:
        focused = service._source(_params("episode", display))
        # The conversation runner merges its two scoped record maps before a
        # tool call. Exercise the actual tool boundary with the display alias.
        focused.records = {**focused.records, **focused.conversation_records}
        encoded = json.dumps({"episode_id": display})
        tool_context = ToolContext(
            focused,
            tool_name=get_investment_details.name,
            tool_call_id="episode-detail-alias",
            tool_arguments=encoded,
        )
        payload = json.loads(asyncio.run(
            get_investment_details.on_invoke_tool(tool_context, encoded)
        ))
        assert payload["status"] == "complete"
        assert len(payload["records"]) == 1
    finally:
        service.close()


def test_focusing_a_deepcopy_of_preattached_account_removes_private_access(episode_source):
    canonical, _, _, _ = episode_source
    service = AccountReviewService(SimpleNamespace())
    try:
        account = service._source(_params("account"))
        account.public_research = object()
        assert hasattr(account, MATERIALIZER_ATTRIBUTE)
        focused = focus_episode_context(copy.deepcopy(account), canonical)
        assert not hasattr(focused, MATERIALIZER_ATTRIBUTE)
        assert focused.public_research is None
        assert hasattr(account, MATERIALIZER_ATTRIBUTE)
        assert account.public_research is not None
    finally:
        service.close()


def test_account_and_episode_source_caches_are_isolated_and_copy_safe(episode_source):
    canonical, _, _, _ = episode_source
    service = AccountReviewService(SimpleNamespace())
    try:
        account, account_fingerprint = service._source_with_fingerprint(_params("account"))
        focused, episode_fingerprint = service._source_with_fingerprint(_params("episode", canonical))
        assert account_fingerprint != episode_fingerprint
        assert len(service._source_cache) == 2
        assert hasattr(account, MATERIALIZER_ATTRIBUTE)
        assert not hasattr(focused, MATERIALIZER_ATTRIBUTE)

        focused.records.clear()
        rebuilt, rebuilt_fingerprint = service._source_with_fingerprint(_params("episode", canonical))
        assert rebuilt_fingerprint == episode_fingerprint
        assert {record.kind for record in rebuilt.records.values()} == {
            "episode_index", "episode_results",
        }
        account_again, _ = service._source_with_fingerprint(_params("account"))
        assert {record.kind for record in account_again.records.values()} >= {
            "snapshot", "performance", "behavior", "self_history", "episode_index",
        }
    finally:
        service.close()


def test_review_runtime_dispatches_showcase_episode_without_model_or_credentials(tmp_path, episode_source):
    canonical, display, _, _ = episode_source
    product = ProductRuntime(tmp_path / "episode-scope.sqlite3")
    try:
        runtime = product.review_runtime()
        account = runtime.context(_params("account"))
        focused = runtime.context(_params("episode", display))
        assert account["scope"]["scope_kind"] == "account"
        assert focused["scope"] == {
            "scope_kind": "episode",
            "subject_id": showcase.SUBJECT_ID,
            "account_id": showcase.ACCOUNT_ID,
            "data_mode": "synthetic_showcase",
            "episode_id": display,
        }
        assert focused["episode_ids"] == [canonical]
        assert focused["finding_options"] == []
        assert {item["kind"] for item in focused["capabilities"]} == {
            "episode_index", "episode_results",
        }
        assert focused["source_fingerprint"] != account["source_fingerprint"]
    finally:
        product.close()


def test_episode_agent_is_dsa_v2_only_and_filters_account_wide_tools(monkeypatch, episode_source):
    canonical, _, _, _ = episode_source
    service = AccountReviewService(SimpleNamespace())
    desktop_calls = []
    monkeypatch.setattr(
        "toujing_core_runtime.model_service.desktop_runtime",
        lambda key: desktop_calls.append(key),
    )
    base = {
        **_params("episode", canonical),
        "allow_model_review": True,
        "question": "只分析这一轮",
    }
    try:
        with pytest.raises(ValueError, match="episode_conversation_requires_dsa_v2"):
            service.start(base)
        with pytest.raises(ValueError, match="dsa_conversation_requires_v2_answer"):
            service.start({**base, "conversation_engine": "dsa"})
        with pytest.raises(ValueError, match="episode_conversation_requires_dsa_v2"):
            service.start({
                **base,
                "conversation_engine": "legacy",
                "answer_version": "account_conversation_answer_v2",
            })
        assert desktop_calls == []

        names = {tool.name for tool in CONVERSATION_TOOLS}
        focused_names = names & EPISODE_TOOL_NAMES
        assert {
            "get_account_episode_index", "get_investment_results", "get_investment_details",
            "read_financial_concept",
        } <= focused_names
        assert not {
            "get_account_snapshot", "get_account_performance", "get_account_behavior",
            "get_account_self_history", "get_account_performance_path", "get_current_allocation",
            "get_hypothetical_trade_impact", "get_owned_period_comparison",
            "get_owned_same_stock_comparison",
        } & focused_names
    finally:
        service.close()


def test_v2_output_classifies_owned_analysis_refs_separately():
    service = AccountReviewService(SimpleNamespace())
    try:
        context = service._source(_params("account"))
        probe = copy.deepcopy(context)
        probe_payload = json.loads(hypothetical_trade_impact(
            probe,
            symbol="SYN_GROWTH",
            side="BUY",
            quantity=300,
            execution_price=14.4,
            fees=None,
        ))
        ref = probe_payload["records"][0]["ref"]
        answer = {
            "paragraphs": [{
                "kind": "fact",
                "text": {
                    "zh": "需要先明确这笔假设交易的费用，才能计算前后变化。",
                    "en": (
                        "The hypothetical fee must be specified before the "
                        "before-and-after change can be calculated."
                    ),
                },
                "refs": [ref],
            }],
            "guides": [],
        }
        model = ScriptedModel([
            ("get_hypothetical_trade_impact", {
                "symbol": "SYN_GROWTH",
                "side": "BUY",
                "quantity": 300,
                "execution_price": 14.4,
                "fees": None,
            }),
            "The registered hypothetical requires an explicit fee.",
            answer,
            {"issues": [], "findings": []},
        ])
        result = asyncio.run(run_account_conversation(
            "买入后有什么变化？",
            context,
            runtime=scripted_runtime(model),
        ))
        assert result["analysis_read_refs"] == [ref]
        assert result["public_read_refs"] == []
        assert result["research_read_refs"] == []
        assert result["read_refs"] == [ref]
    finally:
        service.close()
