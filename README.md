# Wind gate

A desk for a UK electricity buyer. For each day in January 2026 it shows the national wind forecast that had already been published when the day-ahead auction closed, and how far that forecast missed the metered wind.

January 2026 is GMT, so UK clock time and UTC are the same. The default auction is EPEX hourly, gate 09:20. On 14 January the file a buyer could use was the 07:30 publication. The 09:30 file is later, so it is visible to the 09:50 N2EX auction and not to the 09:20 gate. The 15:30 half-hourly auction can use the file stamped 15:30.

## Data and method

Generation is megawatts of national metered wind.

- Actuals come from the [FUELHH stream](https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream), `fuelType=WIND`, filtered by settlement date. There are 1,488 half-hours from 2 January through 1 February 2026.
- The [WINDFOR stream](https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream) ignores a historical settlement range and returns only the current file. The ingest records that and then reads the same WINDFOR dataset from `/forecast/generation/wind/history`, one publication at a time. Publish times are taken from the files, not only from the clock times in the docs. In this month they are 02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30 and 22:30 UTC.
- Forecasts are hourly. Each hour is compared with the average of the two FUELHH half-hours. Error is forecast minus actual. A positive error means the forecast was high, so buying other power as if the forecast were exact would have left the desk short.
- Scope is decisions made on 1–31 January 2026, for delivery the next day. The 1 January delivery was bought on 31 December and is not included.

The API reads `data/wind.sqlite`. It does not call Elexon when a page loads. Rebuild the snapshot with:

```bash
python -m backend.app.ingest
```

## Files and directories

```
api/index.py              Vercel entry, the same FastAPI app
backend/app/ingest.py     download and store the January snapshot
backend/app/metrics.py    gate rule, hourly join, error metrics
backend/app/main.py       HTTP API and, in Docker, the built page
backend/app/db.py         SQLite snapshot
backend/tests/            gate rule, noon case, API
frontend/                 React desk and accuracy screens
data/wind.sqlite          committed January snapshot
Dockerfile                API plus the built page
docker-compose.yml        local run
vercel.json               static page plus the Python API
```

## How to start

Docker, from the repository root:

```bash
docker compose up --build
```

Open http://localhost:8000.

Without Docker:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
uvicorn backend.app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies `/api` to port 8000. Open http://localhost:5173.

## Deployed app

https://hx4p9c.vercel.app

## AI tools

This application was built with assistance from Cursor’s coding agent.

## Video outline

Ten minutes, unlisted. Evaluation starts with the video, so record this before submitting. Open the deployed app in a private window first.

### Part 1, about five minutes, for the buyer

1. The job: the day before delivery, the desk has to decide how much power to buy beyond wind. Only the forecast already published at the gate can be used.
2. Decision desk, 14 January, EPEX 09:20. Point at the published time, 07:30, and the delivery day, 15 January. The chart is the shape they would have bid against. The sentence under it says the forecast was high, so the residual buy would have been short.
3. Switch to N2EX 09:50 and show the published time move to 09:30. The later auction sees a newer file. Then the 15:30 auction.
4. Accuracy. Bias, MAE, RMSE, and the P10 to P90 band. That band is the buffer. The hour chart shows the miss is not confined to one part of the day. Open the worst delivery day from the table.
5. Close on the limit: national metered wind only, January decisions only, no demand and no price. The number is how many megawatt-hours the wind assumption was wrong by.

### Part 2, about five minutes, for the technical reviewer

1. Vintage rule in `backend/app/metrics.py`: latest `publishTime` at or before the gate, then the next delivery day. The test fixes the 14 January noon case: forecast 11,049 MW against half-hours 9,742 and 9,839.
2. Why the WINDFOR stream is not the history. `ingest.py` tries it, stores the failure in the snapshot, and uses the history endpoint of the same dataset.
3. Hourly join, and why January needs no clock-change handling.
4. API reads the SQLite snapshot. Docker serves the API and the built React app. Vercel serves the same API as a Python function.
5. Tests: `pytest`. Show the gate tests and the snapshot test.
6. What was left out on purpose: prices, demand, a buy optimiser, other months.
