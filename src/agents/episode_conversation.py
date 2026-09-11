"""Restricted Episode projection for the shared DSA conversation engine.

No financial calculations: select already-built actual outcomes. The projection
is applied before model access, not merely requested in a system prompt.
"""
from dataclasses import replace
from src.agents.account_review_sources import _stable_id


EPISODE_TOOL_NAMES = frozenset({
    "get_account_episode_index", "get_investment_results", "get_investment_details",
    "read_financial_concept", "identify_public_security", "read_public_daily_ohlcv",
    "read_public_quote_snapshot", "search_public_web", "read_stock_research_method",
    "read_public_technical_indicators", "read_public_financials",
})


def focus_episode_context(context, requested_id):
    """Mutate an unshared, fresh context; reject IDs outside the owned account."""
    details = [r for r in context.conversation_records.values() if r.kind == "episode_detail"
               and (r.episode_id == requested_id or context.episode_display_ids.get(r.episode_id) == requested_id)]
    if len(details) != 1:
        raise ValueError("owned_episode_unavailable")
    detail = details[0]
    canonical = detail.episode_id
    execution_refs = tuple(sorted({operation["execution_id"]
        for operation in detail.value.get("operations", [])}))
    def scoped_value(value):
        # The replay builders include account-import provenance. Retain only
        # this Episode's actual execution references in the conversational view.
        if isinstance(value, dict):
            return {key: ([ref for ref in child if ref in execution_refs]
                          if key == "execution_refs" else scoped_value(child))
                    for key, child in value.items() if key not in {"provenance", "underlying_refs"}}
        if isinstance(value, (list, tuple)):
            return [scoped_value(child) for child in value]
        return value
    detail = replace(detail, underlying_refs=execution_refs, value=scoped_value(detail.value),
                     ref=_stable_id("account_fact_", {"source": detail.ref, "episode_scope": canonical}))
    records = {}
    for r in (*context.records.values(), *context.conversation_records.values()):
        if r.kind not in {"episode_index", "episode_results"}:
            continue
        rows = [row for row in r.value["episodes"] if row["episode_id"] == canonical]
        if not rows:
            continue
        value = scoped_value({**r.value, "episodes": rows})
        selected = replace(r, ref=_stable_id("account_fact_", {"source": r.ref, "episode": canonical}),
                           episode_id=canonical, underlying_refs=execution_refs, value=value)
        records[selected.ref] = selected
    context.records = records
    context.conversation_records = {detail.ref: detail}
    context.finding_options = ()
    context.episode_display_ids = {canonical: context.episode_display_ids.get(canonical, canonical)}
    context.focus_episode_id = requested_id
    context.retrieved = set()
    from src.agents.account_review_sources import PREPARED_HHI_HISTORY_ATTRIBUTE
    from src.agents.owned_analysis_tools import MATERIALIZER_ATTRIBUTE
    if hasattr(context, MATERIALIZER_ATTRIBUTE):
        delattr(context, MATERIALIZER_ATTRIBUTE)
    if hasattr(context, PREPARED_HHI_HISTORY_ATTRIBUTE):
        delattr(context, PREPARED_HHI_HISTORY_ATTRIBUTE)
    context.public_research = None
    return context
