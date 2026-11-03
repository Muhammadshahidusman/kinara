import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api calls go to the FastAPI server (scripts/run_api.bat) during development.
// MapLibre gets its own chunk: it is most of the bundle and changes far less often than the app.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  build: { chunkSizeWarningLimit: 900, rollupOptions: { output: { manualChunks: { maplibre: ["maplibre-gl"] } } } },
});
