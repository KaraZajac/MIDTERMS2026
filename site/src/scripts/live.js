// Election night: live results on the home, chamber, race and results pages.
//
// Two copies of one file (contract: docs/site-data.md, "live.json (election
// night)"): /live.json, which the server rewrites every minute from civicAPI
// (midterms-live.service), and /live-build.json, the copy the refresh commits
// to data/site/live.json, as of this build. While the page is visible it asks
// for both every 30 seconds and shows whichever is newer, so if the server's
// job stops, the committed copy takes over.
//
// Everything in the file is third-party text. It only ever goes into the page
// as text (never as HTML), and links are built from race ids that match the
// id pattern, never from URLs in the data. Fields added on election night
// (held, party, flip, gains, losses, flips, polls_close, held_note) are all
// optional here: without them the page shows what it can.
import { pct, pct1, margin, url } from "../lib/format.js";
import {
  h, ID, TITLE, NOUN, PLURAL, clock, stamp, n, sum, fmtInt, reporting, tag, credit, expectations,
  raceLink, winnerName, gainText, abbr, setSkew, schedule, closeClock, nextClosing, closedCount, stale,
} from "./live-util.js";
import { renderBoard } from "./live-board.js";
import { paintMaps } from "./live-maps.js";

const SOURCES = [url("/live.json"), url("/live-build.json")];
// Simulated nights (tests/fixtures/live/, fixture: true) render only on a local preview.
const LOCAL = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
const EVERY = 30 * 1000;
const FIRST = 8; // calls listed before "earlier calls"
const BOARD = url("/results/");

// --- data --------------------------------------------------------------------

async function get(u) {
  try {
    const r = await fetch(u, { cache: "no-cache" });
    const date = Date.parse(r.headers.get("Date") ?? "");
    if (!Number.isNaN(date)) setSkew(date - Date.now());
    if (!r.ok) return null;
    const d = await r.json();
    const ok =
      d && typeof d === "object" && typeof d.generated === "string" &&
      d.races && typeof d.races === "object" && d.chambers && typeof d.chambers === "object";
    return ok && (!d.fixture || LOCAL) ? d : null;
  } catch {
    return null;
  }
}
async function latest() {
  const got = (await Promise.all(SOURCES.map(get))).filter(Boolean);
  got.sort((a, b) => (a.generated < b.generated ? 1 : a.generated > b.generated ? -1 : 0)); // ISO UTC sorts as time
  return got[0] ?? null;
}
let names = null;
async function index() {
  if (!names) {
    try {
      const r = await fetch(url("/race-index.json"));
      if (r.ok) names = await r.json();
    } catch {}
  }
  return names;
}

// --- shared pieces -----------------------------------------------------------

/** "Results feed delayed — last update 9:31 p.m. ET": kept current by paintDelay(). */
const delayNote = () => h("p", { class: "live-delay", role: "status", "data-live-delay": true, hidden: true });
const boardLink = (text) => h("a", { class: "btn primary live-board-link", href: BOARD }, text);

// --- chambers (home and chamber pages) ---------------------------------------

function oddsBar(segs, label) {
  const shown = segs.filter((s) => n(s.p) > 0.0005);
  return h(
    "div",
    { class: "odds-bar", role: "img", "aria-label": `${label}: ${shown.map((s) => `${s.name} ${pct(s.p)}`).join(", ")}` },
    shown.map((s) =>
      h(
        "span",
        { class: s.k + (s.p < 0.12 ? " tight" : ""), style: `flex:${n(s.p)} 1 0`, "data-tip-value": pct(s.p, 1), "data-tip-label": s.name },
        s.p >= 0.12 ? pct(s.p) : "",
      ),
    ),
  );
}
// The likelier party's chance is the big figure; the other is set smaller.
const fig = (p, other) => h("div", { class: n(p) < n(other) ? "hero-fig lesser" : "hero-fig" }, pct1(p).replace("%", ""), h("span", { class: "unit" }, "%"));

