// MIDTERMS2026 — the correlated simulator, for the browser.
//
// A dependency-free ES module that reproduces midterms/model/simulate.py from
// data/site/sim.json, so a page can answer what-if questions live.
//
// One-shot:
//   import { simulate } from "./simulator.mjs";
//   const out = simulate({ params: sim, n: 5000, seed: 1, shift: 2,
//                          forced: { "senate:TX": "D" } });
//
// Interactive (draw the randomness once, re-run cheaply on every slider move):
//   import { createEngine } from "./simulator.mjs";
//   const engine = createEngine(sim, { nSims: 5000 });      // ~0.3 s, once
//   const out = engine.run({                                  // ~10–30 ms
//     version: "deluxe",       // lite | classic | deluxe
//     shift: 2,                // move every race 2 pts toward Democrats (λ-loaded)
//     natScale: 1,             // scale the national polling-error sd
//     forced: { "senate:TX": "D", "house:PA-07": "R" },      // condition on outcomes
//   });
//   out.accepted                // simulations consistent with `forced`
//   out.chambers.senate.p.D     // P(Democratic control | everything above)
//   out.races["senate:ME"]      // P(D-side wins Maine | everything above)
//
// Error structure per draw s and race r (as in Python):
//   margin = mu_r + shift·λ_r + λ_r·national_s + region_s + state_s
//            + [House only] house_s + idio_{s,r}
// national and idio are unit-variance Student-t (ν from sim.shared), scaled by
// their sds; region, state and the House-wide term are normal. All random
// numbers are drawn once in createEngine; run() only re-adds them, which is
// what makes sliders interactive. Conditioning (`forced`) keeps only the draws
// where the forced races go the forced way — exact, but with fewer effective
// draws as the scenario gets less likely (check `accepted`).

export function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function makeGauss(rand) {
  let spare = null;
  return function gauss() {
    if (spare !== null) {
      const s = spare;
      spare = null;
      return s;
    }
    let u, v, q;
    do {
      u = 2 * rand() - 1;
      v = 2 * rand() - 1;
      q = u * u + v * v;
    } while (q >= 1 || q === 0);
    const f = Math.sqrt((-2 * Math.log(q)) / q);
    spare = v * f;
    return u * f;
  };
}

