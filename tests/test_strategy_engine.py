"""Engine-level tests: point-in-time universe, ranking, windows, determinism,
and the future-data invariance guarantee."""
from __future__ import annotations

import pandas as pd

from src.strategy.data import load_simulation_data
from src.strategy.engine import run_simulation
from src.strategy.strategies.t1 import build_t1_spec
from tests.strategy_fixtures import bar, dataset_writer, day, flat_bar, run, run_params

ROOT = None  # set in tests via __file__ math when the shipped fixture is needed


def bdays(start: str, count: int) -> list[str]:
    return [value.date().isoformat() for value in pd.bdate_range(start, periods=count)]


def test_universe_membership_is_point_in_time(dataset_writer, tmp_path):
    days = bdays("2025-01-02", 60)
    list_date = days[22]
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days[22:47]]
    bars.append(bar(days[47], "SYN_POOL_B01", 10.0, 11.5, 10.0, 11.5))
    bars.append(bar(days[48], "SYN_POOL_B01", 11.5, 11.5, 11.5, 11.5))
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": list_date, "delist_date": ""}]
    data, result, payload = run(dataset_writer(universe, bars))
    # Not selectable before listing, selectable after.
    assert data.listed_on(day(days[0])) == ()
    assert data.listed_on(day(list_date)) == ("SYN_POOL_B01",)
    # The simulation calendar spans the bar dates: it starts at the listing day.
    assert result.days[0].day == day(list_date) and result.days[0].universe_count == 1
    # 25 valid closes exist before the breakout, so the entry fills on day 48.
    fills = [item for item in result.fills]
    assert [item.day.isoformat() for item in fills] == [days[48]]
    # A delisted member leaves the point-in-time universe on its delist date.
    member = data.members["SYN_POOL_B01"]
    assert data.listed_on(member.list_date) == ("SYN_POOL_B01",)


def test_delisted_member_is_never_selectable(dataset_writer):
    days = bdays("2025-01-02", 30)
    bars = [flat_bar(text, "SYN_POOL_B02", 10.0) for text in days[:25]]
    universe = [{"instrument": "SYN_POOL_B02", "display_name": "B02",
                 "list_date": days[0], "delist_date": days[26]}]
    data, result, _ = run(dataset_writer(universe, bars))
    assert data.listed_on(day(days[25])) == ("SYN_POOL_B02",)
    assert data.listed_on(day(days[26])) == ()
    assert data.listed_on(day(days[29])) == ()
    assert result.fills == [] and result.orders == []


def test_windows_count_valid_observations_not_calendar_days(dataset_writer):
    days = bdays("2025-01-02", 60)
    # 25 valid closes with a five-session hole in the middle, then a breakout.
    valid = days[:22] + days[27:31]  # 26 valid sessions total
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in valid[:25]]
    bars.append(bar(valid[25], "SYN_POOL_B01", 10.0, 11.5, 10.0, 11.5))
    bars.append(bar(days[31], "SYN_POOL_B01", 11.5, 11.5, 11.5, 11.5))
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    data, result, _ = run(dataset_writer(universe, bars))
    series = data.series["SYN_POOL_B01"]
    # The observation array keeps every session with a bar and no others:
    # windows count observations, so the entry still lands on the 26th valid close.
    assert list(series.dates) == [day(text) for text in valid] + [day(days[31])]
    assert result.orders, "breakout must trigger the first entry"
    assert result.orders[0].signal_date == day(valid[25])
    assert result.fills[0].day == day(days[31])


def test_ranking_picks_the_strongest_breakout_within_remaining_slots(dataset_writer):
    days = bdays("2025-01-02", 28)
    bars = []
    for instrument, base in (("SYN_POOL_B01", 10.0), ("SYN_POOL_B02", 20.0)):
        bars.extend(flat_bar(text, instrument, base) for text in days[:25])
        strength = 0.12 if instrument == "SYN_POOL_B01" else 0.06
        close = base * (1.0 + strength)
        bars.append(bar(days[25], instrument, base, close, base, close))
        bars.append(bar(days[26], instrument, close, close, close, close))
        bars.append(bar(days[27], instrument, close, close, close, close))
    universe = [{"instrument": name, "display_name": name, "list_date": days[0],
                 "delist_date": ""} for name in ("SYN_POOL_B01", "SYN_POOL_B02")]
    _, result, payload = run(dataset_writer(universe, bars),
                             params=run_params(max_positions=1))
    signal_day = next(item for item in payload["days"] if item["date"] == days[25])
    assert [(item["instrument"], item["selected"]) for item in signal_day["candidates"]] == [
        ("SYN_POOL_B01", True), ("SYN_POOL_B02", False)]
    assert [item.instrument for item in result.orders] == ["SYN_POOL_B01"]
    assert result.orders[0].rank == 1


def test_reruns_of_the_same_spec_and_data_are_identical(dataset_writer):
    days = bdays("2025-01-02", 40)
    bars = [flat_bar(text, "SYN_POOL_B01", 10.0) for text in days[:25]]
    bars.append(bar(days[25], "SYN_POOL_B01", 10.0, 11.5, 10.0, 11.5))
    bars.extend(flat_bar(text, "SYN_POOL_B01", 11.5) for text in days[26:])
    universe = [{"instrument": "SYN_POOL_B01", "display_name": "B01",
                 "list_date": days[0], "delist_date": ""}]
    directory = dataset_writer(universe, bars)
    data = load_simulation_data(directory)
    spec = build_t1_spec()
    from src.strategy.report import result_to_dict
    first = result_to_dict(run_simulation(spec, data))
    second = result_to_dict(run_simulation(spec, data))
    assert first == second


def test_modifying_future_prices_cannot_change_past_days(tmp_path):
    """The minimum handoff test: edits after a cutoff leave earlier days byte-equal."""
    import shutil
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / "data/sample/strategy_universe"
    working = tmp_path / "universe"
    working.mkdir()
    for name in ("universe.csv", "corporate_actions.csv"):
        shutil.copy(source / name, working / name)
    cutoff = "2024-06-01"
    scaled: list[str] = []
    for line in (source / "prices.csv").read_text(encoding="utf-8").splitlines():
        parts = line.split(",")
        if len(parts) == 6 and parts[0] > cutoff and parts[1] == "SYN_POOL_A01":
            parts[2:] = [f"{float(value) * 1.5:.2f}" for value in parts[2:]]
            scaled.append(",".join(parts))
        else:
            scaled.append(line)
    (working / "prices.csv").write_text("\n".join(scaled) + "\n", encoding="utf-8")
    data = load_simulation_data(source)
    modified = load_simulation_data(working)
    assert data.fingerprint != modified.fingerprint
    from src.strategy.report import result_to_dict
    base = result_to_dict(run_simulation(build_t1_spec(), data))
    after = result_to_dict(run_simulation(build_t1_spec(), modified))
    assert [item for item in base["days"] if item["date"] <= cutoff] == \
        [item for item in after["days"] if item["date"] <= cutoff]
    assert [item for item in base["fills"] if item["day"] <= cutoff] == \
        [item for item in after["fills"] if item["day"] <= cutoff]
    assert [item for item in base["orders"] if item["signal_date"] < cutoff] == \
        [item for item in after["orders"] if item["signal_date"] < cutoff]
    # Sanity: the tampering does change the later path.
    assert base["summary"]["final_equity"] != after["summary"]["final_equity"]
