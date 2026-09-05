# Frontend setup — plain-language notes

This explains what got installed in `frontend/` and why, written for someone with
zero frontend background who needs to explain it out loud to a judge. Nothing in
here is a real feature yet — this is just the empty shell the real screens will be
built inside, in the next phase.

---

## 1. The pieces, and why each one is here

### Vite — the thing that runs the app while we build it, and packages it at the end

Every frontend project needs a tool that takes our source code (React + TypeScript
files) and turns it into something a browser can run, and that also serves it on
`localhost` while we're developing so we can see changes instantly.

The older standard tool for this was called Create React App. We used **Vite**
instead because it is dramatically faster at both jobs — the dev server starts in
under a second and reflects a saved change almost instantly, instead of the several
seconds Create React App takes on anything but a tiny project. For a 24-hour
hackathon, the seconds spent waiting on every save add up fast. There is no
functional difference to a user — this only affects how fast we can build.

### Tailwind — writing styles as short class names instead of separate CSS files

Normally, styling a webpage means writing CSS in separate files: `.card { padding:
20px; border: 1px solid gray; }` and so on, then making sure the right class name
is attached to the right HTML element. That works, but on a project with ~20
screens, it produces either a sprawling CSS file that's hard to keep consistent, or
each screen quietly inventing its own slightly-different shade of gray.

**Tailwind** instead gives us a fixed set of small utility classes we apply
directly in the markup — `p-5` for that padding, `border` for a border — pulling
from one shared design vocabulary (see the color list below). Two benefits that
matter for judging: everything visually matches by construction (you cannot
accidentally invent a new blue), and there's no separate stylesheet to keep in
sync with the components as they change.

### shadcn/ui — buttons, dialogs, tables etc. we own outright, not a black box

Most teams reach for a component library like Material UI: install it, import
`<Button>`, done. The catch is that the actual code for that button lives inside
`node_modules`, invisible and hard to change — if the hackathon rubric or a judge's
question needs a component to look or behave slightly differently than the library
author intended, you're often stuck.

**shadcn/ui** works differently: instead of installing a library, its command-line
tool *copies* the actual component source code (a `Button`, a `Table`, a `Dialog`,
etc.) straight into our own repository, under `src/components/ui/`. From that
point on it's just our code — we can open `button.tsx` and change anything, with no
"black-box dependency" in the way, and no risk of an upstream update silently
changing how something looks two days before the demo. We pulled in six of these:
Button, Input, Table, Dialog, Tabs, and Toast (the little pop-up notification that
appears after an action succeeds or fails).

### `useApi.ts` — our own tiny alternative to a "query library"

Data-heavy apps often reach for a library called TanStack Query (also known as
React Query) to manage "loading a list from the server, and refreshing it after
you change something." We deliberately did **not** use it.

The reason: the actual problem it solves here — showing a loading state, catching
an error, and reloading a list after you save something — is one small,
easy-to-read function, `useApi.ts` (about 40 lines). Pulling in a library, with its
own concepts (cache keys, stale time, invalidation) to solve a problem this small
would be exactly the kind of "trendy tech that doesn't add real value" a rubric is
likely to penalize. So instead, every screen that shows a list will call
`useApi('/some-endpoint')`, get back `{ data, loading, error, refetch }`, and after
any action that changes data, just call `refetch()` to reload the list. Simple,
transparent, and it's all code we wrote and can point to.

### `api.ts` — one single place that knows how to talk to the backend

A "fetch wrapper" is just a small helper function that stands in front of the
browser's built-in way of making network requests (`fetch`) so that every part of
the app talks to the backend the same way, instead of each screen reinventing it
slightly differently.

Concretely, `api.ts` is the one place that:
- Knows the backend's address (read from an environment variable, so it's easy to
  point at a different server without changing code).
