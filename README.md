# Agentic AI Software Engineering

[![CI](https://github.com/HeartledAgentEngineer/agentic-ai-software-engineering/actions/workflows/ci.yml/badge.svg)](https://github.com/HeartledAgentEngineer/agentic-ai-software-engineering/actions/workflows/ci.yml)

**I build AI agents — and I build software with AI agents.**

I build software together with AI coding agents — and I build the system around them that makes their work
verifiable: rules, gates, roles and handovers. I come from automation engineering (PLC programming, HMIs,
commissioning), and I bring its habits along: test against the real system, change one thing at a time, keep every
step reversible.

**My role: architect and orchestrator.** I am not a hand-coder, and I don't pretend to be one. I design the
architecture and the logic, cut the work into small steps that can be checked, and let AI agents write most of the
code. What I own is everything around it: I read and understand the code, I decide what counts as done, and I make
every claim checkable — by a test, a gate or a review from a second model. The
[Journey](JOURNEY.md) is the honest record of a steep learning curve over the last months.

This repository is my curated showcase. It shows **what I built**, **how I work with agents**, and **how I got
here**.

| Start here | What you find |
|---|---|
| [My Journey](JOURNEY.md) | From prompting to running several agents and models as one system — stage by stage, each with a project as evidence |
| [How I work](HOW-I-WORK.md) | The working method: verification gate, planner / reviewer / worker roles across harnesses, cross-model review, state in files |
| [Projects](#projects) | The projects that came out of it, from a PLC digital twin to a multi-agent control room (*Leitwarte*) |

---

## Multi-Agent Ecosystem & Control Room (*Leitwarte*)

Coming from industrial automation, I treat multi-agent software engineering like a **control room (*Leitwarte*)**:
multiple specialized harnesses and frontier/cloud models operate under one tool-agnostic rule set ([`AGENTS.md`](agent-setup/AGENTS.md)),
steered by **[OrbitDesk (Master-Schalter)](projects/master-schalter/)** and verified by **[Cross-model review](projects/cross-model-review/)** and automated gates.

- **Agent harnesses:** **Claude Code** · **OpenAI Codex** (ChatGPT CLI & Desktop) · **Google Antigravity** · **Hermes** (open-source agent for private data and cost-controlled runs)
- **Model & provider layer:** Frontier models across families (**Claude Opus/Sonnet**, **OpenAI GPT-6 Sol/Luna/Astra**, **Google Gemini**), **OpenRouter** (e.g. **DeepSeek V4.1 Flash** for fast worker/fallback runs and privacy-first routing), and **Microsoft Foundry / Azure AI Agent Service** (cloud agent patterns, RAG, MCP, AI-103)

```mermaid
flowchart TB
    subgraph Control["Control Plane · OrbitDesk (Leitwarte)"]
        OD["OrbitDesk (Master-Schalter)<br/>Quotas · Role & model profiles · Topic locks · Handovers"]
        RULES["AGENTS.md + Skills<br/>Tool-agnostic governance"]
    end
    subgraph Harnesses["Agent Harnesses & Model Families"]
        PLAN["Planner (Thinker)<br/>Claude Code · Antigravity · Codex<br/>Frontier models"]
        WORK["Worker (Builder)<br/>Codex · Claude Sonnet · Hermes (OpenRouter)<br/>Scoped worktrees"]
        REV["Cross-Model Reviewer<br/>pruefkreis.py · Different model family<br/>Codex read-only sandbox · Hermes -t file,todo"]
        PRIV["Privacy Boundary<br/>Hermes + OpenRouter / Microsoft Foundry<br/>Sensitive data stays isolated"]
    end
    subgraph Gates["Deterministic Verification Gates"]
        HOOK["Git pre-commit hook<br/>Project test suites + identity check"]
        CI["GitHub Actions CI<br/>Gitleaks → Ruff → 6× pytest → Node → Clang C"]
    end
    OD --> PLAN
    RULES --> PLAN
    PLAN -->|Technical task| WORK
    WORK -->|Diff + check command = 0| REV
    REV -->|URTEIL: FREI / EINWAND| PLAN
    PLAN -.->|Sensitive scope only| PRIV
    WORK --> HOOK --> CI
```

---

## Projects

| Project | What it is | Stack | Status |
|---|---|---|---|
| [OrbitDesk (Master-Schalter)](projects/master-schalter/) | SCADA-inspired Windows control-room app (*Leitwarte*) that tracks live agent quotas, manages per-project role/model profiles, and hands work from one agent harness to another | Python, tkinter, pystray, pytest | In daily use |
| [Cross-model review](projects/cross-model-review/) | Review loop: a plan or result is checked by a fresh run of another model family; the verdict is a machine-readable line, the protocol is shown to me | Python, Codex CLI, Hermes | In daily use |
| [Personal AI agent](projects/personal-ai-agent/) | Personal assistant on Android: chat, long-term memory, tool calls, coding-agent routing | Python, FastAPI, web frontend, Termux | In daily use |
| [typeFREE](projects/typefree/) | System-wide dictation tool for Windows with selectable speech-to-text providers and text clean-up | Python, keyboard hooks, pytest | In daily use |
| [Concertify](projects/concertify/) | Web app that builds concert playlists from live setlists, evolved into a 5-layer architecture | Python, Flask, SQLite, Server-Sent Events, Spotify / Ticketmaster APIs | Working prototype |
| [RAG knowledge base](projects/rag-knowledge-base/) | Semantic knowledge base with hybrid search (vector + full-text reciprocal rank fusion) | Python, FastAPI, PostgreSQL + pgvector, Mistral / Gemini | Working prototype |
| [Document automation](projects/document-automation/) | Data-driven CV generator: JSON → validated, escaped HTML → A4 PDF, plus PDF merging | Node.js, Puppeteer, pdf-lib, node:test | Stable local tool |
| [Elevator digital twin](projects/elevator-digital-twin/) | Real TwinCAT 3 PLC logic driving a simulated elevator with a 3D HMI in the browser (hardware-in-the-loop) | Structured Text, Node.js ADS bridge, WebSockets, Three.js | Working prototype |
| [University foundations: mail-order company in C](projects/university-foundations/mail-order-c/) | My 2020 university lab code, unchanged — plus a 2026 review with compiler warnings and characterization tests | C (structs, pointers, linked lists, binary files), clang | Archive + review |
| [Squirrel game](projects/squirrel-game/) | Small canvas game, built as a rapid-prototyping exercise | HTML5 Canvas, vanilla JS | Finished |
| [Agent setup](agent-setup/) | The skills, sub-agents and git hook behind the method | Markdown skills, Bash, Node.js | In daily use |

```mermaid
graph LR
    subgraph OT["Where I come from"]
        U["University foundations (C)"]
        E["Elevator digital twin"]
    end
    subgraph Products["Own products"]
        C["Concertify"]
        R["RAG knowledge base"]
        D["Document automation"]
        S["Squirrel game"]
    end
    subgraph Daily["Tools I use every day"]
        T["typeFREE"]
        P["Personal AI agent"]
    end
    subgraph System["Agents as one system"]
        M["OrbitDesk (Master-Schalter)"]
        X["Cross-model review"]
        A["Agent setup"]
    end
    OT --> Products --> Daily --> System
```

## Quality at a glance

Every push to `main`, pull request, and manual workflow dispatch runs [CI](.github/workflows/ci.yml): a full-history secret scan (Gitleaks), a lint gate (ruff, bug-class rules: syntax errors, undefined names), the test suites below, a syntax check of every JavaScript file, the Node test runner, and the C characterization tests.

| Project | Automated tests | Runs in CI | Known gap |
|---|---|---|---|
| OrbitDesk (Master-Schalter) | 2,043 pytest tests (+ 1 skipped) | yes (Windows) | tray/UI interactions use fakes in headless test runs |
| typeFREE | 659 pytest tests (658 passed, 1 skipped on CI) | yes (Windows) | hotkeys and audio are mocked; real devices are tested by hand |
| Concertify | 193 pytest tests (+ 2 skipped) | yes (Linux) | external APIs are stubbed |
| Personal AI agent | 53 pytest tests | yes (Linux) | this is an excerpt; the full private suite is larger and not published |
| Cross-model review | 96 pytest tests | yes (Linux) | CLI agents are replaced by stand-ins; real review runs are logged in protocols |
| RAG knowledge base | 13 pytest tests (chunking + query path with fakes) | yes (Linux) | ingestion (`ingest.py`) and the real database are not tested; `test_embeddings.py` is a manual check against the live API |
| Document automation | 11 node:test tests (CV data model, HTML rendering, PDF merge error paths) | yes (Linux) | the browser PDF print step (Puppeteer) is checked by hand |
| University foundations (C, 2020) | 12 checks in C against the unchanged 2020 code | yes (Windows, clang) | two of the checks pin known bugs on purpose; see the review |
| Elevator digital twin | — | JS syntax only (ADS bridge) | PLC logic needs the TwinCAT runtime and is checked by hand there, not in CI |
| Squirrel game | — | no | single HTML file with inline script, not covered by the JS check |

The gaps are listed on purpose: a green badge should not claim more than the pipeline checks.

## How the work is done

Every project here was built with AI coding agents (**Claude Code**, **OpenAI Codex**, **Google Antigravity**, and **Hermes** via **OpenRouter** / **Microsoft Foundry**). The short version of the method — the long one is in [How I work](HOW-I-WORK.md):

- **Done means verified.** A step is finished when the project's check command exits with 0, not when it looks
  plausible. A sub-agent's success message is not evidence; the diff is.
- **Rules are wishes, guards are rules.** What an agent *may* do is enforced by permission settings and a
  pre-commit hook, not by a sentence in a prompt.
- **Different roles, different models.** One model plans, a model from a different family reviews, cheaper
  models build — coordinated through [OrbitDesk](projects/master-schalter/). I watch the review protocols instead of carrying messages between agents.
- **State lives in files.** Plans, journals and handover files make it possible to stop, switch tools or switch
  agents in the middle of a task.
- **Code and docs in the same commit.** Documentation must not claim anything the code does not do.

## License

[MIT](LICENSE)
