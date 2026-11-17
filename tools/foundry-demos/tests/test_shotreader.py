"""shotReader (Screenshot → OCR → Vorlesen): Server und Client offline — Attrappen statt Azure/HTTP."""

from __future__ import annotations

import base64
import io

import httpx
import pytest
from fastapi.testclient import TestClient

from shared_core import azure_free_core as core
from shotReader.client import app as client_app
from shotReader.server import main as shotreader

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


def test_shotreader_ocr_liefert_text(monkeypatch):
    monkeypatch.setattr(core, "extract_text_from_image_azure", lambda daten, **kw: "Erste Zeile\nZweite")
    with TestClient(shotreader.app) as client:
        antwort = client.post("/api/v1/ocr", files={"bild": ("b.png", PNG_ATTRAppe, "image/png")})
    assert antwort.status_code == 200
    assert antwort.json()["text"].startswith("Erste Zeile")


def test_shotreader_ohne_text_kein_audio(monkeypatch):
    monkeypatch.setattr(core, "extract_text_from_image_azure", lambda daten, **kw: "")
    with TestClient(shotreader.app) as client:
        antwort = client.post("/api/v1/ocr-und-vorlesen", files={"bild": ("b.png", PNG_ATTRAppe, "image/png")})
    daten = antwort.json()
    assert antwort.status_code == 200
    assert daten["audio_base64"] is None
    assert "Kein Text" in daten["hinweis"]


def test_shotreader_ocr_und_vorlesen_mit_audio(monkeypatch):
    monkeypatch.setattr(core, "extract_text_from_image_azure", lambda daten, **kw: "Hallo Welt")
    monkeypatch.setattr(core, "speak_text_azure_ssml", lambda ssml, play=False, **kw: b"RIFF" + b"\x00" * 100)
    with TestClient(shotreader.app) as client:
        antwort = client.post(
            "/api/v1/ocr-und-vorlesen",
            files={"bild": ("b.png", PNG_ATTRAppe, "image/png")},
            data={"stimme": "de-DE-ConradNeural"},
        )
    daten = antwort.json()
    assert antwort.status_code == 200
    assert base64.b64decode(daten["audio_base64"]).startswith(b"RIFF")


# ── Client ───────────────────────────────────────────────────────────────────


def test_client_schickt_bild_und_speichert_audio(monkeypatch, tmp_path, capsys):
    bild = tmp_path / "s.png"
    bild.write_bytes(PNG_ATTRAppe)
    ziel = tmp_path / "s.wav"
    audio = base64.b64encode(WAV_ATTRAppe).decode()
    post = Aufnahme(httpx.Response(200, json={"text": "Hallo Azure", "audio_base64": audio, "stimme": "x"}))
    monkeypatch.setattr(client_app.httpx, "post", post)
    assert client_app.main(["--bild", str(bild), "--nicht-abspielen", "--audio", str(ziel)]) == 0
    assert post.url.endswith("/api/v1/ocr-und-vorlesen")
    assert post.kwargs["files"]["bild"][1] == PNG_ATTRAppe
    assert ziel.read_bytes() == WAV_ATTRAppe
    assert "Hallo Azure" in capsys.readouterr().out


def test_client_ohne_text_kein_audio(monkeypatch, tmp_path):
    bild = tmp_path / "s.png"
    bild.write_bytes(PNG_ATTRAppe)
    antwort = httpx.Response(200, json={"text": "", "hinweis": "kein Text"})
    monkeypatch.setattr(client_app.httpx, "post", Aufnahme(antwort))
    assert client_app.main(["--bild", str(bild), "--nicht-abspielen"]) == 0
