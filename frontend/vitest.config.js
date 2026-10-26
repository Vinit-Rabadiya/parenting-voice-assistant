import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// keep frontend tests in the shared test folder while using frontend dependencies.
export default defineConfig({
  root: fileURLToPath(new URL("../", import.meta.url)),
  plugins: [react()],
  resolve: {
    alias: {
      "@testing-library/react": fileURLToPath(new URL("./node_modules/@testing-library/react/dist/index.js", import.meta.url)),
      "react-dom": fileURLToPath(new URL("./node_modules/react-dom", import.meta.url)),
      react: fileURLToPath(new URL("./node_modules/react", import.meta.url)),
      "firebase/auth": fileURLToPath(new URL("./node_modules/firebase/auth/dist/esm/index.esm.js", import.meta.url)),
      qrcode: fileURLToPath(new URL("./node_modules/qrcode/lib/browser.js", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/frontend/**/*.test.jsx"],
    maxWorkers: 1,
    clearMocks: true,
  },
});
