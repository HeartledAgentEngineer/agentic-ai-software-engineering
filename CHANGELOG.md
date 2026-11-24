# Changelog

All notable changes to the public showcase repository (`agentic-ai-software-engineering`) are tracked here in Keep a Changelog + Semantic Versioning (`vX.Y.Z`) format.

No SemVer release has been published yet.

## [Unreleased]

- Added ESLint to `projects/document-automation` (same flat config and pinned versions as the workshop copy): `npm run lint` and `npm run check`, and an ESLint step in the CI job before the tests (#49).
- Pinned all 13 GitHub Actions uses in `.github/workflows/ci.yml` to full commit SHAs with an AST guard (`ci_pinned_actions.py`) and Dependabot config.
- Added scoped formatting (`ruff format --check` for `.github/scripts` and `projects/cross-model-review`) and `mypy` type checking (`.github/scripts` and `projects/concertify/domain`).
- Added the release readiness checklist (`docs/release-checklist.md`), this changelog structure, and the baseline validator (`.github/scripts/ci_release_readiness.py`).
- Added the aggregate check `ci ok` (green only when every CI job succeeded) as the one check to require for `main`, with a lint guard (`ci_aggregate_check.py`) that fails when a job is missing from it. Branch protection itself is not enabled yet (#48).
- Dependabot now also watches `tools/readfree` and `tools/foundry-demos` (which also covers `shared_core` one folder down); a lint guard (`ci_dependabot_coverage.py`) fails when a pip or npm manifest directory is missing from `dependabot.yml` (#49).
- Fixed duplicate Dependabot pull requests: `tools/foundry-demos/shared_core` was listed next to `tools/foundry-demos`, whose pip update already reads requirement files one folder down. The coverage guard now counts such folders as covered by the parent and fails on the double listing (#49).
- Docs consistency pass from the text review (#51): foundry-demos row in the quality table, test totals explained in `docs/verification.md`, 15 agent tools in the backend README, setlist.fm key in the Concertify `.env` list, run/check notes for the agent frontend and `agent-setup`, back-links (the showcase validator test now copies the overview README its Sonos link points to), and `agent-setup` now describes `sync-portfolio.ps1` as a reporting check that copies nothing.
