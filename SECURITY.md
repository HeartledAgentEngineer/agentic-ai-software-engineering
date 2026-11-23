# Security

## Reporting a vulnerability

For this private preview, report vulnerabilities directly to the repository owner.
If private vulnerability reporting is available in a public version, use GitHub's **Report a vulnerability** form under Security → Advisories.

## What protects this repository

| Measure | Where |
|---|---|
| No secrets in code: keys come from a local `.env`, which is git-ignored | every project |
| Secret scan over the full git history on every push to `main`, pull request, and manual dispatch; it runs first, and every other job waits for it (`needs: secrets`) | [CI](.github/workflows/ci.yml), gitleaks-action v3 (Node.js 24) |
| Every action in CI is pinned to a full 40-char commit SHA with its release as a comment; a lint step rejects tags, short SHAs and multiline `uses:`, and Dependabot raises SHA and comment together | [`.github/scripts/ci_pinned_actions.py`](.github/scripts/ci_pinned_actions.py), [Dependabot](.github/dependabot.yml) |
| One aggregate check `ci ok` is green only when every CI job succeeded (a skipped job counts as red, because a failed secret scan skips all others); a lint step fails when a job is missing from it | [CI](.github/workflows/ci.yml), [`.github/scripts/ci_aggregate_check.py`](.github/scripts/ci_aggregate_check.py) |
| Curated export: only git-tracked, whitelisted files leave my private workspace; a privacy scan (e-mail addresses, private paths, key patterns, phone numbers, IP addresses, names) must report 0 findings before publishing | [`agent-setup/sync-portfolio.ps1`](agent-setup/sync-portfolio.ps1) |
| Dependency updates as reviewed pull requests; Dependabot covers every pip and npm manifest, and a lint step fails when a manifest directory is missing from its config | [Dependabot](.github/dependabot.yml), [`.github/scripts/ci_dependabot_coverage.py`](.github/scripts/ci_dependabot_coverage.py) |
| The personal agent checks host and origin on every response (against cross-site reads of its API key and DNS rebinding — found by a test, then fixed) and blocks private names before a web search leaves the device | [personal-ai-agent](projects/personal-ai-agent/) |

The GitHub Actions `actions/checkout` v7.0.1, `actions/setup-python` v7.1.0, `actions/setup-node` v7.1.0, and `actions/upload-artifact` v7.0.2 run on Node.js 24.

On pull requests, the secret scan reads the PR commit list with read-only permissions and leaves PR comments disabled.

## Known limits

- Python dependencies are not pinned to exact versions, so there is no reproducible vulnerability audit yet.
- `main` has no branch protection yet: a green `ci ok` before merging is a convention, not enforced
  ([#48](https://github.com/HeartledAgentEngineer/agentic-ai-software-engineering/issues/48)).
- The projects are single-user tools for my own machine or phone; none of them is hardened for public hosting.