/** "For a majority: Democrats need 71 more, Republicans 40." from the seats won or held so far. */
function majorityLine(key, c) {
  const b = c.bloc;
  if (!b || typeof b !== "object" || !n(c.majority)) return null;
  // The Senate: 51 for Democrats; 50 for Republicans, with Vance's tie-breaking vote.
  const need = { D: n(c.majority), R: key === "senate" ? n(c.majority) - 1 : n(c.majority) };
  const left = (p) => Math.max(0, need[p] - n(b[p]));
  const what = key === "governor" ? "governorships" : "seats";
  const reached = (p) =>
    key === "senate" && p === "R"
      ? `Republicans have reached 50 seats: control, with Vice President Vance's tie-breaking vote.`
      : key === "senate"
        ? `Democrats have reached 51 seats: control.`
        : `${PLURAL[p]} have reached ${need[p]} ${what}, a majority.`;
  if (!left("D")) return h("p", { class: "live-need" }, reached("D"));
  if (!left("R")) return h("p", { class: "live-need" }, reached("R"));
  return h(
    "p",
    { class: "live-need" },
    `For ${key === "senate" ? "control" : "a majority"}: Democrats need `,
    h("strong", {}, `${left("D")} more`),
    key === "senate" ? " (51)" : "",
    ", Republicans ",
    h("strong", {}, `${left("R")} more`),
    key === "senate" ? " (50 + Vance)" : "",
    ".",
  );
}

/** "Changed hands: Republicans +5, Democrats +2 · net Rep. +3" */
function changedLine(key, c) {
  const g = c.gains;
  if (!g || typeof g !== "object") return null;
  const gained = Object.entries(g).filter(([, x]) => n(x) > 0).sort((a, b) => n(b[1]) - n(a[1]) || a[0].localeCompare(b[0]));
  const href = `${BOARD}?chamber=${key}&show=flips`;
  if (!gained.length) return n(sum(c.called)) ? h("p", { class: "live-small" }, "No seats have changed hands yet.") : null;
  const lost = c.losses && typeof c.losses === "object" ? c.losses : {};
  const net = (p) => n(g[p]) - n(lost[p]);
  const nd = net("D"), nr = net("R");
  const netText = gained.length > 1 ? (nd > 0 ? `net ${abbr("D")} +${nd}` : nr > 0 ? `net ${abbr("R")} +${nr}` : nd === 0 && nr === 0 ? "no net change" : "") : "";
  return h(
    "p",
    { class: "live-changed" },
    h("span", { class: "live-changed-k" }, "Changed hands"),
    gained.map(([p, x], i) => [i ? ", " : "", `${PLURAL[p] ?? p} +${fmtInt(x)}`]),
    netText ? ` · ${netText}` : "",
    " ",
    h("a", { href }, "see them"),
  );
}

function seatBar(key, c) {
  const b = c.bloc ?? {};
  const D = n(b.D), R = n(b.R), O = n(b.other), U = n(c.uncalled);
  const total = n(c.seats) || D + R + O + U;
  const maj = n(c.majority);
  const parts = [["d", D, "Democrats"], ["i", O, "Others"], ["u", U, "Not yet called"], ["r", R, "Republicans"]].filter(([, x]) => x > 0);
  const held = sum(c.not_up), fixed = sum(c.fixed);
  const incl = [held ? `${held} ${key === "governor" ? "governorships" : "seats"} not up this year` : "", fixed ? `${fixed} uncontested` : ""].filter(Boolean);
  return [
    h(
      "div",
      { class: "live-seatbar", role: "img", "aria-label": `${TITLE[key]} so far: Democrats ${D}, Republicans ${R}${O ? `, others ${O}` : ""}, not yet called ${U}; ${maj} for a majority` },
      h("div", { class: "live-seatfill" }, parts.map(([k, x, name]) => h("span", { class: k, style: `flex:${x} 1 0`, "data-tip-value": fmtInt(x), "data-tip-label": name }))),
      maj && total ? h("span", { class: "live-maj", style: `left:${((100 * maj) / total).toFixed(2)}%` }) : null,
    ),
    h(
      "p",
      { class: "live-seatkey" },
      h("span", {}, h("span", { class: "key d" }), `Democrats ${D}`),
      O ? h("span", {}, h("span", { class: "key i" }), `Others ${O}`) : null,
      h("span", {}, h("span", { class: "key u" }), `Not called ${U}`),
      h("span", {}, h("span", { class: "key r" }), `Republicans ${R}`),
      h("span", {}, `${maj} for a majority`),
    ),
    incl.length ? h("p", { class: "live-small" }, `Won or held so far, including ${incl.join(" and ")}.`) : null,
    majorityLine(key, c),
    changedLine(key, c),
  ];
}

