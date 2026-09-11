"""Versioned strategy specification objects.

A strategy spec is data, not code paths: the engine reads rule parameters from
it, journals must embed it, and two specs with different params must never be
compared as "the same strategy".
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class StrategySpec:
    strategy_id: str
    version: str
    title: str
    description: str
    # Each entry documents one rule: id, source class (lens_rule | adaptation), statement.
    rule_table: tuple[dict[str, str], ...]
    params: dict[str, float | int | str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "strategy_id": self.strategy_id,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "rule_table": [dict(rule) for rule in self.rule_table],
            "params": dict(self.params),
        }
