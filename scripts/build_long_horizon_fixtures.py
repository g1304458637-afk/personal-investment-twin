"""Write deterministic long-horizon Product/method fixtures. No runtime RNG."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = PROJECT_ROOT / "data" / "sample"


def weekdays(start: date, end: date) -> list[date]:
    current = start
    out: list[date] = []
    while current <= end:
        if current.weekday() < 5:
            out.append(current)
        current += timedelta(days=1)
    return out


def lerp(left: float, right: float, t: float) -> float:
    return left + (right - left) * t


def wiggle(day: date) -> float:
    n = (day.toordinal() * 17 + day.month * 29 + day.day * 13) % 11
    return (n - 5) * 0.035


def interpolate(waypoints: list[tuple[date, float]], days: list[date], snaps: dict[date, float]) -> dict[date, float]:
    prices: dict[date, float] = {}
    for day in days:
        if day in snaps:
            prices[day] = snaps[day]
            continue
        if day <= waypoints[0][0]:
            base = waypoints[0][1]
        elif day >= waypoints[-1][0]:
            base = waypoints[-1][1]
        else:
            base = waypoints[-1][1]
            for index in range(1, len(waypoints)):
                start_day, start_price = waypoints[index - 1]
                end_day, end_price = waypoints[index]
                if day <= end_day:
                    span = (end_day - start_day).days
                    t = 0.0 if span == 0 else (day - start_day).days / span
                    base = lerp(start_price, end_price, t)
                    break
        prices[day] = round(max(0.5, base + wiggle(day)), 2)
    return prices


def write_market(path: Path, instrument: str, prices: dict[date, float], days: list[date]) -> None:
    lines = ["date,instrument,close,price_type,data_source,data_version,is_synthetic"]
    for day in days:
        lines.append(
            f"{day.isoformat()},{instrument},{prices[day]:.2f},synthetic,long_horizon_market_v1,v1,true"
        )
    path.write_text("\n".join(lines) + "\n")


def write_executions(path: Path, rows: list[str]) -> None:
    path.write_text(
        "execution_time,symbol,side,quantity,price,fee,currency\n" + "\n".join(rows) + "\n"
    )


def build_closed() -> None:
    days = weekdays(date(2021, 2, 8), date(2025, 7, 16))
    snaps = {
        date(2021, 3, 15): 10.00,
        date(2021, 11, 8): 11.35,
        date(2022, 3, 10): 12.60,
        date(2024, 8, 20): 11.80,
        date(2025, 6, 18): 13.10,
    }
    waypoints = [
        (date(2021, 2, 8), 9.35),
        (date(2021, 3, 15), 10.00),
        (date(2021, 7, 1), 10.85),
        (date(2021, 9, 20), 10.40),
        (date(2021, 11, 8), 11.35),
        (date(2022, 1, 14), 11.90),
        (date(2022, 3, 10), 12.60),
        (date(2022, 6, 15), 14.15),
        (date(2022, 10, 20), 10.45),
        (date(2023, 4, 12), 12.20),
        (date(2023, 9, 8), 13.70),
        (date(2024, 2, 6), 15.25),
        (date(2024, 6, 18), 11.15),
        (date(2024, 8, 20), 11.80),
        (date(2024, 12, 10), 12.40),
        (date(2025, 3, 21), 12.05),
        (date(2025, 6, 18), 13.10),
        (date(2025, 7, 16), 13.35),
    ]
    prices = interpolate(waypoints, days, snaps)
    write_market(SAMPLE / "long_horizon_closed_market_prices_v1.csv", "SYN_LONG_CLOSED", prices, days)
    write_executions(
        SAMPLE / "long_horizon_closed_executions_v1.csv",
        [
            "2021-03-15 09:40:00,SYN_LONG_CLOSED,BUY,400,10.00,3.00,CNY",
            "2021-11-08 10:15:00,SYN_LONG_CLOSED,BUY,300,11.35,2.00,CNY",
            "2022-03-10 13:20:00,SYN_LONG_CLOSED,BUY,400,12.60,2.50,CNY",
            "2024-08-20 10:05:00,SYN_LONG_CLOSED,SELL,500,11.80,4.00,CNY",
            "2025-06-18 14:10:00,SYN_LONG_CLOSED,SELL,600,13.10,4.00,CNY",
        ],
    )
    print("closed observations", len(days))


def build_open() -> None:
    days = weekdays(date(2021, 3, 1), date(2026, 1, 15))
    snaps = {
        date(2021, 4, 6): 10.00,
        date(2022, 1, 12): 11.90,
    }
    waypoints = [
        (date(2021, 3, 1), 9.20),
        (date(2021, 4, 6), 10.00),
        (date(2021, 8, 20), 11.10),
        (date(2021, 11, 30), 10.55),
        (date(2022, 1, 12), 11.90),
        (date(2022, 5, 9), 13.40),
        (date(2022, 11, 15), 10.80),
        (date(2023, 6, 20), 12.90),
        (date(2024, 1, 18), 14.60),
        (date(2024, 8, 7), 12.20),
        (date(2025, 3, 12), 13.85),
        (date(2025, 9, 22), 13.10),
        (date(2026, 1, 15), 13.55),
    ]
    prices = interpolate(waypoints, days, snaps)
    write_market(SAMPLE / "long_horizon_open_market_prices_v1.csv", "SYN_LONG_OPEN", prices, days)
    write_executions(
        SAMPLE / "long_horizon_open_executions_v1.csv",
        [
            "2021-04-06 09:50:00,SYN_LONG_OPEN,BUY,500,10.00,3.00,CNY",
            "2022-01-12 11:05:00,SYN_LONG_OPEN,BUY,400,11.90,2.50,CNY",
        ],
    )
    print("open observations", len(days))


def main() -> int:
    SAMPLE.mkdir(parents=True, exist_ok=True)
    build_closed()
    build_open()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
