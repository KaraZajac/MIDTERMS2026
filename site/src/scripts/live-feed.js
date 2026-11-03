// "Latest calls" on /results/: every call, newest first, beside the seat bars
// (under them on a phone). It reads live.json's events (calls, changed calls
// and withdrawn calls: the newest 120), then, for calls older than those, the
// races' own called_at. Uncontested races aren't calls, so they're left out.
//
// The list sits in a box of fixed height, so a new call never pushes the page
// down. New calls get a short highlight, and if the reader has scrolled the
// list, it keeps their place as calls arrive above them.
import { pct } from "../lib/format.js";
import { h, ID, clock, tag, raceLink, winnerName, gainText, schedule, closeClock } from "./live-util.js";

const CH = { house: "House", senate: "Senate", governor: "Governor" };
const FILTERS = [
  ["all", "All"],
  ["senate", "Senate"],
  ["house", "House"],
  ["governor", "Governors"],
  ["flips", "Changed hands"],
];
const TYPES = ["call", "changed", "retracted"];

/** Every call, newest first: [{k, t, race, type, winner, party, flip, upset, pw}] */
function calls(data) {
  const evs = (Array.isArray(data.events) ? data.events : []).filter(
    (e) => e && typeof e === "object" && ID.test(e.race ?? "") && TYPES.includes(e.type) && typeof e.t === "string" && !Number.isNaN(Date.parse(e.t)),
  );
  const out = evs.map((e, i) => ({
    k: `${e.t}|${e.race}|${e.type}|${e.winner ?? ""}`,
    t: e.t,
    race: e.race,
    type: e.type,
    winner: e.winner,
    party: typeof e.party === "string" ? e.party : null,
    flip: e.flip === true,
    upset: e.upset === true,
    pw: typeof e.p_winner_pre === "number" ? e.p_winner_pre : null,
    order: i,
  }));
  // Calls older than the newest 120 events: from the races themselves.
  const inEvents = new Set(evs.map((e) => e.race));
  for (const [id, r] of Object.entries(data.races ?? {})) {
    if (!ID.test(id) || inEvents.has(id) || !r || r.status !== "called" || typeof r.called_at !== "string" || Number.isNaN(Date.parse(r.called_at))) continue;
    const pw = typeof r.p_pre === "number" && (r.winner === "D" || r.winner === "R") ? (r.winner === "D" ? r.p_pre : 1 - r.p_pre) : null;
    out.push({
      k: `${r.called_at}|${id}|call|${r.winner ?? ""}`,
      t: r.called_at,
      race: id,
      type: "call",
      winner: r.winner,
      party: typeof r.party === "string" ? r.party : null,
      flip: r.flip === true,
      upset: r.upset === true,
      pw,
      order: 1e6,
    });
  }
  return out.sort((a, b) => Date.parse(b.t) - Date.parse(a.t) || a.order - b.order || a.race.localeCompare(b.race));
}

const passes = (f) => (c) => f === "all" || (f === "flips" ? c.flip && c.type !== "retracted" : c.race.startsWith(`${f}:`));

function partyOf(c, N) {
  if (c.party) return c.party;
  const row = N?.[c.race];
  return c.winner === "D" ? (row?.[3] ?? "D") : c.winner === "R" ? (row?.[5] ?? "R") : null;
}
const keyOf = (p) => (p === "D" ? "d" : p === "R" ? "r" : "i");

function row(c, data, N, fresh) {
  const ch = c.race.split(":")[0];
  const r = data.races?.[c.race];
  const gone = c.type === "retracted";
  const party = gone ? null : partyOf(c, N);
  const who = winnerName(N, c.race, c.winner, r);
  const surname = c.winner === "D" ? N?.[c.race]?.[2] : c.winner === "R" ? N?.[c.race]?.[4] : null;
  const cls = ["fe", `is-${c.type}`, c.flip && !gone ? "is-flip" : "", c.upset && !gone ? "is-upset" : "", fresh ? "is-new" : ""].filter(Boolean).join(" ");
  const sub = [];
  if (!gone && c.pw != null) sub.push(`The forecast gave ${surname || "the winner"} ${pct(c.pw)}.`);
  if (!gone && r?.called_by === "wikipedia" && r.status === "called") sub.push("Called per Wikipedia's results.");
  if (gone) sub.push("Back to counting.");
  return h(
    "li",
    { class: cls, "data-k": c.k },
    h("time", { class: "fe-t", datetime: c.t }, clock(c.t)),
    h(
      "div",
      { class: "fe-body" },
      h("p", { class: "fe-race" }, h("span", { class: "fe-ch" }, CH[ch]), raceLink(N, c.race, 1)),
      h(
        "p",
        { class: "fe-what" },
        c.type === "changed" ? h("span", { class: "fe-kind" }, "Call changed") : null,
        gone ? h("span", { class: "fe-kind" }, "Call withdrawn") : null,
        gone ? null : h("span", { class: `key ${keyOf(party)}`, "aria-hidden": "true" }),
        gone ? h("span", { class: "fe-gone" }, `${who} wins`) : h("strong", {}, `${who} wins`),
        c.flip && !gone ? tag(gainText(party, r?.held), "gain") : null,
        c.upset && !gone ? tag("Upset", "upset") : null,
      ),
      sub.length ? h("p", { class: "fe-sub" }, sub.join(" ")) : null,
    ),
  );
}

