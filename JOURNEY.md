# My Journey — from automation engineering to agentic AI software engineering

I am an automation engineer (B.Sc. Electrical and Information Engineering) with a background in machine
building: PLC programming, HMIs and commissioning. Over the last months I turned the way I already worked —
systematic, test-driven, close to the real system — into a way of building software **with AI coding agents**.
My part in it is architecture, logic and verification; the agents write most of the code. This page shows that path step by step. Every stage links to a project in this repository that came out of it.

🔗 Where I come from: [Elevator digital twin](projects/elevator-digital-twin/) — a TwinCAT 3 PLC coupled through a
Node.js ADS bridge to a 3D HMI in the browser, the bridge between my OT background and web software.

> Short version: I started by using one AI assistant, then learned to give agents rules, then gates,
> then roles — and today I run several agents and models as one system, with verification instead of trust.

---

## Before 2025 — Foundations: from Delphi to C, Java and PLCs

- **School:** my first programs in Delphi (small GUI exercises in computer science class).
- **Technical upper secondary school (2016–2018):** Java with the Hamster simulator; PLC programming with Siemens
  LOGO! and S7 in TIA Portal — function block diagram (FBD) and S7-GRAPH sequences (e.g. an industrial gate and a
  lock gate); first contact with IO-Link.
- **University (HAW Hamburg, 2019–2023):** C in Programming I/II — for example a mail-order system with linked lists
  and binary files; object-oriented Java (inheritance, exceptions, Swing GUIs, threads, graph algorithms); RSA
  cryptography in C. Most labs were team work of two.
- 🔗 Evidence: [Mail-order company in C](projects/university-foundations/mail-order-c/) — the 2020 code unchanged,
  next to my 2026 review of it with compiler warnings and tests.
- **What I learned:** I learned high-level languages before PLCs — FBD and GRAPH were one more set of languages,
  not my only one. Reading my old code again with tests showed me where the real skill is: not in typing code, but
  in making it verifiable.

## 2025 – February 2026 — Prompting with an engineering mindset

- Worked with ChatGPT: personalised chatbots and system prompts written like a specification: inputs, constraints, expected output.
- **What I learned:** a model behaves like a new colleague — the clearer the brief, the better the result.

## January – May 2026 — AI agents in my day job & building a 3D PLC Digital Twin

- Started with **Claude Code** in a professional team setting and used it in automation work: TwinCAT 3, a VB.NET HMI, generating I/O lists, and comparing wiring diagrams.
- **From a 2D TIA Portal / WinCC exercise to a 3D Digital Twin:** in December 2025 at my previous company, I had rebuilt a classic TIA Portal / WinCC simulation exercise in **TwinCAT 3** to prepare for Beckhoff PLCs. In January – February 2026 at home, I set up TwinCAT 3 on my own machine and took that idea further — replacing the flat WinCC screen with my own **3D physical simulation (Digital Twin)**: a real TwinCAT 3 PLC (Structured Text) coupled via a Node.js ADS bridge and WebSockets to a Three.js 3D elevator HMI in the browser (hardware-in-the-loop at 20 Hz).
- **What I learned:** the agent did not make me slower at learning a new tool — it made me faster, as long as I
  checked every result against the real system.
- 🔗 Evidence: [Elevator digital twin](projects/elevator-digital-twin/)

## April – July 2026 — First products & Origin of the Dual Engineering System

- Moved to Claude and built my first apps on top of a model API.
- **Concertify**: a Flask web app that builds concert playlists from setlists (Spotify and Ticketmaster APIs).
  - 🔗 **Where the engineering methodology was born:** During Concertify, I realized that AI coding without architectural boundaries quickly collapses into spaghetti code. To solve this, I designed the **[Dual Engineering System](projects/concertify/docs/dual_engineering_system.md)**: splitting the process into two complementary roles — the *Architect* (Clean Architecture, strict layering, dependency injection) and the *Guardian* (static verification, no globals, 100% test isolation with fake repositories).
  - This originally ran as a structured 4-to-8 phase cycle (Brainstorming → Alignment → Implementation → Verification) and served as the direct conceptual foundation for my later multi-agent system.
- A hybrid-search **RAG knowledge base** (PostgreSQL + `pgvector`, Mistral `mistral-embed` & OCR): started as a hands-on exercise from an **Everlast AI** RAG tutorial in **n8n**, which I then rebuilt as a standalone Python pipeline to get away from paid n8n cloud nodes and keep chunking and Reciprocal Rank Fusion in code.
- A declarative **document generator** (Word/PDF), and a small canvas game as a rapid-prototyping exercise.
- May – June 2026: first look at Google Antigravity (Gemini) before I had a shared rule and gate system — without explicit guardrails, an autonomous IDE agent had too little control over what it touched, which pushed me to build tool-agnostic rules and hard verification gates first.
- **What I learned:** speed is easy; keeping a project understandable after the third iteration is the real work.
- 🔗 [Concertify](projects/concertify/) · [Dual Engineering System](projects/concertify/docs/dual_engineering_system.md) · [RAG knowledge base](projects/rag-knowledge-base/) ·
  [Document automation](projects/document-automation/) · [Squirrel game](projects/squirrel-game/)

## July 2026 — A rule set instead of a prompt

- Set up this portfolio and wrote my first **rule set for agents** (eight phases from brainstorm to commit).
- **What I learned:** rules the agent can ignore are wishes. What matters is what is *enforced*.

## August 2026 — Gates, not permissions

