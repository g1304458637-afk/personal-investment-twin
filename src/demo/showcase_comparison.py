"""Comparison export for the shared synthetic showcase accounts.

The account facts live in :mod:`src.demo.showcase`.  This module only binds
those facts to the reusable comparison projection; it does not create a second
portfolio, replay, or financial calculation.
"""
from __future__ import annotations

from typing import Final

from src.compare.research_demo import (
    VERSION as COMPARISON_SCHEMA_VERSION,
    ComparisonExportConfig,
    build_comparison_export,
)
from src.demo import showcase


SHOWCASE_COMPARISON_CONFIG: Final = ComparisonExportConfig(
    source_version=showcase.VERSION,
    synthetic_schedule="declared_synthetic_weekdays_not_exchange_calendar",
    study_start=showcase.START,
    initial_cash=showcase.INITIAL_CASH,
    fund_symbol="SYN_FUND",
    benchmark_symbol="SYN_MARKET",
    # The disclosed synthetic fund composition is a dated source fact, not a
    # derived allocation or an optimization input.
    fund_memberships=(
        ("SYN_GROWTH", "security", 0.40),
        ("SYN_VALUE", "security", 0.35),
        ("SYN_INDUSTRIAL", "security", 0.25),
    ),
    classifications=(
        ("SYN_GROWTH", "growth"),
        ("SYN_VALUE", "value"),
        ("SYN_INDUSTRIAL", "industrial"),
    ),
)


def build_showcase_comparison() -> dict[str, object]:
    """Build the desktop comparison payload from the two shared accounts.

    ``REFERENCE_SUBJECT`` is deliberately the same registered reference
    account used by the same-stock showcase; no comparison-only portfolio is
    manufactured here.  The stable schema version is kept for the existing
    desktop adapter while ``source_version`` identifies these input facts.
    """

    return build_comparison_export(
        subjects=showcase.SUBJECTS,
        input_provider=showcase.showcase_inputs,
        period_labels=(
            ("earlier", showcase.START, showcase.MIDDLE),
            ("recent", showcase.MIDDLE, showcase.END),
            ("full", showcase.START, showcase.END),
        ),
        names={
            **showcase.NAMES,
            showcase.SUBJECT_ID: {"zh": "我的年度投资 · 示例", "en": "My investment year · Example"},
            showcase.REFERENCE_SUBJECT: {"zh": "稳健配置参考 · 模拟", "en": "Balanced allocation reference · Simulated"},
        },
        config=SHOWCASE_COMPARISON_CONFIG,
        schema_version=COMPARISON_SCHEMA_VERSION,
        as_of=showcase.AS_OF,
        source_version=showcase.VERSION,
    )
