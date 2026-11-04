// /results/: every race on election night, from live.json's `races` (never
// `events`, which keeps only the newest 120). Senate, governors or House;
// filtered to called, counting, not yet, changed hands or upsets; narrowed by
// a state, district or candidate. The view lives in the URL
// (?chamber=house&show=flips&q=PA), so it can be linked and survives a reload.
import { pct, margin, STATES, surname } from "../lib/format.js";
import {
  h, ID, tag, clock, reportingText, raceLink, sideName, sideLabel, winnerName, winnerParty, partyKey,
  gainText, decided, windowOf, closingText, stateOf, expectations, n, SEGS, segOf, wonSeg, segLabel,
  topTwo, candName, pairText,
} from "./live-util.js";

const VIEWS = { senate: "Senate", governor: "Governors", house: "House" };
const SHOWS = ["all", "called", "counting", "awaiting", "flips", "upsets"];
const has = (o, k) => typeof k === "string" && Object.hasOwn(o, k);

// seg: one segment of a seat bar ("d1": Lean Democratic), picked on the bar.
const ui = { chamber: "senate", show: "all", q: "", seg: "" };
let wired = null;
let args = null;

function readURL() {
  const p = new URLSearchParams(location.search);
  if (has(VIEWS, p.get("chamber"))) ui.chamber = p.get("chamber");
  if (SHOWS.includes(p.get("show"))) ui.show = p.get("show");
  ui.q = (p.get("q") ?? "").slice(0, 60);
  ui.seg = SEGS.includes(p.get("seg")) ? p.get("seg") : "";
}
function writeURL() {
  const p = new URLSearchParams();
  if (ui.chamber !== "senate") p.set("chamber", ui.chamber);
  if (ui.show !== "all") p.set("show", ui.show);
  if (ui.q.trim()) p.set("q", ui.q.trim());
  if (ui.seg) p.set("seg", ui.seg);
  const qs = p.toString();
  history.replaceState(history.state, "", `${location.pathname}${qs ? `?${qs}` : ""}${location.hash}`);
}

function paintControls(box) {
  box.querySelectorAll("[data-view]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === ui.chamber)));
  box.querySelectorAll("[data-show]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.show === ui.show)));
  box.querySelectorAll("[data-map-for]").forEach((m) => (m.hidden = m.dataset.mapFor !== ui.chamber));
}
function changed(box) {
  writeURL();
  paintControls(box);
  if (args) draw(box, ...args);
}
function wire(box) {
  if (wired === box) return;
  wired = box;
  readURL();
  box.addEventListener("click", (e) => {
    const v = e.target.closest?.("button[data-view]");
    if (v && box.contains(v) && has(VIEWS, v.dataset.view)) {
      if (ui.chamber !== v.dataset.view) ui.seg = "";
      ui.chamber = v.dataset.view;
      return changed(box);
    }
    if (e.target.closest?.("[data-seg-clear]") && box.contains(e.target)) {
      ui.seg = "";
      return changed(box);
    }
    const s = e.target.closest?.("button[data-show]");
    if (s && box.contains(s) && SHOWS.includes(s.dataset.show)) {
      ui.show = s.dataset.show;
      changed(box);
    }
  });
  const q = box.querySelector("[data-board-q]");
  if (q) {
    q.value = ui.q;
    let timer;
    q.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        ui.q = q.value.slice(0, 60);
        changed(box);
      }, 150);
    });
  }
  // A seat bar's segment was picked: list those races here.
  document.addEventListener("midterms:board", (e) => {
    const { chamber, seg } = e.detail ?? {};
    if (!has(VIEWS, chamber) || !SEGS.includes(seg)) return;
    Object.assign(ui, { chamber, seg, show: "all", q: "" });
    if (q) q.value = "";
    changed(box);
    box.scrollIntoView({ block: "start" });
  });
  paintControls(box);
}

// --- which races -------------------------------------------------------------

