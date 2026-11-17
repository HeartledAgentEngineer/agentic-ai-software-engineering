"""readFREE (Vorlesen): Server und Client offline — Azure-SDK und HTTP als Attrappen."""

from __future__ import annotations

import base64
import io

import httpx
import pytest
from fastapi.testclient import TestClient

from shared_core import azure_free_core as core
from ReadFree.client import app as client_app
from ReadFree.server import main as readfree

WAV_ATTRAppe = b"RIFF$\x00\x00\x00WAVEfmt " + b"\x00" * 16
PNG_ATTRAppe = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

# Fachverhalten bei lokal geöffnetem Server; die Anmeldung prüft tests/test_auth.py.
pytestmark = pytest.mark.usefixtures("lokal_offen")


class Aufnahme:
    """Hält den letzten httpx.post-Aufruf eines Clients fest (statt Netz)."""

    def __init__(self, antwort: httpx.Response):
        self.antwort = antwort
        self.url = None
        self.kwargs: dict = {}

    def __call__(self, url, **kwargs):
        self.url, self.kwargs = url, kwargs
        return self.antwort


# ── Server ───────────────────────────────────────────────────────────────────


def test_readfree_speak_liefert_wav(monkeypatch):
    monkeypatch.setattr(core, "speak_text_azure_ssml", lambda ssml, play=False, **kw: b"RIFF" + b"\x00" * 4000)
    with TestClient(readfree.app) as client:
        antwort = client.post("/api/v1/speak", json={"text": "Hallo", "stimme": "de-DE-ConradNeural"})
    assert antwort.status_code == 200
    assert antwort.headers["content-type"].startswith("audio/wav")
    assert len(antwort.content) > 2000
    assert antwort.headers["x-stimme"] == "de-DE-ConradNeural"


def test_readfree_lehnt_ungueltiges_tempo_ab():
    with TestClient(readfree.app) as client:
        antwort = client.post("/api/v1/speak", json={"text": "Hallo", "tempo": "schnell"})
    assert antwort.status_code == 422


def test_readfree_stimmenliste():
    with TestClient(readfree.app) as client:
        antwort = client.get("/api/v1/stimmen")
    assert antwort.status_code == 200
    stimmen = antwort.json()
    assert any(eintrag["name"] == "de-DE-ConradNeural" for eintrag in stimmen)


# ── Client ───────────────────────────────────────────────────────────────────


def test_client_schickt_text_und_speichert_wav(monkeypatch, tmp_path):
    ziel = tmp_path / "aus.wav"
    post = Aufnahme(httpx.Response(200, content=WAV_ATTRAppe, headers={"X-Stimme": "de-DE-ConradNeural"}))
    monkeypatch.setattr(client_app.httpx, "post", post)
    assert client_app.main(["Hallo Welt", "--nicht-abspielen", "--ausgabe", str(ziel), "--tempo", "+15%"]) == 0
    assert post.url.endswith("/api/v1/speak")
    assert post.kwargs["json"] == {"text": "Hallo Welt", "stimme": "de-DE-ConradNeural", "tempo": "+15%"}
    assert ziel.read_bytes() == WAV_ATTRAppe


def test_client_ohne_text_bricht_ab(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("   "))
    assert client_app.main([]) == 2


def test_client_server_nicht_erreichbar(monkeypatch):
    def kaputt(url, **kw):
        raise httpx.ConnectError("weg")

    monkeypatch.setattr(client_app.httpx, "post", kaputt)
    assert client_app.main(["Hallo", "--nicht-abspielen"]) == 2
