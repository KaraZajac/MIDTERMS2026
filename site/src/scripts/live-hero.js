// The top of /results/ on election night: a status line and the next poll
// closing, then a seat bar for the House and one for the Senate (a smaller one
// for governors), each with its chamber's chance of control, and the feed of
// calls beside them. It shows as soon as a live file exists, so before the
// polls close the bars are all forecast: seats not up and uncontested races
// solid, every other race striped or grey.
//
// Built once; every update after that changes text, widths and the feed in
// place, so the bars slide and nothing jumps under a reader.
import { pct1, url } from "../lib/format.js";
import {
  h, NOUN, n, fmtInt, stamp, credit, nextClosing, schedule, closeClock, seatBuckets, majorityLine, changedLine,
} from "./live-util.js";
import { seatBlock, paintSeats } from "./live-seats.js";
import { feedBlock, paintFeed } from "./live-feed.js";
import { checkBlock, paintCheck } from "./live-check.js";

const CHAMBERS = [
  ["house", false],
  ["senate", false],
  ["governor", true],
];
const NAME = { house: "House", senate: "Senate", governor: "Governors" };

function chamberBlock(key, compact) {
  return h(
    "article",
    { class: `hero-ch${compact ? " is-compact" : ""}`, "data-anchor": `hero:${key}`, "data-hero-ch": key },
    h("header", { class: "hero-ch-head" }, h("h3", {}, h("a", { href: url(`/${key}/`) }, NAME[key])), h("p", { class: "hero-odds", "data-odds": true })),
    seatBlock(key, { compact }),
    h("div", { class: "hero-ch-lines", "data-lines": true }),
  );
}

function frame() {
  return h(
    "div",
    { class: "hero" },
    h("h2", { class: "sr-only" }, "Results so far"),
    h(
      "div",
      { class: "hero-top" },
      h("p", { class: "live-fixture", "data-fixture": true, hidden: true }, "Simulated night: test data, not real results"),
      h("p", { class: "hero-status", "data-status": true }),
      h("p", { class: "live-delay", role: "status", "data-live-delay": true, hidden: true }),
      h("div", { "data-live-next": true }),
      h("details", { class: "live-sched", "data-sched": true, hidden: true }, h("summary", {}, "When the polls close, state by state"), h("ol", {}), h("p", { class: "live-small" })),
    ),
    h(
      "div",
      { class: "hero-grid" },
      h(
        "div",
        { class: "hero-bars" },
        CHAMBERS.map(([k, c]) => chamberBlock(k, c)),
        h(
          "p",
          { class: "live-small hero-key" },
          h("span", { class: "sb-sw dw", "aria-hidden": "true" }),
          h("span", { class: "sb-sw rw", "aria-hidden": "true" }),
          " Solid: won, uncontested, or not up this year. ",
          h("span", { class: "sb-sw d3", "aria-hidden": "true" }),
          h("span", { class: "sb-sw r1", "aria-hidden": "true" }),
          " Striped: not called yet, shaded by how strongly the forecast favors a side given the calls so far (solid 95%+, likely 75%+, lean 60%+). ",
          h("span", { class: "sb-sw tu", "aria-hidden": "true" }),
          " Grey: toss-up (neither side at 60%) or headed to a runoff. Past the middle line is a majority. Click a segment to list its races.",
        ),
      ),
      h("div", { class: "hero-feedwrap" }, feedBlock()),
    ),
    checkBlock(),
    h("p", { class: "live-small live-credit", "data-credit": true }),
  );
}

function status(data) {
  const c = data.counts ?? {};
  const contested = n(c.awaiting) + n(c.counting) + n(c.called) + n(c.runoff);
  const first = schedule(data)[0]?.t;
  if (data.status === "awaiting") {
    return [
      h("strong", {}, "No races called yet."),
      first ? ` Polls close from ${closeClock(first)} ET.` : "",
      " Until then the bars show the forecast. This page updates itself every 30 seconds; last update ",
      stamp(data.generated),
      ".",
    ];
  }
  if (data.status === "complete") return [h("strong", {}, `All ${fmtInt(contested)} contested races called.`), " Final update ", stamp(data.generated), "."];
  return [
    h("strong", {}, `${fmtInt(c.called)} of ${fmtInt(contested)} contested races called`),
    n(c.counting) ? `, ${fmtInt(c.counting)} counting` : "",
    n(c.runoff) ? `, ${fmtInt(c.runoff)} headed to runoffs` : "",
    ". Updated ",
    stamp(data.generated),
    ".",
  ];
}

