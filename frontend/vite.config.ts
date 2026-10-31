import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

const backend = process.env.VITE_BACKEND ?? "http://localhost:8000";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "CivicPulse",
        short_name: "CivicPulse",
        description: "Report civic issues in seconds. See what happens next.",
        theme_color: "#1f5fbf",
        background_color: "#f7f8fa",
        display: "standalone",
        start_url: "/",
        icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" }],
      },
      workbox: {
        navigateFallbackDenylist: [/^\/api/, /^\/ack/, /^\/media/, /^\/admin/],
        runtimeCaching: [
          { urlPattern: ({ url }) => url.pathname.startsWith("/api/meta"), handler: "NetworkFirst" },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      "/api": backend,
      "/media": backend,
      "/ack": backend,
      "/admin": backend,
      "/static": backend,
    },
  },
});
