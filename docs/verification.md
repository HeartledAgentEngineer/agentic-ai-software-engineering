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

## Test report and coverage per suite

Since 2026-11-19 every pytest suite also writes a JUnit report and a coverage report. The job summary of each
`Tests · <suite>` job lists the totals, every failed, erroring or skipped test with its reason, all tests grouped by
file, and line coverage per module (test code excluded). Both reports stay attached to the run for 14 days as the
artifact `test-reports-<suite>`. The summary comes from [`.github/scripts/ci_test_report.py`](../.github/scripts/ci_test_report.py);
its 10 tests run in the lint job, and the step cannot fail the job. There is no coverage threshold: the numbers are reported, not enforced.

**Recorded run:** [GitHub Actions run 44498434719](https://github.com/HeartledAgentEngineer/agentic-ai-software-engineering/actions/runs/44498434719)
on 2026-11-19 for pull request #42, commit `16ecfee`, all jobs green.

| Suite | Tests | Line coverage (test code excluded) |
|---|---|---|
| orbitdesk | 2,044 (2,043 passed, 1 skipped) | 89 % (9,191 of 10,319 lines) |
| typefree | 659 (658 passed, 1 skipped) | 82 % (2,039 of 2,480) |
| cross-model-review | 99 passed | 92 % (357 of 388) |
| foundry-demos | 87 passed | 61 % (622 of 1,019) |
| readfree | 88 passed | 53 % (579 of 1,091) |
| concertify | 195 (193 passed, 2 skipped) | 21 % (1,167 of 5,611) |
| personal-ai-agent | 57 passed | 22 % (1,107 of 5,086) |
| rag-knowledge-base | 13 passed | 17 % (112 of 676) |

Where coverage is low, the "Known gap" column in the [README](../README.md#quality-at-a-glance) says what is not
tested. Adding coverage did not change which tests run: the same pull request first ran with the JUnit report only
(commit `aa8c5b5`, [run 44496003931](https://github.com/HeartledAgentEngineer/agentic-ai-software-engineering/actions/runs/44496003931)),
and the two runs were compared test by test. All 3,242 tests matched with the same result in both runs (none added,
missing or changed), and the pytest summary lines of the first run matched the last run on `main`.

## What CI does not check

- The demo GIFs are recorded locally by [`scripts/demos/record-browser-demos.cjs`](../scripts/demos/record-browser-demos.cjs)
  and committed. CI checks their size and that each project README links them; it does not record them again.
- The [cross-model review demo](../projects/cross-model-review/docs/demo.md) needs a signed-in reviewer (Hermes or
  Codex) and costs a few tenths of a cent per run, so it is a recorded run, not a CI job. The offline rules behind it
  are the `cross-model-review` tests above.
- Formatting (`ruff format --check`) is currently enforced only for `.github/scripts` and `projects/cross-model-review`
  (added on 2026-11-21); the remaining Python projects are checked only with `ruff check` (`E9`, `F63`, `F7`, `F82`)
  and are not format-checked in CI yet.
- Static type checking (`mypy` 1.13.0) currently covers only `.github/scripts/ci_pinned_actions.py`,
  `.github/scripts/ci_test_report.py`, `.github/scripts/ci_release_readiness.py`, and `projects/concertify/domain`
  (updated on 2026-11-21); all other modules and test files are not type-checked in CI yet.
