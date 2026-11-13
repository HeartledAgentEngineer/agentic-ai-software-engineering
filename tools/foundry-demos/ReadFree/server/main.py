"""readFREE — Azure Edition: FastAPI service for reading text aloud (neural TTS + SSML).

Start locally (from ``03_Azure_Projects``)::

    ./.venv/Scripts/python.exe -m uvicorn ReadFree.server.main:app --port 8102

Container: see ``ReadFree/server/Dockerfile``.

AI-102 mapping: "Implement a speech solution" (speech synthesis, SSML prosody).
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

PORTFOLIO_ROOT = Path(__file__).resolve().parents[2]
if str(PORTFOLIO_ROOT) not in sys.path:
    sys.path.insert(0, str(PORTFOLIO_ROOT))

from fastapi import Depends, FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from shared_core import api_common
from shared_core import azure_free_core as core

VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    core.load_env()
    yield


app = FastAPI(
    title="readFREE — Azure Edition",
    version=VERSION,
    description="Vorlese-Service: Text → Azure Neural TTS (F0) mit SSML → WAV.",
    lifespan=lifespan,
)


class SprechAnfrage(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)
    stimme: str = core.DEFAULT_SPEECH_VOICE
    tempo: str = "+0%"
    tonhoehe: str | None = None


#: Deutsche Neural-Stimmen, die das Portfolio anbietet (SSML-Voice-Namen).
STIMMEN = [
    {"name": "de-DE-ConradNeural", "charakter": "männlich, neutral (Vorgabe)"},
    {"name": "de-DE-KillianNeural", "charakter": "männlich, jünger"},
    {"name": "de-DE-FlorianMultilingualNeural", "charakter": "männlich, mehrsprachig (Deutsch/Englisch)"},
    {"name": "de-AT-JonasNeural", "charakter": "männlich, österreichisch"},
    {"name": "de-CH-JanNeural", "charakter": "männlich, schweizerisch"},
]


@app.get("/healthz")
def healthz() -> dict:
    return api_common.health_payload("readfree-azure", VERSION)


@app.get("/api/v1/stimmen")
def stimmen() -> list[dict]:
    """Feste Auswahl deutscher Neural-Stimmen (kein Azure-Aufruf nötig)."""
    return STIMMEN


@app.post("/api/v1/speak", dependencies=[Depends(api_common.require_token)])
async def speak(anfrage: SprechAnfrage) -> Response:
    """Text als WAV-Audio (24 kHz/16 Bit/mono) zurückgeben."""
    try:
        ssml = core.build_ssml(
            anfrage.text, voice=anfrage.stimme, rate=anfrage.tempo, pitch=anfrage.tonhoehe
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        audio = await run_in_threadpool(core.speak_text_azure_ssml, ssml=ssml, play=False)
    except core.AzureFreeCoreError as exc:
        raise api_common.azure_fehler(exc) from exc
    if not audio:
        raise HTTPException(status_code=502, detail="Keine Audiodaten von Azure erhalten.")
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"X-Stimme": anfrage.stimme, "Content-Disposition": 'inline; filename="readfree.wav"'},
    )
