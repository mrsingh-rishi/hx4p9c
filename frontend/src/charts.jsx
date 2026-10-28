import { clock, mw, signedMw } from "./format";

function scale(values, minValue, maxValue, top, height) {
  const span = maxValue - minValue || 1;
  return (value) => top + ((maxValue - value) / span) * height;
}

function polyline(points) {
  return points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
}

function segments(hours, key, xOf, yOf) {
  const paths = [];
  let current = [];
  hours.forEach((hour, index) => {
    if (hour[key] == null) {
      if (current.length) paths.push(polyline(current));
      current = [];
      return;
    }
    current.push({ x: xOf(index), y: yOf(hour[key]) });
  });
  if (current.length) paths.push(polyline(current));
  return paths;
}

export function DayChart({ hours }) {
  const width = 860;
  const genTop = 18;
  const genHeight = 210;
  const errTop = 268;
  const errHeight = 110;
  const padL = 56;
  const padR = 12;
  const inner = width - padL - padR;
  const step = inner / Math.max(hours.length - 1, 1);

  const generation = hours.flatMap((hour) => [hour.forecast_mw, hour.actual_mw]).filter((value) => value != null);
  const errors = hours.map((hour) => hour.error_mw).filter((value) => value != null);
  const genMax = Math.max(1000, ...generation) * 1.06;
  const errExtent = Math.max(500, ...errors.map((value) => Math.abs(value)));
  const yGen = scale(generation, 0, genMax, genTop, genHeight);
  const yErr = scale(errors, -errExtent, errExtent, errTop, errHeight);
  const x = (index) => padL + index * step;

  const forecast = segments(hours, "forecast_mw", (index) => x(index), yGen);
  const actual = segments(hours, "actual_mw", (index) => x(index), yGen);

  const ticks = [0, Math.round(genMax / 2), Math.round(genMax)];

  return (
    <figure className="chart">
      <figcaption>
        <span className="swatch forecast">Forecast</span>
        <span className="swatch actual">Actual</span>
        <span className="swatch short">High forecast</span>
        <span className="swatch long">Low forecast</span>
      </figcaption>
      <svg viewBox={`0 0 ${width} 420`} role="img" aria-label="Forecast, actual wind, and hourly error">
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={padL} x2={width - padR} y1={yGen(tick)} y2={yGen(tick)} className="grid" />
            <text x={padL - 8} y={yGen(tick) + 4} className="axis" textAnchor="end">
              {tick >= 1000 ? `${Math.round(tick / 1000)}k` : tick}
            </text>
          </g>
        ))}
        <line x1={padL} x2={width - padR} y1={yErr(0)} y2={yErr(0)} className="grid" />
        <text x={padL - 8} y={yErr(0) + 4} className="axis" textAnchor="end">
          0
        </text>
        {forecast.map((path, index) => (
          <path key={`forecast-${index}`} d={path} className="line forecast" />
        ))}
        {actual.map((path, index) => (
          <path key={`actual-${index}`} d={path} className="line actual" />
        ))}
        {hours.map((hour, index) => {
          if (hour.error_mw == null) return null;
          const barX = x(index) - Math.min(8, step * 0.28);
          const zero = yErr(0);
          const tip = yErr(hour.error_mw);
          const y = Math.min(zero, tip);
          return (
            <rect
              key={hour.start}
              x={barX}
              y={y}
              width={Math.min(16, step * 0.56)}
              height={Math.max(1, Math.abs(tip - zero))}
              className={hour.error_mw >= 0 ? "bar short" : "bar long"}
            >
              <title>{`${clock(hour.start)} error ${signedMw(hour.error_mw)} MW`}</title>
            </rect>
          );
        })}
        {hours.map((hour, index) =>
          index % 3 === 0 ? (
            <text key={hour.start} x={x(index)} y="408" className="axis" textAnchor="middle">
              {clock(hour.start)}
            </text>
          ) : null,
        )}
      </svg>
      <p className="chart-note">Top: generation, MW. Bottom: forecast minus actual. Hours are UTC, which is UK time in January.</p>
    </figure>
  );
}