function chamberCard(key, c, N) {
  const L = c.live ?? {}, P = c.pre ?? {};
  const pc = L.p_control ?? {}, pp = P.p_control ?? {};
  const what = key === "governor" ? "a majority of governorships" : `the ${TITLE[key]}`;
  const unclearName = key === "governor" ? "25–25 split" : "Neither party (an uncommitted independent decides)";
  const sub = key === "senate" ? "51 for Democrats; 50 + Vance for Republicans" : key === "governor" ? `${c.majority} of 50 for a majority` : `${c.majority} seats for control`;
  const fav = c.favorites ?? {};
  const ups = (Array.isArray(c.upsets) ? c.upsets : []).filter((id) => ID.test(id));
  const upList = ups.slice(0, 8).flatMap((id, i) => [i ? ", " : "", raceLink(N, id, 1)]);
  return h(
    "article",
    { class: "card live-card" },
    h("header", { class: "live-card-head" }, h("h3", {}, h("a", { href: url(`/${key}/`) }, TITLE[key])), h("span", { class: "live-small" }, sub)),
    L.reliable === false
      ? h(
          "p",
          { class: "live-unreliable" },
          `Too few simulations fit the calls so far to give a steady chance (an effective ${fmtInt(L.ess)} of ${fmtInt(L.draws)}). Before results, Democrats had ${pct1(pp.D)}.`,
        )
      : [
          h(
            "div",
            { class: "live-odds" },
            h("div", {}, h("div", { class: "live-party" }, h("span", { class: "key d" }), "Democrats"), fig(pc.D, pc.R)),
            h("div", { class: "right" }, h("div", { class: "live-party" }, "Republicans", h("span", { class: "key r after" })), fig(pc.R, pc.D)),
          ),
          oddsBar(
            [
              { k: "d", p: pc.D, name: "Democrats" },
              { k: "x", p: pc.unclear ?? 0, name: unclearName },
              { k: "r", p: pc.R, name: "Republicans" },
            ],
            `Chance of winning ${what}, given the races called so far`,
          ),
          h("p", { class: "live-small" }, `Chance of control given the races called so far. Before results: Democrats ${pct1(pp.D)}, Republicans ${pct1(pp.R)}.`),
        ],
    seatBar(key, c),
    L.seats ? h("p", { class: "live-seats" }, "Democrats' median now: ", h("strong", {}, `${L.seats.p50} ${NOUN[key]}`), ` · 80% range ${L.seats.p10}–${L.seats.p90}`) : null,
    fav.called
      ? h(
          "p",
          { class: "live-small" },
          `The forecast's favorite won ${fav.won} of ${fav.called} called races. `,
          ups.length ? ["Upsets: ", upList, ups.length > 8 ? ` and ${ups.length - 8} more` : "", "."] : "No upsets so far.",
        )
      : null,
  );
}

