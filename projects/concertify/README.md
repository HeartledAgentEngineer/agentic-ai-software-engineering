# Concertify

A local web app that turns the artists I follow on Spotify into playlists for their upcoming concerts. It imports
the follows, searches concerts in configurable cities and festival line-ups, and builds each playlist from real
live setlists (setlist.fm).

**Stack:** Python · Flask (blueprints) · Server-Sent Events · SQLite · Spotify, Ticketmaster, setlist.fm, Tavily
and Gemini APIs · pytest

## Architecture & Evolution

Concertify started in April 2026 as a fast-moving prototype with root-level scripts (`app.py`, `main.py`, and API client modules `spotify_client.py`, `setlist_client.py`, `ticketmaster_client.py`, `festival_scraper.py`, `web_concert_finder.py`). When that initial layout grew harder to test, I introduced a **5-layer architecture** alongside the existing entry point using the [Dual Engineering System](docs/dual_engineering_system.md) (an *Architect* role for clean boundaries and a *Guardian* role for risk and regression checks):

| Layer | Folder / Files | Responsibility |
|---|---|---|
| Domain | `domain/` | plain data models (artist, concert, setlist, song), no framework |
| Repositories | `repositories/`, `db/` | persistence behind interfaces: a JSON file for concert data, SQLite for setlist snapshots |
| Services | `services/` | logic: playlist import/save, setlists, song state, support-act order, concert search |
| Routes | `routes/` | Flask blueprints (HTTP only) registered into `app.py` |
| External & Clients | `external/`, `*_client.py` | third-party API clients and quota guards (e.g. `external/setlistfm_quota.py`) |

Every extracted layer has its own mirrored unit and integration test suite under `tests/`.

## Decisions

- **Long searches as a stream.** The concert search can take minutes because of API quotas. It runs as a
  subprocess, and its output reaches the browser line by line as Server-Sent Events. If the tab is closed, the
  server catches `GeneratorExit` and terminates the subprocess.
- **Atomic writes.** Web requests and the background search share one JSON file. Every write goes through one
  function: thread lock, write to a temporary file, then `Path.replace()`.
- **Count the quota instead of hoping.** setlist.fm allows 1,440 requests per day and blocks the IP for 24 hours
  when exceeded. `external/setlistfm_quota.py` counts every call and stops at 1,000, so the UI always keeps a
  reserve; on `429` the client honours the retry header; fetched setlists are cached.
- **Distance filter against false positives.** Tour pages list dates worldwide. A date is only accepted if it
  appears within 400 characters of a keyword for the searched city (`_extract_date_near_city`).
- **Local-only single-user scope.** The server binds to `127.0.0.1:5000` by default (`CONCERTIFY_HOST`) and rejects cross-origin `POST`/`DELETE` requests; the SQLite snapshot table carries a `user_id` (default `local`) from the start.

## Run it

```powershell
pip install -r requirements.txt
# create .env with SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI,
# TICKETMASTER_API_KEY, TAVILY_API_KEY, GEMINI_API_KEY, CONCERT_CITIES, ACTIVE_FESTIVALS
python app.py      # http://127.0.0.1:5000
pytest tests/      # 193 passed, 2 skipped; also run in CI
```

← [Back to overview](../../README.md)
