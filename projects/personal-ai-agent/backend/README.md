# Personal AI Agent — Backend Reference (`backend/`)

This directory contains the FastAPI backend of the Personal AI Agent. It is designed to run inside **Termux on Android** (`serve.py` / `uvicorn app.main:app --port 8080`) as well as on a desktop workstation.

Because this repository is a privacy-safe architectural excerpt of my daily-driver assistant, private data connectors (raw photo/face stores, WhatsApp SQLite importers, pCloud credentials) are omitted. All core orchestration, routing, tool execution, memory, and security modules are included in full and covered by **53 offline unit tests**.

---

## Directory Layout

```text
backend/
├── serve.py                        # Uvicorn launcher (reads HOST_BIND & PORT from .env)
├── system_prompt.md                # Base persona & behavioral rules injected into every chat
├── requirements.txt                # Runtime dependencies (FastAPI, httpx, numpy, openai, etc.)
├── requirements-dev.txt            # Test dependencies (pytest)
├── app/
│   ├── main.py                     # FastAPI app factory, lifespan self-healing, static file serving
│   ├── sicherheit.py               # Raw ASGI security middleware (Host, Origin, Sec-Fetch-Site, CSP)
│   ├── config.py                   # Environment configuration & LAN-binding safety warnings
│   ├── models.py                   # Pydantic request/response schemas (ChatRequest, ChatResponse, MemoryItem)
│   ├── modelle_de.py               # Curated German descriptions & strengths for OpenRouter models
│   ├── modelle_use.py              # Tool-calling capability filter for the OpenRouter catalog
│   ├── db/
│   │   └── chroma_client.py        # Local JSON vector store (memory_store.json) with cosine similarity
│   ├── router/
│   │   ├── auth.py                 # API key dependency (X-API-Key header, HttpOnly cookie, SSE query param)
│   │   ├── chat.py                 # /api/chat & /api/chat/stream (SSE), conversation management, Hermes switch
│   │   ├── llm_models.py           # /api/models catalog & provider privacy/zero-data-retention details
│   │   ├── memory.py               # /api/memory CRUD, dry-run deduplication, and vector backfilling
│   │   └── selbsttest.py           # /api/selbsttest cable-free mobile diagnostics (never returns HTTP 500)
│   └── services/
│       ├── werkzeug_schleife.py    # Multi-round streaming tool loop harness & <｜DSML｜> filter
│       ├── werkzeuge.py            # 13 registered agent tools, OpenAI schema generator & invariant check
│       ├── faehigkeiten.py         # Deterministic capability manifest & Hermes boundary detector
│       ├── chat_routing.py         # Workstation delegation (Track A: PC gateway, Track B: Queue; retired Track C prototype)
│       ├── modell_router.py        # Task-category classifier & cost-optimal OpenRouter model selector
│       ├── memory_service.py       # Fact extraction, correction-vs-duplicate logic, temporal Top-K ranking
│       ├── llm_service.py          # OpenRouter client, 3-stage STT fallback chain, PII-shielded text polish
│       ├── kontext_service.py      # Prompt context builder (merges memories, archive hits & recent turns)
│       ├── chat_verlauf.py         # Append-only conversation store (atomic writes + .bak recovery)
│       ├── websuche_schutz.py      # Privacy guard blocking private contact/person names in web searches
│       ├── web_suche.py            # Web search wrapper enforcing websuche_schutz before network calls
│       ├── sse.py                  # Server-Sent Events serializer & live Hermes job stream multiplexer
│       └── protokoll.py            # Rotating server log buffer for mobile inspection
└── tests/                          # 57 unit tests (capabilities, edge cases, prompt rules, memory, history)
```

---

## Module & Function Walkthrough

### 1. Application Entry Point & Security (`app/`)

- **[`app/main.py`](app/main.py)**
  - **`lifespan(app)`**: Initializes the local JSON memory store (`chroma_client.connect()`), logs a warning via `bindung_hinweis()` if the server binds to `0.0.0.0` without an `API_KEY`, performs **Track C self-healing** on startup (`sicherstelle_inbox_daemon()` ensures the Termux Hermes inbox daemon is alive; `raeume_alte_job_sessions_auf()` cleans up orphaned `tmux` sessions), and closes stale `'laeuft'` tasks from previous process lifecycles (`verwaiste_auftraege_schliessen()`).
  - **Static & Key Injection**: Serves only whitelisted frontend files (`FRONTEND_DATEIEN`) and disables `/docs`, `/redoc`, and `/openapi.json` (`docs_url=None`) so the internal API surface is not exposed on the local network.
