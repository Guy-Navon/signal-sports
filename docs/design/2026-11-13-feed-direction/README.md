# Feed direction — reference mock (approved 2026-11-13)

The coded mock Guy approved on 2026-11-13 as the new look of the consumer product
(milestone 15, issue #461). It is a **reference mock, not product code**: one static page,
inline CSS and a small script, no React, no tests, no build step in `frontend/`. The written
contract is [`docs/FRONTEND_DESIGN_SYSTEM.md`](../../FRONTEND_DESIGN_SYSTEM.md) Part B; when
the doc and the mock disagree, the doc wins and the mock is the illustration.

| File | What it is |
|---|---|
| `feed-direction.template.html` | The approved page with a `/*DATA*/` placeholder. It does not run until filled |
| `build.py` | Fills the template with the public demo snapshot and real final results |

The template is the mock as approved, with three content-only edits: the account item in the
top bar reads "החשבון" instead of the owner's name, the sample-push toggle says it adds a
sample, and the toggle no longer drops real pushes when no sample is present.

## Build

```powershell
python docs/design/2026-11-13-feed-direction/build.py <out-dir> [--root <repo>] [--no-results]
```

- Inputs (read only): `frontend/dist-demo/demo-data/feed.json` and `meta.json` (written by
  `scripts/demo-publish.ps1`), `backend/app/taxonomy/entities.py` for Hebrew team names, and
  `backend/data/signal_sports.db` opened read-only for the ten latest final results.
- `--root` defaults to this repository. A git worktree holds neither the snapshot nor the
  database, so point it at the main checkout. `--no-results` skips the database and the
  results strip.
- A missing input stops the script with the path and what to do.
- Output: `feed-direction.preview.html` (open it in a browser) and `feed-direction.html` (the
  same page without a doctype, the form published as the claude.ai artifact). The script
  refuses an output folder inside the repository.

The page has a ground switch (לבן / רך / כהה, also `#light`, `#soft`, `#dark` in the URL)
and a toggle that adds a hand-written sample push, so the lead block can be reviewed when
the snapshot has no push. The sample is not a feed record.

## Do not commit

The built output: it holds a snapshot of the owner's feed and results. Write it outside the
repository. Nothing in this folder is linted, built or bundled: ESLint covers
`frontend/src/**` only, and the Vite and demo builds read `frontend/index.html` and
`frontend/demo.html` only.

`template.html`/`build.py` from the earlier three-direction comparison stay outside the repo
on purpose; only the approved direction is kept.
