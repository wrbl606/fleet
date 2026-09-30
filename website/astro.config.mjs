import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";
import icon from "astro-icon";
import sitemap from "@astrojs/sitemap";

// Canonical origin used for absolute URLs (canonical, Open Graph, sitemap).
// Override at build time with SITE_URL=https://your.domain
const site = process.env.SITE_URL || "https://fleet.wrbl.xyz";

export default defineConfig({
  site,
  integrations: [icon(), sitemap()],
  // Prefetch internal pages on hover so navigation (e.g. into /docs) is instant.
  prefetch: {
    prefetchAll: false,
    defaultStrategy: "hover",
  },
  vite: {
    plugins: [tailwindcss()],
  },
});
