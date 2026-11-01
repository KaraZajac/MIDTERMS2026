"""midterms — the command line for the whole loop.

    midterms pull [--only NAME] [--force]   fetch sources into sources/
    midterms build                          sources/ -> data/ tables
    midterms verify                         validation gate (data + forecast)
    midterms forecast [--sims N] [--snapshot]
                                            run the model -> data/forecast/
    midterms backtest                       House fundamentals over past midterms
    midterms show RACE                      one race, with every input shown
    midterms score                          after results: the arena scorecard
    midterms export                         data/site/*.json for the Astro site
    midterms cadence                        what this refresh run does, and when
                                            the next one starts (refresh.yml)
    midterms live [--out PATH]              election night: results, calls, and the
                                            forecast conditioned on them -> live.json
"""

from __future__ import annotations

import argparse
import sys

import midterms._env  # noqa: F401  (loads .env)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="midterms", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pull", help="download sources")
    p.add_argument("--only", action="append", help="limit to a source group (repeatable)")
    p.add_argument("--force", action="store_true", help="ignore cached copies")

    sub.add_parser("build", help="sources -> data/")
    sub.add_parser("verify", help="validation gate")

    p = sub.add_parser("forecast", help="run the model")
    p.add_argument("--sims", type=int, default=50_000)
    p.add_argument("--seed", type=int, default=20261103)
    p.add_argument("--asof", help="ISO date the forecast is made as of (default today)")
    p.add_argument("--snapshot", action="store_true",
                   help="also freeze data/forecast/snapshots/<timestamp>.json")

    sub.add_parser("backtest", help="House fundamentals walk-forward")

    p = sub.add_parser("show", help="one race in detail")
    p.add_argument("race", help="e.g. senate:ME, house:PA-07, governor:AZ")

    sub.add_parser("score", help="score the frozen forecast against results")
    sub.add_parser("export", help="site JSON")

    p = sub.add_parser("live", help="election night: civicAPI results -> live.json")
    p.add_argument("--out", help="write here instead of data/site/live.json (the web server)")
    p.add_argument("--previous", help="the last live.json (default: --out without .tmp, "
                                      "then data/site/live.json)")
    p.add_argument("--draws", type=int, help="weighted simulations (default 40000)")
    p.add_argument("--fixture", type=float, metavar="HOUR",
                   help="no fetch: a simulated night at HOUR (Eastern, e.g. 21.5) for testing")
    p.add_argument("--seed", type=int, default=3, help="the simulated night (--fixture)")
    p.add_argument("--check", type=int, metavar="NIGHTS",
                   help="calibration self-check over NIGHTS simulated election nights")

    p = sub.add_parser("cadence", help="the refresh chain: this run's phase and the next run")
    p.add_argument("--event", default="workflow_dispatch", help="github.event_name")
    p.add_argument("--run-id", type=int, help="github.run_id")
    p.add_argument("--runs", help="`gh run list --json databaseId,event,status,createdAt` output")

    args = ap.parse_args(argv)
    if args.cmd == "pull":
        from midterms.pipeline import pull
        pull.main(only=args.only, force=args.force)
    elif args.cmd == "build":
        from midterms.pipeline import build
        build.main()
    elif args.cmd == "verify":
        from midterms.pipeline import validate
        sys.exit(validate.main())
    elif args.cmd == "forecast":
        from midterms.model import forecast
        forecast.main(sims=args.sims, seed=args.seed, asof=args.asof, snapshot=args.snapshot)
    elif args.cmd == "backtest":
        from midterms.model import backtest, backtest_statewide
        backtest.main()
        backtest_statewide.main()
    elif args.cmd == "show":
        from midterms.model import forecast
        forecast.show(args.race)
    elif args.cmd == "score":
        from midterms.journal import score
        score.main()
    elif args.cmd == "export":
        from midterms.pipeline import site_export
        site_export.main()
    elif args.cmd == "live":
        if args.check:
            import json as _json
            from midterms.model import live as _live
            from midterms.paths import SITE
            sim = _json.loads((SITE / "sim.json").read_text())
            print(_json.dumps(_live.selfcheck(sim, nights=args.check), indent=1))
        else:
            from midterms.pipeline import livefeed
            livefeed.main(out=args.out, previous=args.previous, draws=args.draws, fixture=args.fixture,
                          seed=args.seed)
    elif args.cmd == "cadence":
        from midterms.pipeline import cadence
        cadence.main(event=args.event, run_id=args.run_id, runs_path=args.runs)
