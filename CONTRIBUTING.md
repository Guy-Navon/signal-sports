# Contributing

1. Branch from `main` (`feat/…`, `fix/…`, `docs/…`, `chore/…`).
2. Run the checks before opening a PR: `powershell -File scripts\check.ps1`
   (same as CI; `-Backend` or `-Frontend` to run one side).
3. Keep scoring, ingestion and UI separate (see [docs/RELEVANCE_CONTRACT.md](docs/RELEVANCE_CONTRACT.md)).
   Never hardcode a user into the engine; express users as preference profiles.
4. A behavior change updates the matching contract in `docs/`
   ([docs/CURRENT_PROJECT_STATE.md](docs/CURRENT_PROJECT_STATE.md) has the doc map).
5. Open a PR using the template; one focused change per PR.
