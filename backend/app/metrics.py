"""Gate-time vintage selection and forecast error metrics.

Error is forecast minus actual. A positive error means the wind forecast was
high, so a buyer who treated it as exact would have bought too little other power.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

DECISION_START = date(2026, 1, 1)
DECISION_END = date(2026, 1, 31)


@dataclass(frozen=True)
class Auction:
    id: str
    label: str
    gate: time
    detail: str


AUCTIONS: dict[str, Auction] = {
    "epex_hourly": Auction(
        "epex_hourly",
        "EPEX hourly",
        time(9, 20),
        "Day-ahead hourly auction, gate 09:20 UK",
    ),
    "n2ex": Auction(
        "n2ex",
        "N2EX hourly",
        time(9, 50),
        "Day-ahead hourly auction, gate 09:50 UK",
    ),
    "epex_half_hourly": Auction(
        "epex_half_hourly",
        "EPEX half-hourly",
        time(15, 30),
        "Day-ahead half-hourly auction, gate 15:30 UK",
    ),
}


def parse_time(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def iso_z(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def decision_dates() -> list[date]:
    days = (DECISION_END - DECISION_START).days
    return [DECISION_START + timedelta(days=offset) for offset in range(days + 1)]


def delivery_date(decision: date) -> date:
    return decision + timedelta(days=1)


def gate_time(decision: date, auction: Auction) -> datetime:
    return datetime.combine(decision, auction.gate, tzinfo=timezone.utc)


def select_publish_time(publish_times: list[datetime], gate: datetime) -> datetime | None:
    """Latest publication that already existed when the auction closed."""
    eligible = [published for published in publish_times if published <= gate]
    if not eligible:
        return None
    return max(eligible)


def hour_starts(delivery: date) -> list[datetime]:
    midnight = datetime(delivery.year, delivery.month, delivery.day, tzinfo=timezone.utc)
    return [midnight + timedelta(hours=hour) for hour in range(24)]


def hourly_actual_mw(actuals: dict[datetime, float], hour_start: datetime) -> float | None:
    """Average the two half-hour outturns that make up the clock hour."""
    first = actuals.get(hour_start)
    second = actuals.get(hour_start + timedelta(minutes=30))
    if first is None or second is None:
        return None
    return (first + second) / 2.0


def _keyed(rows: dict[str, float]) -> dict[datetime, float]:
    return {parse_time(stamp): value for stamp, value in rows.items()}


def prepare(forecasts: dict[str, dict[str, float]], actuals: dict[str, float]) -> dict:
    """Parse timestamps once so a full month does not repeat that work."""
    by_publish: dict[datetime, dict[datetime, float]] = {}
    by_delivery: dict[date, set[datetime]] = {}
    for stamp, hours in forecasts.items():
        published = parse_time(stamp)
        parsed = _keyed(hours)
        by_publish[published] = parsed
        for start in parsed:
            by_delivery.setdefault(start.date(), set()).add(published)
    return {
        "actuals": _keyed(actuals),
        "by_publish": by_publish,
        "by_delivery": {day: sorted(pubs) for day, pubs in by_delivery.items()},
    }


@dataclass(frozen=True)
class HourPoint:
    start: datetime
    forecast_mw: float | None
    actual_mw: float | None
    error_mw: float | None


@dataclass(frozen=True)
class DayView:
    decision_date: date
    delivery_date: date
    gate: datetime
    publish_time: datetime | None
    hours: list[HourPoint]

    def errors(self) -> list[float]:
        return [point.error_mw for point in self.hours if point.error_mw is not None]


def build_day(
    decision: date,
    auction: Auction,
    forecasts: dict[str, dict[str, float]],
    actuals: dict[str, float],
    prepared: dict | None = None,
) -> DayView:
    data = prepared if prepared is not None else prepare(forecasts, actuals)
    delivery = delivery_date(decision)
    gate = gate_time(decision, auction)
    chosen = select_publish_time(data["by_delivery"].get(delivery, []), gate)
    vintage = data["by_publish"].get(chosen, {}) if chosen else {}
    points: list[HourPoint] = []
    for start in hour_starts(delivery):
        forecast = vintage.get(start)
        actual = hourly_actual_mw(data["actuals"], start)
        error = None if forecast is None or actual is None else forecast - actual
        points.append(HourPoint(start, forecast, actual, error))
    return DayView(decision, delivery, gate, chosen, points)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarise(errors: list[float]) -> dict[str, float | int | None]:
    count = len(errors)
    if count == 0:
        return {"n": 0, "bias_mw": None, "mae_mw": None, "rmse_mw": None, "p10_mw": None, "p90_mw": None}
    bias = sum(errors) / count
    mae = sum(abs(error) for error in errors) / count
    rmse = math.sqrt(sum(error * error for error in errors) / count)
    return {
        "n": count,
        "bias_mw": bias,
        "mae_mw": mae,
        "rmse_mw": rmse,
        "p10_mw": percentile(errors, 0.10),
        "p90_mw": percentile(errors, 0.90),
    }


def energy_error_mwh(errors: list[float]) -> float | None:
    """Each hourly MW error is one megawatt-hour of energy."""
    if not errors:
        return None
    return sum(errors)


def position(energy_error: float | None) -> str:
    if energy_error is None:
        return "unknown"
    if abs(energy_error) < 1:
        return "flat"
    return "short" if energy_error > 0 else "long"


def consequence(energy_error: float | None) -> str:
    if energy_error is None:
        return "No comparable hours for this delivery day."
    amount = round(abs(energy_error))
    if amount < 1:
        return "This forecast matched the day's wind energy. The residual buy would not have moved."
    if energy_error > 0:
        return (
            f"This forecast was high by {amount:,} MWh. "
            "Buying other power as if it were exact would have left the desk short that much."
        )
    return (
        f"This forecast was low by {amount:,} MWh. "
        "Buying other power as if it were exact would have left the desk long that much."
    )


def build_month(auction: Auction, forecasts: dict[str, dict[str, float]], actuals: dict[str, float]) -> list[DayView]:
    data = prepare(forecasts, actuals)
    return [build_day(day, auction, forecasts, actuals, prepared=data) for day in decision_dates()]


def accuracy_report(days: list[DayView]) -> dict:
    hourly_errors = [error for day in days for error in day.errors()]
    summary = summarise(hourly_errors)
    by_hour = []
    for hour in range(24):
        bucket = [point.error_mw for day in days for point in day.hours if point.start.hour == hour and point.error_mw is not None]
        stats = summarise(bucket)
        by_hour.append({"hour": hour, "n": stats["n"], "bias_mw": stats["bias_mw"], "mae_mw": stats["mae_mw"]})

    day_rows = []
    for day in days:
        errors = day.errors()
        stats = summarise(errors)
        day_rows.append(
            {
                "decision_date": day.decision_date.isoformat(),
                "delivery_date": day.delivery_date.isoformat(),
                "publish_time": iso_z(day.publish_time) if day.publish_time else None,
                "n": stats["n"],
                "bias_mw": stats["bias_mw"],
                "mae_mw": stats["mae_mw"],
                "energy_error_mwh": energy_error_mwh(errors),
            }
        )
    ranked = sorted(
        [row for row in day_rows if row["energy_error_mwh"] is not None],
        key=lambda row: abs(row["energy_error_mwh"]),
        reverse=True,
    )
    return {
        "summary": summary,
        "by_hour": by_hour,
        "days": day_rows,
        "worst_days": ranked[:5],
    }
