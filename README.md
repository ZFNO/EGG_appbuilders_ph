# EGG &mdash; the invisible secretary

**DEADLINE release &middot; "one request in, the right action out."**

EGG is a calm, tireless inbox secretary. You hand it **one thing** in plain
language; it works out what that thing is, does the safe part on its own, and
**stops for your approval** before anything that touches money, people, or a
promise. No commands to memorise &mdash; just plain words, and a hard line it
won't cross.

This repository's web app is a **1:1 pure-ES-module JavaScript port** of the
Python `invisible_secretary` service that runs **entirely in the browser** &mdash;
no server, no network, no build step required &mdash; wrapped in a bold,
high-contrast, angular "menu" theme. Runtime source lives in
[`webcode/web/restyled`](webcode/web/restyled); see that folder's own
[README](webcode/web/restyled/README.md) for the module-by-module notes.

## New in the DEADLINE release

- **Home page** (`home.html`) &mdash; a plain-language front door that explains the whole thing.
- **Get started page** (`getstarted.html`) &mdash; a four-step, animated walkthrough of what EGG does with your words.
- **Second-row navigation** &mdash; a brand subtitle (*"Your calm, tireless inbox secretary"*) and quick links, injected by `nav.js`, so every page carries them.
- New friendly routes `/home` and `/getstarted` in both `serve.mjs` and `vite.config.js`.

## Pages

### Home &mdash; `home.html`
<img src="https://i.ibb.co/KxmsRd8Z/egg-home.png" alt="EGG home page" width="900">

The landing page and the plainest explanation of EGG. An animated
**Request &rarr; Understand &rarr; Route &rarr; Approve** strip sets the tone,
followed by **How it works** (four small steps), **The moving parts** (router,
capability nodes, approval gate, on-device model, scope guard, activity log), and
a side-by-side **"What it will &mdash; and won't &mdash; do"** board. It ends on a
strong **Get started** call to action. Two quick links in the top bar make it the
primary entry point for a first-time visitor.

### Get started &mdash; `getstarted.html`
<img src="https://i.ibb.co/PZfJFdML/egg-getstarted.png" alt="EGG get started page" width="900">

A guided four-step walkthrough, reached from the Home page's main button. Each
step pairs a short explanation with a live demonstration panel:

1. **Type one plain-language request** &mdash; a typing animation runs a real request, then reveals the extracted `intent` / `party` / `risk`.
2. **EGG reads what matters** &mdash; highlights the party and deadline it pulls out of the sentence.
3. **It routes to a capability** &mdash; a miniature Request &rarr; Router &rarr; Node flow.
4. **You approve &mdash; then it acts** &mdash; a mock approval card that pulses, then stamps **APPROVED**.

A scroll progress bar tracks your place, and everything honours
`prefers-reduced-motion`.

### Dashboard &mdash; `index.html`
<img src="https://i.ibb.co/GftQZ09M/egg-dashboard.png" alt="EGG dashboard" width="900">

The screen you actually live in. A request box (*"Tell it what needs handling"*)
takes one plain-language ask; below it are the live **Services / nodes** status,
a **Scope** summary of what EGG handles versus refuses, a **Needs your attention**
approval queue, and a **Recent activity** log. Type a request, watch it route, and
anything consequential lands in the approval queue waiting for your yes.

### Guide &mdash; `guide.html`
<img src="https://i.ibb.co/pBfwsh0S/egg-guide.png" alt="EGG guide" width="900">

The same dashboard, described **in place**. Every section is annotated, and each
one is tagged to show whether it uses the **LLM** or is **rule-based** (or a mix).
It's the "what does this bit do, and does it need the model?" reference.

### Scope &mdash; `scope.html`
<img src="https://i.ibb.co/LDPz98cv/egg-scope.png" alt="EGG scope editor" width="900">

The live scope editor. Shows the full **in-scope mapping**, the **out-of-scope
rejected keywords** (the things EGG refuses outright), the **live nodes**, and a
**dry-run tester** that routes a request through the rules without executing
anything &mdash; so you can see the decision before it matters.

### Routes &mdash; `routes.html`
<img src="https://i.ibb.co/WpGQwCWK/egg-routes.png" alt="EGG routes" width="900">

A reference page listing every **static file route** served by `serve.mjs` and
every **API route** satisfied by the in-browser fetch shim (which never touches
the network). Useful for seeing exactly how the "no backend" story is wired.

### Options &mdash; `configs.html`
<img src="https://i.ibb.co/HTLkVcKn/egg-configs.png" alt="EGG options" width="900">

Every configurable part of EGG in one place: your **identity profile**, the
**model / LLM** settings, **routing policy**, **urgency keywords**, **scope
rejected keywords**, the **intent &rarr; node allow-list**, and the **nodes** and
**contracts** (read-only). Edits here are live &mdash; the badges mark which
controls take effect immediately, which reload, and which are read-only.

## Run

### Zero-dependency static server (no build step)

```bash
node webcode/web/restyled/serve.mjs            # -> http://127.0.0.1:8080/
# optional: node webcode/web/restyled/serve.mjs 8081
```

### Dev server (Vite, hot reload)

```bash
cd webcode/web/restyled
bun install          # once
bun run dev          # -> http://localhost:8080/  (HMR on)
bun run build        # -> dist/
```

`vite.config.js` sets the root to that folder, lists the pages as MPA entry
points, and adds a `friendlyRoutes` middleware so `/`, `/home`, `/getstarted`,
`/guide`, `/scope` and `/routes` work in dev just like `serve.mjs`
(`appType: "mpa"` keeps unknown paths a real 404).

### Tests

```bash
node --test webcode/web/restyled/tests/smoke.mjs
```

## The loop

| Stage | What happens |
|-------|--------------|
| **You ask** | One request, plain language, one ask per message. |
| **It understands** | The router extracts intent, the party and any deadline, and scores risk (R1 routine &rarr; R3 consequential). Too vague? It asks you to clarify instead of guessing. |
| **It routes** | Routine work is handed to the right **capability node** &mdash; follow-up, scheduling, routing &mdash; a small specialist that does one job. |
| **You approve** | Sending, paying, deleting or committing pauses at the **approval gate**, bound to the exact payload. Change the payload and the old approval is void &mdash; a fresh yes is required. |

Payments, refunds, deletions, and legal or hiring decisions are **refused up front,
by design** (the scope guard). The only place a language model is used is the
on-device model &mdash; and it can be switched off; the rules keep working.

## Theme

The look is a bold, high-contrast, angular aesthetic: neon green on a black base,
heavy condensed uppercase display headings (Anton / Bebas Neue), wide-tracked
uppercase labels (Oswald), skewed lettering, hard crisp offset drop-shadows, thick
text strokes, near-black panels and sharp diagonal accents. Every colour lives in
a single `:root` block in
[`assets/theme.css`](webcode/web/restyled/assets/theme.css) &mdash; re-skinning the
whole app means editing just that one block.