- Will attach the login token to every request once login exists (that piece is a
  placeholder for now — there's no real login yet).
- Understands the backend's one standard error format (`{ error: { code, message,
  ... } }`) and turns it into a JavaScript error object every screen can catch the
  same way.

Centralizing this means: if the backend's address changes, or how errors are
shaped changes, there is exactly one file to update — not twenty.

---

## 2. Walkthrough: what happens when this page loads

If a judge asks "what happens when this page loads," here is the honest,
step-by-step answer for the current skeleton:

1. The browser requests `/`, gets back a nearly-empty HTML file, and loads its one
   script tag, `main.tsx`.
2. `main.tsx` starts React and hands control to `App.tsx`.
3. `App.tsx` sets up the app's URL routing (React Router) and, right now, defines
   exactly one page: the `/` route.
4. That one route renders a plain placeholder page: a heading that says "Urban
   Furniture Accounting — Setup OK," a line of explanatory text, and one shadcn
   Button — placed there specifically to prove the whole chain (React + Tailwind +
   shadcn) compiles and renders correctly together.
5. **Nothing on this page calls `useApi` or `api.ts` yet**, because there is no
   real data to load yet — no contacts, no invoices, nothing. Those two pieces are
   built and tested in isolation (they compile, they're typed correctly), ready
   for the next phase, where the first real page (say, the Contacts list) will
   call `useApi('/partners')`, which calls `api.get('/partners')` inside `api.ts`,
   which does the actual network request to the backend.

So today: loading the page proves the pipeline works end-to-end visually. The data
layer is wired and tested but has nothing to fetch yet — that's deliberate, per the
brief for this phase.

---

## 3. If you get asked X, say Y

**"Why does the page look plain — where's the actual app?"**
→ "This step was scoped to just the foundation — the build tool, the design
system, and the data-fetching plumbing — with zero real screens yet, so we could
get it reviewed and merged before building on top of it. The real screens
(Contacts, Invoices, Reports, etc.) are the next phase, built directly on this
foundation."

**"Why these specific colors?"**
→ "They're not arbitrary — they were pulled directly from the mockup we were
given, so the app matches the design brief exactly rather than us guessing at a
palette. They're defined in exactly one place (`tailwind.config.js`), so every
future screen automatically matches instead of each one picking its own shade."

**"Is it responsive / does it work on mobile?"**
→ "The design system and breakpoints (mobile under 768px, tablet, desktop) are
planned and specified up front, but this phase doesn't have any real layouts to
test responsiveness against yet — that gets verified screen-by-screen as they're
built, at 375px, 768px, and 1440px widths, per our own build checklist."

**"What is shadcn, in one sentence?"**
→ "It's a way of getting professional, accessible UI components — buttons,
dialogs, tables — as source code we own directly in our repo, instead of as an
external library we can't easily customize."

**"Why isn't this using [some trendy library, e.g. Redux, React Query, Next.js]?"**
→ "We deliberately kept the dependency list small and justified every entry — a
handful of the most common trendy additions were considered and explicitly left
out because the problem they solve here is small enough to not need them (see
`useApi.ts` above for the concrete example with TanStack Query). Fewer
dependencies means less to explain, less that can break, and less that looks like
padding to a judge."

---

## 4. Known deviations from SPEC.md worth flagging to the team

- **Node runtime version:** SPEC.md §3 pins the Node runtime to "20.x LTS". The
  automated setup environment could not complete an install of Node 20.20.2 (the
  installer failed with MSI error 1603, most likely a UAC/elevation issue specific
  to this machine's automated session) but a working Node 24.19.0 install
  succeeded and was used to scaffold and verify everything in this phase
  (`npm install`, `npm run dev`, `npx tsc --noEmit`, `npm run lint` all pass
  cleanly on it). All *package* versions inside `frontend/package.json` are still
  pinned exactly as SPEC.md §3 specifies. Whoever next touches this machine should
  either install Node 20.x LTS by hand (with elevation) to match the spec exactly,
  or the team should explicitly agree Node 24 is acceptable for local dev.
- **`tailwindcss-animate` dependency:** the shadcn/ui CLI adds this small package
  automatically (it powers the open/close animations on Dialog, Tabs, Toast, etc.)
  It isn't in SPEC.md §3's pinned list because shadcn/ui itself wasn't broken down
  to that level of detail there. It's pinned to an exact version (`1.0.7`), just
  like everything else.
- **Design tokens vs. shadcn's internal tokens:** shadcn/ui's components (Button,
  Dialog, etc.) internally expect certain color names to exist (`primary`,
  `border`, `accent`, and so on) so their built-in styles work out of the box.
  Those names are wired, via CSS variables in `src/index.css`, to the *exact same
  hex values* specified in SPEC.md §13.1 — so there is only one true source for
  every color, it's just that shadcn's own components read it through one extra
  layer of indirection (a CSS variable) rather than the flat color name directly.
  SPEC's literal token names (`surface`, `text_primary`, `text_secondary`,
  `primary_hover`, `success`, `warning`, `danger`, `draft`) are also available
  directly, unchanged, for use in our own components (e.g. `bg-surface`,
  `text-text_secondary`).
- **Font:** SPEC.md §13.1 asks for Inter, "self-hosted or system, never a CDN."
  For this skeleton phase the font stack falls back to the system font (no Inter
  font file is bundled yet), which satisfies the "never a CDN" offline rule but
  not the Inter-specifically part. Self-hosting the actual Inter font file is a
  two-minute follow-up for whoever builds the first real page, flagged here so
  it isn't forgotten.
