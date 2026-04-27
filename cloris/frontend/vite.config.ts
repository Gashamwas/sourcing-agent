import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Cloris frontend build config.
//
// - `base: "/"` because Python serves the SPA from the same origin as the API.
// - `build.outDir: "dist"` because Python serves the built artifact directly
//   (the dist/ directory is committed; CI does not run Node).
// - The dev-server proxy is local-dev-only and minimal: it lets `pnpm dev`
//   talk to a running `cloris start` process on 127.0.0.1:8765 without CORS,
//   but it never appears in production behavior.
export default defineConfig({
  plugins: [svelte()],
  base: "/",
  build: {
    outDir: "dist",
    assetsDir: "assets",
    emptyOutDir: true
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8765", changeOrigin: false },
      "/healthz": { target: "http://127.0.0.1:8765" }
    }
  }
});
