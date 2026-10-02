import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [tanstackRouter({ target: "react", autoCodeSplitting: true }), react(), tailwindcss()],
  server: {
    // Playwright writes traces and its HTML report while tests run; watching
    // them makes Vite reload every open page mid-test.
    watch: { ignored: ["**/playwright-report/**", "**/test-results/**"] },
    proxy: {
      "/api": "http://localhost:8000",
      "/dev": "http://localhost:8000",
      "/channels": {
        target: "ws://localhost:8000",
        ws: true,
      },
    },
  },
});
