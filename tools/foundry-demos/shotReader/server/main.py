"""shotReader — Azure Edition: FastAPI service for OCR + text-to-speech.

Pipeline: image upload → Azure AI Vision, Image Analysis Read (F0) → Azure
Neural TTS (F0) → text plus WAV audio.

Start locally (from ``03_Azure_Projects``)::

    ./.venv/Scripts/python.exe -m uvicorn shotReader.server.main:app --port 8103

Container: see ``shotReader/server/Dockerfile``.

AI-102 mapping: "Implement a computer vision solution" (optical character
recognition) and "Implement a speech solution" (synthesis).
"""

from __future__ import annotations

import base64
import sys
from contextlib import asynccontextmanager
from pathlib import Path

PORTFOLIO_ROOT = Path(__file__).resolve().parents[2]
if str(PORTFOLIO_ROOT) not in sys.path:
    sys.path.insert(0, str(PORTFOLIO_ROOT))

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from shared_core import api_common
from shared_core import azure_free_core as core

VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    core.load_env()
    yield


app = FastAPI(
    title="shotReader — Azure Edition",
    version=VERSION,
    description="Bild → Azure AI Vision Read (F0) → Text → Azure Neural TTS (F0) → WAV.",
    lifespan=lifespan,
)


class VorleseAntwort(BaseModel):
    text: str
    stimme: str
    audio_base64: str | None = None
    format: str = "wav"
    hinweis: str | None = None


async def _bilddaten(bild: UploadFile) -> bytes:
    daten = await bild.read()
    if not daten:
        raise HTTPException(status_code=422, detail="Bilddatei ist leer.")
    return daten


@app.get("/healthz")
def healthz() -> dict:
    return api_common.health_payload("shotreader-azure", VERSION)


@app.post("/api/v1/ocr", dependencies=[Depends(api_common.require_token)])
async def ocr(bild: UploadFile = File(...)) -> dict:
    """Nur Texterkennung (kein Vorlesen)."""
    daten = await _bilddaten(bild)
    try:
        text = await run_in_threadpool(core.extract_text_from_image_azure, daten)
    except core.AzureFreeCoreError as exc:
        raise api_common.azure_fehler(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"text": text}


@app.post("/api/v1/ocr-und-vorlesen", dependencies=[Depends(api_common.require_token)])
async def ocr_und_vorlesen(
    bild: UploadFile = File(...),
    stimme: str = Form(core.DEFAULT_SPEECH_VOICE),
    tempo: str = Form("+0%"),
) -> VorleseAntwort:
    """Texterkennung plus Sprachausgabe in einem Aufruf (Audio als Base64-WAV)."""
    daten = await _bilddaten(bild)
    try:
        text = await run_in_threadpool(core.extract_text_from_image_azure, daten)
    except core.AzureFreeCoreError as exc:
        raise api_common.azure_fehler(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not text.strip():
        return VorleseAntwort(text="", stimme=stimme, hinweis="Kein Text im Bild erkannt.")
    try:
        ssml = core.build_ssml(text, voice=stimme, rate=tempo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        audio = await run_in_threadpool(core.speak_text_azure_ssml, ssml=ssml, play=False)
    except core.AzureFreeCoreError as exc:
        raise api_common.azure_fehler(exc) from exc
    if not audio:
        raise HTTPException(status_code=502, detail="Keine Audiodaten von Azure erhalten.")
    return VorleseAntwort(
        text=text, stimme=stimme, audio_base64=base64.b64encode(audio).decode("ascii")
    )
