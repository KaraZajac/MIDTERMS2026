// Chart math shared by the SVG components: linear scales, clean ticks,
// line paths and rounded-end column paths. (Adapted from TOCSIN.)

export function scale(domainMin, domainMax, rangeMin, rangeMax) {
  const d = domainMax - domainMin || 1;
  return (v) => rangeMin + ((v - domainMin) / d) * (rangeMax - rangeMin);
}

/** 3–5 clean axis ticks covering [0, max]. */
export function ticks(max, count = 4) {
  if (max <= 0) return [0, 1];
  const step = Math.pow(10, Math.floor(Math.log10(max / count)));
  const err = max / count / step;
  const mult = err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
  const s = step * mult;
  const out = [];
  for (let v = 0; v <= max + s * 0.001; v += s) out.push(Math.round(v * 1e6) / 1e6);
  return out;
}

/** Clean ticks spanning [lo, hi], always including 0 — for series that can go
 *  negative (e.g. inflation/deflation). Returns {ticks, lo, hi}. */
export function signedTicks(lo, hi, count = 5) {
  if (lo >= 0) return { ticks: ticks(hi, count), lo: 0, hi: ticks(hi, count).at(-1) };
  const span = hi - lo || 1;
  const raw = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const err = raw / mag;
  const step = (err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1) * mag;
  const start = Math.floor(lo / step) * step;
  const end = Math.ceil(hi / step) * step;
  const out = [];
  for (let v = start; v <= end + step * 0.001; v += step) out.push(Math.round(v * 1e6) / 1e6);
  return { ticks: out, lo: start, hi: end };
}

export const linePath = (pts) =>
  pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");

/** Column with a 4px rounded data-end and a square baseline. */
export function column(x, yTop, w, yBase, r = 4) {
  const h = yBase - yTop;
  const rr = Math.min(r, w / 2, h);
  if (h <= 0.1) return "";
  return (
    `M${x},${yBase}` +
    `V${yTop + rr}` +
    `Q${x},${yTop} ${x + rr},${yTop}` +
    `H${x + w - rr}` +
    `Q${x + w},${yTop} ${x + w},${yTop + rr}` +
    `V${yBase}Z`
  );
}

/** Middle stacked segment: square both ends (the top segment gets column()). */
export function segment(x, yTop, w, yBase) {
  const h = yBase - yTop;
  if (h <= 0.1) return "";
  return `M${x},${yBase}V${yTop}H${x + w}V${yBase}Z`;
}
