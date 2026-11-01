// Election night: live results on the home, chamber and race pages.
//
// Two copies of one file (contract: docs/site-data.md, "live.json (election
// night)"): /live.json, which the server rewrites every minute from civicAPI
// (midterms-live.service), and /live-build.json, the copy the refresh commits
// to data/site/live.json, as of this build. While the page is visible it asks
// for both every minute and shows whichever is newer, so if the server's job
// stops, the committed copy takes over.
//
// Everything in the file is third-party text. It only ever goes into the page
// as text (never as HTML), and links are built from race ids that match the
// id pattern, never from URLs in the data.
import { pct, pct1, margin, url, PARTY_SHORT } from "../lib/format.js";

const SOURCES = [url("/live.json"), url("/live-build.json")];
// Simulated nights (tests/fixtures/live/, fixture: true) render only on a local preview.
const LOCAL = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
const EVERY = 60 * 1000;
const ID = /^(house|senate|governor):[A-Za-z0-9-]+$/;
const TITLE = { house: "House", senate: "Senate", governor: "Governorships" };
const NOUN = { house: "seats", senate: "seats", governor: "governorships" };
const FIRST = 8; // calls listed before "earlier calls"
const CIVICAPI = "https://civicapi.org";

// h("p", {class: "x"}, "text", child, [more]): attribute values are mine or
// numbers; children that are not nodes become text nodes.
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs ?? {})) {
    if (v != null && v !== false) el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const k of kids.flat(Infinity)) {
    if (k != null && k !== false && k !== "") el.append(k instanceof Node ? k : String(k));
  }
  return el;
}

function clock(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d
    .toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" })
    .replace("AM", "a.m.")
    .replace("PM", "p.m.");
}
// Base.astro turns <time data-ago> into "2 min ago (9:31 p.m. ET)" and keeps it current.
const stamp = (iso) => h("time", { datetime: iso, "data-ago": true }, `${clock(iso)} ET`);
const n = (x) => (typeof x === "number" && Number.isFinite(x) ? x : 0);
const sum = (o) => Object.values(o ?? {}).reduce((a, b) => a + n(b), 0);
const fmtInt = (x) => Math.round(n(x)).toLocaleString("en-US");
function reporting(x) {
  if (typeof x !== "number") return null;
  if (x >= 100) return "100%";
  if (x > 99) return ">99%";
  if (x > 0 && x < 1) return "<1%";
  return `${Math.round(x)}%`;
}
const tag = (text, cls = "") => h("span", { class: `live-tag ${cls}`.trim() }, text);
const credit = () => ["Results and race calls: ", h("a", { href: CIVICAPI }, "civicAPI"), " (civicapi.org)"];

// --- data --------------------------------------------------------------------

