# RAG knowledge base

A local knowledge base: documents are split into chunks, embedded and stored in PostgreSQL with pgvector. Questions
are answered from the best chunks, with sources in the answer.

**Stack:** Python · FastAPI · PostgreSQL + pgvector (Supabase) · Mistral embeddings (1024-d) · answer chain:
local LLM → Gemini → Mistral · pywebview desktop shell

## How it evolved

1. **n8n cloud workflow** as a visual design tool: fast to wire up, but running cloud costs and a no-code server
   in the middle.
2. **Local Python pipeline:** same logic, no platform fees, and full control over chunking and ranking.

## How it works

- `init_db.py` creates the vector table, a full-text index and the SQL function `hybrid_search`.
- `ingest.py` splits documents into chunks and stores them with their embeddings.
- `query_db.py` searches and generates the answer.
- `main.py` / `desktop_app.py` provide the API and a small desktop window around `static/index.html`.

**Hybrid search with reciprocal rank fusion.** `hybrid_search` ranks every chunk twice, by vector similarity and
by German full-text rank (`ts_rank_cd`), and combines both with `1 / (k + rank)`, `k = 60`. A chunk that is good in
both lists wins, even if it is first in neither.

**Answer chain.** `generate_answer` tries a local LLM first (if configured), then Gemini, then Mistral. Only if all
three fail does it raise an error.

**Chunking under test.** `chunking.py` holds the paragraph chunker without any API or database import, so
`tests/test_chunking.py` runs offline in CI: paragraph boundaries, sentence ends instead of commas for oversized
paragraphs, and page markers. Its first run found a real bug — a chunk was tagged with the page of the *next*
paragraph when a new page began there, so source citations pointed one page too far. Now each chunk keeps the
page it starts on.

**Query path under test.** `tests/test_query_db.py` runs `query_db.py` against fakes for the network and the
database: it stops before any network call when a key is missing, builds the `hybrid_search` call and the result
rows, labels each context chunk with its source (course → module before file name), and walks the fallback chain
local model → Gemini → Mistral. Its first run found a real bug: the Mistral embedding call was the only network
call without a timeout, so a hanging API froze the whole query. It now has 30 s like the others.

`test_embeddings.py` is a separate, manual plausibility check against the live API: a related pair (dog/cat) must
come out closer than an unrelated pair (dog/car).

## Run it

```powershell
pip install -r requirements.txt
# .env: database URL and API keys
python init_db.py
python ingest.py <file>
python main.py
python -m pytest -q tests    # offline, no keys needed
```

← [Back to overview](../../README.md)
