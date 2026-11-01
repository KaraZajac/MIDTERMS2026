// /live-build.json — the copy of live.json the refresh commits
// (data/site/live.json), as of this build. Pages read the server's /live.json
// (rewritten every minute on election night) and this, and show whichever is
// newer, so the committed copy takes over if the server's job stops. "null"
// until the first copy exists; a simulated night (fixture) is never published.
import { liveFile } from "../lib/data.js";

export function GET() {
  const live = liveFile();
  return new Response(JSON.stringify(live && !live.fixture ? live : null) + "\n", {
    headers: { "Content-Type": "application/json" },
  });
}
