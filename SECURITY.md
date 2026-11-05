# Security

## Reporting a vulnerability

For this private preview, report vulnerabilities directly to the repository owner.
If private vulnerability reporting is available in a public version, use GitHub's **Report a vulnerability** form under Security → Advisories.

## What protects this repository

| Measure | Where |
|---|---|
| No secrets in code: keys come from a local `.env`, which is git-ignored | every project |
| Secret scan over the full git history on every push; it runs first, and every other job waits for it (`needs: secrets`) | [CI](.github/workflows/ci.yml), gitleaks-action v3 (Node.js 24) |
| Curated export: only git-tracked, whitelisted files leave my private workspace; a privacy scan (e-mail addresses, private paths, key patterns, phone numbers, IP addresses, names) must report 0 findings before publishing | export tool, not part of this repository |
| Dependency updates as reviewed pull requests | [Dependabot](.github/dependabot.yml) |
| The personal agent checks host and origin on every response (against cross-site reads of its API key and DNS rebinding — found by a test, then fixed) and blocks private names before a web search leaves the device | [personal-ai-agent](projects/personal-ai-agent/) |

The GitHub Actions `actions/checkout@v6`, `actions/setup-python@v6`, and `actions/setup-node@v5` run on Node.js 24.

On pull requests, the secret scan reads the PR commit list with read-only permissions and leaves PR comments disabled.

## Known limits

- Python dependencies are not pinned to exact versions, so there is no reproducible vulnerability audit yet.
- The projects are single-user tools for my own machine or phone; none of them is hardened for public hosting.