- **[`app/sicherheit.py`](app/sicherheit.py)**
  - **`SicherheitsMiddleware`**: Implemented as a pure ASGI middleware (rather than Starlette's `BaseHTTPMiddleware`) so `/api/chat/stream` SSE responses stream unbuffered:
    1. **`host_erlaubt(host_kopf)`**: Parses IPv4/IPv6/hostname (`host_zerlegen()`) and allows only loopback (`localhost`, `127.0.0.1`, `::1`), RFC-1918 private networks, Tailscale (`100.64.0.0/10` / `*.ts.net`), and configured `ERLAUBTE_HOSTS`. Any other host receives `HTTP 400` (blocks DNS-rebinding attacks).
    2. **`herkunft_erlaubt(scope)`**: Blocks cross-site browser requests (`Sec-Fetch-Site: cross-site` or `same-site`, or a mismatched `Origin` header) on `/api/*`, `/health`, `/ping`, and `/status` with `HTTP 403`.
    3. **`SICHERHEITS_KOEPFE`**: Attaches strict `Content-Security-Policy` (`default-src 'self'`), `Cross-Origin-Resource-Policy: same-origin`, `X-Frame-Options: DENY`, and `X-Content-Type-Options: nosniff` to every response.
    4. **`schluessel_einsetzen(html_text, schluessel)`** & **`client_ist_loopback(scope)`**: Injects the API key into `<meta name="agent-schluessel">` **only** when `index.html` is requested directly from a loopback address (`127.0.0.1` / `::1`), never trusting `X-Forwarded-For`.

---

### 2. HTTP Routers (`app/router/`)

- **[`app/router/chat.py`](app/router/chat.py)**
  - **`POST /api/chat` & `POST /api/chat/stream`**: Main chat endpoints. Every incoming turn runs through:
    1. **Boundary & Task Detection**: Checks `stoesst_an_grenze(message)` and `ist_auftrag(message)` (plus `_wirkt_wie_aufgabe()` cost gate). If the request requires terminal/git/code/system changes, it delegates to `chat_routing.route_auftrag()`.
    2. **Transient Image Continuity (`_bild_cache`)**: Keeps the most recently viewed image (`data_url` + `pfad`) in RAM for 10 minutes (`_BILD_CACHE_DAUER_S = 600`) scoped to a single `conversation_id`, so follow-up questions (*"What else is in the background?"*) work without re-fetching from storage. Cleared automatically via `_bild_cache_verwerfen()` on conversation switch.
    3. **Streaming Tool Loop**: Invokes `werkzeug_schleife.laufe()` and emits Server-Sent Events (`delta`, `status`, `sources`, `bild`, `done`).
  - **`GET /api/conversations` & `GET /api/conversations/{id}`**: Returns persistent conversation histories. Assistant messages that surfaced a photo include `bild_pfad` (path only, never raw image bytes in JSON) so the UI can reload previews after a browser refresh.
  - **`DELETE /api/chat/letzte-runde`**: Intentionally locked (`entfernt: false`) to enforce strict **append-only** conversation histories.
- **[`app/router/memory.py`](app/router/memory.py)**
  - **`GET /api/memory`**, **`POST /api/memory`**, **`DELETE /api/memory/{id}`**: Inspect, manually add, or remove individual long-term memories.
  - **`POST /api/memory/wiederholungen?ausfuehren=false`**: Scans for duplicate facts (`ausfuehren=false` runs as a safe dry-run preview by default).
  - **`POST /api/memory/vektoren`**: Backfills vector embeddings for memories created while offline.
- **[`app/router/llm_models.py`](app/router/llm_models.py)**
  - **`GET /api/models`**: Fetches the live OpenRouter model catalog, filters for tool-capable models (`modelle_use.py`), and enriches entries with curated German explanations (`modelle_de.py`), token pricing, context window size, EU hosting indicators, and training/retention policies.
  - **`GET /api/models/{id}/details`**: Queries per-provider zero-data-retention (ZDR) and privacy profiles.
- **[`app/router/selbsttest.py`](app/router/selbsttest.py)**
  - **`GET /api/selbsttest`**: Mobile-first system diagnostic endpoint. Inspects git `HEAD`, read-only SQLite archive (`~/archiv_index.db`, `mode=ro` with a 3 s timeout), `hermes_inbox_daemon.py` PID and tail of `daemon.log` (truncated to `AUSZUG_LAENGE = 200` characters so secrets can never leak in a screenshot), memory count, STT model chain, and pCloud quota (8 s timeout, masked email). Guaranteed never to return `HTTP 500`.
- **[`app/router/auth.py`](app/router/auth.py)**
  - **`require_api_key`**: Validates `X-API-Key` header, `HttpOnly` session cookie, or query parameter using constant-time comparison (`secrets.compare_digest`).

---

### 3. Core Services (`app/services/`)

#### Tool Loop & Tool Registry
- **[`app/services/werkzeug_schleife.py`](app/services/werkzeug_schleife.py)**
  - **`laufe(erstellen, messages, ausfuehren, status_text, quellen_aus, max_runden=5, max_aufrufe=4)`**:
    - Streams model deltas from `erstellen(messages, tool_choice)`.
    - Reassembles streamed `tool_calls` by index and merges provider `reasoning_details` via `_denkteile_mischen()` so reasoning models accept multi-turn tool continuations.
    - Filters leaked DeepSeek `<｜DSML｜>` / `<|DSML|` markup via `_DsmlFilter`. If DSML appears before any visible text was emitted, raises `DsmlAlsText` so the caller can cleanly fall back to a non-tool call.
    - Executes up to `MAX_AUFRUFE_JE_RUNDE = 4` tools per round, yields concrete `{"status": ...}` and `{"werkzeug": ...}` telemetry events, attaches up to `MAX_BILDER_JE_RUNDE = 3` loaded images as multimodal user content for the next round, and forces a final response on round `MAX_RUNDEN = 5` with `tool_choice="none"`.
- **[`app/services/werkzeuge.py`](app/services/werkzeuge.py)**
  - **`REGISTER`**: Defines all 13 tools available to the model:
    | Tool Name | Mode | Purpose |
    |---|---|---|
    | `dateien_suchen` | Read | Searches phone files (camera photos, screenshots, PDFs, docs) by filename, year, date, or category |
    | `datei_ansehen` | Read | Reads document text or loads an image into the vision context (`realpath`-checked against path traversal) |
    | `archiv_suchen` | Read | Hybrid search (FTS5 + vector) over archived ChatGPT, Claude, Gemini, and WhatsApp conversations |
    | `notizen_suchen` | Read | Searches personal notes on people and stories attached to photo events |
    | `erinnerungen_suchen` | Read | Queries the long-term memory store (`memory_store.json`) |
    | `fotos_uebersicht` | Read | Lists sorted photo events by year, category, or keyword |
    | `fotos_mit_person` | Read | Finds photos/videos containing a confirmed person from the face catalog |
    | `personen_liste` | Read | Lists all known people and their relationship roles |
    | `person_auskunft` | Read | Summarizes everything known about a person (relationship, notes, birthday, photo count, shared events) |
    | `wer_war_wann` | Read | Cross-references photos and chats to show who was present on a specific date (`YYYY-MM-DD`) |
    | `web_suche` | Read (Guarded) | Searches the web via OpenRouter after passing `websuche_schutz.py` (blocks private contact/person names) |
    | `erinnerung_speichern` | Write (Data care) | Saves or updates a long-term fact/appointment/state in `memory_store.json` |
    | `erinnerung_loeschen` | Write (Data care) | Deletes a specific memory by `memory_id` |
    | `person_profil_aendern` | Write (Data care) | Updates a person's birthday, phone numbers, relationship, or notes (syncs with contact store) |
    | `notiz_speichern` | Write (Data care) | Appends a personal note or story to a photo event (`geschichten.jsonl`) |
  - **`status_text(name, argumente)` & `argument_detail(name, argumente)`**: Formats live UI status lines including the actual tool arguments (e.g., `🔧 durchsucht das Gesprächsarchiv (Thema „Urlaub 2022“) …`).
  - **`pruefe_register()`**: Verifies that every OpenAI function schema in `schemata()` has a matching, callable entry in `REGISTER` and vice versa.
  - **`ausfuehren(name, argumente_json)`**: Never raises exceptions into the loop; catches invalid JSON or service errors and returns an honest `Ergebnis(ok=False)` message. Explicitly intercepts hallucinated `hermes` tool calls with a clear instruction that Hermes routing happens in the backend prior to the model.

#### Capability Boundaries, Hermes Routing & Model Selection
- **[`app/services/faehigkeiten.py`](app/services/faehigkeiten.py)**
  - **`FAEHIGKEITEN`** & **`GRENZE_MARKER`**: Declarative definition of what the agent can do (`kann`) vs. what requires Hermes (`kann_nicht`: `terminal`, `dateien_schreiben`, `tool_install`, `git`, `system_zugriff`).
  - **`stoesst_an_grenze(text)`**: Word-boundary regex matcher (`\b...\b`, preventing false positives like `"git"` in `"digital"` or `"run"` in `"darunter"`). Suppresses delegation when `_DATEI_LESE_SIGNALE` (reading files) or `_PERSOENLICHE_DATEN_SIGNALE` (editing contacts/notes/memories without system keywords) are present.
  - **`faehigkeits_block()`**: Generates the system-prompt section explaining the agent's exact capabilities and boundaries.
- **[`app/services/chat_routing.py`](app/services/chat_routing.py)**
  - **`route_auftrag(...)`**: Dispatches engineering tasks to the workstation:
    - **Track A (`pc`)**: Direct HTTP call to the PC gateway when the workstation is reachable on LAN/Tailscale.
    - **Track B (`buch`)**: Queues the task in `auftrag_service` with an honest status explanation (`bereit_reply_text()`) when offline.
    - *(Note: Track C in the code was an early offline prototype for spawning a local Hermes process in Termux that was never used productively and has been stepped down).*
- **[`app/services/modell_router.py`](app/services/modell_router.py)**
  - **`erkenne_kategorie(frage)`**: Classifies prompts into `BILDER`, `EMOTIONAL`, `ERINNERUNG`, `CODING`, `KOMPLEX`, `ALLTAG`, or `SCHNELL`.
  - **`modell_fuer(kategorie, aktuelles_modell)`**: Maps categories to OpenRouter models; in daily practice on the mobile agent, **DeepSeek V4.1 Flash** serves as the universal fast default, dynamically engaging **Gemini Flash** only when images are provided (`ist_vision_faehig()`). Heavy models are reserved for workstation development via OrbitDesk.

#### Memory, Context, LLM & Privacy
- **[`app/services/memory_service.py`](app/services/memory_service.py)**
  - **`_ist_korrektur_statt_wiederholung(alt, neu)`**: Compares non-stopwords (`FUELLWOERTER`). If two facts have high overall similarity (`>= 0.90`) but differ in substantive words (names, numbers, dates), classifies the new fact as a **correction** rather than a duplicate: the new text becomes active and the old text is preserved in `history`.
  - **`retrieve_relevant_memories(query, top_k=8)`**: Combines vector similarity (`openrouter_vektor`) and word overlap with temporal bonuses (`TERMIN_BONUS_NAH = 0.30` for events within 14 days) and gentle age decay (`ALTER_FREI_TAGE = 90`, max penalty `0.10`).
- **[`app/services/llm_service.py`](app/services/llm_service.py)**
  - **`transcribe(audio_bytes, filename)`**: Runs the 3-stage OpenRouter speech-to-text cascade (`microsoft/mai-transcribe-2` → `microsoft/mai-transcribe-1.5` → `openai/whisper-large-v3` with custom German vocabulary `WHISPER_VOKABULAR`).
  - **`polish_text(raw_text)`**: Polishes dictated transcripts via `gemini-2.5-flash` → `gemini-3.5-flash-lite` → `gemini-2.5-flash-lite` while preserving form of address (`Du`/`Sie`), speech act, and technical terms, wrapped in `PIIShield` pre-flight masking.
  - **`fehlertext(err)`**: Sanitizes OpenRouter error messages and strips internal key hashes (`keys/<hash>`) before returning errors to the UI.
- **[`app/services/websuche_schutz.py`](app/services/websuche_schutz.py)**
  - **`bestand_bauen(personen, kontakte)`**, **`enthaelt_namen(text, bestand, freigaben)`**, **`freigaben(nachricht, bestand)`**: Normalizes German umlauts and genitive endings to block any web search containing names from the personal photo catalog or contact book, unless the user explicitly requested a web search for a public namesake.
- **[`app/services/chat_verlauf.py`](app/services/chat_verlauf.py)** & **[`app/db/chroma_client.py`](app/db/chroma_client.py)**
  - Thread-safe, atomic JSON persistence (`conversations.json` and `memory_store.json`) using temporary files, `os.replace()`, and `.bak` fallback recovery.

---

## Running the Test Suite

From inside `backend/`:

```powershell
pytest -q tests    # 57 passed
```

| Test File | What It Verifies |
|---|---|
| [`tests/test_faehigkeiten.py`](tests/test_faehigkeiten.py) | Capability manifest structure (`kann` vs. `kann_nicht`) and core boundary detection (`stoesst_an_grenze`) |
| [`tests/test_faehigkeiten_grenzfaelle.py`](tests/test_faehigkeiten_grenzfaelle.py) | Regex word-boundary edge cases (e.g. `"digital"` vs. `"git"`, `"darunter"` vs. `"run"`, read vs. write signals, empty/case-insensitive inputs) |
| [`tests/test_faehigkeiten_prompt.py`](tests/test_faehigkeiten_prompt.py) | System prompt capability block generation (`faehigkeits_block()`) and honesty rules |
| [`tests/test_gedaechtnis_qualitaet.py`](tests/test_gedaechtnis_qualitaet.py) | Memory deduplication vs. fact correction (`history` preservation), temporal event boosting, gentle decay after 90 days, and Top-K selection |
| [`tests/test_chat_verlauf_service.py`](tests/test_chat_verlauf_service.py) | Conversation persistence, atomic writes, backup recovery on corrupted JSON, and append-only invariants |

← [Back to Personal AI Agent overview](../README.md)
