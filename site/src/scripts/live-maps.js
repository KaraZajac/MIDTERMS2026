// Election night: the maps fill in. Once votes are being counted, every tile of
// the Senate and governor maps (TileMap.astro) and every square of the House
// strip (SeatStrip.astro) shows the result instead of the forecast: a called or
// uncontested race takes its winner's colour, a seat that changed hands is
// outlined, and a race not yet called goes neutral. The forecast colours stay
// in the markup; this only sets data-res* attributes and the tooltip, which the
// CSS in global.css (".is-live") reads.
import { ID, clock, reporting, winnerName, winnerParty, partyKey, gainText, decided, windowOf, closingText, sideName } from "./live-util.js";

const FIGS = "[data-live-map]";
const CELLS = "[data-res-id], #seat-strip .sq[data-id]";

function paintCell(el, data, N) {
  const id = el.dataset.resId ?? el.dataset.id;
  const r = ID.test(id ?? "") ? data.races?.[id] : null;
  if (!r || typeof r !== "object") return;
  const title = N?.[id]?.[0] ?? id.split(":")[1];
  const done = decided(r) && r.winner;
  const party = done ? winnerParty(r, N, id) : null;
  el.dataset.res = done ? partyKey(party) : "u";
  el.toggleAttribute("data-res-flip", Boolean(done && r.flip === true));
  el.toggleAttribute("data-res-counting", r.status === "counting");

  let value, label = title;
  if (done) {
    value = r.status === "uncontested" ? `${winnerName(N, id, r.winner, r)}, uncontested` : `${winnerName(N, id, r.winner, r)} wins`;
    const bits = [title];
    if (r.status === "called" && r.called_at) bits.push(`called ${clock(r.called_at)} ET`);
    if (r.flip === true) bits.push(gainText(party, r.held));
    if (r.upset === true) bits.push("upset");
    label = bits.join(" · ");
  } else if (r.status === "counting") {
    const m = typeof r.margin === "number" && Math.abs(r.margin) >= 0.05 ? r.margin : null;
    const lead = m == null ? null : sideName(N, id, m > 0 ? "D" : "R");
    value = ["Counting", reporting(r.pct_reporting) ? `${reporting(r.pct_reporting)} reporting` : null].filter(Boolean).join(" · ");
    label = lead ? `${title} · ${lead} leads by ${Math.abs(m).toFixed(1)}` : title;
  } else if (r.status === "runoff") {
    value = "Headed to a runoff";
  } else {
    value = closingText(windowOf(data, id));
  }
  el.dataset.tipValue = value;
  el.dataset.tipLabel = label;
}

let last = null;
export function paintMaps(data, N) {
  last = { data, N };
  const live = data.status !== "awaiting";
  const figs = document.querySelectorAll(FIGS);
  figs.forEach((f) => f.classList.toggle("is-live", live));
  if (!live || !figs.length) return;
  document.querySelectorAll(CELLS).forEach((el) => paintCell(el, data, N));
}

// SeatStrip repaints its squares (and their tooltips) when the reader switches
// model version; put the results back once it has.
document.addEventListener("midterms:version", () => {
  if (last) setTimeout(() => paintMaps(last.data, last.N), 0);
});