const closeness = (r) => (typeof r.p_pre === "number" ? Math.abs(r.p_pre - 0.5) : 1);
const byClose = (a, b) => closeness(a[1]) - closeness(b[1]) || a[0].localeCompare(b[0]);
const calledAt = (r) => (typeof r.called_at === "string" ? Date.parse(r.called_at) || 0 : 0);
const byCalled = (a, b) => calledAt(b[1]) - calledAt(a[1]) || byClose(a, b);

// "PA", "pa-7", "PA 07", "Pennsylvania", "Fetterman": every word has to match.
// Names only the live file has count too: a winner outside our sides
// (Scalise) and a first round's top two.
const liveNames = (r) =>
  [r?.winner_name, ...(Array.isArray(r?.top_two) ? r.top_two.map((c) => c?.name) : [])].filter((x) => typeof x === "string");
function matcher(q, N, races) {
  const whole = q.trim().toLowerCase();
  if (!whole) return () => true;
  const dist = /^([a-z]{2})[\s-]?(\d{1,2}|al)$/.exec(whole);
  if (dist) {
    const want = `house:${dist[1]}-${dist[2] === "al" ? "al" : dist[2].padStart(2, "0")}`;
    return (id) => id.toLowerCase() === want;
  }
  const terms = whole.split(/[\s,]+/).filter(Boolean).slice(0, 6);
  return (id) => {
    const st = (stateOf(id) ?? "").toLowerCase();
    const row = N?.[id] ?? [];
    const hay = [STATES[st.toUpperCase()] ?? "", row[0] ?? "", row[1] ?? "", row[2] ?? "", row[4] ?? "", ...liveNames(races?.[id])].join(" ").toLowerCase();
    return terms.every((t) => (/^[a-z]{2}$/.test(t) ? st === t || hay.split(/[^a-z']+/).includes(t) : hay.includes(t)));
  };
}

// --- one row -----------------------------------------------------------------

// No margin in the file, none shown: the pipeline leaves it out where it would
// mislead (a first round, or a side it couldn't find in the count), so none is
// worked out from the votes here (MIDTERMS2026, Nov 4).
function count(r) {
  const m = typeof r.margin === "number" && Number.isFinite(r.margin) ? r.margin : null;
  return { m, rep: reportingText(r) }; // "45% reporting" or "early returns"
}
/** A first round's count: "Moore 33.1%, Firment 20.8%", or null. */
function shares(r, t2) {
  const v = r.votes && typeof r.votes === "object" ? r.votes : null;
  const total = v ? n(v.D) + n(v.R) + n(v.other) : 0;
  if (!t2?.length || total <= 0 || !t2.every((c) => n(c.votes) > 0 && n(c.votes) <= total)) return null;
  return t2.map((c) => `${surname(c.name)} ${((100 * n(c.votes)) / total).toFixed(1)}%`).join(", ");
}
function chance(r, N, id) {
  // The forecast is for our D-side against our R-side, which a first round isn't.
  if (topTwo(r)) return null;
  const pre = typeof r.p_pre === "number" ? r.p_pre : null;
  const live = typeof r.p_live === "number" ? r.p_live : pre;
  if (live == null) return null;
  const side = live >= 0.5 ? "D" : "R";
  const who = sideName(N, id, side) ?? (side === "D" ? "The D-side" : "The R-side");
  const p = side === "D" ? live : 1 - live;
  const pp = pre == null ? null : side === "D" ? pre : 1 - pre;
  if (pp == null || Math.abs(p - pp) < 0.005) return `Forecast: ${who} ${pct(p)}.`;
  return `Chance given the calls so far: ${who} ${pct(p)} (${pct(pp)} before results).`;
}

function row(id, r, data, N) {
  const ch = id.split(":")[0];
  const st = r.status;
  const cls = ["brow", `s-${st}`];
  const vs = [sideName(N, id, "D"), sideName(N, id, "R")].filter(Boolean).join(" vs. ");
  const t2 = topTwo(r);
  let main = [];
  const sub = [];

  if (decided(r) && r.winner) {
    const party = winnerParty(r, N, id);
    const who = winnerName(N, id, r.winner, r);
    main = [
      h("span", { class: `key ${partyKey(party)}`, "aria-hidden": "true" }),
      h("strong", {}, st === "uncontested" ? `${who}, uncontested` : `${who} wins`),
      st === "called" && r.called_at ? h("span", { class: "brow-when" }, ` · called ${clock(r.called_at)} ET`) : null,
      r.called_by === "wikipedia" ? h("span", { class: "brow-when" }, " per Wikipedia") : null,
      r.flip === true ? tag(gainText(party, r.held), "gain") : null,
      r.upset === true ? tag("Upset", "upset") : null,
    ];
    if (r.flip === true) cls.push("flip");
    if (r.upset === true) cls.push("upset");
    if (st === "called" && typeof r.p_pre === "number" && (r.winner === "D" || r.winner === "R")) {
      const pw = r.winner === "D" ? r.p_pre : 1 - r.p_pre;
      sub.push(`The forecast gave ${sideName(N, id, r.winner) ?? "the winner"} ${pct(pw)}.`);
    }
    const c = count(r);
    const when = c.rep ? (c.rep === "early returns" ? " in early returns" : ` with ${c.rep}`) : "";
    if (c.m != null) sub.push(`${margin(c.m, sideLabel(N, id, "D"), sideLabel(N, id, "R"))}${when}.`);
    else if (shares(r, t2)) sub.push(`${shares(r, t2)}${when}.`);
  } else if (st === "counting") {
    const c = count(r);
    const lead =
      c.m != null
        ? Math.abs(c.m) < 0.05 ? "Tied" : `${sideName(N, id, c.m > 0 ? "D" : "R") ?? (c.m > 0 ? "D-side" : "R-side")} leads by ${Math.abs(c.m).toFixed(1)} points`
        : t2?.length ? `${candName(t2[0])} leads`
          : null;
    main = [
      h("strong", {}, "Counting"),
      c.rep ? ` · ${c.rep}` : "",
      lead ? ` · ${lead}` : "",
      r.disputed === true ? tag("Disputed") : null,
    ];
    const ch2 = chance(r, N, id);
    if (ch2) sub.push(ch2);
    if (t2 && shares(r, t2)) sub.push(`So far: ${shares(r, t2)}. A majority wins outright; otherwise the top two meet in a runoff.`);
    sub.push("Early returns can mislead.");
    if (r.disputed === true) sub.push("civicAPI and Wikipedia call this race differently, so it isn't treated as called.");
  } else if (st === "runoff") {
    // A first round's pair is its top two, never our sides; an unusable list names no one.
    const pair = t2 ? pairText(t2) : vs;
    main = [h("strong", {}, "Headed to a runoff"), pair ? ` · ${pair}` : ""];
    if (t2 && shares(r, t2)) sub.push(`First round: ${shares(r, t2)}.`);
  } else {
    const w = windowOf(data, id);
    main = [h("span", {}, closingText(w))];
    if (vs) sub.push(`${vs}.`);
    const ch2 = chance(r, N, id);
    if (ch2) sub.push(ch2);
    if (w?.note) sub.push(`${w.note}.`);
  }

  const nm = N?.[id];
  return h(
    "li",
    { class: cls.join(" "), "data-anchor": id },
    h(
      "div",
      { class: "brow-race" },
      h("span", { class: "brow-name" }, raceLink(N, id, 1)),
      ch === "house" && nm?.[0] ? h("span", { class: "brow-title" }, nm[0]) : null,
    ),
    h("div", { class: "brow-what" }, h("p", { class: "brow-main" }, main), sub.length ? h("p", { class: "brow-sub" }, sub.join(" ")) : null),
  );
}

// --- the board -----------------------------------------------------------------

const GROUPS = [
  ["counting", "Counting", "Closest races first, by the forecast."],
  ["called", "Called", "Newest call first."],
  ["runoff", "Headed to a runoff", ""],
  ["awaiting", "Not yet", "Closest races first, by the forecast."],
  ["uncontested", "Uncontested", "Decided before Election Day."],
];
const EMPTY = {
  all: "No race matches that.",
  called: "No race has been called yet.",
  counting: "No race is counting right now.",
  awaiting: "Every race has votes counted.",
  flips: "No seat has changed hands yet.",
  upsets: "No upsets so far.",
};

function draw(box, data, N) {
  const out = box.querySelector("[data-board-list]");
  if (!out) return;
  const match = matcher(ui.q, N, data.races);
  const usePre = data.chambers?.[ui.chamber]?.live?.reliable === false;
  const inSeg = (id, r) => !ui.seg || (decided(r) ? wonSeg(id, r, N) : segOf(id, r, N, usePre)) === ui.seg;
  const all = Object.entries(data.races ?? {}).filter(
    ([id, r]) => ID.test(id) && id.startsWith(`${ui.chamber}:`) && r && typeof r === "object" && match(id) && inSeg(id, r),
  );
  const pill = box.querySelector("[data-board-seg]");
  if (pill) {
    pill.hidden = !ui.seg;
    if (ui.seg) {
      const runoffs = all.filter(([, r]) => r.status === "runoff").length;
      pill.querySelector("[data-board-seg-name]").textContent = `${segLabel(ui.seg, runoffs)} (${all.length} race${all.length === 1 ? "" : "s"})`;
    }
  }
  const g = Object.fromEntries(GROUPS.map(([k]) => [k, []]));
  for (const e of all) (g[e[1].status] ?? g.awaiting).push(e);
  g.counting.sort(byClose);
  g.called.sort(byCalled);
  g.runoff.sort(byClose);
  g.awaiting.sort(byClose);
  g.uncontested.sort((a, b) => a[0].localeCompare(b[0]));
  const flips = all.filter(([, r]) => r.flip === true && decided(r)).sort(byCalled);
  const order = new Map((Array.isArray(data.chambers?.[ui.chamber]?.upsets) ? data.chambers[ui.chamber].upsets : []).map((id, i) => [id, i]));
  const upsets = all
    .filter(([, r]) => r.upset === true && r.status === "called")
    .sort((a, b) => (order.get(a[0]) ?? 1e9) - (order.get(b[0]) ?? 1e9) || byCalled(a, b));

  const counts = { all: all.length, called: g.called.length, counting: g.counting.length, awaiting: g.awaiting.length, flips: flips.length, upsets: upsets.length };
  box.querySelectorAll("[data-ct]").forEach((el) => (el.textContent = String(counts[el.dataset.ct] ?? "")));

  const list = (rows) => h("ol", { class: "brows" }, rows.map(([id, r]) => row(id, r, data, N)));
  let body;
  if (ui.show === "all") {
    const parts = GROUPS.filter(([k]) => g[k].length).map(([k, title, note]) =>
      h("section", { class: "bgroup" }, h("h3", { "data-anchor": `group:${k}` }, `${title} `, h("span", { class: "bgroup-n" }, String(g[k].length))), note ? h("p", { class: "live-small" }, note) : null, list(g[k])),
    );
    body = parts.length ? parts : [h("p", { class: "board-empty" }, EMPTY.all)];
  } else {
    const rows = ui.show === "flips" ? flips : ui.show === "upsets" ? upsets : g[ui.show];
    body = rows.length ? [list(rows)] : [h("p", { class: "board-empty" }, ui.q.trim() ? EMPTY.all : EMPTY[ui.show])];
    if (ui.show === "flips" && typeof data.held_note === "string" && data.held_note) body.push(h("p", { class: "live-small board-foot" }, data.held_note));
  }
  out.replaceChildren(expectations(), ...body);
}

export function renderBoard(box, data, N) {
  wire(box);
  args = [data, N];
  box.querySelector("[data-board-wait]")?.setAttribute("hidden", "");
  box.querySelector("[data-board-main]")?.removeAttribute("hidden");
  draw(box, data, N);
}
