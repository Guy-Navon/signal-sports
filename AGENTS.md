# Repository delivery workflow

The owner's standing preference is one branch and one pull request per feature.
Keep implementation and delivery together; a working local demo is not repository
delivery or production deployment.

- Fetch origin before starting and base new work on current `origin/main`, unless
  the feature explicitly depends on an existing PR. Preserve unrelated local work.
- Use a descriptive topic branch. Keep independent features in separate commits,
  branches and PRs. For dependent work, target the preceding feature branch and
  link the dependency and merge order in each PR.
- Implement the product behavior and its demo equivalent where relevant. Document
  differences caused by static data, settings, provider support or read-only mode.
- Run checks appropriate to the changed behavior and document their actual results.
  Distinguish local checks from GitHub CI and report pending or failed checks.
- Commit only intended source, tests and documentation; never publish local
  settings, credentials, databases or generated snapshots/builds.
- Push the branch and open or update its PR as part of feature delivery. Include
  the problem, resulting behavior, relevant validation, limitations and dependencies.
  Do not leave completed requested features only in a local working tree.
- Report the branch and PR link, plus whether it is open, merged and deployed.
  Do not describe opening a PR as updating main or a live website. Follow the
  user's merge/deployment instructions; these are distinct delivery steps.
- When a dependency lands, retarget the next PR to current main and verify that
  its diff and checks still represent only its intended change.

Results/demo delivery history and the initial feature stack are documented in
[docs/archive/FEATURE_DELIVERY_2026-11-16.md](docs/archive/FEATURE_DELIVERY_2026-11-16.md).
