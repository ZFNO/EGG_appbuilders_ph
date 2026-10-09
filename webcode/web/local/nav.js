// Shared top navigation bar for the local (no-backend) build.
//
// Injected into <header> on every page so the nav lives in one place. Each page
// carries a placeholder <nav class="navbar" id="navbar" data-page="..."></nav>;
// this module fills it and highlights the current page. No backend, no network.

const PAGES = [
  { id: "dashboard", href: "index.html", label: "Dashboard" },
  { id: "guide",     href: "guide.html", label: "Element guide" },
  { id: "scope",     href: "scope.html", label: "Scope" },
  { id: "routes",    href: "routes.html", label: "Routes" },
];

export function renderNav(target) {
  target = target || (typeof document !== "undefined" && document.getElementById("navbar"));
  if (!target) return;
  const here = (typeof location !== "undefined" && location.pathname.split("/").pop()) || "index.html";
  const current = target.dataset.page || null;

  target.textContent = "";
  for (const p of PAGES) {
    const a = document.createElement("a");
    a.href = p.href;
    a.textContent = p.label;
    const active = current ? p.id === current : p.href === here;
    if (active) a.className = "active";
    target.appendChild(a);
  }
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => renderNav());
  } else {
    renderNav();
  }
}

export default renderNav;
