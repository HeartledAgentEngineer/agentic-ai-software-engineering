# Agent setup

The working parts behind [How I work](../HOW-I-WORK.md): skills, sub-agents, the commit gate and the rule sync.
They are written for Claude Code and kept tool-agnostic where possible. The texts are in German, as in daily use.

| Part | What it does | When it is used |
|---|---|---|
| [`AGENTS.md`](AGENTS.md) | the tool-agnostic master instruction file defining core rules: verification gates, code+docs, cross-model cascade, multi-agent collision protection, and privacy boundaries | read by every agent harness (Claude Code, Codex, Antigravity, Hermes) at session start |
| [`sync-portfolio.ps1`](sync-portfolio.ps1) | pre-publication check: confirms the whitelisted components exist in the private playground, scans the showcase for private paths, e-mail addresses and tokens, and runs two test suites; it reports findings but does not stop on them, and it copies nothing | whenever verified changes from the playground workspace are published to the showcase repository |
| [`skills/fehlersuche`](skills/fehlersuche/SKILL.md) | root-cause debugging: find the cause before proposing a fix | every error, failed test or unexpected behaviour, especially when the fix looks obvious |
| [`skills/grill-me`](skills/grill-me/SKILL.md) | the agent asks me questions until the goal is unambiguous, with a question catalogue and an alignment template | before planning, at design forks, when a wish could mean several things |
| [`skills/critic`](skills/critic/SKILL.md) | independent second opinion from a model of another family; `pruefe.mjs` runs it, `review.py` and `protokoll-schema.json` keep the verdict machine-readable | before a slice is committed, for security-related or concurrent code |
| [`agents/tester`](agents/tester.md) | runs the project's check command and reports only the result | testing and after refactoring, so test logs stay out of the main context |
| [`agents/rechercheur`](agents/rechercheur.md) | searches the workspace and returns only the finding | before a search would pull many files into the main context |
| [`settings.example.json`](settings.example.json) | my Claude Code permission rules (allow / ask / deny) as a sanitized example: the two private deny paths are replaced by placeholders | copy to `.claude/settings.json` and adapt the deny paths |
| [`githooks/pre-commit`](githooks/pre-commit) | no commit without a green check command for the touched project (`git config core.hooksPath agent-setup/githooks`); blocks author addresses that GitHub would assign to a foreign account | every commit once the hook path is configured |

## Staging & Synchronization Workflow

Copying from the private playground to the public showcase repository is a manual, reviewed step. `sync-portfolio.ps1`
supports it with checks that **report** problems; the gates that **stop** a change are the pre-commit hook and CI:

```mermaid
flowchart TD
    subgraph Private["Private Development (Playground Workspace)"]
        Dev["Active Development & Experiments"]
        LocalTests["Local Verification & Check Commands"]
        Dev --> LocalTests
    end

    subgraph SyncGate["Staging Gate (agent-setup/sync-portfolio.ps1)"]
        WhitelistFilter["1. Whitelist check<br/>Curated projects, docs & configs exist in the playground (nothing is copied)"]
        PrivacyScan["2. Privacy & leak scan<br/>Regex search: paths, emails, secrets (findings are reported)"]
        TargetVerify["3. Test run<br/>concertify and personal-ai-agent backend (a red suite is reported)"]
        WhitelistFilter --> PrivacyScan --> TargetVerify
    end

    subgraph Public["Showcase Repository (GitHub)"]
        StagedClean["Manual copy & review"]
        PreCommit["Local Pre-Commit Hook<br/>Project check must exit 0"]
        GitPush["Push to origin/main"]
        CloudCI["GitHub Actions Matrix CI<br/>Gitleaks + Ruff + Pytest (Win/Linux)"]
        StagedClean --> PreCommit --> GitPush --> CloudCI
    end

    LocalTests -->|"Run sync-portfolio.ps1"| WhitelistFilter
    TargetVerify -->|"Report read by a human"| StagedClean
```

## Check

No automated test covers this folder; CI does not run anything from it. Before using the hook, a syntax check:

```bash
bash -n agent-setup/githooks/pre-commit   # exit 0 = the hook parses
```

Turning the report of `sync-portfolio.ps1` into a real gate (exit code 1 on a privacy finding or a red suite) is an
open item in [#51](https://github.com/HeartledAgentEngineer/agentic-ai-software-engineering/issues/51).

## Why these exist

- **Skills instead of prose.** A rule in a long instruction file is easy to skip. A skill has a trigger
  description, a fixed procedure and, where possible, a script with an exit code.
- **Sub-agents for throw-away context.** Test output and search results are large and needed once. A sub-agent
  reads them and returns three lines.
- **A git hook is not an agent feature.** Once configured (`git config core.hooksPath agent-setup/githooks`), it runs for Claude Code, other agents and humans alike, so the gate does not depend on any agent remembering it. If a project's local `.venv` is not set up yet, the hook prints a warning and lets the commit pass so a fresh clone remains usable.

← [Back to overview](../README.md)
