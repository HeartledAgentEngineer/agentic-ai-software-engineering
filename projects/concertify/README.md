# Concertify

A local web app that turns the artists I follow on Spotify into playlists for their upcoming concerts. It imports
the follows, searches concerts in configurable cities and festival line-ups, and builds each playlist from real
live setlists (setlist.fm).

**Stack:** Python · Flask (blueprints) · Server-Sent Events · SQLite · Spotify, Ticketmaster, setlist.fm, Tavily
and Gemini APIs · pytest

## Architecture & Structure

Concertify started in April 2026 as a fast-moving prototype and was structured into a **5-layer architecture** using the [Dual Engineering System](docs/dual_engineering_system.md) (an *Architect* role for clean boundaries and a *Guardian* role for risk and regression checks). At the project root sits only `app.py` (the Flask web entry point); all domain models, repositories, services, HTTP blueprints, and external API clients live in dedicated layers:

| Layer | Folder | Responsibility |
|---|---|---|
| Entry point | `app.py`, `templates/` | Flask web server (`127.0.0.1:5000`), SSE streaming endpoints, UI template |
| Domain | `domain/` | Plain data models (`artist.py`, `concert.py`, `setlist.py`, `song.py`, `saved_playlist.py`), no framework |
| Repositories | `repositories/`, `db/` | Persistence behind interfaces: `json_repo.py` for concert data, `snapshot_repository.py` + SQLite (`db/connection.py`) for setlist snapshots |
| Services | `services/` | Business logic & runners: playlist import/save, setlist & snapshot services, song state, support-act order & search, artist matcher, festival year rollover, and background runners (`fetch_data.py`, `main.py`, `preview_run.py`) |
| Routes | `routes/` | Flask blueprints (`playlists.py`, `songs.py`, `imports.py` under `/api/v2/...`) |
| External | `external/` | Third-party API clients (`spotify_client.py`, `setlist_client.py`, `ticketmaster_client.py`, `eventim_client.py`, `songkick_client.py`, `festival_client.py`, `rock_im_park.py`, `tavily_*`, `gemini_*`, `claude_*`, `serper_*`) and quota guard (`setlistfm_quota.py`) |
| Tests | `tests/` | Mirrored unit and integration test suites (`193 passed, 2 skipped`) |

## Decisions

- **Long searches as a stream.** The concert search can take minutes because of API quotas. It runs as a
  subprocess (`services/fetch_data.py`, `services/main.py`, `services/preview_run.py`), and its output reaches the browser line by line as Server-Sent Events. If the tab is closed, the
  server catches `GeneratorExit` and terminates the subprocess.
- **Atomic writes.** Web requests and the background search share one JSON file. Every write goes through one
  function: thread lock, write to a temporary file, then `Path.replace()`.
- **Count the quota instead of hoping.** setlist.fm allows 1,440 requests per day and blocks the IP for 24 hours
  when exceeded. `external/setlistfm_quota.py` counts every call and stops at 1,000, so the UI always keeps a
  reserve; on `429` the client honours the retry header; fetched setlists are cached.
- **Distance filter against false positives.** Tour pages list dates worldwide. A date is only accepted if it
  appears within 400 characters of a keyword for the searched city (`_extract_date_near_city`).
- **Local-only single-user scope.** The server binds to `127.0.0.1:5000` by default (`CONCERTIFY_HOST`), validates `Host`, `Sec-Fetch-Site`/`Sec-Fetch-Mode`, and local `Origin`/`Referer` headers on all API and stream endpoints (every route except `/`, `/health`, `/callback`, and `/static/*`), and verifies an OAuth `state` token plus HTML-escaped error messages on `/callback`; the SQLite snapshot table carries a `user_id` (default `local`) from the start.

## Run it

```powershell
pip install -r requirements.txt
# create .env with SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI,
# TICKETMASTER_API_KEY, TAVILY_API_KEY, GEMINI_API_KEY, CONCERT_CITIES, ACTIVE_FESTIVALS
python app.py      # http://127.0.0.1:5000
pytest tests/      # 193 passed, 2 skipped; also run in CI
```

← [Back to overview](../../README.md)
