import { Link } from "react-router-dom";
import { getDesk } from "./api";
import { DayChart, Numbers } from "./charts";
import { clock, dayLabel, mw, signedMw } from "./format";
import { AuctionControl, Shell, useAsync, useDeskQuery } from "./shell";

export function Desk() {
  const { date, auction, update } = useDeskQuery();
  const state = useAsync(() => getDesk(date, auction), [date, auction]);

  return (
    <Shell>
      <p className="eyebrow">National wind · January 2026 decisions</p>
      <h1>What was known at the gate.</h1>
      <div className="controls">
        <label className="control">
          Decision date
          <input
            type="date"
            min="2026-01-01"
            max="2026-01-31"
            value={date}
            onChange={(event) => update({ date: event.target.value })}
          />
        </label>
        <AuctionControl auction={auction} onChange={(next) => update({ auction: next })} />
      </div>
      {state.status === "loading" && <p className="status">Opening the file that was on the desk…</p>}
      {state.status === "error" && <p className="status error">{state.error.message}</p>}
      {state.status === "ready" && <DeskBody view={state.data} auction={auction} />}
    </Shell>
  );
}

function DeskBody({ view, auction }) {
  const known = Boolean(view.publish_time);
  return (
    <>
      <dl className="stamp">
        <div>
          <dt>Decision</dt>
          <dd>{dayLabel(view.decision_date)}</dd>
        </div>
        <div>
          <dt>Delivery</dt>
          <dd>{dayLabel(view.delivery_date)}</dd>
        </div>
        <div>
          <dt>Gate</dt>
          <dd>{clock(view.gate)}</dd>
        </div>
        <div>
          <dt>Forecast published</dt>
          <dd>{known ? clock(view.publish_time) : "None"}</dd>
        </div>
        <div>
          <dt>Hours compared</dt>
          <dd>
            {view.n}
            <span> / 24</span>
          </dd>
        </div>
      </dl>
      <p className={`consequence ${view.position}`}>{view.consequence}</p>
      {known ? (
        <>
          <section className="stats" aria-label="Delivery day error">
            <Stat label="Bias" value={signedMw(view.bias_mw)} unit="MW" hint="Mean forecast minus actual" />
            <Stat label="MAE" value={mw(view.mae_mw)} unit="MW" hint="Typical size of the miss" />
            <Stat label="Energy error" value={signedMw(view.energy_error_mwh)} unit="MWh" hint="Sum of the hourly misses" />
          </section>
          <DayChart hours={view.hours} />
          <Numbers hours={view.hours} />
        </>
      ) : (
        <p className="status">No WINDFOR file covering this delivery day had been published by the gate.</p>
      )}
      <p className="jump">
        <Link to={`/accuracy?date=${view.decision_date}&auction=${auction}`}>How this auction performed across January</Link>
      </p>
    </>
  );
}

function Stat({ label, value, unit, hint }) {
  return (
    <article>
      <h2>{label}</h2>
      <p className="figure">
        {value}
        <span>{unit}</span>
      </p>
      <p className="hint">{hint}</p>
    </article>
  );
}
