// Shared by the election-night scripts: live.js (the loop, chambers, ticker,
// race banners), live-board.js (/results/) and live-maps.js (the maps).
//
// Everything in live.json is third-party text. It only ever enters the page as
// text nodes or setAttribute values, never as HTML, and links are built from
// race ids that match ID, never from URLs in the data.
import { url, bucket, PARTY_SHORT, STATES } from "../lib/format.js";

export const ID = /^(house|senate|governor):[A-Za-z0-9-]+$/;
export const TITLE = { house: "House", senate: "Senate", governor: "Governorships" };
export const NOUN = { house: "seats", senate: "seats", governor: "governorships" };
export const CIVICAPI = "https://civicapi.org";
export const BOARD = url("/results/");
const ABBR = { D: "Dem.", R: "Rep.", IND: "Ind.", I: "Ind." };
export const PLURAL = { D: "Democrats", R: "Republicans", IND: "Independents", I: "Independents" };

// h("p", {class: "x"}, "text", child, [more]): attribute values are mine or
// numbers; children that are not nodes become text nodes.
export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs ?? {})) {
    if (v != null && v !== false) el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const k of kids.flat(Infinity)) {
    if (k != null && k !== false && k !== "") el.append(k instanceof Node ? k : String(k));
  }
  return el;
}

// The server's clock: the reader's, corrected by the Date header of the last
// live fetch, so "polls close in 10 min" and "feed delayed" don't depend on a
// reader's wrong clock.
let skew = 0;
export const setSkew = (ms) => {
  if (Number.isFinite(ms)) skew = ms;
};
export const now = () => Date.now() + skew;

const ET = "America/New_York";
/** "9:41 p.m." */
export function clock(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d
    .toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: ET })
    .replace("AM", "a.m.")
    .replace("PM", "p.m.");
}
/** Poll-closing times as people say them: "6 p.m.", "7:30 p.m.", "midnight", "1 a.m." */
export function closeClock(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: ET }).formatToParts(d);
  const get = (t) => parts.find((p) => p.type === t)?.value ?? "";
  const hh = get("hour"), mm = get("minute"), am = /a/i.test(get("dayPeriod"));
  if (hh === "12" && mm === "00") return am ? "midnight" : "noon";
  return `${hh}${mm === "00" ? "" : `:${mm}`} ${am ? "a.m." : "p.m."}`;
}
/** "7–8 p.m.", "11 p.m.–midnight" */
function closeRange(a, b) {
  const x = closeClock(a), y = closeClock(b);
  const m = /^(.*) (a\.m\.|p\.m\.)$/.exec(x);
  return m && y.endsWith(` ${m[2]}`) ? `${m[1]}–${y}` : `${x}–${y}`;
}
// Base.astro turns <time data-ago> into "2 min ago (9:31 p.m. ET)" and keeps it current.
export const stamp = (iso) => h("time", { datetime: iso, "data-ago": true }, `${clock(iso)} ET`);

export const n = (x) => (typeof x === "number" && Number.isFinite(x) ? x : 0);
export const sum = (o) => Object.values(o ?? {}).reduce((a, b) => a + n(b), 0);
export const fmtInt = (x) => Math.round(n(x)).toLocaleString("en-US");
export function reporting(x) {
  if (typeof x !== "number") return null;
  if (x >= 100) return "100%";
  if (x > 99) return ">99%";
  if (x > 0 && x < 1) return "<1%";
  return `${Math.round(x)}%`;
}
/** "45% reporting", or "early returns" when votes are in but the percent is 0 or
 *  missing: civicAPI's percent often stays at 0 until precincts finish, and "0%"
 *  next to thousands of votes reads as an error (MIDTERMS2026, Nov 4). Null when
 *  there's nothing to say. */
