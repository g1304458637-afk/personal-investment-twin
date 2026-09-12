"""Registry mapping strategy ids to their close-signal providers.

Adding a strategy = a module with ``evaluate_close_signals`` under
``src/strategy/strategies/`` plus an entry here.  Unknown ids fall back to
the T1 provider so the default demo never breaks.
"""
from __future__ import annotations

from importlib import import_module
from typing import Callable

_PROVIDERS: dict[str, str] = {
    "toujing_t1_breakout_trend": "t1",
    "toujing_dual_ma": "dual_ma",
    "toujing_rsi_mean_reversion": "rsi_mr",
    "toujing_turtle_s2_long": "turtle",
}


def resolve_signals(strategy_id: str, fallback: Callable):
    module_name = _PROVIDERS.get(strategy_id)
    if module_name is None:
        return fallback
    module = import_module(f"src.strategy.strategies.{module_name}")
    return module.evaluate_close_signals
