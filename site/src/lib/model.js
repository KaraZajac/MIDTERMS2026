// Shapes the export into what the pages need. Everything here runs at build
// time; nothing from races.json or polls.json is shipped whole to a browser.
import { racesFile, pollsFile, summary, meta } from "./data.js";
import { STATES, ordinal, rating, surname, PARTY_SHORT } from "./format.js";

export const VERSIONS = ["lite", "classic", "deluxe"];
export const VERSION_NAMES = { lite: "Lite", classic: "Classic", deluxe: "Deluxe" };
export const VERSION_BLURB = {
  lite: "Polls only, and lean plus the national environment where there are none.",
  classic: "Polls plus fundamentals: partisan lean, incumbency and fundraising.",
  deluxe: "Classic plus the expert raters' consensus. The headline forecast.",
};
export const CHAMBERS = ["house", "senate", "governor"];
export const CHAMBER_NAMES = { house: "House", senate: "Senate", governor: "Governors" };

let _races;
export function races() {
  if (!_races) {
    _races = racesFile().races.map((r) => ({ ...r, title: raceTitle(r), short: raceShort(r) }));
  }
  return _races;
}
let _byId;
export function raceById(id) {
  if (!_byId) _byId = new Map(races().map((r) => [r.id, r]));
  return _byId.get(id);
}
export const chamberRaces = (ch) => races().filter((r) => r.chamber === ch);

export function pollsFor(id) {
  return pollsFile().races[id] ?? null;
}

/** "Pennsylvania's 7th District", "Maine Senate", "Ohio Senate (special)", "Ohio governor". */
export function raceTitle(r) {
  const st = r.state_name || STATES[r.state] || r.state;
  if (r.chamber === "house") {
    if (!r.district || /AL$/.test(r.id)) return `${st} at-large district`;
    return `${st}'s ${ordinal(r.district)} District`;
  }
  if (r.chamber === "senate") return `${st} Senate${r.special ? " (special)" : ""}`;
  return `${st} governor`;
}
/** Compact label for tables and tiles: "PA-07", "Maine", "Ohio (special)". */
export function raceShort(r) {
  if (r.chamber === "house") return r.label;
  return `${r.state_name}${r.special ? " (special)" : ""}`;
}

export const pD = (r, v = "deluxe") => r.forecast?.[v]?.p_d_side ?? null;
export const sideKey = (party) => (party === "D" ? "d" : party === "R" ? "r" : "i");

/** Colour class and words for a race under a version. */
export function raceRating(r, v = "deluxe") {
  const p = pD(r, v);
  if (p == null) return { key: "na", label: "No forecast" };
  const out = rating(p, r.d.party);
  // an R-side independent (Kiley) colours amber, not red
  if (p < 0.5 && r.r.party !== "R" && out.key.startsWith("r")) {
    return { key: "i" + out.key.slice(1), label: out.label.replace(/ R$/, " Ind.") };
  }
  return out;
}

/**
 * Is this candidate a sitting member? Redistricting put two incumbents in
 * some districts, and the export then names both: "Al Green & Christian
 * Menefee". Match the candidate against each.
 */
export function isIncumbent(r, c) {
  if (!r.incumbent?.running || !r.incumbent?.name || !c?.name) return false;
  return r.incumbent.name.split(" & ").some((n) => n.trim() === c.name);
}

/** Party letter as shown beside a name. */
export const partyTag = (party) => PARTY_SHORT[party] ?? party;
/** "Collins (R)" */
export function candShort(c) {
  if (!c?.name) return "No candidate";
  return `${surname(c.name)} (${partyTag(c.party)})`;
}
/** Label for the side that leads a margin: "D", "R", or a surname for independents. */
export function sideLabel(r, side) {
  const c = side === "d" ? r.d : r.r;
  if (c.party === "D" || c.party === "R") return c.party;
  return surname(c.name) || "Ind.";
}

/** Competitiveness, 0 (certain) to 1 (coin flip), on the headline version. */
export const closeness = (r, v = "deluxe") => {
  const p = pD(r, v);
  return p == null ? 0 : 1 - Math.abs(p - 0.5) * 2;
};

/** Range of a {min, p} histogram that holds all but `tail` of the mass at each end. */
export function histRange(hist, tail = 0.0005) {
  const { min, p } = hist;
  let lo = 0, hi = p.length - 1, acc = 0;
  for (let i = 0; i < p.length; i++) { acc += p[i]; if (acc > tail) { lo = i; break; } }
  acc = 0;
  for (let i = p.length - 1; i >= 0; i--) { acc += p[i]; if (acc > tail) { hi = i; break; } }
  return [min + lo, min + hi];
}

export function chamberInfo(ch) {
  const s = summary().chambers[ch];
  return { ...s, name: CHAMBER_NAMES[ch], key: ch };
}

export const states = () => meta().states;

/** All races in a state, House districts last. */
export function stateRaces(st) {
  const order = { senate: 0, governor: 1, house: 2 };
  return races()
    .filter((r) => r.state === st)
    .sort((a, b) => order[a.chamber] - order[b.chamber] || (a.district ?? 0) - (b.district ?? 0));
}

/** Races whose favourite is not the incumbent's party, keyed by the favourite's party. */
export function flips(ch, v = "deluxe") {
  const out = { D: [], R: [], IND: [] };
  for (const r of chamberRaces(ch)) {
    const p = pD(r, v);
    if (p == null || r.fixed) continue;
    const inc = r.incumbent?.party;
    const fav = p >= 0.5 ? r.d.party : r.r.party;
    if (!inc || inc === fav) continue;
    (out[fav] ?? out.IND).push(r);
  }
  return out;
}
