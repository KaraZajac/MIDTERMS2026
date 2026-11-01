// Display helpers shared by every page. Pure functions, no data access.

export const STATES = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California",
  CO: "Colorado", CT: "Connecticut", DE: "Delaware", FL: "Florida", GA: "Georgia",
  HI: "Hawaii", ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa",
  KS: "Kansas", KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland",
  MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi",
  MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada", NH: "New Hampshire",
  NJ: "New Jersey", NM: "New Mexico", NY: "New York", NC: "North Carolina",
  ND: "North Dakota", OH: "Ohio", OK: "Oklahoma", OR: "Oregon", PA: "Pennsylvania",
  RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota", TN: "Tennessee",
  TX: "Texas", UT: "Utah", VT: "Vermont", VA: "Virginia", WA: "Washington",
  WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming", DC: "District of Columbia",
};

/** Base-aware internal URL. */
export const url = (p) => import.meta.env.BASE_URL.replace(/\/$/, "") + p;

export const num = (n) => (n == null ? "—" : Math.round(n).toLocaleString("en-US"));

/** A probability for display: whole percent, with the tails kept honest. */
export function pct(p, digits = 0) {
  if (p == null || Number.isNaN(p)) return "—";
  if (p > 0 && p < 0.005) return "<1%";
  if (p < 1 && p > 0.995) return ">99%";
  return (p * 100).toFixed(digits) + "%";
}
/** One decimal, for the chamber headlines. Tails still clamp. */
export function pct1(p) {
  if (p == null) return "—";
  if (p > 0 && p < 0.001) return "<0.1%";
  if (p < 1 && p > 0.999) return ">99.9%";
  return (p * 100).toFixed(1) + "%";
}

/** "about 9 in 10", "about 3 in 4", "about 1 in 3" — the 538 register. */
export function inWords(p) {
  if (p == null) return "";
  if (p >= 0.995) return "more than 99 in 100";
  if (p <= 0.005) return "less than 1 in 100";
  const fracs = [[1,2],[1,3],[2,3],[1,4],[3,4],[1,5],[4,5],[1,6],[5,6],[1,8],[7,8],[1,10],[9,10],[1,20],[19,20],[1,50],[49,50],[1,100],[99,100]];
  let best = fracs[0], err = 1;
  for (const [a, b] of fracs) {
    const e = Math.abs(a / b - p);
    if (e < err - 1e-9) { err = e; best = [a, b]; }
  }
  return `about ${best[0]} in ${best[1]}`;
}

/** Signed two-party margin from the D side's point of view, e.g. "D+3.4". */
export function margin(m, dLabel = "D", rLabel = "R", digits = 1) {
  if (m == null || Number.isNaN(m)) return "—";
  const a = Math.abs(m);
  if (a < 0.05) return "Even";
  return `${m > 0 ? dLabel : rLabel}+${a.toFixed(digits)}`;
}

/** 538's probability buckets, from the favourite's chance. */
export function bucket(pFav) {
  if (pFav >= 0.95) return 3;   // solid
  if (pFav >= 0.75) return 2;   // likely
  if (pFav >= 0.6) return 1;    // lean
  return 0;                     // toss-up
}
export const BUCKET_WORDS = ["Toss-up", "Lean", "Likely", "Solid"];

/**
 * The colour/label class for a race from the D side's win probability.
 * `dParty` is the D-side candidate's party (D or IND); R side is always R.
 * Returns { key: "d3"|"d2"|"d1"|"i3".."i1"|"tu"|"r1".."r3", label }.
 */
export function rating(pD, dParty = "D") {
  if (pD == null) return { key: "na", label: "No forecast" };
  const fav = pD >= 0.5 ? "D" : "R";
  const b = bucket(fav === "D" ? pD : 1 - pD);
  if (b === 0) return { key: "tu", label: "Toss-up" };
  const side = fav === "R" ? "r" : dParty === "D" ? "d" : "i";
  const who = fav === "R" ? "R" : dParty === "D" ? "D" : "Ind.";
  return { key: `${side}${b}`, label: `${BUCKET_WORDS[b]} ${who}` };
}

/** Sentence fragment for a chamber headline. */
export function favoured(p) {
  if (p >= 0.99) return "are all but certain to";
  if (p >= 0.95) return "are very likely to";
  if (p >= 0.85) return "are clearly favored to";
  if (p >= 0.7) return "are favored to";
  if (p >= 0.6) return "are slightly favored to";
  return null; // toss-up territory
}

export function ordinal(n) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

const ET = "America/New_York";
export function fmtDate(iso, opts = {}) {
  if (!iso) return "—";
  const d = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(iso + "T12:00:00Z") : new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: /T/.test(iso) ? ET : "UTC", ...opts });
}
export function fmtShortDate(iso) {
  return fmtDate(iso, { year: undefined });
}
/** "Nov 1, 2026, 12:12 a.m. ET" */
export function fmtStamp(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const date = d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: ET });
  const time = d
    .toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: ET })
    .replace("AM", "a.m.")
    .replace("PM", "p.m.");
  return `${date}, ${time} ET`;
}

/** Surname for compact labels: "Sherrod Brown" -> "Brown". */
export function surname(name) {
  if (!name) return "";
  const parts = String(name).replace(/\s*\(.*?\)\s*/g, " ").trim().split(/\s+/);
  const suffix = /^(jr\.?|sr\.?|ii|iii|iv)$/i;
  let last = parts.at(-1);
  if (suffix.test(last) && parts.length > 1) last = parts.at(-2);
  return last;
}

export const PARTY_NAMES = { D: "Democrat", R: "Republican", IND: "Independent", I: "Independent", L: "Libertarian", G: "Green" };
export const PARTY_SHORT = { D: "D", R: "R", IND: "Ind.", I: "Ind.", L: "Lib.", G: "Grn." };
