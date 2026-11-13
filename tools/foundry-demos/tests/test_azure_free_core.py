"""Offline-Tests für azure_free_core — kein Netz, kein Azure-Konto nötig."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest

from shared_core import azure_free_core as core


# ── SSML (Modul 2) ───────────────────────────────────────────────────────────


def test_ssml_ist_wohlgeformtes_xml_mit_stimme_und_tempo():
    ssml = core.build_ssml("Hallo Welt", voice="de-DE-ConradNeural", rate="+20%")
    wurzel = ET.fromstring(ssml)  # wirft bei ungültigem XML
    assert wurzel.tag == f"{{{core.SSML_NAMESPACE}}}speak"
    stimme = wurzel.find(f"{{{core.SSML_NAMESPACE}}}voice")
    assert stimme is not None
    assert stimme.get("name") == "de-DE-ConradNeural"
    assert "rate='+20%'" in ssml
    assert "xml:lang='de-DE'" in ssml


def test_ssml_maskiert_sonderzeichen():
    ssml = core.build_ssml("Tom & Jerry <b>")
    ET.fromstring(ssml)
    assert "Tom &amp; Jerry &lt;b&gt;" in ssml
    assert "<b>" not in ssml


def test_ssml_rate_und_pitch_werden_geprueft():
    with pytest.raises(ValueError):
        core.build_ssml("Text", rate="20%")
    with pytest.raises(ValueError):
        core.build_ssml("Text", rate="schnell")
    with pytest.raises(ValueError):
        core.build_ssml("Text", pitch="+2")
    with pytest.raises(ValueError):
        core.build_ssml("   ")


def test_ssml_pitch_optional():
    ohne = core.build_ssml("Hallo")
    assert "pitch" not in ohne
    mit = core.build_ssml("Hallo", pitch="-3Hz")
    assert "pitch='-3Hz'" in mit


def test_speak_ohne_text_oder_ssml_faellt_auf():
    with pytest.raises(ValueError):
        core.speak_text_azure_ssml()


# ── OCR (Modul 3) ────────────────────────────────────────────────────────────


def test_zeilen_aus_read_ergebnis_werden_zusammengefuegt():
    ergebnis = SimpleNamespace(
        blocks=[
            SimpleNamespace(
                lines=[SimpleNamespace(text="Erste Zeile"), SimpleNamespace(text=" Zweite Zeile ")]
            ),
            SimpleNamespace(lines=[SimpleNamespace(text="Dritte")]),
        ]
    )
    assert core._read_lines_from_result(ergebnis) == "Erste Zeile\nZweite Zeile\nDritte"


def test_leeres_read_ergebnis_ergibt_leeren_text():
    assert core._read_lines_from_result(SimpleNamespace(blocks=None)) == ""
    assert core._read_lines_from_result(SimpleNamespace(blocks=[])) == ""


def test_ocr_ohne_endpunkt_meldet_konfigurationsfehler():
    with pytest.raises(core.ConfigurationError):
        core.extract_text_from_image_azure(b"\x89PNG", env={})


def test_ocr_mit_leeren_bilddaten_faellt_auf():
    with pytest.raises(ValueError):
        core.extract_text_from_image_azure(b"", env={"AZURE_VISION_ENDPOINT": "https://beispiel"})


# ── STT (Modul 1) ────────────────────────────────────────────────────────────


def test_transcribe_braucht_genau_eine_quelle():
    with pytest.raises(ValueError):
        core.transcribe_audio_azure()
    with pytest.raises(ValueError):
        core.transcribe_audio_azure("datei.wav", use_default_microphone=True)


def test_transcribe_ohne_region_meldet_konfigurationsfehler():
    with pytest.raises(core.ConfigurationError):
        core.transcribe_audio_azure("datei.wav", env={})


# ── Glättung (Modul 4) ───────────────────────────────────────────────────────


def test_provider_reihenfolge_standard_und_wahl():
    assert core.provider_order(None, {}) == ["github_azure", "openrouter", "azure_foundry"]
    assert core.provider_order(None, {"LLM_PROVIDER": "openrouter"}) == [
        "openrouter",
        "github_azure",
        "azure_foundry",
    ]
    assert core.provider_order("azure_foundry", {})[0] == "azure_foundry"


def test_provider_reihenfolge_lehnt_unbekanntes_ab():
    with pytest.raises(core.ConfigurationError):
        core.provider_order(None, {"LLM_PROVIDER": "quatsch"})


def test_provider_verfuegbarkeit():
    assert core.provider_available("github_azure", {"GITHUB_TOKEN": "t"})
    assert not core.provider_available("github_azure", {})
    assert core.provider_available("openrouter", {"OPENROUTER_API_KEY": "k"})
    assert core.provider_available(
        "azure_foundry", {"AZURE_FOUNDRY_ENDPOINT": "https://x", "AZURE_FOUNDRY_DEPLOYMENT": "d"}
    )
    assert not core.provider_available("azure_foundry", {"AZURE_FOUNDRY_ENDPOINT": "https://x"})
    with pytest.raises(core.ConfigurationError):
        core.provider_available("unbekannt", {})


def test_plausibilitaet_kurzer_text_und_kuerzung():
    assert core.smoothing_plausible("Kurzer Text.", "Kurz.")
    lang = "wort " * 60
    assert core.smoothing_plausible(lang, lang[: int(len(lang) * 0.7)])
    assert not core.smoothing_plausible(lang, lang[: int(len(lang) * 0.3)])
    assert not core.smoothing_plausible(lang, "")


def test_auftragstext_mit_und_ohne_kontext():
    mit = core._build_user_prompt("Rohtext hier", "Vorheriger Kontext")
    assert "NICHT wiederholen" in mit
    assert "Rohtext hier" in mit
    assert "Vorheriger Kontext" in mit
    ohne = core._build_user_prompt("Rohtext hier", "")
    assert ohne.startswith("Bereinige diesen gesprochenen Text:")


def test_smooth_lehnt_leeren_text_ab():
    with pytest.raises(ValueError):
        asyncio.run(core.smooth_dictation_text("   "))


def test_smooth_ohne_zugangsdaten_meldet_unverfuegbar():
    with pytest.raises(core.LlmUnavailableError):
        asyncio.run(core.smooth_dictation_text("Ein Satz zum Glätten.", env={}))


# ── Auth-Weiche ──────────────────────────────────────────────────────────────


def test_auth_modus_key_gewinnt_im_auto_modus():
    assert core.choose_auth_mode("vision", {"AZURE_VISION_KEY": "k"}) == "key"
    assert core.choose_auth_mode("vision", {}) == "entra"
    assert core.choose_auth_mode("speech", {"AZURE_AUTH_MODE": "entra", "AZURE_SPEECH_KEY": "k"}) == "entra"
    assert core.choose_auth_mode("speech", {"AZURE_AUTH_MODE": "key"}) == "key"


def test_auth_modus_lehnt_unbekanntes_ab():
    with pytest.raises(core.ConfigurationError):
        core.choose_auth_mode("vision", {"AZURE_AUTH_MODE": "jwt"})
    with pytest.raises(core.ConfigurationError):
        core.choose_auth_mode("unbekannt", {})


def test_end_of_stream_gilt_als_normales_dateiende():
    """Das Speech-SDK meldet das Dateiende als canceled/EndOfStream — kein Fehler."""

    class FakeReason:
        EndOfStream = "EndOfStream"

    class FakeSdk:
        CancellationReason = FakeReason

        class CancellationDetails:  # nur als Fallback-Attrappe nötig
            @staticmethod
            def from_result(_result):
                return None

            def __init__(self, _result):
                pass

    dateiende = SimpleNamespace(cancellation_details=SimpleNamespace(reason="EndOfStream", error_details=""))
    assert core._ist_dateiende(FakeSdk, dateiende) is True

    echter_fehler = SimpleNamespace(cancellation_details=SimpleNamespace(reason="Error", error_details="401"))
    assert core._ist_dateiende(FakeSdk, echter_fehler) is False

    ohne_details = SimpleNamespace(cancellation_details=None, reason="Canceled")
    assert core._ist_dateiende(FakeSdk, ohne_details) is False