export function reportingText(r) {
  const x = r?.pct_reporting;
  const v = r?.votes && typeof r.votes === "object" ? r.votes : null;
  const any = v ? n(v.D) + n(v.R) + n(v.other) > 0 : false;
  if (any && (typeof x !== "number" || x === 0)) return "early returns";
  const p = reporting(x);
  return p ? `${p} reporting` : null;
}
export const tag = (text, cls = "") => h("span", { class: `live-tag ${cls}`.trim() }, text);
export const credit = () => ["Results and race calls: ", h("a", { href: CIVICAPI }, "civicAPI"), " (civicapi.org)"];
/** The one line that sets expectations wherever calls are listed. */
export const expectations = () =>
  h(
    "p",
    { class: "live-small live-expect" },
    "Calls come from civicAPI's decision desk, checked against Wikipedia (which follows AP and the networks). A call here can come before or after the one on TV.",
  );

// --- names and links ---------------------------------------------------------

// N is /race-index.json: race id -> [title, short, D-side surname, party, R-side surname, party]
export function raceLink(N, id, which = 0) {
  const row = N?.[id];
  const label = row?.[which] ?? id.split(":")[1];
  return row && ID.test(id) ? h("a", { href: url(`/${id.replace(":", "/").toLowerCase()}/`) }, label) : label;
}
const short = (p) => PARTY_SHORT[p] ?? p;
/** "Brown (D)" for a side, or null when the index has no candidate. */
export function sideName(N, id, side) {
  const row = N?.[id];
  if (side === "D" && row?.[2]) return `${row[2]} (${short(row[3])})`;
  if (side === "R" && row?.[4]) return `${row[4]} (${short(row[5])})`;
  return null;
}
export function winnerName(N, id, side, race) {
  const s = side === "D" || side === "R" ? sideName(N, id, side) : null;
  if (s) return s;
  if (race?.winner_name) return String(race.winner_name);
  return "A candidate";
}
/** Label for the side that leads a margin: "D", "R", or a surname for independents. */
export function sideLabel(N, id, side) {
  const row = N?.[id];
  const party = side === "D" ? row?.[3] : row?.[5];
  if (party === "D" || party === "R") return party;
  return (side === "D" ? row?.[2] : row?.[4]) || (side === "D" ? "D" : "R");
}

// --- parties and seats changing hands ------------------------------------------

/** The winner's party: the file's `party`, else the nominee's from the index. */
export function winnerParty(r, N, id) {
  if (typeof r?.party === "string" && r.party) return r.party;
  const row = N?.[id];
  if (r?.winner === "D") return row?.[3] ?? "D";
  if (r?.winner === "R") return row?.[5] ?? "R";
  return null;
}
/** Colour key for a party: d, r, or i (independents and everyone else). */
export const partyKey = (p) => (p === "D" ? "d" : p === "R" ? "r" : "i");
export const abbr = (p) => ABBR[p] ?? short(p) ?? "";
/** "Dem. gain from Rep." */
export function gainText(party, held) {
  if (!party) return "Changed hands";
  return held && held !== party ? `${abbr(party)} gain from ${abbr(held)}` : `${abbr(party)} gain`;
}
export const decided = (r) => r?.status === "called" || r?.status === "uncontested";

// --- poll closings -------------------------------------------------------------

export const stateOf = (id) => /^[a-z]+:([A-Za-z]{2})/.exec(id)?.[1].toUpperCase() ?? null;
const iso = (x) => typeof x === "string" && !Number.isNaN(Date.parse(x));

/** A race's polling window: its own (FL-01, FL-02), else its state's. */
export function windowOf(data, id) {
  const pc = data?.polls_close;
  if (!pc || typeof pc !== "object") return null;
  const own = pc.races?.[id];
  const st = pc.states?.[stateOf(id)];
  const w = own && iso(own.first) ? own : st && iso(st.first) ? st : null;
  if (!w) return null;
  const last = iso(w.last) ? w.last : w.first;
  return { first: w.first, last, note: w === st && last !== w.first && typeof st.note === "string" ? st.note : null };
}

/** The not-yet line: "Polls close 8 p.m. ET", then "Polls closed at 8 p.m. ET · no votes counted yet". */
export function closingText(w, t = now()) {
  if (!w) return "No votes counted yet";
  const f = Date.parse(w.first), l = Date.parse(w.last);
  if (t < f) return w.first === w.last ? `Polls close at ${closeClock(w.first)} ET` : `Polls close ${closeRange(w.first, w.last)} ET`;
  if (t < l) return `Polls closed at ${closeClock(w.first)} ET in part of the state; the rest close at ${closeClock(w.last)} ET`;
  return `Polls closed at ${closeClock(w.last)} ET · no votes counted yet`;
}

