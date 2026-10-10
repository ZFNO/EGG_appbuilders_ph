// Shared brand + top navigation for the local (no-backend) build.
//
// Injected into <header> on every page so the brand and nav live in one place.
// Each page carries a placeholder <div class="brand" id="brand" data-title="EGG">
// and <nav class="navbar" id="navbar" data-page="...">; this module fills both.
//
// The bar has two rows on desktop: the primary links, and a slim second row
// (a tagline + quick links) that is hidden on small screens. On small screens
// the primary links also collapse behind a hamburger toggle.

const PAGES = [
  { id: "home",      href: "home.html",   label: "Home" },
  { id: "dashboard", href: "index.html",  label: "Dashboard" },
  { id: "guide",     href: "guide.html",  label: "Element guide" },
  { id: "scope",     href: "scope.html",  label: "Scope" },
  { id: "routes",    href: "routes.html", label: "Routes" },
  { id: "options",   href: "configs.html", label: "Options" },
];

// The desktop-only second row: a one-line tagline on the left, quick links on
// the right. Kept out of the main links so the top row stays uncluttered.
const SUB_TAGLINE = "One request in \u2014 the right action out.";
const SUB_LINKS = [
  { href: "home.html#how",   label: "How it works" },
  { href: "getstarted.html", label: "Get started" },
];

// The layman's subtitle that sits under the EGG wordmark.
const BRAND_SUB = "Your calm, tireless inbox secretary";

export function renderNav(target) {
  target = target || (typeof document !== "undefined" && document.getElementById("navbar"));
  if (!target) return;
  const here = (typeof location !== "undefined" && location.pathname.split("/").pop()) || "index.html";
  const current = target.dataset.page || null;

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "navtoggle";
  toggle.setAttribute("aria-label", "Toggle menu");
  toggle.setAttribute("aria-expanded", "false");
  toggle.innerHTML = "<span></span><span></span><span></span>";
  toggle.addEventListener("click", () => {
    const open = target.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
  });

  const links = document.createElement("div");
  links.className = "navlinks";
  for (const p of PAGES) {
    const a = document.createElement("a");
    a.href = p.href;
    a.textContent = p.label;
    const active = current ? p.id === current : p.href === here;
    if (active) a.className = "active";
    links.appendChild(a);
  }

  target.textContent = "";
  target.appendChild(toggle);
  target.appendChild(links);

  renderSubNav(target.parentElement, here);
}

// The desktop-only second row of the bar. Appended to the header so it rides
// along on every page that uses this module; guarded so re-renders don't stack.
export function renderSubNav(header, here) {
  if (!header || header.querySelector(".navsub")) return;
  const bar = document.createElement("div");
  bar.className = "navsub";

  const tag = document.createElement("span");
  tag.className = "navsub-tag";
  tag.textContent = SUB_TAGLINE;

  const links = document.createElement("span");
  links.className = "navsub-links";
  for (const l of SUB_LINKS) {
    const a = document.createElement("a");
    a.href = l.href;
    a.textContent = l.label;
    if (here && l.href.split("#")[0] === here) a.classList.add("active");
    links.appendChild(a);
  }

  bar.appendChild(tag);
  bar.appendChild(links);
  header.appendChild(bar);
}

// The EGG brand: an egg-shaped SVG mark + the wordmark, left of the title slot.
const EGG_SVG = `
<svg class="egg" viewBox="0 0 48 60" aria-hidden="true" focusable="false">
  <path class="shell" d="M24 3 C35 3 44 21 44 37 C44 51 35 58 24 58 C13 58 4 51 4 37 C4 21 13 3 24 3 Z"/>
  <path class="shine" d="M17 20 C14 26 13.5 32 15 37"/>
</svg>`;

export function renderBrand() {
  if (typeof document === "undefined") return;
  const el = document.getElementById("brand");
  if (!el || el.dataset.done) return;
  const title = el.dataset.title || "EGG";
  const sub = el.dataset.sub || BRAND_SUB;
  el.innerHTML = `<a class="brandlink" href="home.html" aria-label="${title} home">${EGG_SVG}` +
    `<span class="eggtext"><span class="eggword">${title}</span>` +
    `<span class="eggsub">${sub}</span></span></a>`;
  el.dataset.done = "1";
}

if (typeof document !== "undefined") {
  const boot = () => { renderBrand(); renderNav(); };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
}

export default renderNav;
