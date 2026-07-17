import path from "path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  define: {
    __BUNDLED_DEV__: JSON.stringify(process.env.NODE_ENV !== "production"),
  },
  build: {
    rollupOptions: {
      output: {
        // Split large, rarely-changing dependencies into their own cacheable
        // vendor chunks. This keeps the per-route chunks (Landing, Workbench,
        // MapSearch) smaller — vendor code is downloaded once and reused across
        // routes, and an app-code change no longer busts the vendor cache.
        // Behaviour is unchanged; this is a build-output grouping only.
        manualChunks(id) {
          if (!id.includes("/node_modules/")) return;
          if (id.includes("/node_modules/three/")) return "three-vendor";
          if (/\/node_modules\/(react-dom|scheduler)\//.test(id)) return "react-vendor";
          if (/\/node_modules\/(react|react-router|react-router-dom)\//.test(id)) return "react-vendor";
          if (id.includes("/node_modules/@xyflow/")) return "flow-vendor";
          if (/\/node_modules\/(motion|framer-motion|motion-dom)\//.test(id)) return "motion-vendor";
          if (id.includes("/node_modules/@radix-ui/")) return "ui-vendor";
          // The world-map data (dotted-map / react-svg-worldmap) is used by BOTH
          // Landing and MapSearch. Grouping it into one shared vendor chunk
          // de-duplicates it (downloaded + cached once) instead of shipping a
          // copy inside each route chunk. It is inherently large (~560 kB), so
          // the chunk-size warning limit below is set to accommodate it.
          if (/\/node_modules\/(react-svg-worldmap|dotted-map)\//.test(id)) return "map-vendor";
          if (
            /\/node_modules\/(react-markdown|remark-gfm|micromark|mdast|hast|unist|unified|vfile|property-information|.*-separated-tokens|decode-named-character-reference|character-entities|trim-lines|zwitch|longest-streak)/.test(
              id,
            )
          )
            return "markdown-vendor";
        },
      },
    },
    // Two vendor libs are inherently large: three.js (~500 kB) and the shared
    // world-map data (~560 kB). Every app/route chunk now sits well under this;
    // the limit is set so the warning would flag a genuine regression, not
    // these two known, deliberately-split vendors.
    chunkSizeWarningLimit: 600,
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api": {
        target: process.env.VITE_BACKEND_URL ?? "http://localhost:8000",
        changeOrigin: true,
        proxyTimeout: 300_000,
        timeout: 300_000,
      },
      "/auth": {
        target: process.env.VITE_BACKEND_URL ?? "http://localhost:8000",
        changeOrigin: true,
        proxyTimeout: 30_000,
        timeout: 30_000,
      },
      "/health": {
        target: process.env.VITE_BACKEND_URL ?? "http://localhost:8000",
        changeOrigin: true,
        proxyTimeout: 10_000,
        timeout: 10_000,
      },
    },
  },
});