const list = (a) => (a.length <= 2 ? a.join(" and ") : `${a.slice(0, -1).join(", ")} and ${a.at(-1)}`);
const names = (codes) => codes.map((c) => STATES[c] ?? c).sort((a, b) => a.localeCompare(b));

/** The night's closings: [{t, text}] in time order. A state split across time
 *  zones appears twice: "parts of Florida", then "the rest of Florida". */
export function schedule(data) {
  const st = data?.polls_close?.states;
  if (!st || typeof st !== "object") return [];
  const at = new Map();
  const slot = (t) => {
    if (!at.has(t)) at.set(t, { t, all: [], part: [], rest: [] });
    return at.get(t);
  };
  for (const [code, w] of Object.entries(st)) {
    if (!/^[A-Z]{2}$/.test(code) || !w || !iso(w.first)) continue;
    const last = iso(w.last) ? w.last : w.first;
    if (Date.parse(last) === Date.parse(w.first)) slot(w.first).all.push(code);
    else {
      slot(w.first).part.push(code);
      slot(last).rest.push(code);
    }
  }
  return [...at.values()]
    .sort((a, b) => Date.parse(a.t) - Date.parse(b.t))
    .map((s) => ({
      t: s.t,
      text: [
        s.all.length ? list(names(s.all)) : "",
        s.part.length ? `parts of ${list(names(s.part))}` : "",
        s.rest.length ? `the rest of ${list(names(s.rest))}` : "",
      ]
        .filter(Boolean)
        .join("; ")
        .replace(/^./, (c) => c.toUpperCase()),
    }));
}

function until(ms) {
  const m = Math.max(1, Math.round(ms / 60000));
  if (m < 60) return `in ${m} min`;
  const hr = Math.floor(m / 60), r = m % 60;
  return r ? `in ${hr} hr ${r} min` : `in ${hr} hr`;
}
/** "Next poll closing: 8 p.m. ET, in 25 min · Alabama, ..." or null once every poll has closed. */
export function nextClosing(data) {
  const t = now();
  const next = schedule(data).find((s) => Date.parse(s.t) > t);
  if (!next) return null;
  const left = Date.parse(next.t) - t;
  return h(
    "p",
    { class: "live-next" },
    h("span", { class: "live-next-k" }, "Next poll closing"),
    h("strong", {}, `${closeClock(next.t)} ET`),
    left < 3 * 3600000 ? h("span", { class: "live-next-in" }, until(left)) : null,
    h("span", { class: "live-next-st" }, next.text),
  );
}
/** How many closing times have passed: when it changes, "not yet" rows need redrawing. */
export const closedCount = (data) => schedule(data).filter((s) => Date.parse(s.t) <= now()).length;

// --- a stalled feed --------------------------------------------------------------

// How old the newest copy may get before the page says "Results feed delayed",
// in minutes, by when the server's job runs: every 5 minutes until Nov 3 22:30Z,
// every minute through Nov 5, then every 5 minutes again from Nov 6 through
// Nov 10 while late ballots are counted (15 minutes: three missed runs). The job
// ends with Nov 10. After that the only copy is the repository's, refreshed every
// six hours, and the page's updated time says enough, so the warning stays off
// (MIDTERMS2026, Nov 4).
const LIMITS = [
  [Date.parse("2026-11-03T22:30:00Z"), 12],
  [Date.parse("2026-11-06T00:00:00Z"), 5],
  [Date.parse("2026-11-11T00:00:00Z"), 15],
];
/** True when the newest copy is older than the job's cadence allows. */
export function stale(data) {
  if (!data || data.status === "complete" || !iso(data.generated)) return false;
  const t = now();
  const step = LIMITS.find(([until]) => t < until);
  return step ? t - Date.parse(data.generated) > step[1] * 60000 : false;
}

// --- what each chamber still needs, and what changed hands ----------------------

