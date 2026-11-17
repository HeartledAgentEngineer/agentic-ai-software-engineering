# Demo plan: the contract a caller of pruefkreis.py relies on — Fassung 2

Sample template for the recorded demo in [`../docs/demo.md`](../docs/demo.md), about real code in this repository.

## Purpose

A caller — for example a script that starts a review and then acts on the result — will rely on the four claims
below. Before anyone relies on them, each claim has to be checked against `projects/cross-model-review/pruefkreis.py`.

## Claims

1. Only the last non-empty line of the reviewer's answer counts. It must be `URTEIL: FREI` or `URTEIL: EINWAND`
   (surrounding whitespace is ignored); anything else makes the round an error, never an approval.
2. Exit codes of `pruefkreis.py pruefen`: 0 = `FREI`, 1 = `EINWAND`, 2 = error.
3. `--pruefer codex --sensibel` is rejected before any review starts.
4. A Hermes review runs with the toolset `-t file,todo`, and model and provider are passed explicitly.

## Review journal

- Round 1: EINWAND — claim 2 had exit codes 1 and 2 swapped (`pruefkreis.py:597`). Corrected in Fassung 2.
