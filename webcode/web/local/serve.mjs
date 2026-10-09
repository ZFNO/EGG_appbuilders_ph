// Tiny dependency-free static server for the local (no-backend) build.
//   node webcode/web/local/serve.mjs [port]
//
// The app itself has NO backend: the pages talk to an in-browser engine via the
// fetch shim in api.js. This server only serves the static files (and maps the
// friendly routes / , /guide , /scope onto the three pages).

import http from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.argv[2] || process.env.IS_PORT || 8080);

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

// friendly route -> file in ROOT
const ROUTES = {
  "/": "index.html",
  "/index.html": "index.html",
  "/guide": "guide.html",
  "/guide.html": "guide.html",
  "/scope": "scope.html",
  "/scope.html": "scope.html",
};

function resolvePath(urlPath) {
  const clean = decodeURIComponent(urlPath.split("?")[0]);
  if (ROUTES[clean]) return path.join(ROOT, ROUTES[clean]);
  // block traversal, then serve from ROOT
  const safe = path.normalize(clean).replace(/^(\.\.[/\\])+/, "");
  return path.join(ROOT, safe);
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.url.startsWith("/api/")) {
      // Never expected: the fetch shim intercepts /api/* before it leaves the
      // page. If we see one, the shim was not loaded.
      res.writeHead(501, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "no backend; api.js shim should intercept /api/*" }));
      return;
    }

    let filePath = resolvePath(req.url);
    let info;
    try {
      info = await stat(filePath);
      if (info.isDirectory()) filePath = path.join(filePath, "index.html");
    } catch {
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("404 not found");
      return;
    }

    const body = await readFile(filePath);
    const type = TYPES[path.extname(filePath).toLowerCase()] || "application/octet-stream";
    res.writeHead(200, { "Content-Type": type, "Cache-Control": "no-store" });
    res.end(body);
  } catch (err) {
    res.writeHead(500, { "Content-Type": "text/plain" });
    res.end("500 " + (err && err.message ? err.message : err));
  }
});

server.listen(PORT, () => {
  console.log(`Invisible Secretary (local, no backend) -> http://127.0.0.1:${PORT}/`);
  console.log("all integrations SIMULATED");
});
