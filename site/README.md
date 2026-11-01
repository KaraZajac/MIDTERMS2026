# site/ — midterms.karazajac.io

Astro 7, static output. Reads `../data/site/*.json` (written by
`midterms export`, contract in `../docs/site-data.md`) and renders
`../docs/method.md`; imports the browser simulator from `../sim/`.

```sh
npm ci
npm run dev      # http://localhost:4321
npm run build    # -> dist/
```

Layout:

- `src/lib/` — `data.js` (loads the export, cwd-relative), `model.js`
  (race helpers), `format.js`, `density.js` (margin distribution from the
  nine quantiles), `scale.js`.
- `src/components/` — charts (`SeatHist`, `TrendChart`, `MarginDensity`,
  `TileMap`, `SeatStrip`, `Calibration`, `OddsBar`) and page parts.
- `src/pages/` — `/`, `/house/`, `/senate/`, `/governor/`, one page per race
  at `/<chamber>/<race>/`, `/simulator/`, `/generic-ballot/`, `/methods/`,
  `/scorecard/`, `/data/`.

Every number is rendered for all three model versions; the version switch
only toggles which one shows (`.v .v-lite|classic|deluxe` in
`global.css`), so pages work without JavaScript and never fetch data.

Deployment: `../docs/deploy.md`.
