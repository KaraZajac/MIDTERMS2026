// Election night: the maps fill in. Once votes are being counted, every tile of
// the Senate and governor maps (TileMap.astro) and every square of the House
// strip (SeatStrip.astro) shows the result instead of the forecast: a called or
// uncontested race takes its winner's colour, a seat that changed hands is
// outlined, and a race not yet called goes neutral. The forecast colours stay
// in the markup; this only sets data-res* attributes and the tooltip, which the
// CSS in global.css (".is-live") reads.
//
// A race still counting is shaded for the side ahead (Kara's ask on election
// night, when civicAPI's desk called races slowly): the leader's lighter colour
// under stripes, like a seat bar's projected segments (data-res-lead). It is
// never a call, so the label says "Leading", never "wins" or "projected".
import { ID, clock, reportingText, winnerName, winnerParty, partyKey, gainText, decided, windowOf, closingText, sideName, n } from "./live-util.js";

const FIGS = "[data-live-map]";
const CELLS = "[data-res-id], #seat-strip .sq[data-id]";

// Votes the two sides need between them before a lead is shown, so a handful of
// early towns (New Hampshire's at midnight) don't paint a state.
const LEAD_FLOOR = 1000;

/** "D" or "R" for the side ahead in a race still counting, or null to leave it plain. */
export function leader(r) {
  if (r?.status !== "counting" || typeof r.margin !== "number" || !Number.isFinite(r.margin) || r.margin === 0) return null;
  const v = r.votes ?? {};
  const d = n(v.D), rep = n(v.R), other = n(v.other);
  if (d + rep < LEAD_FLOOR) return null;
  if (other > d && other > rep) return null; // someone outside the two sides is ahead
  return r.margin > 0 ? "D" : "R"; // margin is the two-party margin, D-side minus R-side
}

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
  const ahead = done ? null : leader(r);
  if (ahead) el.dataset.resLead = ahead === "D" ? "d" : "r";
  else delete el.dataset.resLead;

  let value, label = title;
  if (done) {
    value = r.status === "uncontested" ? `${winnerName(N, id, r.winner, r)}, uncontested` : `${winnerName(N, id, r.winner, r)} wins`;
    const bits = [title];
    if (r.status === "called" && r.called_at) bits.push(`called ${clock(r.called_at)} ET`);
    if (r.flip === true) bits.push(gainText(party, r.held));
    if (r.upset === true) bits.push("upset");
    label = bits.join(" · ");
  } else if (ahead) {
    // "Leading: Kaine (D) +12.3, 45% reporting"
    const by = Math.abs(r.margin) < 0.05 ? "<0.1" : Math.abs(r.margin).toFixed(1);
    const who = sideName(N, id, ahead) ?? (ahead === "D" ? "Democratic side" : "Republican side");
    const rep = reportingText(r);
    value = `Leading: ${who} +${by}${rep ? `, ${rep}` : ""}`;
  } else if (r.status === "counting") {
    const m = typeof r.margin === "number" && Math.abs(r.margin) >= 0.05 ? r.margin : null;
    const lead = m == null ? null : sideName(N, id, m > 0 ? "D" : "R");
    value = ["Counting", reportingText(r)].filter(Boolean).join(" · ");
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