function ticker(data, N, chambers) {
  const evs = (Array.isArray(data.events) ? data.events : []).filter((e) => e && ID.test(e.race) && chambers.includes(e.race.split(":")[0]));
  if (!evs.length) return null;
  const row = (e) => {
    const ch = e.race.split(":")[0];
    const who = winnerName(N, e.race, e.winner, data.races[e.race]);
    const gone = e.type === "retracted";
    const lead = gone ? "Call withdrawn" : e.type === "changed" ? `Call changed: ${who} wins` : `${who} wins`;
    const after = e.after?.[ch];
    const flip = e.flip === true && !gone;
    return h(
      "li",
      { class: [e.upset && !gone ? "is-upset" : "", flip ? "is-flip" : ""].filter(Boolean).join(" ") || null },
      h("time", { class: "live-t", datetime: e.t }, clock(e.t)),
      h(
        "div",
        {},
        h(
          "div",
          { class: "live-ev-race" },
          raceLink(N, e.race, 0),
          flip ? tag(gainText(e.party, data.races[e.race]?.held), "gain") : null,
          e.upset && !gone ? tag("Upset", "upset") : null,
        ),
        h(
          "div",
          { class: "live-ev-what" },
          lead,
          typeof e.p_winner_pre === "number" && !gone ? ` · the forecast gave ${pct(e.p_winner_pre)}` : "",
          typeof after === "number" ? ` · Democrats' ${ch === "governor" ? "governorships" : TITLE[ch]} chance ${pct1(after)}` : "",
        ),
      ),
    );
  };
  const first = evs.slice(0, FIRST), rest = evs.slice(FIRST);
  return h(
    "div",
    { class: "live-ticker" },
    h("h3", {}, chambers.length > 1 ? "Latest calls" : `Latest ${TITLE[chambers[0]]} calls`, h("span", { class: "live-small" }, " · Eastern time")),
    expectations(),
    h("ol", { class: "live-events" }, first.map(row)),
    rest.length ? h("details", { class: "live-more" }, h("summary", {}, `${rest.length} earlier`), h("ol", { class: "live-events" }, rest.map(row))) : null,
    h("p", { class: "live-small live-more-link" }, h("a", { href: BOARD }, "Every call, race by race, on the results board →")),
  );
}

function chambersView(box, data, N, chambers) {
  const c = data.counts ?? {};
  const contested = n(c.awaiting) + n(c.counting) + n(c.called) + n(c.runoff);
  const done = data.status === "complete";
  const fromWiki = Object.values(data.races).some((r) => r && r.called_by === "wikipedia");
  const f = data.forecast ?? {};
  const withTicker = box.dataset.ticker === "1";
  const withLink = box.dataset.boardLink !== "0";
  return h(
    "div",
    {},
    h(
      "div",
      { class: "live-head" },
      h("p", { class: "eyebrow live-eyebrow" }, h("span", { class: "live-dot", "aria-hidden": "true" }), done ? "Election results" : "Live · election night"),
      data.fixture ? h("p", { class: "live-fixture" }, "Simulated night: test data, not real results") : null,
      h(
        "div",
        { class: "live-head-row" },
        h("h2", {}, done ? "The results" : "Results so far"),
        withLink ? boardLink(done ? "Every race →" : "Every race, live →") : null,
      ),
      h(
        "p",
        { class: "live-status" },
        `${fmtInt(c.called)} of ${fmtInt(contested)} contested races called`,
        n(c.counting) ? `, ${fmtInt(c.counting)} counting` : "",
        n(c.runoff) ? `, ${fmtInt(c.runoff)} headed to runoffs` : "",
        ". Updated ",
        stamp(data.generated),
        ".",
      ),
      delayNote(),
      done ? null : h("div", { "data-live-next": true }, nextClosing(data)),
    ),
    h("div", { class: "live-grid" }, chambers.map((k) => chamberCard(k, data.chambers[k], N))),
    withTicker ? ticker(data, N, chambers) : null,
    h(
      "p",
      { class: "live-small live-credit" },
      typeof data.method === "string" ? `${data.method} ` : "",
      `Chances use the ${f.of_record === false ? "latest" : "frozen"} ${f.version === "deluxe" || !f.version ? "Deluxe" : String(f.version)} forecast. `,
      credit(),
      typeof data.source?.note === "string" && data.source.note ? `; ${data.source.note}` : "",
      ".",
      fromWiki ? " Calls marked “per Wikipedia” come from Wikipedia's results tables." : "",
    ),
  );
}