- **typeFREE**, a system-wide dictation tool for Windows that I use every day — most of my instructions to my
  agents are dictated with it.
- A **personal AI assistant** on Android (Termux): chat, long-term memory and tool calls.
- **The mobile engineering experiment (vacation coding):** I experimented with running an open-source autonomous coding harness (Hermes CLI inside `tmux`) entirely locally on my Android phone in Termux. It was an ambitious attempt to do full autonomous engineering on the go, but the reality was sobering: phone battery drain, Termux background daemon kills by the OS, tiny touchscreens, and thermal throttling during long runs.
- **The architectural lesson:** heavy software engineering (compilation, full test suites, git hooks, multi-file AST parsing) belongs on a dedicated workstation. The smartphone is ideal as an *orchestration and voice cockpit*, not a build server.
- Switched my main setup to an open-source agent (Hermes) with a model gateway (OpenRouter) — several models,
  each for what it does best and at the right price.
- Rebuilt the rules: one tool-agnostic core file (`AGENTS.md`), executable skills instead of prose, permission
  guards, and sub-agents for throw-away context.
- **What I learned:** my approvals at every phase boundary cost the most time and gave the least safety.
  I replaced them with machine checks: *done means the project's check command exits with 0*, and code and
  docs go into the same commit.
- 🔗 [typeFREE](tools/typefree/) · [Personal AI agent](projects/personal-ai-agent/) · [How I work](HOW-I-WORK.md)

## September 2026 — Planner and workers

- A strong model plans and reviews, cheaper models build, and private data is only handled by one dedicated
  agent — first coordinated through a simple file-based message bus.
- Long jobs run as their own processes with resume points; several agents commit to the same repository
  without stepping on each other (explicit file lists, never “add all”).
- Started a structured Microsoft Azure and AI training programme.
- **What I learned:** errors show up at role boundaries — which is exactly where they should be caught.

## October 2026 — Agents as one system

- Retired the message bus in favour of direct, short-lived review sessions.
- A **role matrix** across subscriptions: who plans, who reviews and who builds depends on which quota is free;
  the reviewer always comes from a different model family than the planner (for example Claude plans, OpenAI's Codex
  reviews).
- A **cross-model review loop**: every result is checked by another model and reworked until it is approved; the
  review protocol is shown to me after each round.
- **OrbitDesk** (formerly *Master-Schalter*), a SCADA-inspired Windows control-room app (*Leitwarte*) that tracks the live quotas of my agents,
  keeps the role and model profile of each project, and hands a project from one agent harness to another — with a handover assistant, a visible
  log and automatic switching when a limit is reached.
- Passed **Microsoft AZ-900** (Azure Fundamentals) and **AI-901** (Azure AI Fundamentals).
- **What I learned:** autonomy needs transparency. The more an agent does on its own, the more important it is
  that every step is visible and reversible.
- 🔗 [OrbitDesk](projects/orbitdesk/) · [Cross-model review](projects/cross-model-review/)

## November 2026 — Multi-harness orchestration, cloud agents & the hybrid Leitwarte

- Brought **Google Antigravity** back into active daily use alongside **Claude Code**, **OpenAI Codex** (ChatGPT), and **Hermes** — now governed by one shared rule and verification system (`AGENTS.md` + **OrbitDesk** as the central *Leitwarte*), which solved the control problem I had seen in May.
- **The Hybrid Leitwarte architecture:** crystallized the clear separation between compute and control:
  - **Workstation:** the heavy-duty engine running test matrices, compiler runs, isolated git worktrees, and desktop agent harnesses (Claude Code, Codex, Antigravity, local Hermes gateway).
  - **Smartphone as the mobile control cockpit:** replacing clumsy mobile coding terminals with a **universal Live Voice Mode** (full-duplex Web Audio / WebSocket, hands-free interaction across all tools) and building **OrbitView** — an **MCP (Model Context Protocol)** server and responsive mobile frontend for OrbitDesk that lets me monitor subscription quotas, topic ownership locks, and agent transitions on the go from any browser, Telegram, or mobile agent client.
- Connected **Microsoft Foundry** models directly to **Hermes** (using the 30-day / \$200 Azure Foundry trial) to test enterprise model deployments, privacy-scoped routing, and cross-family review/worker runs hands-on alongside **OpenRouter** (DeepSeek V4.1 Flash) and frontier models.
- Working through **Microsoft AI-103** (*Developing AI Apps and Agents on Azure*): building with **Microsoft Foundry** and the **Azure AI Agent Service** (stateful threads, Code Interpreter, File Search, custom tool calls, RAG, Model Context Protocol / MCP, and multi-agent orchestration), alongside privacy-first routing concepts (GDPR / Zero Data Retention) and token cost control.
- **readFREE**, the counterpart to typeFREE: select text anywhere, press a key, listen. With four or five agent chats running in parallel, the stream of text to read became the bottleneck; moving part of it to the ears gives the eyes a break.
- Hardened this portfolio for release: automated secret scanning (Gitleaks), CI test matrices across Windows and Linux, and strict data-privacy / PII checks before publication.
- **What I learned:** whether in industrial PLCs or cloud agent pipelines, reliability comes from explicit state boundaries, deterministic checks, and knowing exactly where data goes.
- 🔗 [readFREE](tools/readfree/) · [Agent setup](agent-setup/) · [CI workflow](.github/workflows/ci.yml) · [Security policy](SECURITY.md)

---

## What stayed the same

The habits from automation engineering carried over unchanged: test against the real system, change one thing at
a time, keep every step reversible, and write down why. Agents made these habits more important, not less.
