// Election night: a Senate or governor race page's county map (CountyMap.astro).
// It fetches /counties/<chamber>/<slug>.json, written by MIDTERMS2026's
// `midterms counties` (docs/site-data.md) every 5 minutes through Nov 5 and
// every 15 from Nov 6 to Nov 10, now and every 2 minutes while the page is
// visible, and shades each county for the side ahead
// there: four steps by the two-party margin (under 5, 5–15, 15–30, 30+ points),
// striped while under 95% reporting, grey with no votes yet. A missing file
// (Caddy answers null), null, regions: [] or no county that matches a shape
// hides the map, without an error. Text goes in with textContent and dataset
// only; names come from civicAPI.
import { clock, n, reportingText } from "./live-util.js";

const EVERY = 120000; // ms between fetches while the page is visible
const FULL = 95; // a county under this percent reporting gets stripes
const fmt = new Intl.NumberFormat("en-US");

const box = document.querySelector("[data-county-map]");
if (box) start(box);

function start(box) {
  const src = box.dataset.src;
  const paths = new Map([...box.querySelectorAll("path.cty")].map((p) => [p.dataset.fips, p]));
  const names = { D: box.dataset.dname || "D-side", R: box.dataset.rname || "R-side" };
  const from = Date.parse(box.dataset.from ?? "");
  const local = location.hostname === "localhost" || location.hostname === "127.0.0.1";
  const asof = box.querySelector("[data-cm-asof]");
  let timer = null;
  let loaded = 0;

  async function load() {
    // Same rule as live.js: nothing is fetched before the polls start closing.
    if (!local && Number.isFinite(from) && Date.now() < from) return;
    loaded = Date.now();
    let doc;
    try {
      const res = await fetch(src, { cache: "no-cache" });
      doc = res.ok ? await res.json() : null;
    } catch {
      return; // a network blip: keep what is shown and try again next time
    }
    paint(doc);
  }

  function paint(doc) {
    const regions = doc && Array.isArray(doc.regions) ? doc.regions : [];
    for (const p of paths.values()) {
      p.dataset.c = "u";
      p.removeAttribute("data-partial");
      p.dataset.tipValue = `${p.dataset.name}: no votes yet`;
    }
    let matched = 0;
    for (const g of regions) {
      const p = g && typeof g === "object" ? paths.get(String(g.fips ?? "").padStart(5, "0")) : null;
      if (!p) continue;
      matched++;
      const v = g.votes && typeof g.votes === "object" ? g.votes : {};
      const total = n(v.D) + n(v.R) + n(v.other);
      // civicAPI's own name, without a trailing note like New York's
      // "(Active Registered Voters: 211,266)"; the Census name if it has none
      const raw = typeof g.name === "string" ? g.name.replace(/\s*\([^)]*\)\s*$/, "").trim() : "";
      const name = raw || p.dataset.name;
      if (total <= 0) {
        p.dataset.tipValue = `${name}: no votes yet`;
        continue;
      }
      const m = typeof g.margin === "number" && Number.isFinite(g.margin) ? g.margin : null;
      const rep = reportingText({ pct_reporting: g.pct_reporting, votes: v });
      const tail = `${rep ? `${rep}, ` : ""}${fmt.format(total)} votes`;
      if (m == null) {
        p.dataset.c = "n"; // votes, but no two-way margin: a side didn't match
        p.dataset.tipValue = `${name}: ${tail}`;
      } else if (m === 0) {
        p.dataset.c = "t";
        p.dataset.tipValue = `${name}: tied, ${tail}`;
      } else {
        const a = Math.abs(m);
        const side = m > 0 ? "D" : "R";
        p.dataset.c = side.toLowerCase() + (a < 5 ? 1 : a < 15 ? 2 : a < 30 ? 3 : 4);
        p.dataset.tipValue = `${name}: ${names[side]} +${a < 0.05 ? "<0.1" : a.toFixed(1)}, ${tail}`;
      }
      const pr = g.pct_reporting;
      if (typeof pr !== "number" || pr < FULL) p.setAttribute("data-partial", "");
    }
    box.hidden = !matched;
    const t = doc?.fetched ?? doc?.generated;
    const url = typeof doc?.source?.url === "string" && /^https:\/\//.test(doc.source.url) ? doc.source.url : "https://civicapi.org";
    const a = document.createElement("a");
    a.href = url;
    a.textContent = "civicAPI";
    asof.replaceChildren(typeof t === "string" && clock(t) ? `County results as of ${clock(t)} ET · ` : "County results · ", a);
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (document.visibilityState === "visible") await load();
      schedule();
    }, EVERY);
  }
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && Date.now() - loaded >= EVERY) {
      load();
      schedule();
    }
  });
  load();
  schedule();
}
