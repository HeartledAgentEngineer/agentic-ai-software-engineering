# Release checklist and promotion workflow

This checklist defines how a showcase milestone becomes a SemVer release in this public repository (`agentic-ai-software-engineering`). It adds a repeatable verification baseline without creating a tag or publishing a release automatically.

## Promotion and release flow

```text
Playground (main)
  -> sanitized privacy export & verification
  -> feature branch & pull request in this repository
  -> green GitHub Actions CI (14/14 jobs on exact commit)
  -> independent cross-model review (different model family, URTEIL: FREI)
  -> SemVer tag vX.Y.Z & GitHub draft release (keeping prior release downloadable)
  -> explicit owner approval before publishing or visibility changes
```

## Five-point release gate (`#110`)

| Gate | How it is verified | Scope / owner |
|---|---|---|
| 1. Required docs & workflow files present | Automated in CI and locally via `python .github/scripts/ci_release_readiness.py --repo-root .` | `README.md`, `SECURITY.md`, `CHANGELOG.md`, `docs/verification.md`, `docs/enterprise-rollout.md`, `docs/release-checklist.md`, `.github/workflows/ci.yml` |
| 2. Hygiene scan (secrets/paths/markers) | Automated (`gitleaks` in CI + `ci_release_readiness.py` scan for conflict markers and non-placeholder `C:\Users\<user>` paths) | Script checks tracked text files; CI additionally runs `gitleaks` over history |
| 3. SemVer & changelog verification | Automated on release prep via `python .github/scripts/ci_release_readiness.py --repo-root . --version vX.Y.Z` | Validates strict `vX.Y.Z` format and a populated `## [vX.Y.Z] - YYYY-MM-DD` section in `CHANGELOG.md` |
| 4. Full CI & cross-model review | External / mandatory on exact commit | All 14 GitHub Actions jobs green + cross-model review `URTEIL: FREI` from another model family |
| 5. Rollback path & explicit owner approval | Human sign-off (never automated) | Prior release remains available for rollback; Sebastian explicitly approves publication |

## Current release status

No SemVer release (`vX.Y.Z`) has been published for this showcase repository yet. Do not create release tags or publish releases without explicit owner approval.
