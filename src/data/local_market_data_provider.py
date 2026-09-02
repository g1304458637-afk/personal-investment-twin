from __future__ import annotations

from pathlib import Path

import pandas as pd


PRICE_COLUMNS = {
    "date",
    "instrument",
    "close",
    "price_type",
    "data_source",
    "data_version",
    "is_synthetic",
}

INDUSTRY_COLUMNS = {
    "symbol",
    "industry_id",
    "industry_name",
    "valid_from",
    "valid_to",
    "classification",
    "data_source",
    "data_version",
    "is_synthetic",
}

BENCHMARK_COLUMNS = {
    "benchmark_id",
    "benchmark_name",
    "benchmark_type",
}


class LocalMarketDataProvider:
    def __init__(self, root: str | Path = "data/reference") -> None:
        self.root = Path(root)

        self.prices = pd.read_csv(self.root / "prices.csv")
        self.industry_membership = pd.read_csv(
            self.root / "industry_membership.csv"
        )
        self.benchmark_mapping = pd.read_csv(
            self.root / "benchmark_mapping.csv"
        )

        self._validate()
        self._normalize()

    def _validate(self) -> None:
        missing_prices = PRICE_COLUMNS - set(self.prices.columns)
        missing_industry = INDUSTRY_COLUMNS - set(
            self.industry_membership.columns
        )
        missing_benchmarks = BENCHMARK_COLUMNS - set(
            self.benchmark_mapping.columns
        )

        if missing_prices:
            raise ValueError(
                f"Missing price columns: {sorted(missing_prices)}"
            )

        if missing_industry:
            raise ValueError(
                f"Missing industry columns: {sorted(missing_industry)}"
            )

        if missing_benchmarks:
            raise ValueError(
                f"Missing benchmark columns: {sorted(missing_benchmarks)}"
            )

    def _normalize(self) -> None:
        self.prices["date"] = pd.to_datetime(self.prices["date"])
        self.prices["close"] = pd.to_numeric(
            self.prices["close"],
            errors="raise",
        )

        self.industry_membership["valid_from"] = pd.to_datetime(
            self.industry_membership["valid_from"]
        )
        self.industry_membership["valid_to"] = pd.to_datetime(
            self.industry_membership["valid_to"],
            errors="coerce",
        )

    def get_prices(
        self,
        instruments: list[str],
        start: str | pd.Timestamp,
        end: str | pd.Timestamp,
    ) -> pd.DataFrame:
        start = pd.Timestamp(start)
        end = pd.Timestamp(end)

        result = self.prices[
            self.prices["instrument"].isin(instruments)
            & self.prices["date"].between(start, end)
        ].copy()

        return result.sort_values(
            ["instrument", "date"]
        ).reset_index(drop=True)

    def get_industry(
        self,
        symbol: str,
        as_of: str | pd.Timestamp,
    ) -> pd.Series:
        as_of = pd.Timestamp(as_of)

        rows = self.industry_membership[
            (self.industry_membership["symbol"] == symbol)
            & (self.industry_membership["valid_from"] <= as_of)
            & (
                self.industry_membership["valid_to"].isna()
                | (self.industry_membership["valid_to"] >= as_of)
            )
        ]

        if len(rows) == 0:
            raise LookupError(
                f"No point-in-time industry membership for "
                f"{symbol} at {as_of.date()}"
            )

        if len(rows) > 1:
            raise ValueError(
                f"Multiple industry memberships for "
                f"{symbol} at {as_of.date()}"
            )

        return rows.iloc[0]

    def get_benchmark(
        self,
        benchmark_id: str,
    ) -> pd.Series:
        rows = self.benchmark_mapping[
            self.benchmark_mapping["benchmark_id"] == benchmark_id
        ]

        if len(rows) == 0:
            raise LookupError(
                f"Unknown benchmark: {benchmark_id}"
            )

        if len(rows) > 1:
            raise ValueError(
                f"Duplicate benchmark: {benchmark_id}"
            )

        return rows.iloc[0]
