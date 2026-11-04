// /results/, under the gauges: the closest races still counting (Kara's ask on
// Nov 4, through MIDTERMS2026). From live.json: races counting with a numeric
// margin and at least 1,000 votes between the two sides (the same floor as the
// map's lead shading), closest first by |margin|, the first 10, all chambers
// mixed. Each row: the race, the leader in the map's lead look (lighter colour
// under stripes), percent reporting or "early returns", votes counted, and the
// forecast's favourite. A phone shows 5 and a button for the rest.
import { pct } from "../lib/format.js";
import { h, n, raceLink, sideName, reportingText } from "./live-util.js";

const FLOOR = 1000, TOP = 10, PHONE = 5;
const CH = { house: "House", senate: "Senate", governor: "Governor" };
const fmt = new Intl.NumberFormat("en-US");

export function closeBlock() {
  return h(
    "section",
    { class: "close-races", "data-close": true, "aria-labelledby": "close-title" },
    h("h2", { class: "close-title", id: "close-title" }, "Closest races still counting"),
    h("ol", { class: "close-list", "data-close-list": true }),
    h("button", { type: "button", class: "btn close-more", "data-close-more": true, hidden: true }),
    h("p", { class: "live-small" }, "Uncalled races with at least 1,000 votes counted, closest first by the current margin. Leads can change as more ballots are counted."),
  );
}

/** [[id, race], ...]: the closest races counting, at most TOP. */
export function closest(data) {
  return Object.entries(data?.races ?? {})
    .filter(([id, r]) => CH[id.split(":")[0]] && r && r.status === "counting" && typeof r.margin === "number" && Number.isFinite(r.margin) && n(r.votes?.D) + n(r.votes?.R) >= FLOOR)
    .sort((a, b) => Math.abs(a[1].margin) - Math.abs(b[1].margin) || (a[0] < b[0] ? -1 : 1))
    .slice(0, TOP);
}

function row(id, r, N, i) {
  const ch = id.split(":")[0];
  const side = r.margin > 0 ? "D" : r.margin < 0 ? "R" : null;
  const a = Math.abs(r.margin);
  const lead = side
    ? h("span", { class: `close-lead ${side === "D" ? "d" : "r"}` }, `${sideName(N, id, side) ?? (side === "D" ? "D-side" : "R-side")} +${a < 0.05 ? "<0.1" : a.toFixed(1)}`)
    : h("span", { class: "close-lead t" }, "Tied");
  const v = r.votes && typeof r.votes === "object" ? r.votes : {};
  const total = n(v.D) + n(v.R) + n(v.other);
  const fav = typeof r.p_pre === "number" ? (r.p_pre >= 0.5 ? "D" : "R") : null;
  return h(
    "li",
    { class: `close-row${i >= PHONE ? " is-extra" : ""}`, "data-race": id },
    h("span", { class: "close-ch" }, CH[ch]),
    h("span", { class: "close-name" }, raceLink(N, id, ch === "house" ? 1 : 0)),
    h("span", { class: "close-leadcell" }, lead),
    // one grid cell each on a desktop (display: contents); its own line on a phone
    h(
      "span",
      { class: "close-meta" },
      h("span", { class: "close-rep" }, reportingText(r) ?? ""),
      h("span", { class: "close-votes" }, `${fmt.format(total)} votes`),
      h("span", { class: "close-fc" }, fav ? `Forecast: ${sideName(N, id, fav) ?? `${fav}-side`} ${pct(Math.max(r.p_pre, 1 - r.p_pre))}` : ""),
    ),
  );
}

export function paintClose(box, data, N) {
  const rows = closest(data);
  const list = box.querySelector("[data-close-list]");
  const more = box.querySelector("[data-close-more]");
  if (!rows.length) {
    list.replaceChildren(h("li", { class: "close-empty" }, "No close races counting right now."));
    more.hidden = true;
    return;
  }
  list.replaceChildren(...rows.map(([id, r], i) => row(id, r, N, i)));
  const extra = rows.length - PHONE;
  more.hidden = extra <= 0;
  const label = () => (box.classList.contains("is-open") ? "Show fewer" : `Show ${extra} more`);
  more.textContent = label();
  more.onclick = () => {
    box.classList.toggle("is-open");
    more.textContent = label();
  };
}
