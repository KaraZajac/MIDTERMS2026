// The seat bars: one per chamber, across all its seats. Democrats fill from
// the left and Republicans from the right, so whoever passes the line in the
// middle has a majority. Seats won or held are solid. Races not yet called sit
// between them, striped and tinted by how strongly the forecast, given the
// calls so far, favors a side (Solid, Likely, Lean: format.js bucket(), the
// forecast maps' thresholds); toss-ups and runoffs are grey; independents and
// others are amber, in the middle, because the model counts them as
// uncommitted. No "projected total" is added up from the stripes: the only
// projection shown is the model's own median (live.seats).
//
// A bar is built once (seatBlock) and then updated in place (paintSeats), so
// a new call slides the segments instead of redrawing them. Clicking a
// segment, or its legend entry, narrows the results board to those races.
import { h, n, sum, fmtInt, SEGS, segLabel, caucusing } from "./live-util.js";

const NOUN1 = { house: ["seat", "seats"], senate: ["seat", "seats"], governor: ["governorship", "governorships"] };
const noun = (key, x) => NOUN1[key][x === 1 ? 0 : 1];
// Legend words: the side is told by where the entry sits and by its group label.
const WORD = { dw: "won", d3: "solid", d2: "likely", d1: "lean", ow: "others won", o: "others favored", tu: "toss-up", r1: "lean", r2: "likely", r3: "solid", rw: "won" };
const MAJ = {
  house: (c) => `${fmtInt(c.majority)} for a majority`,
  senate: () => "50 + Vance for Republicans · 51 for Democrats",
  governor: (c) => `${fmtInt(c.majority)} for a majority`,
};

function legendItem(s) {
  return h(
    "li",
    { "data-lgi": s },
    h(
      "button",
      { type: "button", class: "sb-lg-item", "data-seg-pick": s },
      h("span", { class: `sb-sw ${s}`, "aria-hidden": "true" }),
      h("span", { class: "sb-lg-n", "data-lgn": s }, "0"),
      h("span", { class: "sb-lg-t", "data-lgt": s }, WORD[s]),
    ),
  );
}

/** The frame of one chamber's bar; paintSeats() fills it. */
export function seatBlock(key, { compact = false } = {}) {
  return h(
    "div",
    { class: `sb${compact ? " sb-compact" : ""}`, "data-sb": key },
    h(
      "div",
      { class: "sb-ends" },
      h("div", { class: "sb-end" }, h("span", { class: "sb-party" }, h("span", { class: "key d", "aria-hidden": "true" }), "Democrats"), h("strong", { class: "sb-num", "data-end": "dw" }, "0"), h("span", { class: "sb-cap" }, "won or held")),
      h("div", { class: "sb-end r" }, h("span", { class: "sb-party" }, "Republicans", h("span", { class: "key r after", "aria-hidden": "true" })), h("strong", { class: "sb-num", "data-end": "rw" }, "0"), h("span", { class: "sb-cap" }, "won or held")),
    ),
    h(
      "div",
      { class: "sb-bar is-still", role: "img" },
      h("div", { class: "sb-segs" }, SEGS.map((s) => h("span", { class: `sb-seg ${s} is-empty`, "data-seg": s }))),
      h("span", { class: "sb-mid", "aria-hidden": "true" }),
    ),
    h("p", { class: "sb-maj", "aria-hidden": "true" }, h("span", {}, "")),
    h(
      "div",
      { class: "sb-legend" },
      h("ul", { class: "sb-lg", "aria-label": "Democrats" }, h("li", { class: "sb-lg-k" }, "Democrats"), ["dw", "d3", "d2", "d1"].map(legendItem)),
      h("ul", { class: "sb-lg", "aria-label": "Republicans" }, h("li", { class: "sb-lg-k" }, "Republicans"), ["rw", "r3", "r2", "r1"].map(legendItem)),
      h("ul", { class: "sb-lg", "aria-label": "Neither side yet" }, h("li", { class: "sb-lg-k", "aria-hidden": "true" }), ["tu", "ow", "o"].map(legendItem)),
    ),
    h("p", { class: "live-small sb-note" }),
  );
}

// "PA-07, NY-17, CA-13 and 44 more", closest races first.
function raceList(ids, data, N, max = 10) {
  const close = (id) => {
    const r = data.races[id];
    const p = typeof r?.p_live === "number" ? r.p_live : typeof r?.p_pre === "number" ? r.p_pre : 0.5;
    return Math.abs(p - 0.5);
  };
  const sorted = [...ids].sort((a, b) => close(a) - close(b) || a.localeCompare(b));
  const names = sorted.slice(0, max).map((id) => N?.[id]?.[1] ?? id.split(":")[1]);
  const more = sorted.length - names.length;
  return more > 0 ? `${names.join(", ")} and ${more} more` : names.join(", ");
}
// "Kiley (Ind.), CA-06": a lone amber sliver should explain itself.
function othersList(ids, data, N) {
  return ids
    .map((id) => {
      const row = N?.[id], r = data.races[id];
      const dSide = typeof r?.p_live === "number" ? r.p_live >= 0.5 : typeof r?.p_pre === "number" ? r.p_pre >= 0.5 : true;
      const who = dSide ? row?.[2] : row?.[4];
      const party = dSide ? row?.[3] : row?.[5];
      const where = row?.[1] ?? id.split(":")[1];
      return who ? `${who} (${party === "IND" || party === "I" ? "Ind." : party}), ${where}` : where;
    })
    .join("; ");
}

