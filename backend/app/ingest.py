"""Pull January 2026 wind actuals and forecast vintages into the SQLite snapshot.

The FUELHH stream accepts a settlement-date range. The WINDFOR stream ignores
historical filters and returns only the current file, so vintages come from the
WINDFOR history endpoint, which is the same dataset.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from backend.app.db import connect, default_db_path, replace_snapshot
from backend.app.metrics import parse_time

BASE = "https://data.elexon.co.uk/bmrs/api/v1"
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "raw"
ACTUAL_START = date(2026, 1, 2)
ACTUAL_END = date(2026, 2, 1)
PUBLISH_START = date(2026, 1, 1)
PUBLISH_END = date(2026, 1, 31)

# Clock times seen on January 2026 files. The docs list these one hour later.
# The evolution probe adds any other stamp that actually occurs.
FALLBACK_SLOTS = {
    (2, 30),
    (4, 30),
    (7, 30),
    (9, 30),
    (11, 30),
    (15, 30),
    (18, 30),
    (22, 30),
}
PROBE_STARTS = (
    "2026-01-02T12:00:00Z",
    "2026-01-15T12:00:00Z",
    "2026-02-01T00:00:00Z",
)


def rows_of(payload) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        return data if isinstance(data, list) else []
    return []


def cache_path(name: str) -> Path:
    return CACHE / name


def get_json(client: httpx.Client, url: str, params: dict, name: str):
    path = cache_path(name)
    if path.exists():
        return json.loads(path.read_text())
    for attempt in range(6):
        response = client.get(url, params=params, timeout=60)
        if response.status_code == 429:
            wait = float(response.headers.get("Retry-After", 2)) + attempt
            print(f"429 {name}, sleeping {wait:.0f}s")
            time.sleep(wait)
            continue
        if response.status_code == 404:
            payload = {"data": []}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload))
            return payload
        response.raise_for_status()
        payload = response.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
        time.sleep(0.12)
        return payload
    raise RuntimeError(f"rate limited: {url}")


def iso_date(day: date) -> str:
    return day.isoformat()


def each_day(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def january_publish(stamp: str) -> bool:
    try:
        moment = parse_time(stamp)
    except ValueError:
        return False
    return moment.year == 2026 and moment.month == 1


def stream_has_january(rows: list[dict]) -> bool:
    stamps = [row.get("publishTime") for row in rows if row.get("publishTime")]
    return bool(stamps) and all(january_publish(stamp) for stamp in stamps)


def probe_windfor_stream(client: httpx.Client) -> str:
    attempts = {
        "windfor-stream-settlement.json": {
            "settlementDateFrom": "2026-01-15",
            "settlementDateTo": "2026-01-15",
        },
        "windfor-stream-from-to.json": {
            "from": "2026-01-14T00:00:00Z",
            "to": "2026-01-15T00:00:00Z",
        },
    }
    notes = []
    for name, params in attempts.items():
        payload = get_json(client, f"{BASE}/datasets/WINDFOR/stream", params, name)
        rows = rows_of(payload)
        useful = stream_has_january(rows)
        sample = rows[0]["publishTime"] if rows else "empty"
        notes.append(f"{name}: n={len(rows)} sample={sample} january={useful}")
        print(notes[-1])
        if useful:
            return "stream:" + name
    return "history; stream ignored (" + "; ".join(notes) + ")"


def discover_slots(client: httpx.Client) -> set[tuple[int, int]]:
    slots = set(FALLBACK_SLOTS)
    for start in PROBE_STARTS:
        payload = get_json(
            client,
            f"{BASE}/forecast/generation/wind/evolution",
            {"startTime": start, "format": "json"},
            f"evolution-{start.replace(':', '')}.json",
        )
        for row in rows_of(payload):
            moment = parse_time(row["publishTime"])
            if PUBLISH_START <= moment.date() <= PUBLISH_END:
                slots.add((moment.hour, moment.minute))
        print(f"evolution {start}: {len(rows_of(payload))} vintages")
    return slots


def fetch_actuals(client: httpx.Client) -> list[dict]:
    payload = get_json(
        client,
        f"{BASE}/datasets/FUELHH/stream",
        {
            "settlementDateFrom": iso_date(ACTUAL_START),
            "settlementDateTo": iso_date(ACTUAL_END),
            "fuelType": "WIND",
        },
        "fuelhh-range.json",
    )
    rows = [row for row in rows_of(payload) if row.get("fuelType") == "WIND"]
    dates = {row.get("settlementDate") for row in rows}
    expected = {iso_date(day) for day in each_day(ACTUAL_START, ACTUAL_END)}
    if expected - dates:
        print(f"range request missed {len(expected - dates)} days, fetching daily")
        rows = []
        for day in each_day(ACTUAL_START, ACTUAL_END):
            daily = get_json(
                client,
                f"{BASE}/datasets/FUELHH/stream",
                {
                    "settlementDateFrom": iso_date(day),
                    "settlementDateTo": iso_date(day),
                    "fuelType": "WIND",
                },
                f"fuelhh-{iso_date(day)}.json",
            )
            rows.extend(row for row in rows_of(daily) if row.get("fuelType") == "WIND")
    best: dict[str, dict] = {}
    for row in rows:
        start = row["startTime"]
        previous = best.get(start)
        if previous is None or row.get("publishTime", "") >= previous.get("publishTime", ""):
            best[start] = row
    stored = []
    for row in best.values():
        start = parse_time(row["startTime"])
        if not (ACTUAL_START <= start.date() <= ACTUAL_END):
            continue
        stored.append(
            {
                "start_time": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "settlement_date": row.get("settlementDate") or start.date().isoformat(),
                "settlement_period": int(row.get("settlementPeriod") or 0),
                "generation_mw": float(row["generation"]),
            }
        )
    stored.sort(key=lambda item: item["start_time"])
    print(f"actuals {len(stored)}")
    return stored


def fetch_forecasts(client: httpx.Client, slots: set[tuple[int, int]]) -> list[dict]:
    stored: dict[tuple[str, str], dict] = {}
    days = list(each_day(PUBLISH_START, PUBLISH_END))
    total = len(days) * len(slots)
    done = 0
    for day in days:
        for hour, minute in sorted(slots):
            published = datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)
            stamp = published.strftime("%Y-%m-%dT%H:%M:%SZ")
            payload = get_json(
                client,
                f"{BASE}/forecast/generation/wind/history",
                {"publishTime": stamp, "format": "json"},
                f"history-{stamp.replace(':', '')}.json",
            )
            done += 1
            found = rows_of(payload)
            if done % 25 == 0 or found:
                print(f"history {done}/{total} {stamp} rows={len(found)}")
            for row in found:
                if row.get("publishTime") is None or row.get("startTime") is None:
                    continue
                publish = parse_time(row["publishTime"])
                start = parse_time(row["startTime"])
                if publish.date() < PUBLISH_START or publish.date() > PUBLISH_END:
                    continue
                key = (publish.strftime("%Y-%m-%dT%H:%M:%SZ"), start.strftime("%Y-%m-%dT%H:%M:%SZ"))
                stored[key] = {
                    "publish_time": key[0],
                    "start_time": key[1],
                    "settlement_date": row.get("settlementDate") or start.date().isoformat(),
                    "settlement_period": int(row.get("settlementPeriod") or 0),
                    "generation_mw": float(row["generation"]),
                }
    forecasts = list(stored.values())
    forecasts.sort(key=lambda item: (item["publish_time"], item["start_time"]))
    print(f"forecasts {len(forecasts)}")
    return forecasts


def main() -> None:
    db_path = default_db_path()
    with httpx.Client(headers={"Accept": "application/json", "User-Agent": "wind-gate/1.0"}) as client:
        source = probe_windfor_stream(client)
        slots = discover_slots(client)
        actuals = fetch_actuals(client)
        forecasts = fetch_forecasts(client, slots)
    conn = connect(db_path)
    try:
        replace_snapshot(
            conn,
            actuals,
            forecasts,
            {
                "forecast_source": source,
                "publish_slots": ",".join(f"{hour:02d}:{minute:02d}" for hour, minute in sorted(slots)),
                "actual_rows": str(len(actuals)),
                "forecast_rows": str(len(forecasts)),
                "ingested_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
    finally:
        conn.close()
    print(f"wrote {db_path}")


if __name__ == "__main__":
    main()
