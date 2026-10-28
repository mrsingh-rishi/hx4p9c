const timeFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: "UTC",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const dayFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: "UTC",
  day: "numeric",
  month: "short",
});

export function mw(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return Math.round(value).toLocaleString("en-GB");
}

export function signedMw(value) {
  if (value == null || Number.isNaN(value)) return "—";
  const rounded = Math.round(value);
  const text = Math.abs(rounded).toLocaleString("en-GB");
  if (rounded > 0) return `+${text}`;
  if (rounded < 0) return `−${text}`;
  return "0";
}

export function clock(iso) {
  return timeFormat.format(new Date(iso));
}

export function dayLabel(isoDate) {
  const [year, month, day] = isoDate.split("-").map(Number);
  return dayFormat.format(new Date(Date.UTC(year, month - 1, day)));
}
