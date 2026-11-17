"""typeFREE (Diktat): Server und Client offline — Azure-SDK und HTTP als Attrappen."""

from __future__ import annotations

import base64
import io

import httpx
import pytest
from fastapi.testclient import TestClient

from shared_core import azure_free_core as core
from TypeFree.client import app as client_app
from TypeFree.server import main as typefree

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


def test_typefree_transcribe_liefert_rohtext(monkeypatch):
    monkeypatch.setattr(core, "transcribe_audio_azure", lambda pfad, **kw: "Hallo aus Azure")
    with TestClient(typefree.app) as client:
        antwort = client.post("/api/v1/transcribe", files={"audio": ("probe.wav", WAV_ATTRAppe, "audio/wav")})
    assert antwort.status_code == 200
    assert antwort.json()["text"] == "Hallo aus Azure"


def test_typefree_transcribe_ohne_datei_ist_422():
    with TestClient(typefree.app) as client:
        antwort = client.post("/api/v1/transcribe", data={"language": "de-DE"})
    assert antwort.status_code == 422


def test_typefree_diktat_glaettet(monkeypatch):
    monkeypatch.setattr(core, "transcribe_audio_azure", lambda pfad, **kw: "Ähm also der Test läuft")

    async def falsche_glaettung(text, *, context="", provider=None, env=None):
        assert text == "Ähm also der Test läuft"
        return core.SmoothResult(
            text="Der Test läuft.", provider="openrouter", model="deepseek/deepseek-v4.1-flash", is_fallback=True
        )

    monkeypatch.setattr(core, "smooth_dictation_text", falsche_glaettung)
    with TestClient(typefree.app) as client:
        antwort = client.post("/api/v1/dictate", files={"audio": ("probe.wav", WAV_ATTRAppe, "audio/wav")})
    daten = antwort.json()
    assert antwort.status_code == 200
    assert daten["geglaettet"] is True
    assert daten["text"] == "Der Test läuft."
    assert daten["ausweichweg"] is True


def test_typefree_diktat_ohne_glaettung_liefert_rohtext(monkeypatch):
    monkeypatch.setattr(core, "transcribe_audio_azure", lambda pfad, **kw: "roher Text")

    async def kaputte_glaettung(*args, **kwargs):
        raise core.LlmUnavailableError("kein LLM-Weg konfiguriert")

    monkeypatch.setattr(core, "smooth_dictation_text", kaputte_glaettung)
    with TestClient(typefree.app) as client:
        antwort = client.post("/api/v1/dictate", files={"audio": ("probe.wav", WAV_ATTRAppe, "audio/wav")})
    daten = antwort.json()
    assert antwort.status_code == 200
    assert daten["geglaettet"] is False
    assert daten["text"] == "roher Text"
    assert "Glättung nicht möglich" in daten["hinweis"]


def test_typefree_konfigurationsfehler_ist_503(monkeypatch):
    def kaputt(pfad, **kw):
        raise core.ConfigurationError("AZURE_SPEECH_REGION fehlt")

    monkeypatch.setattr(core, "transcribe_audio_azure", kaputt)
    with TestClient(typefree.app) as client:
        antwort = client.post("/api/v1/transcribe", files={"audio": ("probe.wav", WAV_ATTRAppe, "audio/wav")})
    assert antwort.status_code == 503


# ── Client ───────────────────────────────────────────────────────────────────


def test_client_schickt_wav_und_zeigt_text(monkeypatch, tmp_path, capsys):
    wav = tmp_path / "probe.wav"
    wav.write_bytes(WAV_ATTRAppe)
    post = Aufnahme(
        httpx.Response(
            200,
            json={"rohtext": "hallo welt", "text": "Hallo Welt.", "geglaettet": True, "provider": "attrappe", "model": "m"},
        )
    )
    monkeypatch.setattr(client_app.httpx, "post", post)
    assert client_app.main(["--datei", str(wav), "--server", "http://test:1"]) == 0
    assert post.url == "http://test:1/api/v1/dictate"
    assert post.kwargs["files"]["audio"][1] == WAV_ATTRAppe
    assert post.kwargs["headers"] == {}  # ohne ENTRA_* kein Token
    assert "Hallo Welt." in capsys.readouterr().out


def test_client_sendet_entra_token(monkeypatch, tmp_path):
    wav = tmp_path / "probe.wav"
    wav.write_bytes(WAV_ATTRAppe)
    post = Aufnahme(httpx.Response(200, json={"rohtext": "a", "text": "a"}))
    monkeypatch.setattr(client_app.httpx, "post", post)
    monkeypatch.setattr(client_app, "auth_kopf", lambda: {"Authorization": "Bearer t"})
    assert client_app.main(["--datei", str(wav)]) == 0
    assert post.kwargs["headers"] == {"Authorization": "Bearer t"}


def test_client_meldet_serverfehler(monkeypatch, tmp_path):
    wav = tmp_path / "probe.wav"
    wav.write_bytes(WAV_ATTRAppe)
    monkeypatch.setattr(client_app.httpx, "post", Aufnahme(httpx.Response(401, text="Entra-Token fehlt")))
    assert client_app.main(["--datei", str(wav)]) == 1
