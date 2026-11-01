// /sim.json — the simulator's parameters, fetched by the /simulator/ page.
// The one export file a browser downloads (about 11 KB gzipped).
import { simParams } from "../lib/data.js";

export function GET() {
  return new Response(JSON.stringify(simParams()), { headers: { "Content-Type": "application/json" } });
}
