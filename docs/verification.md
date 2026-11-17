# Verification run

Every claim in this repository should be checkable. This page lists each CI job, the command that runs the same check
locally, and what the job printed in one recorded run.

**Recorded run:** [GitHub Actions run 44077682545](https://github.com/HeartledAgentEngineer/agentic-ai-software-engineering/actions/runs/44077682545)
on 2026-11-17 for pull request #32, commit `87e0aa7` (tested as merge commit `593d868` with `main`), result
**success**, 13 of 13 jobs green. This is a dated snapshot; the current state is the CI badge in the
[README](../README.md).

| CI job | Runner | Local command (from the repository root) | Result line in the recorded run |
|---|---|---|---|
| Secret scan (gitleaks) | Ubuntu | runs as GitHub Action `gitleaks/gitleaks-action@v3` over the whole history | `no leaks found` |
| Lint (ruff) | Ubuntu | `pip install ruff==0.6.9` · `ruff check .` | exit 0, no findings reported |
| Tests · orbitdesk | Windows | `cd projects/orbitdesk` · `pip install -e ".[leiste,dev]"` · `python -m pytest -q` | `2043 passed, 1 skipped in 106.72s` |
| Tests · typefree | Windows | `cd tools/typefree` · `pip install -r windows/requirements.txt -r windows/requirements-dev.txt` · `python -m pytest -q windows/tests` | `658 passed, 1 skipped in 22.26s` |
| Tests · readfree | Windows | `cd tools/readfree` · `pip install -r requirements.txt pytest` · `python -m pytest -q tests` | `88 passed in 0.67s` |
| Tests · concertify | Ubuntu | `cd projects/concertify` · `pip install -r requirements.txt pytest` · `python -m pytest -q tests` | `193 passed, 2 skipped in 0.94s` |
| Tests · cross-model-review | Ubuntu | `cd projects/cross-model-review` · `pip install pytest` · `python -m pytest -q tests` | `99 passed in 4.39s` |
| Tests · rag-knowledge-base | Ubuntu | `cd projects/rag-knowledge-base` · `pip install pytest -r requirements.txt` · `python -m pytest -q tests` | `13 passed, 1 warning in 0.63s` |
| Tests · personal-ai-agent | Ubuntu | `cd projects/personal-ai-agent/backend` · `pip install -r requirements.txt -r requirements-dev.txt` · `python -m pytest -q tests` | `57 passed, 115 warnings in 1.53s` |
| ShotReader · PowerShell self-test | Windows | `cd tools/shotreader` · `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ShotReader.ps1 -Test` | `Automatik-Regeln: ok` · `OCR: This is a screenshot reading test.` · `Audio bytes: 58450` |
| C · university foundations | Windows | `cd projects/university-foundations/mail-order-c` · `CC=clang bash check.sh` | `0 check(s) failed` — the compiler warnings in the log come from the unchanged 2020 code; the [2026 review](../projects/university-foundations/mail-order-c/REVIEW-2026.md) uses them as evidence |
| JavaScript syntax | Ubuntu | `node --check` on every `.js` under `projects/` and `tools/` · `cd projects/document-automation` · `npm ci --ignore-scripts` · `node --test` | `# pass 11` · `# fail 0` |
| Sonos simulation · tests, validator and browser QA | Windows | `node --test projects/sonos-music-drop/demo/ducker.test.js` · `node scripts/verify-showcase.mjs` · `node --test scripts/verify-showcase.test.mjs` · `node projects/sonos-music-drop/demo/browser-check.cjs` (needs Playwright and Edge) | `# pass 9` · `Showcase validation passed: … and 3 demo file(s) within 5 MB and linked from their README.` · `# pass 2` · `Browser QA passed at 390px and 1280px; guard probes blocked: 1; unexpected external requests: 0; page errors: 0; …` |

In total: 3,151 Python tests passed across seven suites (4 skipped), plus 22 Node tests, the C characterization checks
and the PowerShell self-test.

## What CI does not check

- The demo GIFs are recorded locally by [`scripts/demos/record-browser-demos.cjs`](../scripts/demos/record-browser-demos.cjs)
  and committed. CI checks their size and that each project README links them; it does not record them again.
- The [cross-model review demo](../projects/cross-model-review/docs/demo.md) needs a signed-in reviewer (Hermes or
  Codex) and costs a few tenths of a cent per run, so it is a recorded run, not a CI job. The offline rules behind it
  are the `cross-model-review` tests above.
