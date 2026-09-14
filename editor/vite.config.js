import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const here = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  base: "/ui/",
  build: {
    outDir: resolve(here, "../ui"),
    emptyOutDir: false,
    sourcemap: false,
    cssCodeSplit: false,
    rollupOptions: {
      input: resolve(here, "index.html"),
      output: {
        inlineDynamicImports: true,
        entryFileNames: "app.js",
        assetFileNames: (asset) =>
          asset.name && asset.name.endsWith(".css") ? "app.css" : "assets/[name][extname]",
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/v0": "http://127.0.0.1:18380",
      "/health": "http://127.0.0.1:18380",
      "/files": "http://127.0.0.1:18380",
    },
  },
});
