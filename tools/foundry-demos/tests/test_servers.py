"""Offline-Tests der drei FastAPI-Server — Azure-Aufrufe sind durch Attrappen ersetzt.

Getestet wird das HTTP-Verhalten (Statuscodes, Antwortformen, Token-Schutz),
nicht Azure selbst; die echten Aufrufe belegt der Live-Smoke-Test.
"""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from ReadFree.server import main as readfree
from shotReader.server import main as screenshot
from TypeFree.server import main as typefree
from shared_core import azure_free_core as core

WAV_ATTRAppe = b"RIFF$\x00\x00\x00WAVEfmt " + b"\x00" * 16
PNG_ATTRAppe = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_healthz_aller_drei_dienste():
    for app, name in (
        (typefree.app, "typefree-azure"),
        (readfree.app, "readfree-azure"),
        (screenshot.app, "shotreader-azure"),
    ):
        with TestClient(app) as client:
            antwort = client.get("/healthz")
        assert antwort.status_code == 200
        daten = antwort.json()
        assert daten["status"] == "ok"
        assert daten["service"] == name
        assert isinstance(daten["llm_wege_verfuegbar"], list)


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


def test_screenshot_ocr_liefert_text(monkeypatch):
    monkeypatch.setattr(core, "extract_text_from_image_azure", lambda daten, **kw: "Erste Zeile\nZweite")
    with TestClient(screenshot.app) as client:
        antwort = client.post("/api/v1/ocr", files={"bild": ("b.png", PNG_ATTRAppe, "image/png")})
    assert antwort.status_code == 200
    assert antwort.json()["text"].startswith("Erste Zeile")


def test_screenshot_ohne_text_kein_audio(monkeypatch):
    monkeypatch.setattr(core, "extract_text_from_image_azure", lambda daten, **kw: "")
    with TestClient(screenshot.app) as client:
        antwort = client.post("/api/v1/ocr-und-vorlesen", files={"bild": ("b.png", PNG_ATTRAppe, "image/png")})
    daten = antwort.json()
    assert antwort.status_code == 200
    assert daten["audio_base64"] is None
    assert "Kein Text" in daten["hinweis"]


def test_screenshot_ocr_und_vorlesen_mit_audio(monkeypatch):
    monkeypatch.setattr(core, "extract_text_from_image_azure", lambda daten, **kw: "Hallo Welt")
    monkeypatch.setattr(core, "speak_text_azure_ssml", lambda ssml, play=False, **kw: b"RIFF" + b"\x00" * 100)
    with TestClient(screenshot.app) as client:
        antwort = client.post(
            "/api/v1/ocr-und-vorlesen",
            files={"bild": ("b.png", PNG_ATTRAppe, "image/png")},
            data={"stimme": "de-DE-ConradNeural"},
        )
    daten = antwort.json()
    assert antwort.status_code == 200
    assert base64.b64decode(daten["audio_base64"]).startswith(b"RIFF")


def test_tokenschutz_greift_wenn_gesetzt(monkeypatch):
    monkeypatch.setenv("PORTFOLIO_API_TOKEN", "example-api-token")
    monkeypatch.setattr(core, "speak_text_azure_ssml", lambda ssml, play=False, **kw: b"RIFF" + b"\x00" * 4000)
    with TestClient(readfree.app) as client:
        ohne = client.post("/api/v1/speak", json={"text": "Hallo"})
        falsch = client.post("/api/v1/speak", json={"text": "Hallo"}, headers={"Authorization": "Bearer falsch"})
        richtig = client.post(
            "/api/v1/speak", json={"text": "Hallo"}, headers={"Authorization": "Bearer example-api-token"}
        )
    assert ohne.status_code == 401
    assert falsch.status_code == 403
    assert richtig.status_code == 200


def test_tokenschutz_aus_ohne_konfiguration(monkeypatch):
    monkeypatch.delenv("PORTFOLIO_API_TOKEN", raising=False)
    monkeypatch.setattr(core, "speak_text_azure_ssml", lambda ssml, play=False, **kw: b"RIFF" + b"\x00" * 4000)
    with TestClient(readfree.app) as client:
        antwort = client.post("/api/v1/speak", json={"text": "Hallo"})
    assert antwort.status_code == 200
