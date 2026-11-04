# Deploying the site — midterms.karazajac.io

The site in `site/` is a static Astro build over the committed export in
`data/site/*.json` (contract: [site-data.md](site-data.md)) plus
`docs/method.md`, which the Methods page renders. No Python, database or
secret is needed to build it; Node 22+ is.

## Build

```sh
git clone https://github.com/KaraZajac/MIDTERMS2026
cd MIDTERMS2026/site
npm ci
npm run build          # -> site/dist/, about 520 pages, ~10 s
```

`astro.config.mjs` sets the canonical origin to `https://midterms.karazajac.io`;
set `PAGES_SITE` at build time to serve it anywhere else. The data loader
(`site/src/lib/data.js`) finds `data/site/` by walking up from the working
directory, so build from `site/` or the repo root.

`/build.json` records the commit the build came from; `/sim.json` is the one
export file a browser downloads (the simulator's parameters, ~11 KB gzipped).

## How the live site stays current

It is hosted on the same box as karazajac.io, behind Cloudflare, with a Tor
mirror. The server keeps a clone at `/srv/src/midterms.karazajac.io` and
publishes with `site-deploy midterms.karazajac.io site` (pull, `npm ci`,
build, rsync to the web root, refresh the onion mirror).

`midterms-sync.timer` runs every minute. It asks GitHub for `main`'s
commit (`git ls-remote`) and compares it with the `commit` in the live
`/build.json`; if they differ it runs `site-deploy` (about 30 s). So every
refresh commit (every 30 minutes until the polls open) and, on election
night, every results and scoring commit is live within about 90 seconds.
A failed build leaves the last good site up, because `site-deploy` only
publishes after a clean build.

Open pages ask `/build.json` once a minute what the site was built from,
and offer a reload when the forecast (`generated`) or its `phase` has
changed since they were built. Their "Updated … ago" times use the
server's clock, from that response's `Date` header.

Logs: `journalctl -u midterms-sync.service`.

## Election night: `/live.json`

From Nov 3 22:30 UTC through Nov 5, `midterms-live.timer` runs
`midterms-live.service` every minute, then every 5 minutes (on the :00
and :05 marks) from Nov 6 through Nov 10 while late ballots are counted.
That runs `python3 -m midterms live` in the server's checkout: it reads
the frozen forecast of record and civicAPI's results and race calls, and
writes `/live.json`.

- The job runs as the unprivileged `midterms-live` user in a systemd
  sandbox. The system and the checkout are read-only, and its only
  writable directory is `/srv/live/midterms.karazajac.io/`. It needs
  Python 3.11+ with numpy and PyYAML (Fedora's `python3-numpy` and
  `python3-pyyaml`).
- `/usr/local/bin/midterms-live` has it write `live.json.tmp`, checks
  that the file parses, and renames it into place, so a failed run leaves
  the last good file live.
- Caddy serves that directory's `live.json` at `/live.json`, on the site
  and on the onion, with `Cache-Control: no-cache`. It sits outside the
  web root because every deploy runs `rsync --delete` over the root.
  Until the first run writes one, `/live.json` answers `null` (the
  directory's `none.json`) rather than a 404.
- The site builds `/live-build.json` (the committed
  `data/site/live.json`, or `null`) and `/race-index.json` (race names
  for the lists). From the deadline on, the home, chamber and race pages
  fetch `/live.json` and `/live-build.json` every minute while visible,
  and show whichever has the newer `generated` (`site/src/scripts/live.js`).
  Before the deadline they request nothing. A simulated night
  (`"fixture": true`) only ever renders on a local preview: copy one from
  `tests/fixtures/live/` to `site/dist/live.json` and serve `dist/`.
- A page says "Results feed delayed" when the copy it shows is older than
  the job's cadence allows (`stale()` in `site/src/scripts/live-util.js`):
  5 minutes through Nov 5, then 15 minutes (three missed runs) through
  Nov 10. After that the only copy is the repository's, refreshed every
  six hours, so the warning stays off and the "Updated" time beside the
  results says how old they are.
- Run it once now: `systemctl start midterms-live.service`. Stop it:
  `systemctl disable --now midterms-live.timer`. Logs:
  `journalctl -u midterms-live.service`.

## Election night: county maps, `/counties/`

From Nov 4 01:55 UTC through Nov 5, `midterms-counties.timer` runs
`midterms-counties.service` every 5 minutes (at :00:30, :05:30, …), then
every 15 minutes from Nov 6 through Nov 10 (at :00:30, :15:30, :30:30 and
:45:30, 30 s after a live run).
That runs `python3 -m midterms counties --cache-dir
/srv/live/midterms.karazajac.io --out-dir
/srv/live/midterms.karazajac.io/counties`, which writes one file per
Senate and governor race with votes, `counties/<chamber>/<slug>.json`
(the shape is in `docs/site-data.md`).

- Same user and sandbox as `midterms-live`, `TimeoutStartSec=200`. It
  reads civicAPI's race ids from the answers the live job keeps beside
  `live.json`, so it adds no searches.
- Caddy serves only paths matching
  `^/counties/(senate|governor)/[a-z0-9-]+\.json$` from that directory,
  on the site and the onion, `Cache-Control: no-cache`. A race with no
  file yet answers `null`, not a 404.
- Senate and governor race pages carry their state's counties as an
  inline SVG (`site/src/components/CountyMap.astro`, shapes in
  `site/src/data/county-shapes/`), and `site/src/scripts/live-counties.js`
  fetches the race's file every 2 minutes while visible and shades each
  county. `null`, `regions: []` or no county matching a shape keeps the
  map hidden. House races and Alaska have no county map.
- Run it once now: `systemctl start midterms-counties.service`. Stop it:
  `systemctl disable --now midterms-counties.timer`. Logs:
  `journalctl -u midterms-counties.service`.

## Election night: the archive

Since Nov 4 02:32 UTC every good update is also kept on the server, gzipped,
outside every web root and never served: GitHub's 10-minute copy has gaps
whenever civicAPI fails those runs, so these are the night's complete record.

- `/usr/local/bin/midterms-live` writes `/srv/live-archive/midterms/live/
  <UTC %Y%m%dT%H%M%SZ>.json.gz` after each successful rename.
- `/usr/local/bin/midterms-counties` (the county service's ExecStart) runs
  `midterms counties`, then copies each county file that run wrote to
  `/srv/live-archive/midterms/counties/<stamp>/<chamber>/<slug>.json.gz`.
- Both services may write there (`ReadWritePaths`). A failed copy is logged,
  never fatal. Keep everything through Nov 10.

## Checks after a deploy

- `/` shows the three chambers and the version switch changes the numbers.
- A race page, e.g. `/senate/me/`, draws its margin distribution and polls.
- `/simulator/` loads (status line reports 10,000 simulations) and calling
  a race moves the others.
- `/build.json` shows the commit you just pushed.
