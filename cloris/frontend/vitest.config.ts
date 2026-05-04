import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

// Cloris frontend test config.
//
// Extends vite.config.ts so resolution stays in sync with the production
// build. happy-dom emulates the DOM (lighter than jsdom; sufficient for the
// component-level assertions Phases 0-4 need). The setup file pulls
// @testing-library/jest-dom matchers into the global expect namespace.
//
// resolve.conditions: ["browser"] is REQUIRED for Svelte 5: without it Vitest
// pulls Svelte's server-side index, which makes `mount(...)` (used by
// @testing-library/svelte under the hood) throw lifecycle_function_unavailable.
export default mergeConfig(
  viteConfig,
  defineConfig({
    resolve: {
      conditions: ["browser"]
    },
    test: {
      environment: "happy-dom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.{test,spec}.{ts,svelte}"],
      coverage: {
        provider: "v8",
        reporter: ["text", "html"],
        include: ["src/**/*.{ts,svelte}"],
        exclude: [
          "src/**/*.{test,spec}.{ts,svelte}",
          "src/test/**",
          "src/main.ts",
          "src/vite-env.d.ts"
        ]
      }
    }
  })
);
