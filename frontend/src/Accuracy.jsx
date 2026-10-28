import { Link } from "react-router-dom";
import { getAccuracy } from "./api";
import { EnergyStrip, HourBias } from "./charts";
import { dayLabel, mw, signedMw } from "./format";
import { AuctionControl, Shell, useAsync, useDeskQuery } from "./shell";

export function Accuracy() {
  const { date, auction, update } = useDeskQuery();
  const state = useAsync(() => getAccuracy(auction), [auction]);
  const auctionLabel = {
    epex_hourly: "EPEX hourly, gate 09:20",
    n2ex: "N2EX, gate 09:50",
    epex_half_hourly: "EPEX half-hourly, gate 15:30",
  }[auction];

  return (
    <Shell>
      <p className="eyebrow">Same gate rule · 31 decision days</p>
      <h1>How far the forecast missed.</h1>
      <div className="controls">
        <AuctionControl auction={auction} onChange={(next) => update({ auction: next })} />
      </div>
      {state.status === "loading" && <p className="status">Scoring every January decision…</p>}
      {state.status === "error" && <p className="status error">{state.error.message}</p>}
      {state.status === "ready" && (
        <AccuracyBody report={state.data} auction={auction} date={date} label={auctionLabel} />
      )}
    </Shell>
  );
}

function AccuracyBody({ report, auction, date, label }) {
  const low = report.p10_mw;
  const high = report.p90_mw;
  return (
    <>
      <p className="lede">
        {label}. {report.n.toLocaleString("en-GB")} hours scored. Eight hours in ten, the error sat between{" "}
        {signedMw(low)} and {signedMw(high)} MW. A residual buy sized off the forecast alone would have been outside
        that band one hour in ten on either side.
      </p>
      <section className="stats" aria-label="January error">
        <article>
          <h2>Bias</h2>
          <p className="figure">
            {signedMw(report.bias_mw)}
            <span>MW</span>
          </p>
          <p className="hint">
            {report.bias_mw > 0 ? "Forecasts ran high" : report.bias_mw < 0 ? "Forecasts ran low" : "No average bias"}
          </p>
        </article>
        <article>
          <h2>MAE</h2>
          <p className="figure">
            {mw(report.mae_mw)}
            <span>MW</span>
          </p>
          <p className="hint">Average absolute miss</p>
        </article>
        <article>
          <h2>RMSE</h2>
          <p className="figure">
            {mw(report.rmse_mw)}
            <span>MW</span>
          </p>
          <p className="hint">Large misses count more</p>
        </article>
        <article>
          <h2>P10 to P90</h2>
          <p className="figure range">
            {signedMw(low)}
            <span>to {signedMw(high)}</span>
          </p>
          <p className="hint">MW band covering 80% of hours</p>
        </article>
      </section>
      <HourBias rows={report.by_hour} />
      <EnergyStrip days={report.days} />
      <div className="table-wrap">
        <table>
          <caption>Largest daily energy misses</caption>
          <thead>
            <tr>
              <th scope="col">Decision</th>
              <th scope="col">Delivery</th>
              <th scope="col">Energy error</th>
              <th scope="col">MAE</th>
            </tr>
          </thead>
          <tbody>
            {report.worst_days.map((day) => (
              <tr key={day.decision_date}>
                <th scope="row">
                  <Link to={`/?date=${day.decision_date}&auction=${auction}`}>{dayLabel(day.decision_date)}</Link>
                </th>
                <td>{dayLabel(day.delivery_date)}</td>
                <td className={day.energy_error_mwh > 0 ? "short" : "long"}>{signedMw(day.energy_error_mwh)} MWh</td>
                <td>{mw(day.mae_mw)} MW</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="jump">
        <Link to={`/?date=${date}&auction=${auction}`}>Back to the decision desk</Link>
      </p>
    </>
  );
}
