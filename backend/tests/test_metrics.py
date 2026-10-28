from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.db import connect, replace_snapshot
from backend.app.main import create_app
from backend.app.metrics import (
    AUCTIONS,
    accuracy_report,
    build_day,
    consequence,
    energy_error_mwh,
    hourly_actual_mw,
    parse_time,
    position,
    select_publish_time,
    summarise,
)


def utc(value: str) -> datetime:
    return parse_time(value)


def test_morning_gate_ignores_the_file_published_after_it():
    gate = utc("2026-01-14T09:20:00Z")
    published = [
        utc("2026-01-14T07:30:00Z"),
        utc("2026-01-14T09:30:00Z"),
        utc("2026-01-14T11:30:00Z"),
    ]
    assert select_publish_time(published, gate) == utc("2026-01-14T07:30:00Z")
    # 09:30 is before the 09:50 N2EX gate, so that auction sees a newer file.
    assert select_publish_time(published, utc("2026-01-14T09:50:00Z")) == utc("2026-01-14T09:30:00Z")


def test_half_hourly_gate_can_use_the_file_stamped_at_the_gate():
    published = [utc("2026-01-14T11:30:00Z"), utc("2026-01-14T15:30:00Z")]
    assert select_publish_time(published, utc("2026-01-14T15:30:00Z")) == utc("2026-01-14T15:30:00Z")


def test_hourly_actual_averages_the_two_half_hours():
    hour = utc("2026-01-15T12:00:00Z")
    actuals = {
        hour: 9742,
        utc("2026-01-15T12:30:00Z"): 9839,
    }
    assert hourly_actual_mw(actuals, hour) == pytest.approx(9790.5)
    assert hourly_actual_mw({hour: 9742}, hour) is None


def test_noon_error_on_14_january_decision():
    """14 Jan 07:30 forecast for 15 Jan noon, checked against FUELHH."""
    forecasts = {
        "2026-01-14T07:30:00Z": {"2026-01-15T12:00:00Z": 11049},
        "2026-01-14T09:30:00Z": {"2026-01-15T12:00:00Z": 11178},
    }
    actuals = {
        "2026-01-15T12:00:00Z": 9742,
        "2026-01-15T12:30:00Z": 9839,
    }
    view = build_day(date(2026, 1, 14), AUCTIONS["epex_hourly"], forecasts, actuals)
    noon = next(point for point in view.hours if point.start == utc("2026-01-15T12:00:00Z"))
    assert view.publish_time == utc("2026-01-14T07:30:00Z")
    assert noon.forecast_mw == 11049
    assert noon.actual_mw == pytest.approx(9790.5)
    assert noon.error_mw == pytest.approx(1258.5)
    assert view.delivery_date == date(2026, 1, 15)


def test_summary_and_consequence():
    errors = [2.0, -2.0, 2.0]
    stats = summarise(errors)
    assert stats["n"] == 3
    assert stats["bias_mw"] == pytest.approx(2 / 3)
    assert stats["mae_mw"] == pytest.approx(2)
    assert stats["rmse_mw"] == pytest.approx(2)
    assert energy_error_mwh(errors) == pytest.approx(2)
    assert position(1500) == "short"
    assert position(-40) == "long"
    assert "short" in consequence(1500)
    assert "long" in consequence(-40)
    assert energy_error_mwh([]) is None


def test_accuracy_ranks_the_larger_daily_miss():
    forecasts = {
        "2026-01-01T07:30:00Z": {"2026-01-02T00:00:00Z": 100},
        "2026-01-02T07:30:00Z": {"2026-01-03T00:00:00Z": 300},
    }
    actuals = {
        "2026-01-02T00:00:00Z": 90,
        "2026-01-02T00:30:00Z": 90,
        "2026-01-03T00:00:00Z": 100,
        "2026-01-03T00:30:00Z": 100,
    }
    days = []
    for decision in (date(2026, 1, 1), date(2026, 1, 2)):
        days.append(build_day(decision, AUCTIONS["epex_hourly"], forecasts, actuals))
    # build_month would include every January day. Rank the two we care about directly.
    report = accuracy_report(days)
    assert report["worst_days"][0]["decision_date"] == "2026-01-02"
    assert report["worst_days"][0]["energy_error_mwh"] == pytest.approx(200)


def test_desk_api_uses_the_gate_vintage(tmp_path):
    db_path = tmp_path / "wind.sqlite"
    conn = connect(db_path)
    replace_snapshot(
        conn,
        [
            {
                "start_time": "2026-01-15T12:00:00Z",
                "settlement_date": "2026-01-15",
                "settlement_period": 25,
                "generation_mw": 9742,
            },
            {
                "start_time": "2026-01-15T12:30:00Z",
                "settlement_date": "2026-01-15",
                "settlement_period": 26,
                "generation_mw": 9839,
            },
        ],
        [
            {
                "publish_time": "2026-01-14T07:30:00Z",
                "start_time": "2026-01-15T12:00:00Z",
                "settlement_date": "2026-01-15",
                "settlement_period": 25,
                "generation_mw": 11049,
            },
            {
                "publish_time": "2026-01-14T09:30:00Z",
                "start_time": "2026-01-15T12:00:00Z",
                "settlement_date": "2026-01-15",
                "settlement_period": 25,
                "generation_mw": 11178,
            },
        ],
        {"forecast_source": "test"},
    )
    conn.close()
    client = TestClient(create_app(db_path))
    response = client.get("/api/desk", params={"decision_date": "2026-01-14", "auction": "epex_hourly"})
    assert response.status_code == 200
    body = response.json()
    assert body["publish_time"] == "2026-01-14T07:30:00Z"
    noon = next(hour for hour in body["hours"] if hour["start"] == "2026-01-15T12:00:00Z")
    assert noon["error_mw"] == 1258.5
    assert body["position"] == "short"
    rejected = client.get("/api/desk", params={"decision_date": "2026-02-01", "auction": "epex_hourly"})
    assert rejected.status_code == 400


def test_committed_snapshot_keeps_the_14_january_noon_case():
    from backend.app.db import connect, default_db_path, load_actuals, load_forecasts

    path = default_db_path()
    assert path.exists(), "run python -m backend.app.ingest to build data/wind.sqlite"
    conn = connect(path)
    try:
        forecasts = load_forecasts(conn)
        actuals = load_actuals(conn)
    finally:
        conn.close()
    view = build_day(date(2026, 1, 14), AUCTIONS["epex_hourly"], forecasts, actuals)
    noon = next(point for point in view.hours if point.start == utc("2026-01-15T12:00:00Z"))
    assert view.publish_time == utc("2026-01-14T07:30:00Z")
    assert noon.forecast_mw == 11049
    assert noon.actual_mw == pytest.approx(9790.5)
    assert len(view.errors()) == 24