function empty(filter, data) {
  const first = schedule(data)[0]?.t;
  const label = FILTERS.find(([k]) => k === filter)?.[1];
  const text =
    filter === "flips"
      ? "No seat has changed hands yet."
      : filter !== "all"
        ? `No ${filter === "governor" ? "governor" : label} calls yet.`
        : data.status === "awaiting" && first
          ? `No races called yet. The first polls close at ${closeClock(first)} ET.`
          : "No races called yet.";
  return h("li", { class: "fe-empty" }, text);
}

/** The feed's frame; paintFeed() fills it. */
export function feedBlock() {
  return h(
    "section",
    { class: "feed card", "data-anchor": "feed", "aria-labelledby": "feed-h" },
    h("div", { class: "feed-head" }, h("h3", { id: "feed-h" }, "Latest calls"), h("span", { class: "live-small" }, "Newest first · Eastern time")),
    h(
      "div",
      { class: "seg feed-seg", role: "group", "aria-label": "Which calls" },
      FILTERS.map(([k, label]) => h("button", { type: "button", "data-feed": k, "aria-pressed": String(k === "all") }, label, h("span", { class: "ct", "data-feed-ct": k }))),
    ),
    h("ol", { class: "feed-list", "data-feed-list": true, tabindex: "0", "aria-label": "Race calls, newest first" }),
    h(
      "p",
      { class: "live-small feed-foot" },
      "Calls come from civicAPI's decision desk, checked against Wikipedia (which follows AP and the networks). A call here can come before or after the one on TV.",
    ),
  );
}

const state = new WeakMap();

function draw(block, st, keepPlace) {
  const { data, N } = st.last;
  const list = block.querySelector("[data-feed-list]");
  const all = calls(data);
  const shown = all.filter(passes(st.filter));

  // Where the reader is in the list, if they've scrolled it.
  let place = null;
  if (keepPlace && list.scrollTop > 0) {
    const top = list.getBoundingClientRect().top;
    for (const li of list.children) {
      const b = li.getBoundingClientRect();
      if (b.bottom > top + 1) {
        place = { k: li.dataset.k, off: b.top - top };
        break;
      }
    }
  }
  const fresh = st.seen ? all.filter((c) => !st.seen.has(c.k)).map((c) => c.k) : [];
  st.seen = new Set([...(st.seen ?? []), ...all.map((c) => c.k)]);
  const isNew = new Set(fresh);

  list.replaceChildren(...(shown.length ? shown.map((c) => row(c, data, N, isNew.has(c.k))) : [empty(st.filter, data)]));
  if (place) {
    const li = [...list.children].find((x) => x.dataset.k === place.k);
    if (li) list.scrollTop += li.getBoundingClientRect().top - list.getBoundingClientRect().top - place.off;
  } else if (!keepPlace) list.scrollTop = 0;

  for (const [k] of FILTERS) {
    const ct = block.querySelector(`[data-feed-ct="${k}"]`);
    if (ct) ct.textContent = String(all.filter((c) => c.type !== "retracted").filter(passes(k)).length || "");
  }
}

/** Fill or update the feed. */
export function paintFeed(block, data, N) {
  if (!block) return;
  let st = state.get(block);
  if (!st) {
    st = { filter: "all", seen: null, last: null };
    state.set(block, st);
    block.addEventListener("click", (e) => {
      const b = e.target.closest?.("button[data-feed]");
      if (!b || !block.contains(b) || !FILTERS.some(([k]) => k === b.dataset.feed)) return;
      st.filter = b.dataset.feed;
      block.querySelectorAll("button[data-feed]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      if (st.last) draw(block, st, false);
    });
  }
  st.last = { data, N };
  draw(block, st, true);
}
