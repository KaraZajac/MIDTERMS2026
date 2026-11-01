# MIDTERMS2026 — pipeline, model and verification gate. See README.md and docs/.

.PHONY: help pull build verify test forecast snapshot backtest score export site site-dev install-hooks

help:                ## list targets
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | sort

pull:                ## download every source into sources/ (polls, ratings, FEC, history)
	@python3 -m midterms pull

build:               ## sources/ -> data/ (races, polls, ratings, finance, history)
	@python3 -m midterms build

verify:              ## validation gate: data + forecast checks, then unit tests
	@python3 -m midterms verify
	@python3 -m unittest discover -s tests -q

test:                ## unit tests only
	@python3 -m unittest discover -s tests -q

forecast:            ## run the model -> data/forecast/latest.json
	@python3 -m midterms forecast

snapshot:            ## run the model and freeze a dated, committed snapshot
	@python3 -m midterms forecast --snapshot

backtest:            ## walk the House fundamentals model over past midterms
	@python3 -m midterms backtest

score:               ## after results land: Brier/log score vs every challenger
	@python3 -m midterms score

export:              ## write data/site/*.json for the Astro site
	@python3 -m midterms export

site: export         ## build the static site (site/dist)
	@cd site && npm run build

site-dev: export     ## run the site dev server
	@cd site && npm run dev

install-hooks:       ## enable the git pre-commit gate for this clone
	@chmod +x .githooks/pre-commit
	@git config core.hooksPath .githooks
	@echo "✓ pre-commit gate installed (core.hooksPath=.githooks). Bypass once with: git commit --no-verify"