function odds(key, c) {
  const L = c.live ?? {}, P = c.pre ?? {};
  const pc = L.p_control ?? {}, pp = P.p_control ?? {};
  if (L.reliable === false) {
    return [h("span", { class: "hero-odds-k" }, "Chance of control"), h("span", {}, `Not steady yet: too few simulations fit the calls. Before results, Democrats had ${pct1(pp.D)}.`)];
  }
  const neither = n(pc.unclear) >= 0.0005;
  return [
    h("span", { class: "hero-odds-k" }, key === "governor" ? "Chance of a majority" : "Chance of control"),
    h("span", { class: "hero-odds-v" }, h("span", { class: "key d", "aria-hidden": "true" }), "Dem. ", h("strong", {}, pct1(pc.D))),
    h("span", { class: "hero-odds-v" }, h("span", { class: "key r", "aria-hidden": "true" }), "Rep. ", h("strong", {}, pct1(pc.R))),
    neither
      ? h(
          "span",
          { class: "hero-odds-v", "data-tip-value": pct1(pc.unclear), "data-tip-label": key === "governor" ? "A 25–25 split" : "Neither party: an uncommitted independent decides" },
          key === "governor" ? "Tie " : "Neither ",
          h("strong", {}, pct1(pc.unclear)),
        )
      : null,
  ];
}

function lines(key, c, data) {
  const L = c.live ?? {}, P = c.pre ?? {};
  const out = [];
  const moved = n(L.p_control?.D) !== n(P.p_control?.D);
  if (data.status === "awaiting") {
    out.push(h("p", { class: "live-small" }, `No races called yet: the stripes and the chances are the forecast.`));
  } else if (moved && P.p_control) {
    out.push(h("p", { class: "live-small" }, `Chances given the races called so far. Before results: Democrats ${pct1(P.p_control.D)}, Republicans ${pct1(P.p_control.R)}.`));
  }
  if (L.seats && L.reliable !== false) {
    out.push(
      h(
        "p",
        { class: "live-seats" },
        data.status === "awaiting" ? "Democrats' median in the forecast: " : "Democrats' median given the calls: ",
        h("strong", {}, `${L.seats.p50} ${NOUN[key]}`),
        ` · 80% range ${L.seats.p10}–${L.seats.p90}`,
      ),
    );
  }
  out.push(majorityLine(key, c), changedLine(key, c));
  return out.filter(Boolean);
}

/** Fill or update the top of /results/. */
export function renderHero(box, data, N) {
  let root = box.querySelector(":scope > .hero");
  if (!root) {
    root = frame();
    box.replaceChildren(root);
  }
  box.hidden = false;

  root.querySelector("[data-fixture]").hidden = !data.fixture;
  root.querySelector("[data-status]").replaceChildren(...status(data).flat().filter((x) => x != null && x !== ""));
  root.querySelector("[data-live-next]").replaceChildren(data.status === "complete" ? "" : (nextClosing(data) ?? ""));

  const sch = schedule(data);
  const det = root.querySelector("[data-sched]");
  det.hidden = !sch.length || data.status === "complete" || !nextClosing(data);
  det.querySelector("ol").replaceChildren(...sch.map((s) => h("li", {}, h("strong", {}, `${closeClock(s.t)} ET`), h("span", {}, s.text))));
  const src = data.polls_close?.source;
  det.querySelector("p").textContent =
    typeof src?.name === "string" ? `Times from ${src.name}${typeof src.note === "string" ? `: ${src.note}` : ""}.` : "";

  for (const [key] of CHAMBERS) {
    const art = root.querySelector(`[data-hero-ch="${key}"]`);
    const c = data.chambers?.[key];
    if (!c) {
      art.hidden = true;
      continue;
    }
    art.hidden = false;
    art.querySelector("[data-odds]").replaceChildren(...odds(key, c).filter(Boolean));
    paintSeats(art.querySelector(".sb"), seatBuckets(key, data, N), data, N);
    art.querySelector("[data-lines]").replaceChildren(...lines(key, c, data));
  }

  const grid = root.querySelector(".hero-grid");
  grid.classList.toggle("is-awaiting", data.status === "awaiting");
  paintFeed(root.querySelector(".feed"), data, N);
  paintCheck(root.querySelector("[data-check]"), data, N);

  const f = data.forecast ?? {};
  const fromWiki = Object.values(data.races ?? {}).some((r) => r && r.called_by === "wikipedia");
  root.querySelector("[data-credit]").replaceChildren(
    ...[
      typeof data.method === "string" ? `${data.method} ` : "",
      `Chances use the ${f.of_record === false ? "latest" : "frozen"} ${f.version === "deluxe" || !f.version ? "Deluxe" : String(f.version)} forecast. `,
      credit(),
      typeof data.source?.note === "string" && data.source.note ? `; ${data.source.note}` : "",
      ".",
      fromWiki ? " Calls marked “per Wikipedia” come from Wikipedia's results tables." : "",
    ]
      .flat()
      .filter((x) => x != null && x !== ""),
  );
}

