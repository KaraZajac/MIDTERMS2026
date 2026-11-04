// County shapes for the race pages' county maps: one JSON per state, with the
// state's outline and each county as an SVG path in a viewBox fitted to the
// state, keyed by the 5-digit FIPS that civicAPI's county results carry.
// Source: us-atlas 3.0.1 counties-10m (Census cartographic boundaries, 1:10m).
// usage (from site/, without touching package.json):
//   npm i --no-save d3-geo@3.1.1 topojson-client@3.1.0 us-atlas@3.0.1
//   node scripts/county-shapes.mjs src/data/county-shapes AL,AR,...
import fs from "node:fs";
import { geoConicConformal, geoPath, geoBounds } from "d3-geo";
import { feature } from "topojson-client";

const topo = JSON.parse(fs.readFileSync(new URL("../node_modules/us-atlas/counties-10m.json", import.meta.url)));
const FIPS = { AL: "01", AZ: "04", AR: "05", CA: "06", CO: "08", CT: "09", DE: "10", FL: "12", GA: "13", HI: "15", ID: "16", IL: "17", IN: "18", IA: "19", KS: "20", KY: "21", LA: "22", ME: "23", MD: "24", MA: "25", MI: "26", MN: "27", MS: "28", MO: "29", MT: "30", NE: "31", NV: "32", NH: "33", NJ: "34", NM: "35", NY: "36", NC: "37", ND: "38", OH: "39", OK: "40", OR: "41", PA: "42", RI: "44", SC: "45", SD: "46", TN: "47", TX: "48", UT: "49", VT: "50", VA: "51", WA: "53", WV: "54", WI: "55", WY: "56" };
const [OUT, list] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const counties = feature(topo, topo.objects.counties).features;
const states = feature(topo, topo.objects.states).features;
let total = 0;
for (const st of list.split(",")) {
  const f = FIPS[st];
  const sf = states.find((s) => s.id === f);
  const cs = counties.filter((c) => String(c.id).startsWith(f)).sort((a, b) => (a.id < b.id ? -1 : 1));
  if (!sf || !cs.length) throw new Error(`no shapes for ${st}`);
  // A conformal conic centred on the state, standard parallels inside its span.
  const [[x0, y0], [x1, y1]] = geoBounds(sf);
  const span = y1 - y0;
  const proj = geoConicConformal().parallels([y0 + span / 6, y1 - span / 6]).rotate([-(x0 + x1) / 2, 0]);
  proj.fitSize([1000, 1000], sf);
  const [[a0, b0], [a1, b1]] = geoPath(proj).bounds(sf);
  const aspect = (b1 - b0) / (a1 - a0);
  let w = 600, h = Math.round(w * aspect);
  if (h > 720) { h = 720; w = Math.round(h / aspect); }
  if (h < 260) h = Math.max(Math.round(w * aspect), 200);
  const pad = 3;
  proj.fitExtent([[pad, pad], [w - pad, h - pad]], sf);
  const path = geoPath(proj).digits(1);
  const doc = {
    st,
    w,
    h,
    source: "us-atlas 3.0.1 counties-10m (U.S. Census Bureau cartographic boundaries)",
    outline: path(sf),
    counties: cs.map((c) => [String(c.id), c.properties.name, path(c)]),
  };
  const s = JSON.stringify(doc);
  fs.writeFileSync(`${OUT}/${st}.json`, s);
  total += s.length;
  console.log(`${st} ${cs.length} counties ${w}x${h} ${(s.length / 1024).toFixed(0)} KB`);
}
console.log(`total ${(total / 1024).toFixed(0)} KB`);
