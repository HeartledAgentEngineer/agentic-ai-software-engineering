# Personal AI Agent — Mobile-First PWA (`frontend/`)

This directory contains the browser client of the Personal AI Agent. It is built with **zero external JavaScript frameworks or CDNs** (plain HTML5, CSS3, and vanilla ES2022) and runs as an installable **Progressive Web App (PWA)** on Android (served directly by the local FastAPI backend in Termux) and on desktop browsers.

---

## Files in `frontend/`

| File | Responsibility |
|---|---|
| [`index.html`](index.html) | Single-page application shell: header controls, dual-chat switcher (`💬` / `</>`), streaming speed menu, message container, reply quote preview, voice status bar (`#mic-status`), and modal sheets (Memory, Self-Test, Model Selector) |
| [`app.js`](app.js) | Complete client logic: same-origin API key handling, SSE stream consumer, dual-chat state management, collapsible thought bubbles (`🧠`), AudioWorklet PCM/WAV recording, Web Audio / SpeechSynthesis TTS, and model filter UI |
| [`style.css`](style.css) | Dark-mode mobile-first layout (`100dvh` + `visualViewport` keyboard resize compensation), chat bubble styling, collapsible thought strips, and sheet animations |
| [`sw.js`](sw.js) | Service Worker for PWA installability (intentionally does **not** cache `index.html` so loopback API key injection stays fresh and never persists in cache storage) |
| [`manifest.json`](manifest.json) | Web App Manifest (`display: standalone`, dark theme `#0f0f1a`, app icons `icon-192.png` & `icon-512.png`) |

*(In the full private workspace, additional standalone modules `erzaehlen.js`, `bild_beschreibung.js`, and `gruppen_quiz.js` mount into the header buttons `📖` and `👥` for the photo storytelling slideshow and face-group naming quiz.)*

---

## Key Frontend Engineering Details

### 1. Same-Origin Security & Zero-Config Authentication (`app.js`)
- **Fixed Origin (`API_BASE = location.origin`)**: Earlier prototypes allowed overriding `api_base` via `localStorage`, which meant any injected script could redirect requests (including the API key) to an external host. `app.js` deletes any legacy `localStorage.api_base` entry on startup and strictly binds to `location.origin`.
- **Loopback Meta-Tag Injection**: The backend injects the API key into `<meta name="agent-schluessel">` when serving `index.html` to a loopback client (`127.0.0.1` / `::1`). A single `window.fetch` wrapper in `app.js` attaches `X-API-Key` only to same-origin `/api/*` requests.

### 2. Dual-Chat Architecture & Evolution to OrbitView (`conv_main` vs. `conv_code`)
- The header button `#codechat-btn` toggles between two persistent conversation contexts:
  - **`💬` Main Assistant (`conv_main`)**: Everyday personal chat, memory lookup, archive search, and photo/note tools.
  - **`</>` Hermes Coding Chat (`conv_code`)**: Originally built as an experimental on-device coding channel routing to a local Termux session (`hermes_code` in `tmux`) for vacation programming without a PC. As heavy coding proved impractical on phone hardware, this slot is evolving into a direct **Live Voice Mode** and mobile **OrbitView (MCP-connected OrbitDesk)** interface.
- An explicit status banner (`#chat-aktuell`) above the message list always displays which conversation is currently active and persists the selection across page reloads.

### 3. Live SSE Streaming, Collapsible Thought Bubbles & Zero-Jump Scroll (`app.js`)
- **Adjustable Stream Pacing (`#stream-menu`)**: Users read at different speeds on a phone screen. The gear menu offers four pacing presets (`Schnell` 20 ms, `Normal` 120 ms, `Entspannt` 400 ms, `Sehr langsam` 1000 ms) that buffer incoming SSE chunks into smooth reading steps.
- **No Empty Placeholder Bubbles (`zeigeBlaseMitText()`)**: Live assistant and thought bubbles stay hidden (`hidden`) until the first visible character arrives (`data-lazy-zeit`), preventing empty timestamp shells while tools or local Hermes jobs initialize.
- **Auto-Collapsing Thought Bubbles (`klappeGedankeEin()`) with Zero-Jump Scroll (`mitGehaltenerScrollposition()`)**:
  - When a `🧠 Gedanke` (reasoning/Hermes thought) bubble finishes streaming, it stays open for 2.5 seconds of reading time and then collapses into a compact one-line summary (`Uhrzeit · 🧠 erste Zeile…`). Tapping the strip expands it permanently (`data-gedanke-manuell`).
  - To prevent the chat viewport from jumping when a tall thought bubble collapses above the current reading position, `mitGehaltenerScrollposition()` tracks the exact height delta across animation frames and compensates `scrollTop` by the exact pixel difference (verified in headless browser tests with `0 px` visual jump).

### 4. Mobile Voice Pipeline: AudioWorklet WAV + Visible State Machine
- **Why PCM/WAV Instead of `MediaRecorder`**: Android browser `MediaRecorder` outputs WebM/Opus chunks that caused HTTP 400 errors on downstream transcription endpoints. `app.js` records raw PCM audio in memory via Web Audio API and encodes a clean 16-bit WAV buffer in the browser before posting to `/api/sprache/transkript`.
- **Visible Mobile Status (`#mic-status`)**: Because button tooltips are invisible on touchscreens, a dedicated status bar above the input field transitions through four explicit states:
  1. `Mikrofon offen` (stream initialized)
  2. `hört zu` (first non-silent audio frame received)
  3. `denkt nach` (transcribing & polishing via OpenRouter)
  4. `spricht` (TTS audio playback active)

### 5. Interactive OpenRouter Model Catalog & Privacy Filters
- Tapping the model pill opens a searchable bottom sheet backed by `GET /api/models`:
  - **Combinable Filter Chips (AND logic)**: `🔧 Werkzeuge` (tool-use support), `🖼️ Bilder` (vision), `🧠 Reasoning`, `🇪🇺 EU`, `🔒 Kein Training` (zero data retention / no prompt training), `⚡ Schnell`, `💰 Günstig`.
  - **Per-Provider Privacy Inspection**: Tapping a model queries `GET /api/models/{id}/details` to display exact input/output/cache costs, context window length, German capability notes, and provider data-retention policies.

← [Back to Personal AI Agent overview](../README.md)
