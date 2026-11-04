// /results/: how the forecast is doing on the races called so far (Kara's ask on
// Nov 4, through MIDTERMS2026). Everything comes from live.json: each race's
// status, upset flag and p_pre (the D-side's chance before results), and
// chambers.*.upsets (race ids, biggest upset first). Calls aren't results; the
// scorecard grades the forecast once they're in.
import { pct, url } from "../lib/format.js";
import { h, raceLink, sideLabel } from "./live-util.js";

const COMPETITIVE = 0.75; // "competitive": the favorite had under 75% before results
const SHOW = 5; // upsets listed by name; the rest are counted

export function checkBlock() {
  return h(
    "section",
    { class: "hero-check", "data-check": true, hidden: true },
    h("h3", {}, "Forecast check"),
    h("div", { class: "hero-check-lines", "data-check-lines": true }),
    h("p", { class: "live-small" }, "Calls aren't final results; the ", h("a", { href: url("/scorecard/") }, "scorecard"), " grades the forecast once results are in."),
  );
}

const plural = (k, word) => `${k} ${word}${k === 1 ? "" : "s"}`;

/** The winner's chance before results: p_pre for the D-side, 1 − p_pre for the R-side. */
function winnerPre(r) {
  if (!r || typeof r.p_pre !== "number") return null;
  return r.winner === "D" ? r.p_pre : r.winner === "R" ? 1 - r.p_pre : null;
}

export function paintCheck(box, data, N) {
  const called = Object.entries(data.races ?? {}).filter(([, r]) => r && typeof r === "object" && r.status === "called");
  box.hidden = called.length === 0;
  if (!called.length) return;
  const upsets = called.filter(([, r]) => r.upset === true).length;
  const comp = called.filter(([, r]) => typeof r.p_pre === "number" && Math.max(r.p_pre, 1 - r.p_pre) < COMPETITIVE);
  const compWon = comp.filter(([, r]) => r.upset !== true).length;
  const lines = [
    h("p", {}, "The forecast's favorite has won ", h("strong", {}, `${called.length - upsets} of ${called.length}`), ` ${called.length === 1 ? "race" : "races"} called so far.`),
  ];
  if (comp.length) {
    lines.push(h("p", {}, `In the ${plural(comp.length, "competitive race")} called (the favorite under 75%), the favorite won ${compWon}.`));
  }
  // Each chamber lists its upsets biggest first; across chambers, order by the
  // winner's chance before results, smallest first.
  const ids = [...new Set(Object.values(data.chambers ?? {}).flatMap((c) => (Array.isArray(c?.upsets) ? c.upsets : [])))].filter(
    (id) => typeof id === "string" && winnerPre(data.races?.[id]) != null,
  );
  ids.sort((a, b) => winnerPre(data.races[a]) - winnerPre(data.races[b]));
  if (ids.length) {
    const items = ids.slice(0, SHOW).flatMap((id, i) => {
      const r = data.races[id];
      return [i ? "; " : "", raceLink(N, id, id.startsWith("house:") ? 1 : 0), ` (${sideLabel(N, id, r.winner)} won; the forecast gave the ${r.winner}-side ${pct(winnerPre(r))})`];
    });
    lines.push(h("p", {}, h("strong", {}, "Upsets: "), ...items, ids.length > SHOW ? `; and ${ids.length - SHOW} more` : "", "."));
  }
  box.querySelector("[data-check-lines]").replaceChildren(...lines);
}