export function HourBias({ rows }) {
  const width = 860;
  const height = 180;
  const padL = 56;
  const padR = 12;
  const padT = 12;
  const padB = 28;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;
  const values = rows.map((row) => row.bias_mw).filter((value) => value != null);
  const extent = Math.max(200, ...values.map((value) => Math.abs(value)));
  const y = scale(values, -extent, extent, padT, innerH);
  const slot = innerW / rows.length;

  return (
    <figure className="chart">
      <figcaption>Mean error by hour of the delivery day</figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Mean forecast error by hour">
        <line x1={padL} x2={width - padR} y1={y(0)} y2={y(0)} className="grid" />
        {rows.map((row) => {
          if (row.bias_mw == null) return null;
          const zero = y(0);
          const tip = y(row.bias_mw);
          return (
            <rect
              key={row.hour}
              x={padL + row.hour * slot + slot * 0.2}
              y={Math.min(zero, tip)}
              width={slot * 0.6}
              height={Math.max(1, Math.abs(tip - zero))}
              className={row.bias_mw >= 0 ? "bar short" : "bar long"}
            >
              <title>{`${String(row.hour).padStart(2, "0")}:00 ${signedMw(row.bias_mw)} MW`}</title>
            </rect>
          );
        })}
        {[0, 6, 12, 18].map((hour) => (
          <text key={hour} x={padL + hour * slot + slot / 2} y={height - 8} className="axis" textAnchor="middle">
            {String(hour).padStart(2, "0")}
          </text>
        ))}
      </svg>
    </figure>
  );
}

export function EnergyStrip({ days }) {
  const width = 860;
  const height = 160;
  const padL = 56;
  const padR = 8;
  const padT = 12;
  const padB = 24;
  const values = days.map((day) => day.energy_error_mwh).filter((value) => value != null);
  const extent = Math.max(1000, ...values.map((value) => Math.abs(value)));
  const innerH = height - padT - padB;
  const y = scale(values, -extent, extent, padT, innerH);
  const slot = (width - padL - padR) / Math.max(days.length, 1);

  return (
    <figure className="chart">
      <figcaption>Energy error on each delivery day, MWh</figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Daily energy error across January decisions">
        <line x1={padL} x2={width - padR} y1={y(0)} y2={y(0)} className="grid" />
        {days.map((day, index) => {
          if (day.energy_error_mwh == null) return null;
          const zero = y(0);
          const tip = y(day.energy_error_mwh);
          return (
            <rect
              key={day.decision_date}
              x={padL + index * slot + 1}
              y={Math.min(zero, tip)}
              width={Math.max(2, slot - 2)}
              height={Math.max(1, Math.abs(tip - zero))}
              className={day.energy_error_mwh >= 0 ? "bar short" : "bar long"}
            >
              <title>{`${day.delivery_date} ${signedMw(day.energy_error_mwh)} MWh`}</title>
            </rect>
          );
        })}
      </svg>
    </figure>
  );
}

export function Numbers({ hours }) {
  return (
    <div className="table-wrap">
      <table>
        <caption>Hourly numbers for the delivery day</caption>
        <thead>
          <tr>
            <th scope="col">Hour</th>
            <th scope="col">Forecast MW</th>
            <th scope="col">Actual MW</th>
            <th scope="col">Error MW</th>
          </tr>
        </thead>
        <tbody>
          {hours.map((hour) => (
            <tr key={hour.start}>
              <th scope="row">{clock(hour.start)}</th>
              <td>{mw(hour.forecast_mw)}</td>
              <td>{mw(hour.actual_mw)}</td>
              <td className={hour.error_mw > 0 ? "short" : hour.error_mw < 0 ? "long" : ""}>{signedMw(hour.error_mw)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