// "Includes 32 not up this year, 2 independents who caucus with Democrats, 11 called tonight"
function wonDetail(sb, s) {
  const c = sb.c;
  const p = s === "dw" ? "D" : s === "rw" ? "R" : null;
  if (!p) {
    const ids = sb.races.ow;
    return ids.length ? `Includes ${ids.map((id) => sb.N?.[id]?.[1] ?? id.split(":")[1]).join(", ")}` : "";
  }
  const held = n(c.not_up?.[p]), caucus = caucusing(c, p), fixed = n(c.fixed?.[p]), tonight = n(c.called?.[p]);
  const bits = [
    held ? `${fmtInt(held)} not up this year` : "",
    caucus ? `${fmtInt(caucus)} independent${caucus === 1 ? "" : "s"} who caucus with ${p === "D" ? "Democrats" : "Republicans"}` : "",
    fixed ? `${fmtInt(fixed)} uncontested` : "",
    tonight ? `${fmtInt(tonight)} called tonight` : "",
  ].filter(Boolean);
  return bits.length ? `Includes ${bits.join(", ")}` : "";
}

/** Fill or update a bar from seatBuckets(). */
export function paintSeats(block, sb, data, N) {
  if (!block || !sb) return;
  const { key, c, count, races, total, runoffs } = sb;
  sb.N = N;
  const bar = block.querySelector(".sb-bar");
  let left = 0;
  for (const s of SEGS) {
    const el = block.querySelector(`.sb-seg[data-seg="${s}"]`);
    const x = count[s];
    const w = total ? (100 * x) / total : 0;
    el.style.left = `${left.toFixed(4)}%`;
    el.style.width = `${w.toFixed(4)}%`;
    left += w;
    el.classList.toggle("is-empty", !x);
    el.classList.toggle("no-races", !races[s].length);
    if (x) {
      el.dataset.tipValue = `${fmtInt(x)} ${noun(key, x)} · ${segLabel(s, runoffs)}`;
      el.dataset.tipLabel =
        s === "dw" || s === "rw" || s === "ow" ? wonDetail(sb, s) : s === "o" ? othersList(races.o, data, N) : raceList(races[s], data, N);
    } else {
      delete el.dataset.tipValue;
      delete el.dataset.tipLabel;
    }
  }
  // Sliding in on the first paint would only be noise.
  if (bar.classList.contains("is-still")) requestAnimationFrame(() => requestAnimationFrame(() => bar.classList.remove("is-still")));

  block.querySelector('[data-end="dw"]').textContent = fmtInt(count.dw);
  block.querySelector('[data-end="rw"]').textContent = fmtInt(count.rw);
  block.querySelector(".sb-maj > span").textContent = MAJ[key](c);

  for (const s of SEGS) {
    const li = block.querySelector(`[data-lgi="${s}"]`);
    if (!li) continue;
    const x = count[s];
    li.hidden = (s === "ow" || s === "o") && !x;
    li.classList.toggle("is-zero", !x);
    block.querySelector(`[data-lgn="${s}"]`).textContent = fmtInt(x);
    if (s === "tu") block.querySelector('[data-lgt="tu"]').textContent = runoffs ? "toss-up or runoff" : "toss-up";
    const btn = li.querySelector("button");
    btn.disabled = !races[s].length; // seats not up this year aren't races: nothing to list
    btn.setAttribute(
      "aria-label",
      `${segLabel(s, runoffs)}: ${fmtInt(x)} ${noun(key, x)}${races[s].length ? ". Show these races on the board" : ""}`,
    );
  }

  bar.setAttribute(
    "aria-label",
    [
      `${key === "governor" ? "Governorships" : key === "senate" ? "Senate seats" : "House seats"}:`,
      `Democrats ${fmtInt(count.dw)} won or held;`,
      `not yet called, favoring Democrats ${count.d3} solid, ${count.d2} likely, ${count.d1} lean;`,
      count.o || count.ow ? `others ${count.ow} won, ${count.o} favored;` : "",
      `${runoffs ? "toss-up or runoff" : "toss-up"} ${count.tu};`,
      `favoring Republicans ${count.r1} lean, ${count.r2} likely, ${count.r3} solid;`,
      `Republicans ${fmtInt(count.rw)} won or held.`,
      `${MAJ[key](c)}.`,
    ]
      .filter(Boolean)
      .join(" "),
  );

  const notUp = sum(c.not_up), fixed = sum(c.fixed), caucus = caucusing(c, "D");
  const parts = [notUp ? `${fmtInt(notUp)} ${noun(key, notUp)} not up this year` : "", fixed ? `${fmtInt(fixed)} uncontested` : ""].filter(Boolean);
  const note = [
    parts.length ? `Won or held includes ${parts.join(" and ")}.` : "",
    caucus ? `The Democrats' ${fmtInt(count.dw)} include ${caucus} independent${caucus === 1 ? "" : "s"} who caucus with them.` : "",
    sb.usePre ? `Too few simulations fit the calls so far, so the stripes use the forecast from before results.` : "",
  ].filter(Boolean);
  block.querySelector(".sb-note").textContent = note.join(" ");
}

// A click on a segment or a legend entry narrows the results board to those races.
document.addEventListener("click", (e) => {
  const t = e.target.closest?.(".sb-seg[data-seg], [data-seg-pick]");
  const block = t?.closest(".sb[data-sb]");
  if (!t || !block || t.disabled || t.classList.contains("is-empty") || t.classList.contains("no-races")) return;
  const seg = t.dataset.seg ?? t.dataset.segPick;
  document.dispatchEvent(new CustomEvent("midterms:board", { detail: { chamber: block.dataset.sb, seg } }));
});

