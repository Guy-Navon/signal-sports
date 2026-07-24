# Signal Sports — frontend

A personalized, Hebrew-first sports newsroom built with React 18, Vite 6, and
the Signal Ledger design system.

See [`../docs/FRONTEND_DESIGN_SYSTEM.md`](../docs/FRONTEND_DESIGN_SYSTEM.md)
for the architecture, tokens, responsive/RTL rules, component boundaries,
validation baseline, and rollback notes.

## Run locally

```bash
npm install
npm run dev
```

Vite uses `http://127.0.0.1:5173` with a strict port because same-origin API
proxying and private remote access depend on that address.

Data modes are selected with `VITE_DATA_MODE`:

- `local` (default): repository fixtures plus the in-browser relevance engine;
- `backend`: the real FastAPI API through same-origin `/api/*` and `/health`.

`VITE_API_BASE_URL` is an explicit debugging override only. Cookie-authenticated
product use should stay same-origin.

## Quality commands

```bash
npm run test
npm run lint
npm run typecheck
npm run build
```

## Structure

```text
src/
├── api/              API client and response normalizers
├── components/
│   ├── feed/         edition hierarchy, clusters, attribution, feedback
│   ├── interests/    taxonomy-backed interest selection
│   ├── preferences/  explicit and learned preference presentation
│   ├── shell/        product/ops shells and navigation
│   ├── shared/       ledger panels, headers, loading/empty/error states
│   ├── ops/          scheduler, ingestion, notification, source tooling
│   ├── debug/        classification and reasoning diagnostics
│   └── ui/           Radix/shadcn primitives
├── context/          auth and product identity/data routing
├── data/             local development fixtures
├── engine/           local relevance behavior and taxonomy reach
├── pages/            route-level product, auth, and ops screens
├── index.css         Signal Ledger semantic tokens and global recipes
└── main.jsx          guarded routes and route-level code splitting
```

The frontend presentation must not re-decide ranking, visibility, clustering,
push policy, or authorization. Those remain backend/data-contract concerns.
