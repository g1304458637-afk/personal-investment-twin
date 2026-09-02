from pathlib import Path

import pandas as pd
import pytest

from src.core.vectorbt_validation import replay_single_symbol_executions
from src.data.csv_importer import load_normalized_csv
from src.episodes.investment_episode import from_vectorbt_position_record


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CSV = PROJECT_ROOT / "data" / "sample" / "synthetic_executions.csv"
INITIAL_CASH = 100_000.0


@pytest.fixture(scope="module")
def normalized_executions() -> pd.DataFrame:
    return load_normalized_csv(SAMPLE_CSV)


def _replay(executions: pd.DataFrame):
    symbol = executions["symbol"].iat[0]
    valuation_prices = executions.set_index("event_time")["executed_price"].rename(symbol)
    return replay_single_symbol_executions(
        executions,
        valuation_prices,
        init_cash=INITIAL_CASH,
    )


@pytest.fixture(scope="module")
def closed_position_record(normalized_executions: pd.DataFrame) -> pd.Series:
    records = _replay(normalized_executions).positions.records_readable
    assert len(records) == 1
    return records.iloc[0]


def test_synthetic_vectorbt_position_maps_to_investment_episode(
    closed_position_record: pd.Series,
):
    episode = from_vectorbt_position_record(closed_position_record)

    assert episode.episode_id == "investment-episode:600000.SH:0"
    assert episode.symbol == "600000.SH"
    assert episode.size == pytest.approx(1500.0)
    assert episode.entry_time == pd.Timestamp("2025-01-06 09:35:00")
    assert episode.avg_entry_price == pytest.approx(10.333333)
    assert episode.pnl == pytest.approx(3369.1)
    assert episode.return_value == pytest.approx(0.217361, abs=1e-6)
    assert episode.direction == "Long"
    assert episode.status == "Closed"
    assert episode.position_id == 0
    assert episode.valuation_time is None
    assert episode.valuation_price is None


def test_episode_fields_are_copied_from_vectorbt_position_record(
    closed_position_record: pd.Series,
):
    episode = from_vectorbt_position_record(closed_position_record)

    assert episode.symbol == str(closed_position_record["Column"])
    assert episode.size == float(closed_position_record["Size"])
    assert episode.entry_time == pd.Timestamp(closed_position_record["Entry Timestamp"])
    assert episode.avg_entry_price == float(closed_position_record["Avg Entry Price"])
    assert episode.entry_fees == float(closed_position_record["Entry Fees"])
    assert episode.exit_time == pd.Timestamp(closed_position_record["Exit Timestamp"])
    assert episode.avg_exit_price == float(closed_position_record["Avg Exit Price"])
    assert episode.exit_fees == float(closed_position_record["Exit Fees"])
    assert episode.valuation_time is None
    assert episode.valuation_price is None
    assert episode.pnl == float(closed_position_record["PnL"])
    assert episode.return_value == float(closed_position_record["Return"])
    assert episode.direction == str(closed_position_record["Direction"])
    assert episode.status == str(closed_position_record["Status"])
    assert episode.position_id == int(closed_position_record["Position Id"])


def test_converter_does_not_recalculate_vectorbt_metrics(
    closed_position_record: pd.Series,
):
    deliberately_inconsistent = closed_position_record.copy()
    deliberately_inconsistent["PnL"] = -123.45
    deliberately_inconsistent["Return"] = 9.876
    deliberately_inconsistent["Avg Exit Price"] = 999.0

    episode = from_vectorbt_position_record(deliberately_inconsistent)

    assert episode.pnl == -123.45
    assert episode.return_value == 9.876
    assert episode.avg_exit_price == 999.0


def test_open_vectorbt_position_remains_open(normalized_executions: pd.DataFrame):
    open_executions = normalized_executions.iloc[:2].copy()
    record = _replay(open_executions).positions.records_readable.iloc[0]

    episode = from_vectorbt_position_record(record)

    assert record["Status"] == "Open"
    assert episode.status == "Open"
    assert episode.exit_time is None
    assert episode.avg_exit_price is None
    assert episode.exit_fees is None
    assert episode.valuation_time == pd.Timestamp(record["Exit Timestamp"])
    assert episode.valuation_price == float(record["Avg Exit Price"])
    assert episode.pnl == float(record["PnL"])
    assert episode.return_value == float(record["Return"])


def test_missing_vectorbt_field_is_rejected(closed_position_record: pd.Series):
    incomplete = closed_position_record.drop(labels=["PnL"])

    with pytest.raises(ValueError, match="Missing vectorbt Position fields"):
        from_vectorbt_position_record(incomplete)


@pytest.mark.parametrize("field", ["Column", "Direction"])
def test_null_text_identity_field_is_rejected(
    closed_position_record: pd.Series,
    field: str,
):
    record = closed_position_record.copy()
    record[field] = float("nan")

    with pytest.raises(ValueError, match=f"{field} cannot be null"):
        from_vectorbt_position_record(record)