// Marsaglia–Tsang gamma(shape >= 1, scale 1)
function gamma(shape, gauss, rand) {
  const d = shape - 1 / 3;
  const c = 1 / Math.sqrt(9 * d);
  for (;;) {
    let x, v;
    do {
      x = gauss();
      v = 1 + c * x;
    } while (v <= 0);
    v = v * v * v;
    const u = rand();
    if (u < 1 - 0.0331 * x * x * x * x) return d * v;
    if (Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v;
  }
}

// Student-t rescaled to unit variance (nu > 2); normal when nu is huge
function studentT(nu, gauss, rand) {
  if (!Number.isFinite(nu) || nu > 200) return gauss();
  const z = gauss();
  const chi2 = 2 * gamma(nu / 2, gauss, rand);
  return (z / Math.sqrt(chi2 / nu)) * Math.sqrt((nu - 2) / nu);
}

export function createEngine(sim, { nSims = 5000, seed = 20261103 } = {}) {
  const races = sim.races;
  const R = races.length;
  const sh = sim.shared;
  const rand = mulberry32(seed);
  const gauss = makeGauss(rand);

  const regionOf = {};
  for (const [reg, sts] of Object.entries(sim.regions)) for (const s of sts) regionOf[s] = reg;
  const regions = Object.keys(sim.regions).sort();
  const states = [...new Set(races.map((r) => r.state))].sort();
  const sIdx = Int32Array.from(races.map((r) => states.indexOf(r.state)));
  const gIdx = Int32Array.from(races.map((r) => Math.max(0, regions.indexOf(regionOf[r.state] ?? "South"))));
  const chamberNames = [...new Set(races.map((r) => r.chamber))];
  const cIdx = Int32Array.from(races.map((r) => chamberNames.indexOf(r.chamber)));
  const lam = Float64Array.from(races.map((r) => r.lam ?? 1));
  const sdChamber = Float64Array.from(chamberNames.map((c) => (sh.sd_chamber || {})[c] || 0));

  // unit random draws, once
  const G = regions.length, S = states.length, C = chamberNames.length;
  const nat = new Float32Array(nSims);
  const reg = new Float32Array(nSims * G);
  const st = new Float32Array(nSims * S);
  const cham = new Float32Array(nSims * C);
  const idio = new Float32Array(nSims * R);
  for (let s = 0; s < nSims; s++) {
    nat[s] = studentT(sh.nu_national, gauss, rand);
    for (let g = 0; g < G; g++) reg[s * G + g] = gauss();
    for (let k = 0; k < S; k++) st[s * S + k] = gauss();
    for (let c = 0; c < C; c++) cham[s * C + c] = gauss();
    for (let r = 0; r < R; r++) idio[s * R + r] = studentT(sh.nu_race, gauss, rand);
  }

  // party codes for seat accounting
  const parties = new Set();
  for (const r of races) {
    parties.add(r.d_side || "D");
    parties.add(r.r_side || "R");
  }
  for (const ch of Object.values(sim.chambers)) for (const p of Object.keys(ch.seats_not_up || {})) parties.add(p);
  const partyList = [...parties].sort();
  const pcode = Object.fromEntries(partyList.map((p, i) => [p, i]));
  const dParty = Int32Array.from(races.map((r) => pcode[r.d_side || "D"]));
  const rParty = Int32Array.from(races.map((r) => pcode[r.r_side || "R"]));
  const indexOf = Object.fromEntries(races.map((r, i) => [r.id, i]));

  function control(totals, ch, caucus) {
    let d = 0, r = 0;
    for (let i = 0; i < partyList.length; i++) {
      const p = partyList[i];
      const bloc = (caucus && caucus[p]) || p;
      if (bloc === "D") d += totals[i];
      else if (bloc === "R") r += totals[i];
    }
    let dc = d >= ch.majority, rc = r >= ch.majority;
    if (ch.tie_breaker) {
      const half = ch.majority - 1;
      if (d === half && r === half) {
        if (ch.tie_breaker === "D") dc = true;
        else rc = true;
      }
    }
    return [d, dc ? "D" : rc ? "R" : "unclear"];
  }

  function run({ version = "deluxe", shift = 0, natScale = 1, forced = {} } = {}) {
    const mu = new Float64Array(R), sd = new Float64Array(R), fixedVal = new Int8Array(R);
    for (let i = 0; i < R; i++) {
      const r = races[i];
      if (r.fixed) {
        fixedVal[i] = r.fixed === r.d_side ? 1 : -1;
      } else {
        mu[i] = r.mu[version];
        sd[i] = Math.max(r.sd[version], sh.floor_idio ?? 0.5);
      }
    }
    const forcedList = Object.entries(forced)
      .filter(([id]) => id in indexOf)
      .map(([id, side]) => [indexOf[id], side === "D" ? 1 : -1]);
    const sdNat = sh.sd_national * natScale;

    const wins = new Float64Array(R);
    const tallies = {};
    for (const c of chamberNames) tallies[c] = { D: 0, R: 0, unclear: 0, alt: { D: 0, R: 0, unclear: 0 }, hist: new Map() };
    const totals = {};
    for (const c of chamberNames) totals[c] = new Int32Array(partyList.length);
    const dwin = new Uint8Array(R);
    let accepted = 0;

    for (let s = 0; s < nSims; s++) {
      const n = nat[s] * sdNat;
      let ok = true;
      for (let i = 0; i < R; i++) {
        let m;
        if (fixedVal[i] !== 0) {
          m = fixedVal[i];
        } else {
          m = mu[i] + lam[i] * (shift + n) + reg[s * G + gIdx[i]] * sh.sd_region
            + st[s * S + sIdx[i]] * sh.sd_state + cham[s * C + cIdx[i]] * sdChamber[cIdx[i]]
            + idio[s * R + i] * sd[i];
        }
        dwin[i] = m > 0 ? 1 : 0;
      }
      for (const [i, side] of forcedList) {
        if ((side === 1) !== (dwin[i] === 1)) { ok = false; break; }
      }
      if (!ok) continue;
      accepted++;
      for (const c of chamberNames) totals[c].fill(0);
      for (let i = 0; i < R; i++) {
        wins[i] += dwin[i];
        totals[races[i].chamber][dwin[i] ? dParty[i] : rParty[i]]++;
      }
      for (const c of chamberNames) {
        const ch = sim.chambers[c];
        const t = totals[c];
        for (const [p, k] of Object.entries(ch.seats_not_up || {})) t[pcode[p]] += k;
        const [dSeats, who] = control(t, ch, ch.caucus);
        const tal = tallies[c];
        tal[who]++;
        tal.hist.set(dSeats, (tal.hist.get(dSeats) || 0) + 1);
        if (ch.alt_caucus) tal.alt[control(t, ch, ch.alt_caucus)[1]]++;
      }
    }

    const out = { accepted, nSims, chambers: {}, races: {} };
    for (let i = 0; i < R; i++) out.races[races[i].id] = accepted ? wins[i] / accepted : null;
    for (const c of chamberNames) {
      const tal = tallies[c];
      const xs = [...tal.hist.keys()].sort((a, b) => a - b);
      const hist = xs.map((x) => [x, tal.hist.get(x) / Math.max(accepted, 1)]);
      let acc = 0;
      const q = (p) => {
        acc = 0;
        for (const [x, w] of hist) { acc += w; if (acc >= p) return x; }
        return xs[xs.length - 1];
      };
      const mean = hist.reduce((a, [x, w]) => a + x * w, 0);
      out.chambers[c] = {
        p: { D: tal.D / Math.max(accepted, 1), R: tal.R / Math.max(accepted, 1),
             unclear: tal.unclear / Math.max(accepted, 1) },
        pAlt: sim.chambers[c].alt_caucus
          ? { D: tal.alt.D / Math.max(accepted, 1), R: tal.alt.R / Math.max(accepted, 1),
              unclear: tal.alt.unclear / Math.max(accepted, 1) }
          : null,
        seats: { mean, p10: q(0.1), p50: q(0.5), p90: q(0.9) },
        hist,
      };
    }
    return out;
  }

  return { run, nSims, races: races.map((r) => r.id) };
}

// One-shot convenience: simulate({ params, n, seed, version, shift, natScale, forced }).
// Engines are cached per (params, n, seed), so repeated calls with new
// shift/forced values reuse the same draws and stay fast.
const _engines = new WeakMap();
export function simulate({ params, n = 5000, seed = 20261103, version = "deluxe",
                           shift = 0, natScale = 1, forced = {} } = {}) {
  let byKey = _engines.get(params);
  if (!byKey) _engines.set(params, (byKey = new Map()));
  const key = `${n}:${seed}`;
  let engine = byKey.get(key);
  if (!engine) byKey.set(key, (engine = createEngine(params, { nSims: n, seed })));
  return engine.run({ version, shift, natScale, forced });
}