/** "For a majority: Democrats need 71 more, Republicans 40." from the seats won or held so far. */
export function majorityLine(key, c) {
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
export function changedLine(key, c) {
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

// --- the seat bars (live-seats.js) and the board's segment filter -----------------

/** Seat-bar segments, left to right: Democrats' seats won or held (dw); races
 *  not yet called that lean their way, Solid, Likely, Lean (d3, d2, d1); seats
 *  won by independents and others (ow) and races they're favored in (o), in the
 *  middle because the model counts them as uncommitted; toss-ups and runoffs
 *  (tu); then the Republican mirror (r1, r2, r3, rw). */
export const SEGS = ["dw", "d3", "d2", "d1", "ow", "o", "tu", "r1", "r2", "r3", "rw"];
const STRENGTH = { 3: "Solid", 2: "Likely", 1: "Lean" };

/** "Lean Republican", "Toss-up or runoff", "Democrats: won or held" */
export function segLabel(seg, runoffs = 0) {
  if (seg === "dw") return "Democrats: won or held";
  if (seg === "rw") return "Republicans: won or held";
  if (seg === "ow") return "Others: won or held";
  if (seg === "o") return "Others favored";
  if (seg === "tu") return runoffs ? "Toss-up or runoff" : "Toss-up";
  const m = /^([dr])([123])$/.exec(seg);
  return m ? `${STRENGTH[m[2]]} ${m[1] === "d" ? "Democratic" : "Republican"}` : "";
}

const prob = (x) => (typeof x === "number" && Number.isFinite(x) ? x : null);

/** Where a race not yet decided sits on the bar. By P(D-side wins) given the
 *  calls so far (or before results, when too few simulations fit the calls),
 *  bucketed with format.js bucket(), the forecast maps' thresholds; the
 *  favored side's party comes from the race index, and anything but D or R is
 *  "o". Runoffs are grey. */
export function segOf(id, r, N, usePre = false) {
  if (r?.status === "runoff") return "tu";
  const p = usePre ? (prob(r?.p_pre) ?? prob(r?.p_live)) : (prob(r?.p_live) ?? prob(r?.p_pre));
  if (p == null) return "tu";
  const fav = p >= 0.5 ? "D" : "R";
  const b = bucket(fav === "D" ? p : 1 - p);
  if (!b) return "tu";
  const party = fav === "D" ? (N?.[id]?.[3] ?? "D") : (N?.[id]?.[5] ?? "R");
  return party === "D" ? `d${b}` : party === "R" ? `r${b}` : "o";
}
/** The won segment a decided race belongs to. */
export function wonSeg(id, r, N) {
  const p = winnerParty(r, N, id);
  return p === "D" ? "dw" : p === "R" ? "rw" : "ow";
}

/** Independents folded into a party's seats: King and Sanders, not up this
 *  year, caucus with Democrats. bloc = not_up + fixed + called, under the caucus rule. */
export function caucusing(c, p) {
  return Math.max(0, n(c?.bloc?.[p]) - n(c?.not_up?.[p]) - n(c?.fixed?.[p]) - n(c?.called?.[p]));
}

/** One chamber's bar: seats per segment and the races behind each. */
export function seatBuckets(key, data, N) {
  const c = data?.chambers?.[key];
  if (!c || typeof c !== "object") return null;
  const usePre = c.live?.reliable === false;
  const count = Object.fromEntries(SEGS.map((s) => [s, 0]));
  const races = Object.fromEntries(SEGS.map((s) => [s, []]));
  const b = c.bloc ?? {};
  count.dw = n(b.D);
  count.rw = n(b.R);
  count.ow = n(b.other);
  let runoffs = 0;
  for (const [id, r] of Object.entries(data.races ?? {})) {
    if (!ID.test(id) || !id.startsWith(`${key}:`) || !r || typeof r !== "object") continue;
    if (decided(r)) {
      races[wonSeg(id, r, N)].push(id);
      continue;
    }
    const s = segOf(id, r, N, usePre);
    count[s] += 1;
    races[s].push(id);
    if (r.status === "runoff") runoffs += 1;
  }
  const filled = SEGS.reduce((a, s) => a + count[s], 0);
  return { key, c, count, races, total: filled || n(c.seats), usePre, runoffs };
}
