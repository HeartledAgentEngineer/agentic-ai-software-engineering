"""typeFREE — Azure Edition: FastAPI service for dictation (STT + smoothing).

Pipeline: audio upload → Azure AI Speech (F0) → optional LLM smoothing
(Azure Foundry / GitHub Models / OpenRouter) → plain text.

Start locally (from ``03_Azure_Projects``)::

    ./.venv/Scripts/python.exe -m uvicorn TypeFree.server.main:app --port 8101

Container: see ``TypeFree/server/Dockerfile`` (build context = ``03_Azure_Projects``).

AI-102 mapping: "Implement a speech solution" (speech to text) and
"Implement generative AI solutions" (text optimisation).
"""

from __future__ import annotations

import sys
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

PORTFOLIO_ROOT = Path(__file__).resolve().parents[2]
if str(PORTFOLIO_ROOT) not in sys.path:
    sys.path.insert(0, str(PORTFOLIO_ROOT))

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from shared_core import api_common
from shared_core import azure_free_core as core

VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    core.load_env()  # liest shared_core/.env; fehlt sie (Container), gelten die -e-Variablen
    yield


app = FastAPI(
    title="typeFREE — Azure Edition",
    version=VERSION,
    description="Diktat-Service: Audio → Azure AI Speech (F0) → optionale Glättung → Text.",
    lifespan=lifespan,
)


class GlaettungsAnfrage(BaseModel):
    text: str = Field(..., min_length=1)
    context: str = ""


class GlaettungsAntwort(BaseModel):
    text: str
    provider: str
    model: str
    ausweichweg: bool


class DiktatAntwort(BaseModel):
    rohtext: str
    text: str
    geglaettet: bool
    provider: str | None = None
    model: str | None = None
    ausweichweg: bool = False
    hinweis: str | None = None


async def _zu_tempdatei(audio: UploadFile) -> Path:
    daten = await audio.read()
    if not daten:
        raise HTTPException(status_code=422, detail="Audiodatei ist leer.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as datei:
        datei.write(daten)
        return Path(datei.name)


def _tempdatei_entfernen(pfad: Path) -> None:
    """Windows: das Speech-SDK hält die WAV nach dem Erkennen kurz offen (WinError 32).

    Deshalb mit kurzen Pausen erneut versuchen; bleibt die Datei gesperrt, wird das
    geloggt und Windows räumt den Temp-Ordner später auf.
    """
    for _ in range(30):
        try:
            pfad.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(0.1)
    core.LOGGER.warning("Temp-Datei bleibt vorerst gesperrt: %s", pfad)


@app.get("/healthz")
def healthz() -> dict:
    """Dienststatus ohne Geheimnisse (Booleans, Modus, verfügbare LLM-Wege)."""
    return api_common.health_payload("typefree-azure", VERSION)


@app.post("/api/v1/transcribe", dependencies=[Depends(api_common.require_token)])
async def transcribe(audio: UploadFile = File(...), language: str = Form("de-DE")) -> dict:
    """Nur Spracherkennung (Rohtext ohne Glättung)."""
    pfad = await _zu_tempdatei(audio)
    try:
        text = await run_in_threadpool(core.transcribe_audio_azure, pfad, language=language)
    except core.AzureFreeCoreError as exc:
        raise api_common.azure_fehler(exc) from exc
    finally:
        _tempdatei_entfernen(pfad)
    return {"text": text}


@app.post("/api/v1/dictate", dependencies=[Depends(api_common.require_token)])
async def dictate(
    audio: UploadFile = File(...),
    context: str = Form(""),
    language: str = Form("de-DE"),
) -> DiktatAntwort:
    """Der komplette Diktat-Weg: Erkennung + Glättung (Glättung ist optional)."""
    pfad = await _zu_tempdatei(audio)
    try:
        rohtext = await run_in_threadpool(core.transcribe_audio_azure, pfad, language=language)
    except core.AzureFreeCoreError as exc:
        raise api_common.azure_fehler(exc) from exc
    finally:
        _tempdatei_entfernen(pfad)
    if not rohtext:
        return DiktatAntwort(rohtext="", text="", geglaettet=False, hinweis="Keine Sprache erkannt.")
    try:
        ergebnis = await core.smooth_dictation_text(rohtext, context=context)
    except core.AzureFreeCoreError as exc:
        return DiktatAntwort(
            rohtext=rohtext, text=rohtext, geglaettet=False, hinweis=f"Glättung nicht möglich: {exc}"
        )
    return DiktatAntwort(
        rohtext=rohtext,
        text=ergebnis.text,
        geglaettet=True,
        provider=ergebnis.provider,
        model=ergebnis.model,
        ausweichweg=ergebnis.is_fallback,
    )


@app.post("/api/v1/smooth", dependencies=[Depends(api_common.require_token)])
async def smooth(anfrage: GlaettungsAnfrage) -> GlaettungsAntwort:
    """Nur die Glättung (ohne Audio)."""
    try:
        ergebnis = await core.smooth_dictation_text(anfrage.text, context=anfrage.context)
    except core.AzureFreeCoreError as exc:
        raise api_common.azure_fehler(exc) from exc
    return GlaettungsAntwort(
        text=ergebnis.text,
        provider=ergebnis.provider,
        model=ergebnis.model,
        ausweichweg=ergebnis.is_fallback,
    )
