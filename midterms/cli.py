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
