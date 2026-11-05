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

## January – May 2026 — AI agents in my day job

- Started with **Claude Code** in a professional team setting.
- Used it in automation work: TwinCAT 3, a VB.NET HMI, generating I/O lists, comparing wiring diagrams.
- **What I learned:** the agent did not make me slower at learning a new tool — it made me faster, as long as I
  checked every result against the real system.

## April – July 2026 — First products of my own

- Moved to Claude and built my first apps on top of a model API.
- **Concertify**: a Flask web app that builds concert playlists from setlists (Spotify and Ticketmaster APIs).
- A hybrid-search **knowledge base** (PostgreSQL + pgvector), a declarative **document generator**
  (Word/PDF), and a small canvas game as a rapid-prototyping exercise.
- May – June 2026: tried Google Antigravity (Gemini) as a cheaper agent platform and dropped it again: too little
  control over what the agent actually touched.
- **What I learned:** speed is easy; keeping a project understandable after the third iteration is the real work.
- 🔗 [Concertify](projects/concertify/) · [RAG knowledge base](projects/rag-knowledge-base/) ·
  [Document automation](projects/document-automation/) · [Squirrel game](projects/squirrel-game/)

## July 2026 — A rule set instead of a prompt

- Set up this portfolio and wrote my first **rule set for agents** (eight phases from brainstorm to commit).
- **What I learned:** rules the agent can ignore are wishes. What matters is what is *enforced*.

## August 2026 — Gates, not permissions

- **typeFREE**, a system-wide dictation tool for Windows that I use every day — most of my instructions to my
  agents are dictated with it.
- A **personal AI assistant** on Android (Termux): chat, long-term memory and tool calls.
- Switched my main setup to an open-source agent (Hermes) with a model gateway (OpenRouter) — several models,
  each for what it does best and at the right price.
- Rebuilt the rules: one tool-agnostic core file (`AGENTS.md`), executable skills instead of prose, permission
  guards, and sub-agents for throw-away context.
- **What I learned:** my approvals at every phase boundary cost the most time and gave the least safety.
  I replaced them with machine checks: *done means the project's check command exits with 0*, and code and
  docs go into the same commit.
- 🔗 [typeFREE](projects/typefree/) · [Personal AI agent](projects/personal-ai-agent/) · [How I work](HOW-I-WORK.md)

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
- **Master-Schalter**, a Windows tray app that measures the quotas of my agents, keeps the role of each project and
  hands a project from one agent to another — with a handover assistant, a visible log and automatic switching
  when a limit is reached.
- Passed **Microsoft AZ-900** (Azure Fundamentals) and **AI-901** (Azure AI Fundamentals); AI-103 is next.
- **What I learned:** autonomy needs transparency. The more an agent does on its own, the more important it is
  that every step is visible and reversible.
- 🔗 [Master-Schalter](projects/master-schalter/) · [Cross-model review](projects/cross-model-review/)

---

## What stayed the same

The habits from automation engineering carried over unchanged: test against the real system, change one thing at
a time, keep every step reversible, and write down why. Agents made these habits more important, not less.
