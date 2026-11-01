// @ts-check
import sitemap from "@astrojs/sitemap";
import { defineConfig } from "astro/config";

// Static site over the committed export in ../data/site/*.json (written by
// `midterms export`). The server rebuilds it whenever main moves; see
// docs/deploy.md. PAGES_SITE overrides the canonical origin for a preview.
export default defineConfig({
  site: process.env.PAGES_SITE || "https://midterms.karazajac.io",
  trailingSlash: "ignore",
  integrations: [sitemap({ filter: (page) => !page.endsWith("/404/") })],
  build: { format: "directory" },
  // Scope component styles with a class, not a data-astro-cid attribute:
  // same specificity, a third of the bytes on the table-heavy pages.
  scopedStyleStrategy: "class",
  vite: {
    // The simulator is imported from ../sim/ and the data from ../data/.
    server: { fs: { allow: [".."] } },
  },
});
