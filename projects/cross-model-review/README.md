# Cross-model review

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

Not built yet: a technical read-only lock for the Hermes reviewer. Until then, only the instruction text keeps it
from writing files.

← [Back to overview](../../README.md)
