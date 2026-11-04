// /results/: each chamber's chance of Democratic control through the night, as
// a small step chart (Kara's ask on Nov 4, through MIDTERMS2026). live.json's
// history is [[t, house, senate, governor, called], ...], oldest first: the
// forecast of record at the deadline, then a point whenever a chance or the
// number of calls changed. Each value holds until the next point and the last
// runs to now; the axis starts at 6 p.m. ET with the value in force then.
// One series per chart (no legend: the caption names it), a dashed 50% line,
// a crosshair with the site's tooltip on hover, and every step as a table.
import { pct1 } from "../lib/format.js";
import { h, now, clock, closeClock } from "./live-util.js";

const X0 = Date.parse("2026-11-03T23:00:00Z"); // 6 p.m. ET, when the first polls closed
const KEYS = [
  ["house", "House", 1],
  ["senate", "Senate", 2],
  ["governor", "Governors", 3],
];
const W = 1000; // viewBox units across; 100 down
const SVG = "http://www.w3.org/2000/svg";
const s = (tag, attrs = {}) => {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  return el;
};
const ok = (p) => Array.isArray(p) && Number.isFinite(Date.parse(p[0])) && [1, 2, 3].every((i) => p[i] == null || (typeof p[i] === "number" && p[i] >= 0 && p[i] <= 1));

export function chancesBlock() {
  return h(
    "section",
    { class: "hero-chances", "data-chances": true, hidden: true },
    h("h3", {}, "Chances of control through the night"),
    h(
      "div",
      { class: "chn-grid" },
      KEYS.map(([k, name]) =>
        h(
          "figure",
          { class: "chn", "data-chn": k },
          h("figcaption", {}, h("span", { class: "chn-name" }, name), h("span", { class: "chn-now", "data-chn-now": true })),
          h("div", { class: "chn-plot", "data-chn-plot": true }),
        ),
      ),
    ),
    h(
      "p",
      { class: "live-small" },
      "Democrats' chance of control given the races called so far, from the frozen forecast at 6 p.m. ET. Each step is a batch of calls; the dashed line is 50%.",
    ),
    h("details", { class: "chn-table" }, h("summary", {}, "Every step, as a table"), h("div", { class: "chn-table-wrap", "data-chn-table": true })),
  );
}

let last = null;
// The last step runs to now, so redraw each minute even when no new file comes.
setInterval(() => {
  if (last && document.visibilityState === "visible") paintChances(last.box, last.data);
}, 60000);

export function paintChances(box, data) {
  const H = (Array.isArray(data?.history) ? data.history : []).filter(ok).sort((a, b) => Date.parse(a[0]) - Date.parse(b[0]));
  box.hidden = H.length === 0;
  if (!H.length) return;
  last = { box, data };
  const tEnd = Math.max(now(), Date.parse(H[H.length - 1][0]) + 60000, X0 + 3600000);
  for (const [key, name, i] of KEYS) {
    const fig = box.querySelector(`[data-chn="${key}"]`);
    const steps = stepsFor(H, i, tEnd);
    fig.hidden = !steps.length;
    if (steps.length) draw(fig, name, steps, tEnd);
  }
  table(box.querySelector("[data-chn-table]"), H);
}

/** [{from, to, v, called, t}] from 6 p.m. ET to tEnd; the value in force at 6 p.m. starts it. */
function stepsFor(H, i, tEnd) {
  const out = [];
  for (let k = 0; k < H.length; k++) {
    const v = H[k][i];
    if (typeof v !== "number") continue;
    const t = Date.parse(H[k][0]);
    const next = H.slice(k + 1).find((p) => typeof p[i] === "number");
    const to = next ? Date.parse(next[0]) : tEnd;
    if (to <= X0) continue;
    const prev = out[out.length - 1];
    if (prev && prev.v === v) {
      prev.to = to; // same chance: one flat step (the call count rides along)
      prev.called = H[k][4];
      continue;
    }
    out.push({ from: Math.max(t, X0), to, v, called: H[k][4], t });
  }
  return out;
}

function when(t) {
  return t < X0 ? "Before results (the forecast)" : `${clock(new Date(t).toISOString())} ET`;
}

