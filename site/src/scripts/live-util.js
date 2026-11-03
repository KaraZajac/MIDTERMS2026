// Shared by the election-night scripts: live.js (the loop, chambers, ticker,
// race banners), live-board.js (/results/) and live-maps.js (the maps).
//
// Everything in live.json is third-party text. It only ever enters the page as
// text nodes or setAttribute values, never as HTML, and links are built from
// race ids that match ID, never from URLs in the data.
import { url, PARTY_SHORT, STATES } from "../lib/format.js";

export const ID = /^(house|senate|governor):[A-Za-z0-9-]+$/;
export const TITLE = { house: "House", senate: "Senate", governor: "Governorships" };
export const NOUN = { house: "seats", senate: "seats", governor: "governorships" };
export const CIVICAPI = "https://civicapi.org";
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

// The server's job runs every 5 minutes until 22:30Z, then every minute.
const MINUTELY = Date.parse("2026-11-03T22:30:00Z");
/** True when the newest copy is older than the job's cadence allows. */
export function stale(data) {
  if (!data || data.status === "complete" || !iso(data.generated)) return false;
  const t = now();
  const limit = (t < MINUTELY ? 12 : 5) * 60000;
  return t - Date.parse(data.generated) > limit;
}
