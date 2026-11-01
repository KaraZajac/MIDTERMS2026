// /race-index.json — names for the election-night lists, which only carry race
// ids: id -> [title, short label, D-side surname, party, R-side surname, party].
// Fetched once, only when a page has live results to show.
import { races } from "../lib/model.js";
import { surname } from "../lib/format.js";

export function GET() {
  const out = {};
  for (const r of races()) {
    out[r.id] = [r.title, r.short, r.d.name ? surname(r.d.name) : null, r.d.party, r.r.name ? surname(r.r.name) : null, r.r.party];
  }
  return new Response(JSON.stringify(out) + "\n", { headers: { "Content-Type": "application/json" } });
}
