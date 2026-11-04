// /results/, top: each chamber's chance of control as a gauge (Kara's ask on
// Nov 4, through MIDTERMS2026). A semicircle runs from Democrats 100% at the
// left, through 50% straight up, to Republicans 100% at the right, banded in
// the forecast's rating colours (solid 95%+, likely 75%+, lean 60%+, toss-up
// between, mirrored for Republicans), so the needle's zone reads like a
// rating. The needle sits at chambers.<c>.live.p_control.D and glides 0.6 s
// when that changes. It never jitters on its own: these chances move only
// with calls, not with partial counts. A tick marks where the night started
// (the sealed forecast). Under the row, the step charts of how the chances
// moved, closed by default (live-chances.js).
import { pct1 } from "../lib/format.js";
import { h } from "./live-util.js";
import { chancesBlock, paintChances } from "./live-chances.js";

const CHAMBERS = [
  ["house", "House", "control"],
  ["senate", "Senate", "control"],
  ["governor", "Governors", "a majority"],
];
// viewBox 0 0 200 106: the arc's centre line has radius R about (CX, CY)
const CX = 100, CY = 98, R = 80, BAND = 18, GAP = 0.006;
const BANDS = [
  [0.95, 1, "d3"],
  [0.75, 0.95, "d2"],
  [0.6, 0.75, "d1"],
  [0.4, 0.6, "tu"],
  [0.25, 0.4, "r1"],
  [0.05, 0.25, "r2"],
  [0, 0.05, "r3"],
];
const SVG = "http://www.w3.org/2000/svg";
const s = (tag, attrs = {}) => {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  return el;
};
// p is Democrats' chance: 1 at the far left, 0 at the far right.
const at = (p, r) => [CX + r * Math.cos(Math.PI * p), CY - r * Math.sin(Math.PI * p)];
const f = (v) => v.toFixed(2);
const num = (x) => (typeof x === "number" && Number.isFinite(x) ? Math.min(1, Math.max(0, x)) : null);

function gauge(key, name) {
  const svg = s("svg", { viewBox: "0 0 200 106", class: "g-svg" });
  for (const [lo, hi, cls] of BANDS) {
    const a = at(lo + (lo > 0 ? GAP : 0), R), b = at(hi - (hi < 1 ? GAP : 0), R);
    svg.append(s("path", { class: `g-band ${cls}`, d: `M${f(a[0])} ${f(a[1])}A${R} ${R} 0 0 0 ${f(b[0])} ${f(b[1])}` }));
  }
  svg.append(s("line", { class: "g-pre", "data-g-pre": "" }));
  const needle = s("g", { class: "g-needle", "data-g-needle": "" });
  needle.append(s("line", { x1: CX, y1: CY, x2: CX, y2: CY - (R + BAND / 2 - 3) }), s("circle", { cx: CX, cy: CY, r: 6 }));
  svg.append(needle);
  return h(
    "figure",
    { class: "gauge", "data-gauge": key },
    svg,
    h("figcaption", {}, h("span", { class: "g-name" }, name), h("span", { class: "g-val", "data-g-val": true }), h("span", { class: "g-was", "data-g-was": true })),
  );
}

function frame() {
  const hist = chancesBlock();
  return h(
    "div",
    { class: "gauges" },
    h("div", { class: "g-row" }, CHAMBERS.map(([k, name]) => gauge(k, name))),
    h("p", { class: "live-small g-cap" }, "Chances of control given the races called so far, from the frozen forecast. The tick marks where each stood before results."),
    h("details", { class: "g-history", "data-g-history": true }, h("summary", {}, "How the chances moved tonight"), hist),
  );
}

export function renderGauges(box, data) {
  let root = box.querySelector(":scope > .gauges");
  const first = !root;
  if (first) {
    root = frame();
    root.classList.add("no-anim"); // the first position is set, not swept to
    box.replaceChildren(root);
  }
  let any = false;
  for (const [key, name, what] of CHAMBERS) {
    const fig = root.querySelector(`[data-gauge="${key}"]`);
    const c = data.chambers?.[key];
    const live = c?.live ?? {}, pre = c?.pre?.p_control ?? {};
    const steady = live.reliable !== false;
    const pD = num(steady ? live.p_control?.D : pre.D);
    const pre0 = num(pre.D);
    fig.hidden = pD == null;
    if (pD == null) continue;
    any = true;
    const pR = num(steady ? live.p_control?.R : pre.R) ?? 1 - pD;
    const dFav = pD >= pR;
    // the needle: rotate from straight up, clockwise toward Republicans
    fig.querySelector("[data-g-needle]").style.transform = `rotate(${f((0.5 - pD) * 180)}deg)`;
    fig.classList.toggle("is-unsteady", !steady);
    const tick = fig.querySelector("[data-g-pre]");
    tick.toggleAttribute("hidden", pre0 == null);
    if (pre0 != null) {
      const [x1, y1] = at(pre0, R - BAND / 2 - 3), [x2, y2] = at(pre0, R + BAND / 2 + 3);
      for (const [k, v] of Object.entries({ x1, y1, x2, y2 })) tick.setAttribute(k, f(v));
    }
    const party = dFav ? "Democrats" : "Republicans";
    const val = fig.querySelector("[data-g-val]");
    val.className = `g-val ${dFav ? "d" : "r"}`;
    val.replaceChildren(steady ? `${party} ${pct1(dFav ? pD : pR)}` : "Not steady yet");
    const was = pre0 == null ? null : dFav ? pre0 : num(pre.R) ?? 1 - pre0;
    fig.querySelector("[data-g-was]").replaceChildren(was == null ? "" : `was ${pct1(was)} before results`);
    const label = steady
      ? `${name}: ${party}' chance of ${what} ${pct1(dFav ? pD : pR)}${was == null ? "" : `; ${pct1(was)} before results`}`
      : `${name}: chance of ${what} not steady yet; Democrats ${pct1(pre0)} before results`;
    fig.querySelector(".g-svg").setAttribute("role", "img");
    fig.querySelector(".g-svg").setAttribute("aria-label", label);
  }
  box.hidden = !any;
  const hist = root.querySelector("[data-chances]");
  paintChances(hist, data);
  root.querySelector("[data-g-history]").hidden = hist.hidden;
  if (first) requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove("no-anim")));
}