function draw(fig, name, steps, tEnd) {
  const x = (t) => ((t - X0) / (tEnd - X0)) * W;
  const y = (v) => 100 * (1 - v);
  const plot = fig.querySelector("[data-chn-plot]");
  const svg = s("svg", { viewBox: `0 0 ${W} 100`, preserveAspectRatio: "none", "aria-hidden": "true" });
  svg.append(s("line", { class: "chn-rule", x1: 0, x2: W, y1: 100, y2: 100 }));
  svg.append(s("line", { class: "chn-half", x1: 0, x2: W, y1: 50, y2: 50 }));
  let d = `M${x(steps[0].from).toFixed(1)} ${y(steps[0].v).toFixed(2)}`;
  for (const [k, st] of steps.entries()) {
    if (k) d += `V${y(st.v).toFixed(2)}`;
    d += `H${x(st.to).toFixed(1)}`;
  }
  svg.append(s("path", { class: "chn-line", d }));
  // A hit area per step, the full height: the site's tooltip reads it.
  for (const st of steps) {
    const r = s("rect", { class: "chn-hit", x: x(st.from).toFixed(1), y: 0, width: Math.max(0.5, x(st.to) - x(st.from)).toFixed(1), height: 100 });
    r.dataset.tipValue = `${when(st.t)} · Democrats ${pct1(st.v)} · ${st.called ?? 0} called`;
    r.dataset.tipLabel = name;
    svg.append(r);
  }
  const cross = h("div", { class: "chn-cross" });
  const dot = h("div", { class: "chn-dot" });
  const labels = [
    ["100%", 0],
    ["50%", 50],
    ["0%", 100],
  ].map(([t, top]) => h("span", { class: "chn-y", style: `top:${top}%` }, t));
  const ticks = hourTicks(tEnd).map((t) => h("span", { class: t === X0 ? "chn-x is-first" : "chn-x", style: `left:${(x(t) / W) * 100}%` }, closeClock(new Date(t).toISOString())));
  plot.replaceChildren(svg, ...labels, ...ticks, cross, dot);
  const lastStep = steps[steps.length - 1];
  fig.querySelector("[data-chn-now]").replaceChildren("Democrats ", h("strong", {}, pct1(lastStep.v)));
  plot.setAttribute("role", "img");
  plot.setAttribute("aria-label", `${name}: Democrats' chance of control, ${pct1(steps[0].v)} at 6 p.m. ET, ${pct1(lastStep.v)} now.`);
  plot.onpointermove = (e) => {
    const b = plot.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (e.clientX - b.left) / b.width));
    const t = X0 + f * (tEnd - X0);
    const st = steps.find((q) => t >= q.from && t < q.to) ?? lastStep;
    cross.style.left = `${f * 100}%`;
    dot.style.left = `${f * 100}%`;
    dot.style.top = `${y(st.v)}%`;
    plot.classList.add("is-hover");
  };
  plot.onpointerleave = () => plot.classList.remove("is-hover");
}

/** Whole hours (ET is a whole number of hours off UTC) from 6 p.m., spaced to fit. */
function hourTicks(tEnd) {
  const hours = (tEnd - X0) / 3600000;
  const every = hours <= 5 ? 1 : hours <= 10 ? 2 : hours <= 18 ? 3 : 6;
  const out = [];
  for (let t = X0; t <= tEnd - 0.4 * every * 3600000; t += every * 3600000) out.push(t);
  return out;
}

function table(wrap, H) {
  const rows = H.slice(-200).reverse();
  wrap.replaceChildren(
    h(
      "table",
      {},
      h("thead", {}, h("tr", {}, ["Time (ET)", "House", "Senate", "Governors", "Called"].map((t) => h("th", { scope: "col" }, t)))),
      h(
        "tbody",
        {},
        rows.map((p) =>
          h(
            "tr",
            {},
            h("td", {}, Date.parse(p[0]) < X0 ? "Forecast of record" : clock(p[0])),
            [1, 2, 3].map((i) => h("td", {}, typeof p[i] === "number" ? pct1(p[i]) : "—")),
            h("td", {}, String(p[4] ?? "")),
          ),
        ),
      ),
    ),
    H.length > 200 ? h("p", { class: "live-small" }, `The latest 200 of ${H.length} steps.`) : "",
  );
}
