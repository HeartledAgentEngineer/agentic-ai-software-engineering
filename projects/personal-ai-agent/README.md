# Personal AI agent

My personal assistant. It runs phone-first: a FastAPI backend in Termux on Android, the frontend in a browser tab,
models through OpenRouter. It chats, remembers, uses tools, and hands coding tasks to a separate coding agent.

**This folder is an excerpt.** It contains the architecture core: chat, memory, tool loop, model routing and the
security layer. Everything that touches personal data stays private: photo and face features, messenger and
contact imports, cloud storage, run logs and handovers. Names in examples and tests are invented. Because of the
cut, the backend does not start as it is here; it is meant to be read. The included tests are the ones that run
without the private parts.

**Stack:** Python · FastAPI · Server-Sent Events · OpenRouter · vanilla JS frontend (PWA) · Termux · pytest

## Architecture

```
Phone (Termux)
├── FastAPI backend, port 8080
│   ├── router/chat.py ─── chat_routing ──▶ coding tasks to the coding agent (PC → phone → queue)
│   ├── werkzeug_schleife ─▶ tool loop: stream model, run tool calls, feed results back
│   ├── modell_router ────▶ cheapest model that can do the task reliably
│   ├── memory_service ───▶ long-term memory (JSON store with embeddings)
│   └── sicherheit ───────▶ host and origin checks for every response
└── frontend/ (browser tab, installable as PWA)
```

## Design decisions

- **Tool loop as a small harness** (`werkzeug_schleife.py`): per round the model is streamed, tool calls are
  collected and executed, results are appended as `role=tool`. After `max_runden` rounds with tools, a last call
  with `tool_choice="none"` forces an answer. The model call is injectable, so the loop is tested offline.
- **The agent knows its limits** (`faehigkeiten.py`): a deterministic capability manifest says what it can and
  cannot do. When a request needs a terminal or files, the backend (not the model) routes it to the coding agent.
- **Model routing by task** (`modell_router.py`): price only goes up where the task needs it (vision, coding,
  complex reasoning). Standard library only, testable in isolation.
- **Memory that corrects instead of deletes** (`memory_service.py`): a correction makes the new text active and
  moves the old one into `history`; nothing is deleted. Old entries fade gently instead of disappearing.
- **Security found by measuring** (`sicherheit.py`, `router/auth.py`): a test showed that any web page opened in the browser could
  read the API key from `127.0.0.1:8080` (CORS `*` with credentials, no host check). The middleware now checks
  host and origin on every response, which also blocks DNS rebinding; requests authenticate via `X-API-Key` header or
  `HttpOnly` session cookie (with a query-parameter fallback for browser media/SSE links).
- **No known private names in web searches** (`websuche_schutz.py`): general topics, places and public people may be
  searched; full names and multi-word catalog entries from the local contact/person store are blocked before the query leaves the device.

## Run the tests

```powershell
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest tests       # 53 passed on 27.10.2026
```

The code and comments are in German; that is the language I work in.

← [Back to overview](../../README.md)
