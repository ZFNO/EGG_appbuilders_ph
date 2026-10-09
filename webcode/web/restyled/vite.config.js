import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.dirname(fileURLToPath(import.meta.url));

// Friendly routes -> the matching .html, mirroring serve.mjs, so
// /guide, /scope and /routes work in the live dev server too.
const FRIENDLY = {
  "/": "index.html",
  "/index.html": "index.html",
  "/guide": "guide.html",
  "/guide.html": "guide.html",
  "/scope": "scope.html",
  "/scope.html": "scope.html",
  "/routes": "routes.html",
  "/routes.html": "routes.html",
};

function friendlyRoutes() {
  return {
    name: "friendly-routes",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const clean = (req.url || "/").split("?")[0];
        if (FRIENDLY[clean]) req.url = "/" + FRIENDLY[clean] + (req.url.includes("?") ? "?" + req.url.split("?")[1] : "");
        next();
      });
    },
  };
}

// Multi-page app: these are the entry points; Vite serves any *.html in root
// during `dev`. `appType: "mpa"` disables the SPA history fallback so unknown
// paths 404 like serve.mjs, rather than silently loading index.html.
export default defineConfig({
  root,
  appType: "mpa",
  plugins: [friendlyRoutes()],
  server: {
    port: 8080,
    open: true,
    strictPort: false,
  },
  build: {
    outDir: "dist",
    rollupOptions: {
      input: {
        index: path.resolve(root, "index.html"),
        guide: path.resolve(root, "guide.html"),
        scope: path.resolve(root, "scope.html"),
        routes: path.resolve(root, "routes.html"),
      },
    },
  },
});
