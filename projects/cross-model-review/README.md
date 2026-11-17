# Cross-model review

**Demo — [two recorded runs](docs/demo.md):** a sample plan with one deliberately wrong claim is reviewed by Hermes
(DeepSeek V4.1 Flash) and gets an objection that cites the code line; after a one-line fix, a fresh run approves it.

```text
Behauptung 2 (0=FREI, 1=Fehler, 2=EINWAND):
FALSCH. pruefkreis.py:597 gibt `{"frei": 0, "einwand": 1}.get(status, 2)` zurueck, d.h. 1=EINWAND und 2=Fehler. Die Zuordnung in der Behauptung ist vertauscht. Bestaetigt auch im eigenen Modul-Docstring :52 ("0 = FREI, 1 = EINWAND, 2 = Fehler"). Konkreter Fehler.
[…]
URTEIL: EINWAND
```

**What you see:** an excerpt of round 1 as the tool printed it (German, as the review prompt asks; `[…]` marks
omitted lines). Round 1 took 79.5 s and cost 0.0024 USD; round 2 after the fix ended with `URTEIL: FREI` in 51.5 s
for 0.0035 USD. The full output of both rounds, the fix as a diff and how it was recorded are in
[docs/demo.md](docs/demo.md).

A small CLI that lets one agent's plan or result be checked by a fresh run of another model. I read the review
protocol instead of carrying messages between agents by hand.

**Stack:** Python (standard library) · Codex CLI and Hermes as reviewers

## How it works

```powershell
python pruefkreis.py pruefen --vorlage <file> --thema <id> [--pruefer codex|hermes] [--sensibel] [--gruendlich]
```

1. The planning agent writes its plan or result to a file and calls `pruefen`.
2. The tool starts a **fresh** review run with another model (Codex in its read-only sandbox). The reviewer has no
   memory of the planning chat.
3. It reads the verdict, appends the round to a protocol file (`## Runde N · time · reviewer · input`) and prints
   it for the planning chat.

| Exit code | Meaning |
|---|---|
| 0 | `URTEIL: FREI`, approved |
| 1 | `URTEIL: EINWAND`, objection |
| 2 | error: run failed, timeout, no verdict line or invalid call |

## Rules in the code

- **Only a fixed last line counts.** `URTEIL: FREI` or `URTEIL: EINWAND` must be the last non-empty line. A missing
  line, a non-zero exit or a timeout is `error`, never `approved`.
- **Sensitive topics stay with the private agent.** With `--sensibel`, the reviewer is always Hermes, and
  `--pruefer codex --sensibel` is rejected before anything starts. Only verdict, session id and cost go into the
  protocol; the reasoning stays in the Hermes session.
- **Fallback on quota limits.** If Codex ends with a limit message (`usage limit`, `rate limit`, `quota`, `429`),
  Hermes takes over the same review and the protocol notes the substitution. Other errors don't trigger it.
- **Topic ids become file names**, so only `a-z`, `0-9` and `-` are allowed, up to 80 characters.

## Status

For Codex reviews, `codex exec` runs inside its `--sandbox read-only` mode. For Hermes reviews, `pruefkreis.py` restricts the active toolset via `-t file,todo` alongside the read-only system instruction, and passes the model and provider explicitly (`-m deepseek/deepseek-v4.1-flash --provider openrouter`) instead of relying on the local Hermes profile. A kernel-level read-only filesystem sandbox for Hermes is not built yet.

### Leftover helper processes

Reviewer output goes to temporary files instead of pipes, so a helper process left behind by a reviewer cannot block the run, and the time limit ends the whole process tree.

## Check it yourself

The rules above are covered by an offline test suite — no reviewer, no network, no cost:

```bash
cd projects/cross-model-review
python -m pytest -q tests
```

Local run on 2026-11-17 (Windows, Python 3.12, pytest 9.0.3): `99 passed in 31.75s`. CI runs the same command on
every push and pull request.

← [Back to overview](../../README.md)