function awaiting(box, data) {
  const sch = schedule(data);
  const withLink = box.dataset.boardLink !== "0";
  return h(
    "div",
    { class: "card live-await" },
    h("p", { class: "eyebrow live-eyebrow" }, h("span", { class: "live-dot", "aria-hidden": "true" }), "Election night"),
    h("p", {}, "Polls close from 6 p.m. ET. Results and race calls will appear here as they come in, and the page updates itself every 30 seconds."),
    delayNote(),
    h("div", { "data-live-next": true }, nextClosing(data)),
    sch.length
      ? h(
          "details",
          { class: "live-sched" },
          h("summary", {}, "When the polls close, state by state"),
          h("ol", {}, sch.map((s) => h("li", {}, h("strong", {}, `${closeClock(s.t)} ET`), h("span", {}, s.text)))),
          typeof data.polls_close?.source?.name === "string"
            ? h("p", { class: "live-small" }, `Times from ${data.polls_close.source.name}`, typeof data.polls_close.source.note === "string" ? `: ${data.polls_close.source.note}` : "", ".")
            : null,
        )
      : null,
    withLink ? h("p", {}, boardLink("The results board →")) : null,
    h("p", { class: "live-small" }, credit(), "."),
  );
}

// --- one race (race pages) ---------------------------------------------------

function raceBanner(box, data) {
  const id = box.dataset.race;
  const r = data.races?.[id];
  if (!r || typeof r !== "object" || data.status === "awaiting" || r.status === "uncontested") return null;
  const side = {
    D: { name: box.dataset.dname, tag: box.dataset.dtag, key: box.dataset.dkey, label: box.dataset.dlabel },
    R: { name: box.dataset.rname, tag: box.dataset.rtag, key: box.dataset.rkey, label: box.dataset.rlabel },
  };
  const who = (s) => (side[s]?.name ? `${side[s].name} (${side[s].tag})` : r.winner_name ? String(r.winner_name) : "Another candidate");
  const called = r.status === "called";

  let status;
  if (called) {
    status = [
      h("strong", {}, `${who(r.winner)} wins`),
      r.called_at ? ` · called ${clock(r.called_at)} ET` : "",
      r.called_by === "wikipedia" ? " per Wikipedia's results" : "",
      r.flip === true ? tag(gainText(r.party, r.held), "gain") : null,
      r.upset ? tag("Upset", "upset") : null,
    ];
  } else if (r.status === "runoff") {
    status = h("strong", {}, "Headed to a runoff");
  } else if (r.status === "counting") {
    status = [h("strong", {}, "Counting"), reporting(r.pct_reporting) ? ` · ${reporting(r.pct_reporting)} reporting` : "", r.disputed ? tag("Disputed") : null];
  } else {
    status = h("strong", {}, "No votes counted yet");
  }

  const v = r.votes && typeof r.votes === "object" ? r.votes : null;
  const total = v ? n(v.D) + n(v.R) + n(v.other) : 0;
  const rows = [];
  if (total > 0) {
    for (const [s, k, name] of [["D", side.D.key, who("D")], ["R", side.R.key, who("R")], ["other", "x", "Others"]]) {
      const x = n(v[s]);
      if (s === "other" && !x) continue;
      const share = x / total;
      rows.push(
        h(
          "div",
          { class: "live-vrow" },
          h("span", { class: "nm" }, name),
          h("span", { class: "sh" }, `${(share * 100).toFixed(1)}%`),
          h("span", { class: "vt" }, fmtInt(x)),
          h("div", { class: "live-vbar", "aria-hidden": "true" }, h("span", { class: k || "x", style: `width:${(share * 100).toFixed(2)}%` })),
        ),
      );
    }
  }

  const pPre = typeof r.p_pre === "number" ? r.p_pre : null;
  const pLive = typeof r.p_live === "number" ? r.p_live : null;
  let chance = null;
  if (called && (r.winner === "D" || r.winner === "R") && pPre != null) {
    const pw = r.winner === "D" ? pPre : 1 - pPre;
    chance = `Before results, the forecast gave ${side[r.winner].name || "the winner"} ${pct(pw)}.`;
  } else if (!called && pLive != null) {
    chance = [
      `Chance now, given the races called elsewhere: ${side.D.name || "D-side"} ${pct1(pLive)}, ${side.R.name || "R-side"} ${pct1(1 - pLive)}`,
      pPre != null ? ` (before results: ${pct1(pPre)} and ${pct1(1 - pPre)})` : "",
      ". Only calls move it, not this count: early returns can mislead.",
      r.disputed ? " civicAPI and Wikipedia call this race differently, so it isn't treated as called." : "",
    ];
  }

  return h(
    "div",
    {},
    h(
      "p",
      { class: "eyebrow live-eyebrow" },
      h("span", { class: "live-dot", "aria-hidden": "true" }),
      data.status === "complete" ? "Results" : "Live results",
      h("span", { class: "live-asof" }, " · ", stamp(data.generated)),
    ),
    data.fixture ? h("p", { class: "live-fixture" }, "Simulated night: test data, not real results") : null,
    delayNote(),
    h("p", { class: "live-race-status" }, status),
    rows.length ? h("div", { class: "live-votes" }, rows) : null,
    typeof r.margin === "number" ? h("p", { class: "live-small" }, `Two-party margin: ${margin(r.margin, side.D.label || "D", side.R.label || "R")}`) : null,
    chance ? h("p", { class: "live-chance" }, chance) : null,
    h("p", { class: "live-small" }, credit(), r.called_by === "wikipedia" ? "; this call: Wikipedia's results table" : "", ". ", h("a", { href: BOARD }, "All results →")),
  );
}