async function get(u) {
  try {
    const r = await fetch(u, { cache: "no-cache" });
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

// --- names and links ---------------------------------------------------------

// race id -> [title, short, D-side surname, party, R-side surname, party]
function raceLink(N, id, which = 0) {
  const row = N?.[id];
  const label = row?.[which] ?? id.split(":")[1];
  return row && ID.test(id) ? h("a", { href: url(`/${id.replace(":", "/").toLowerCase()}/`) }, label) : label;
}
function winnerName(N, id, side, race) {
  const row = N?.[id];
  if (side === "D" && row?.[2]) return `${row[2]} (${PARTY_SHORT[row[3]] ?? row[3]})`;
  if (side === "R" && row?.[4]) return `${row[4]} (${PARTY_SHORT[row[5]] ?? row[5]})`;
  if (race?.winner_name) return String(race.winner_name);
  return "A candidate";
}

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
          `Too few simulations match the calls so far to give a steady chance (an effective ${fmtInt(L.ess)} of ${fmtInt(L.draws)}). Before results, Democrats had ${pct1(pp.D)}.`,
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
    return h(
      "li",
      { class: e.upset && !gone ? "is-upset" : null },
      h("time", { class: "live-t", datetime: e.t }, clock(e.t)),
      h(
        "div",
        {},
        h("div", { class: "live-ev-race" }, raceLink(N, e.race, 0), e.upset && !gone ? tag("Upset", "upset") : null),
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
    h("ol", { class: "live-events" }, first.map(row)),
    rest.length ? h("details", { class: "live-more" }, h("summary", {}, `${rest.length} earlier`), h("ol", { class: "live-events" }, rest.map(row))) : null,
  );
}

function chambersView(data, N, chambers, withTicker) {
  const c = data.counts ?? {};
  const contested = n(c.awaiting) + n(c.counting) + n(c.called) + n(c.runoff);
  const done = data.status === "complete";
  const fromWiki = Object.values(data.races).some((r) => r && r.called_by === "wikipedia");
  const f = data.forecast ?? {};
  return h(
    "div",
    {},
    h(
      "div",
      { class: "live-head" },
      h("p", { class: "eyebrow live-eyebrow" }, h("span", { class: "live-dot", "aria-hidden": "true" }), done ? "Election results" : "Live · election night"),
      data.fixture ? h("p", { class: "live-fixture" }, "Simulated night: test data, not real results") : null,
      h("h2", {}, done ? "The results" : "Results so far"),
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

function awaiting() {
  return h(
    "div",
    { class: "card live-await" },
    h("p", { class: "eyebrow live-eyebrow" }, h("span", { class: "live-dot", "aria-hidden": "true" }), "Election night"),
    h("p", {}, "Polls close from 6 p.m. ET. Results and race calls will appear here as they come in, and the page updates itself every minute."),
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
      ". The count itself doesn't move it.",
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
    h("p", { class: "live-race-status" }, status),
    rows.length ? h("div", { class: "live-votes" }, rows) : null,
    typeof r.margin === "number" ? h("p", { class: "live-small" }, `Two-party margin: ${margin(r.margin, side.D.label || "D", side.R.label || "R")}`) : null,
    chance ? h("p", { class: "live-chance" }, chance) : null,
    h("p", { class: "live-small" }, credit(), r.called_by === "wikipedia" ? "; this call: Wikipedia's results table" : "", "."),
  );
}

// --- loop --------------------------------------------------------------------

const boxes = [...document.querySelectorAll("[data-live]")];
let shown = "";
// No live file can exist before the forecast freezes (data-from = the deadline),
// so until then there is nothing to ask for. A local preview always asks.
const FROM = Math.min(...boxes.map((b) => Date.parse(b.dataset.from ?? "")).filter((t) => !Number.isNaN(t)));
const due = () => LOCAL || !Number.isFinite(FROM) || Date.now() >= FROM;

function render(box, data, N) {
  let node = null;
  if (box.dataset.live === "race") node = raceBanner(box, data);
  else {
    const chambers = (box.dataset.chambers ?? "").split(",").filter((k) => k in TITLE && data.chambers[k]);
    if (chambers.length) node = data.status === "awaiting" ? awaiting() : chambersView(data, N, chambers, box.dataset.ticker === "1");
  }
  if (!node) {
    box.hidden = true;
    box.replaceChildren();
    return;
  }
  const open = box.querySelector(".live-more")?.open;
  box.replaceChildren(node);
  if (open) box.querySelector(".live-more")?.setAttribute("open", "");
  box.hidden = false;
}

async function tick() {
  if (document.hidden || !due()) return;
  const data = await latest();
  if (!data || data.generated === shown) return; // nothing yet, or nothing new: leave what's shown
  const needNames = data.status !== "awaiting" && boxes.some((b) => b.dataset.live === "chambers");
  const N = needNames ? await index() : null;
  boxes.forEach((b) => render(b, data, N));
  if (!needNames || N) shown = data.generated; // retry next minute if the names didn't load
  document.dispatchEvent(new Event("midterms:ages"));
}

if (boxes.length) {
  tick();
  setInterval(tick, EVERY);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) tick();
  });
}
