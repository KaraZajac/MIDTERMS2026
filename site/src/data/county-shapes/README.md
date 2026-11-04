# County shapes for the race pages' county maps

One file per state with a 2026 Senate or governor race (Alaska excepted: civicAPI
reports its results by state house district, not county). Each holds the state's
outline and every county as an SVG path in a viewBox fitted to the state, keyed by
the 5-digit FIPS code that civicAPI's county results carry:

    { st, w, h, source, outline, counties: [[fips, name, d], ...] }

`CountyMap.astro` inlines the race's state; `scripts/live-counties.js` colours it
from `/counties/<chamber>/<slug>.json` (see `docs/site-data.md`).

Source: [us-atlas](https://github.com/topojson/us-atlas) 3.0.1 `counties-10m.json`
(ISC licence), made from the U.S. Census Bureau's cartographic boundary files at
1:10,000,000. Projection: a conformal conic centred on each state.

Regenerate with `scripts/county-shapes.mjs` (instructions at its top). Connecticut
is drawn with its eight former counties, as in the Census files us-atlas uses; if
civicAPI reports its 2022 planning regions instead, no county matches and the page
simply shows no map.
