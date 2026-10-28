import { useEffect, useId, useState } from "react";
import { NavLink, useSearchParams } from "react-router-dom";

export const AUCTIONS = [
  { id: "epex_hourly", label: "EPEX hourly", gate: "09:20" },
  { id: "n2ex", label: "N2EX", gate: "09:50" },
  { id: "epex_half_hourly", label: "EPEX half-hour", gate: "15:30" },
];

export function useDeskQuery() {
  const [params, setParams] = useSearchParams();
  const date = params.get("date") || "2026-01-14";
  const auction = params.get("auction") || "epex_hourly";

  function update(next) {
    const following = new URLSearchParams(params);
    if (next.date) following.set("date", next.date);
    if (next.auction) following.set("auction", next.auction);
    setParams(following, { replace: true });
  }

  return { date, auction, update };
}

function QueryNav() {
  const [params] = useSearchParams();
  const search = params.toString();
  return (
    <nav>
      <NavLink to={{ pathname: "/", search }} end>
        Decision desk
      </NavLink>
      <NavLink to={{ pathname: "/accuracy", search }}>Accuracy</NavLink>
    </nav>
  );
}

export function Shell({ children }) {
  return (
    <div className="page">
      <header className="mast">
        <NavLink to="/" className="mark">
          Wind gate
        </NavLink>
        <QueryNav />
      </header>
      <main>{children}</main>
      <footer className="method">
        <p>
          National metered wind only, from Elexon FUELHH (fuel type WIND) and WINDFOR. Figures are megawatts.
          Forecasts are hourly, so each hour is compared with the average of the two half-hour actuals. The vintage
          is the latest publication at or before the auction gate. Scope is decisions made on 1–31 January 2026, for
          delivery the next day. A positive error means the forecast was high: buying other power as if the forecast
          were exact would have left the desk short.
        </p>
      </footer>
    </div>
  );
}

export function AuctionControl({ auction, onChange }) {
  const labelId = useId();
  return (
    <div className="control">
      <span id={labelId}>Auction</span>
      <div role="radiogroup" aria-labelledby={labelId} className="segment">
        {AUCTIONS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="radio"
            aria-checked={auction === item.id}
            className={auction === item.id ? "on" : ""}
            onClick={() => onChange(item.id)}
          >
            {item.label}
            <small>{item.gate}</small>
          </button>
        ))}
      </div>
    </div>
  );
}

export function useAsync(loader, deps) {
  const [state, setState] = useState({ status: "loading", data: null, error: null });
  useEffect(() => {
    let live = true;
    setState((current) => ({ ...current, status: "loading", error: null }));
    loader()
      .then((data) => {
        if (live) setState({ status: "ready", data, error: null });
      })
      .catch((error) => {
        if (live) setState({ status: "error", data: null, error });
      });
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}
