// A smooth margin distribution from the export's nine quantiles.
// The CDF is interpolated with a monotone cubic (Fritsch–Carlson PCHIP)
// through (q, p) plus two tail points per side placed where a normal's would
// sit, and the density is its derivative. Monotone interpolation guarantees
// the density never goes negative; nothing here invents a shape the
// quantiles don't already imply.

const QS = [
  ["q01", 0.01], ["q05", 0.05], ["q10", 0.1], ["q25", 0.25], ["q50", 0.5],
  ["q75", 0.75], ["q90", 0.9], ["q95", 0.95], ["q99", 0.99],
];

function pchipSlopes(x, y) {
  const n = x.length;
  const h = [], d = [];
  for (let i = 0; i < n - 1; i++) {
    h.push(x[i + 1] - x[i]);
    d.push((y[i + 1] - y[i]) / (x[i + 1] - x[i]));
  }
  const m = new Array(n).fill(0);
  m[0] = d[0];
  m[n - 1] = d[n - 2];
  for (let i = 1; i < n - 1; i++) {
    if (d[i - 1] * d[i] <= 0) { m[i] = 0; continue; }
    const w1 = 2 * h[i] + h[i - 1], w2 = h[i] + 2 * h[i - 1];
    m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i]);
  }
  return m;
}

/** Points for the CDF knots, deduplicated so x is strictly increasing. */
function knots(margin) {
  const q01 = margin.q01, q05 = margin.q05, q95 = margin.q95, q99 = margin.q99;
  const lo1 = q01 - (q05 - q01), lo2 = q01 - 2 * (q05 - q01);
  const hi1 = q99 + (q99 - q95), hi2 = q99 + 2 * (q99 - q95);
  const pts = [[lo2, 0.0001], [lo1, 0.00135], ...QS.map(([k, p]) => [margin[k], p]), [hi1, 0.99865], [hi2, 0.9999]];
  const out = [];
  for (const [xv, pv] of pts) {
    if (out.length && xv <= out[out.length - 1][0] + 1e-6) continue;
    out.push([xv, pv]);
  }
  return out;
}

/** {x: [...], f: [...], F: [...]} sampled at `n` points across the support. */
export function densityFromQuantiles(margin, n = 160) {
  const k = knots(margin);
  const x = k.map((p) => p[0]), y = k.map((p) => p[1]);
  const m = pchipSlopes(x, y);
  const xs = [], fs = [], Fs = [];
  const a = x[0], b = x[x.length - 1];
  let j = 0;
  for (let s = 0; s < n; s++) {
    const xv = a + ((b - a) * s) / (n - 1);
    while (j < x.length - 2 && xv > x[j + 1]) j++;
    const hh = x[j + 1] - x[j];
    const t = Math.min(Math.max((xv - x[j]) / hh, 0), 1);
    const h00 = 2 * t ** 3 - 3 * t ** 2 + 1, h10 = t ** 3 - 2 * t ** 2 + t, h01 = -2 * t ** 3 + 3 * t ** 2, h11 = t ** 3 - t ** 2;
    const F = h00 * y[j] + h10 * hh * m[j] + h01 * y[j + 1] + h11 * hh * m[j + 1];
    const dF = ((6 * t * t - 6 * t) * y[j] + (3 * t * t - 4 * t + 1) * hh * m[j] + (-6 * t * t + 6 * t) * y[j + 1] + (3 * t * t - 2 * t) * hh * m[j + 1]) / hh;
    xs.push(xv);
    fs.push(Math.max(dF, 0));
    Fs.push(Math.min(Math.max(F, 0), 1));
  }
  return { x: xs, f: fs, F: Fs };
}
