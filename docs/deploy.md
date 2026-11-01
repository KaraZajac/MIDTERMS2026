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

`midterms-sync.timer` runs every five minutes. It asks GitHub for `main`'s
commit (`git ls-remote`) and compares it with the `commit` in the live
`/build.json`; if they differ it runs `site-deploy`. So every refresh
commit (six-hourly, then hourly through the night before the polls open)
and, on election night, every scoring commit is live within about six
minutes. A failed build leaves the last good site up,
because `site-deploy` only publishes after a clean build.

Logs: `journalctl -u midterms-sync.service`.

## Checks after a deploy

- `/` shows the three chambers and the version switch changes the numbers.
- A race page, e.g. `/senate/me/`, draws its margin distribution and polls.
- `/simulator/` loads (status line reports 10,000 simulations) and calling
  a race moves the others.
- `/build.json` shows the commit you just pushed.
