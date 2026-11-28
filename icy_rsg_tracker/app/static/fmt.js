// Formatting helpers. Times are in-game milliseconds unless noted.

const pad = (n, w = 2) => String(n).padStart(w, "0");

/** 223955 -> "3:43.955" */
export function time(ms) {
  if (ms == null) return "–";
  if (ms < 0) return `-${time(-ms)}`;  // e.g. an advancement before the split it's timed from
  const m = Math.floor(ms / 60000), s = Math.floor((ms % 60000) / 1000), r = ms % 1000;
  return `${m}:${pad(s)}.${pad(r, 3)}`;
}

/** 223955 -> "3:44.0" (for averages, where milliseconds are false precision) */
export function timeTenths(ms) {
  if (ms == null) return "–";
  if (ms < 0) return `-${timeTenths(-ms)}`;
  const tenths = Math.round(ms / 100);
  const m = Math.floor(tenths / 600), s = Math.floor((tenths % 600) / 10), t = tenths % 10;
  return `${m}:${pad(s)}.${t}`;
}

/** 223955 -> "3:44" (axis ticks) */
export function timeShort(ms) {
  if (ms < 0) return `-${timeShort(-ms)}`;
  const total = Math.round(ms / 1000);
  return `${Math.floor(total / 60)}:${pad(total % 60)}`;
}

/** seconds -> "3h 51m" / "42m" */
export function duration(seconds) {
  if (seconds == null) return "–";
  const mins = Math.round(seconds / 60);
  const h = Math.floor(mins / 60), m = mins % 60;
  return h ? `${h}h ${pad(m)}m` : `${m}m`;
}

export function int(n) {
  return n == null ? "–" : n.toLocaleString("en-US");
}

export function num(n, digits = 1) {
  return n == null ? "–" : n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function pct(rate) {
  return rate == null ? "–" : `${(rate * 100).toFixed(1)}%`;
}

/** "2026-11-24T16:30:00" -> "Nov 24" */
export function day(iso) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** "2026-11-24T16:30:00" -> "Nov 24, 4:30 PM" */
export function dateTime(iso) {
  return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

/** "2026-11-24T16:30:00" -> "4:30 PM" */
export function clock(iso) {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

/** A score in seconds with its sign: "+25.3 s", "−4.0 s". */
export function signedSeconds(s) {
  return `${s < 0 ? "−" : "+"}${Math.abs(s).toFixed(1)} s`;
}
