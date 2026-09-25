import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),

    /**
     * Installable web app. The shell is precached. The export under /data/
     * (meta, the index and the place files) is network-first: a fresh copy
     * whenever the network answers, the cached one only when it does not, so
     * an expired or replaced export is never served over a live one. Google's
     * tiles are never cached, and there are no web fonts to cache.
     */
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icons/*.png", "og-card.png"],
      manifest: {
        name: "San Diego Food Inspection Record",
        short_name: "Food Inspection Record",
        description:
          "The County's inspection record for City of San Diego restaurants and markets, place by place. Independent student project, not affiliated with or endorsed by the County of San Diego.",
        start_url: "/",
        scope: "/",
        display: "standalone",
        orientation: "portrait",
        theme_color: "#FBF9F5",
        background_color: "#FBF9F5",
        categories: ["food", "health", "utilities"],
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "/icons/icon-512-maskable.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,png,svg}"],
        globIgnores: ["data/**"],
        navigateFallbackDenylist: [/^\/data\//],
        maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith("/data/"),
            handler: "NetworkFirst",
            options: {
              cacheName: "food-data",
              networkTimeoutSeconds: 6,
              expiration: { maxEntries: 300, maxAgeSeconds: 7 * 24 * 60 * 60 },
              cacheableResponse: { statuses: [200] },
            },
          },
        ],
      },
    }),
  ],

  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          deck: ["@deck.gl/core", "@deck.gl/layers", "@deck.gl/google-maps"],
          charts: ["recharts"],
          react: ["react", "react-dom"],
        },
      },
    },
  },
});
