// /build.json — what the live site was built from. The server's sync timer
// compares `commit` with main on GitHub and rebuilds when they differ.
import { buildCommit, meta } from "../lib/data.js";

export function GET() {
  const m = meta();
  return new Response(
    JSON.stringify({ commit: buildCommit(), built: new Date().toISOString(), generated: m.generated, phase: m.phase }) + "\n",
    { headers: { "Content-Type": "application/json" } },
  );
}
