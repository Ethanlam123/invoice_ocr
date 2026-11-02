import { defineConfig } from "vitest/config";

// e2e/ holds Playwright specs (npm run e2e); vitest runs unit tests only.
// Without this, vitest also collects e2e/*.spec.ts and fails them (Playwright's
// test() cannot register inside vitest).
export default defineConfig({
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
