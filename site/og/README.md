# og/ — the share card's source

`og-card.html` (with `hemicycle.svg`) is the source of `../public/og.png`,
the 1200×630 image every page names in `og:image`. It is decorative and
carries no forecast numbers on purpose: social sites cache share images
for days, and a stale probability is worse than none.

To regenerate: open `og-card.html` in headless Chromium at 1200×630
(file access on, so the fonts in `../public/fonts/` load), screenshot it,
and save as `../public/og.png`. `hemicycle.svg` is 435 seats shaded
blue → grey → red, generated once; it is not data.
