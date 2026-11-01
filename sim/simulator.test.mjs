// Parity test: the browser simulator must reproduce the Python forecast.
//   node sim/simulator.test.mjs        (run by `make web-test` and CI)
import { readFileSync } from "node:fs";
import { createEngine, simulate } from "./simulator.mjs";

const sim = JSON.parse(readFileSync(new URL("../data/site/sim.json", import.meta.url)));
const races = JSON.parse(readFileSync(new URL("../data/site/races.json", import.meta.url))).races;

let failures = 0;
function check(ok, msg) {
  if (!ok) { failures++; console.error("  ✗ " + msg); }
}

const t0 = Date.now();
const engine = createEngine(sim, { nSims: 20000, seed: 7 });
const tInit = Date.now() - t0;

for (const version of ["lite", "classic", "deluxe"]) {
  const t1 = Date.now();
  const out = engine.run({ version });
  const tRun = Date.now() - t1;
  for (const c of ["house", "senate", "governor"]) {
    const js = out.chambers[c].p.D, py = sim.reference[version][c].D;
    check(Math.abs(js - py) < 0.02, `${version}/${c}: JS P(D) ${js.toFixed(4)} vs Python ${py.toFixed(4)}`);
  }
  if (version === "deluxe") {
    let worst = 0, worstId = "";
    for (const r of races) {
      const d = Math.abs(out.races[r.id] - r.forecast.deluxe.p_d_side);
      if (d > worst) { worst = d; worstId = r.id; }
    }
    check(worst < 0.03, `deluxe race-level max |JS - Python| = ${worst.toFixed(4)} (${worstId})`);
    console.log(`deluxe: house ${out.chambers.house.p.D.toFixed(3)} senate ${out.chambers.senate.p.D.toFixed(3)} ` +
      `governor ${out.chambers.governor.p.D.toFixed(3)}; worst race gap ${worst.toFixed(4)} (${worstId}); run ${tRun} ms`);
  }
}

// a shift toward Republicans must lower Democratic odds monotonically
const p0 = engine.run({ shift: 0 }).chambers.senate.p.D;
const pm = engine.run({ shift: -3 }).chambers.senate.p.D;
check(pm < p0, `shift -3 should lower Senate P(D): ${pm.toFixed(3)} vs ${p0.toFixed(3)}`);

// conditioning on a Democratic Texas win must raise Democratic Senate odds
const cond = engine.run({ forced: { "senate:TX": "D" } });
check(cond.races["senate:TX"] === 1, "forced race must be won in every accepted draw");
check(cond.chambers.senate.p.D > p0, "winning Texas should raise P(D Senate)");
console.log(`if Democrats win Texas: Senate P(D) ${cond.chambers.senate.p.D.toFixed(3)} ` +
  `(from ${p0.toFixed(3)}; ${cond.accepted} of ${cond.nSims} draws); init ${tInit} ms`);

// the one-shot API agrees with the engine it wraps
const one = simulate({ params: sim, n: 2000, seed: 3, forced: { "senate:TX": "D" } });
check(one.races["senate:TX"] === 1 && one.accepted > 0, "simulate() one-shot with forced outcome");

if (failures) {
  console.error(`✗ web simulator parity: ${failures} failure(s)`);
  process.exit(1);
}
console.log("✓ web simulator parity");
