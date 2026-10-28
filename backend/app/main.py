"""HTTP API for the day-ahead wind desk."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.db import connect, default_db_path, load_actuals, load_forecasts
from backend.app.metrics import (
    AUCTIONS,
    accuracy_report,
    build_day,
    build_month,
    consequence,
    energy_error_mwh,
    iso_z,
    position,
    summarise,
)

_CACHE: dict = {}


def round1(value):
    if value is None:
        return None
    return round(float(value), 1)


def load_tables(db_path: Path):
    if not db_path.exists():
        raise HTTPException(status_code=503, detail=f"Snapshot not found at {db_path}")
    stamp = db_path.stat().st_mtime
    cached = _CACHE.get(db_path)
    if cached and cached["mtime"] == stamp:
        return cached["forecasts"], cached["actuals"]
    conn = connect(db_path)
    try:
        forecasts = load_forecasts(conn)
        actuals = load_actuals(conn)
    finally:
        conn.close()
    _CACHE[db_path] = {"mtime": stamp, "forecasts": forecasts, "actuals": actuals}
    return forecasts, actuals


def parse_decision(value: str) -> date:
    try:
        decision = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="decision_date must be YYYY-MM-DD") from exc
    if decision.year != 2026 or decision.month != 1:
        raise HTTPException(status_code=400, detail="decision_date must be in January 2026")
    return decision


def parse_auction(auction_id: str):
    auction = AUCTIONS.get(auction_id)
    if auction is None:
        known = ", ".join(AUCTIONS)
        raise HTTPException(status_code=400, detail=f"auction must be one of {known}")
    return auction


def hour_payload(point) -> dict:
    return {
        "start": iso_z(point.start),
        "forecast_mw": round1(point.forecast_mw),
        "actual_mw": round1(point.actual_mw),
        "error_mw": round1(point.error_mw),
    }


def create_app(db_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="Wind gate", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    resolved = db_path or default_db_path()

    @app.get("/api/health")
    def health():
        return {"ok": resolved.exists(), "snapshot": str(resolved)}

    @app.get("/api/auctions")
    def auctions():
        return [
            {"id": auction.id, "label": auction.label, "gate": auction.gate.strftime("%H:%M"), "detail": auction.detail}
            for auction in AUCTIONS.values()
        ]

    @app.get("/api/desk")
    def desk(
        decision_date: str = Query(...),
        auction: str = Query("epex_hourly"),
    ):
        decision = parse_decision(decision_date)
        chosen = parse_auction(auction)
        forecasts, actuals = load_tables(resolved)
        view = build_day(decision, chosen, forecasts, actuals)
        errors = view.errors()
        stats = summarise(errors)
        energy = energy_error_mwh(errors)
        return {
            "decision_date": view.decision_date.isoformat(),
            "delivery_date": view.delivery_date.isoformat(),
            "auction": chosen.id,
            "gate": iso_z(view.gate),
            "publish_time": iso_z(view.publish_time) if view.publish_time else None,
            "hours": [hour_payload(point) for point in view.hours],
            "n": stats["n"],
            "bias_mw": round1(stats["bias_mw"]),
            "mae_mw": round1(stats["mae_mw"]),
            "rmse_mw": round1(stats["rmse_mw"]),
            "energy_error_mwh": round1(energy),
            "position": position(energy),
            "consequence": consequence(energy),
        }

    @app.get("/api/accuracy")
    def accuracy(auction: str = Query("epex_hourly")):
        chosen = parse_auction(auction)
        forecasts, actuals = load_tables(resolved)
        report = accuracy_report(build_month(chosen, forecasts, actuals))
        summary = report["summary"]
        return {
            "auction": chosen.id,
            "n": summary["n"],
            "bias_mw": round1(summary["bias_mw"]),
            "mae_mw": round1(summary["mae_mw"]),
            "rmse_mw": round1(summary["rmse_mw"]),
            "p10_mw": round1(summary["p10_mw"]),
            "p90_mw": round1(summary["p90_mw"]),
            "by_hour": [
                {
                    "hour": row["hour"],
                    "n": row["n"],
                    "bias_mw": round1(row["bias_mw"]),
                    "mae_mw": round1(row["mae_mw"]),
                }
                for row in report["by_hour"]
            ],
            "days": [
                {
                    **row,
                    "bias_mw": round1(row["bias_mw"]),
                    "mae_mw": round1(row["mae_mw"]),
                    "energy_error_mwh": round1(row["energy_error_mwh"]),
                }
                for row in report["days"]
            ],
            "worst_days": [
                {
                    **row,
                    "bias_mw": round1(row["bias_mw"]),
                    "mae_mw": round1(row["mae_mw"]),
                    "energy_error_mwh": round1(row["energy_error_mwh"]),
                }
                for row in report["worst_days"]
            ],
        }

    static_dir = os.environ.get("STATIC_DIR")
    if static_dir and Path(static_dir).is_dir():
        assets = Path(static_dir) / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/")
        def index_page():
            return FileResponse(Path(static_dir) / "index.html")

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            candidate = Path(static_dir) / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(Path(static_dir) / "index.html")

    return app


app = create_app()