// --- loop --------------------------------------------------------------------

const boxes = [...document.querySelectorAll("[data-live]")];
let shown = "";
let current = null; // {data, N, closed}: what the page shows now
// No live file can exist before the forecast freezes (data-from = the deadline),
// so until then there is nothing to ask for. A local preview always asks.
const FROM = Math.min(...boxes.map((b) => Date.parse(b.dataset.from ?? "")).filter((t) => !Number.isNaN(t)));
const due = () => LOCAL || !Number.isFinite(FROM) || Date.now() >= FROM;

function render(box, data, N) {
  if (box.dataset.live === "board") return renderBoard(box, data, N);
  let node = null;
  if (box.dataset.live === "race") node = raceBanner(box, data);
  else {
    const chambers = (box.dataset.chambers ?? "").split(",").filter((k) => k in TITLE && data.chambers[k]);
    if (chambers.length) node = data.status === "awaiting" ? awaiting(box, data) : chambersView(box, data, N, chambers);
  }
  if (!node) {
    box.hidden = true;
    box.replaceChildren();
    return;
  }
  const open = [...box.querySelectorAll("details")].map((d) => d.open);
  box.replaceChildren(node);
  box.querySelectorAll("details").forEach((d, i) => open[i] && d.setAttribute("open", ""));
  box.hidden = false;
}

// Things that change with the clock rather than the file.
function paintDelay() {
  const late = stale(current?.data);
  document.querySelectorAll("[data-live-delay]").forEach((el) => {
    el.hidden = !late;
    el.textContent = late ? `Results feed delayed — last update ${clock(current.data.generated)} ET` : "";
  });
}
function paintClock() {
  if (!current) return;
  document.querySelectorAll("[data-live-next]").forEach((el) => el.replaceChildren(nextClosing(current.data) ?? ""));
  const closed = closedCount(current.data);
  if (closed !== current.closed) {
    // A closing time has passed: "Polls close 8 p.m." rows now read "closed at".
    current.closed = closed;
    boxes.filter((b) => b.dataset.live === "board").forEach((b) => render(b, current.data, current.N));
    paintMaps(current.data, current.N);
  }
}

async function tick() {
  if (document.hidden || !due()) return;
  const data = await latest();
  if (data && data.generated !== shown) {
    const needNames = data.status !== "awaiting" || boxes.some((b) => b.dataset.live === "board");
    const N = needNames ? await index() : null;
    boxes.forEach((b) => render(b, data, N));
    paintMaps(data, N);
    current = { data, N, closed: closedCount(data) };
    if (!needNames || N) shown = data.generated; // retry next time if the names didn't load
    document.dispatchEvent(new Event("midterms:ages"));
  } else {
    paintClock();
  }
  paintDelay();
}

if (boxes.length) {
  tick();
  setInterval(tick, EVERY);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) tick();
  });
}
