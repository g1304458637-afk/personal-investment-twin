import pytest

from test_import_confirmation import confirmed
from test_product_runtime import ROOT, trade_params, _market_params
from toujing_core_runtime.product import ProductRuntime


@pytest.mark.parametrize("currency", ["USD", "CNY", ""])
def test_currency_survives_runtime_projection_without_inference(tmp_path, currency):
    runtime = ProductRuntime(tmp_path / "db")
    try:
        trade = tmp_path / "trades.csv"
        trade.write_text((ROOT / "tests/fixtures/ingestion/fixture_a_lifecycle.csv").read_text().replace(",CNY,", f",{currency},"))
        market = tmp_path / "prices.csv"
        market.write_text((ROOT / "tests/fixtures/market_data/runtime_lifecycle_prices.csv").read_text().replace(",CNY,", f",{currency or 'CNY'},"))
        params = {**trade_params(), "file_path": str(trade)}
        runtime.commit_trade(confirmed(runtime, "trade", params))
        runtime.commit_market(confirmed(runtime, "market", {**_market_params(), "file_path": str(market)}))
        listing = runtime.investments(params)
        assert listing["portfolio_state_status"] == "available"
        assert all(item["currency"] == (currency or None) for item in listing["episodes"])
        open_episode = next(item for item in listing["episodes"] if item["status"] == "open")
        result = runtime.episode({**params, "episode_id": open_episode["episode_id"]})
        assert result["entry"]["instrument"]["currency"] == (currency or None)
        assert open_episode["quantity"] == 20
        assert result["entry"]["snapshot"] is not None
        assert runtime.episode({**params, "episode_id": "demo-or-other-owner"})["entry"] is None
    finally:
        runtime.close()


def test_mixed_currency_facts_are_stored_but_never_replayed_as_one_cash_ledger(tmp_path, monkeypatch):
    runtime = ProductRuntime(tmp_path / "db")
    try:
        file = tmp_path / "mixed.csv"
        file.write_text((ROOT / "tests/fixtures/ingestion/fixture_a_lifecycle.csv").read_text().replace(",CNY,", ",USD,", 1))
        params = {**trade_params(), "file_path": str(file)}
        runtime.commit_trade(confirmed(runtime, "trade", params))
        monkeypatch.setattr("toujing_core_runtime.product.build_episode_when_market_ready", lambda *a, **k: pytest.fail("mixed currency reached replay"))
        assert len(runtime.repo.executions("local-user", "ACC-1")) == 5
        listing = runtime.investments(params)
        assert listing["portfolio_state_reason"] == "unavailable_mixed_currency_without_fx"
        assert listing["episodes"] == []
    finally:
        runtime.close()
