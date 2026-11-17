"""Offline-Tests für bootstrap_azure_f0 — die az-Aufrufe selbst werden hier nicht gefahren."""

from __future__ import annotations

import os
import subprocess
import sys

from shared_core import bootstrap_azure_f0 as boot


def test_env_aktualisieren_legt_neue_datei_an(tmp_path):
    pfad = tmp_path / ".env"
    neu = boot.env_aktualisieren(pfad, {"AZURE_SPEECH_KEY": "s1", "AZURE_SPEECH_REGION": "swedencentral"})
    assert neu == ["AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION"]
    inhalt = pfad.read_text(encoding="utf-8")
    assert "AZURE_SPEECH_KEY=s1" in inhalt
    assert "AZURE_SPEECH_REGION=swedencentral" in inhalt


def test_env_aktualisieren_behaelt_fremde_schluessel_und_kommentare(tmp_path):
    pfad = tmp_path / ".env"
    pfad.write_text("# Bestand\nOPENROUTER_API_KEY=geheim\nGITHUB_TOKEN=abc\n", encoding="utf-8")
    boot.env_aktualisieren(pfad, {"AZURE_SPEECH_KEY": "s1"})
    inhalt = pfad.read_text(encoding="utf-8")
    assert "# Bestand" in inhalt
    assert "OPENROUTER_API_KEY=geheim" in inhalt
    assert "GITHUB_TOKEN=abc" in inhalt


def test_env_aktualisieren_ueberschreibt_nur_den_gleichen_schluessel(tmp_path):
    pfad = tmp_path / ".env"
    pfad.write_text("AZURE_SPEECH_KEY=alt\nOPENROUTER_API_KEY=x\n", encoding="utf-8")
    neu = boot.env_aktualisieren(pfad, {"AZURE_SPEECH_KEY": "neu"})
    inhalt = pfad.read_text(encoding="utf-8")
    assert neu == []
    assert "AZURE_SPEECH_KEY=neu" in inhalt
    assert "AZURE_SPEECH_KEY=alt" not in inhalt
    assert "OPENROUTER_API_KEY=x" in inhalt


def test_env_aktualisieren_ist_idempotent(tmp_path):
    pfad = tmp_path / ".env"
    werte = {"AZURE_SPEECH_KEY": "s1", "AZURE_VISION_ENDPOINT": "https://beispiel"}
    boot.env_aktualisieren(pfad, werte)
    erster_stand = pfad.read_text(encoding="utf-8")
    neu = boot.env_aktualisieren(pfad, werte)
    assert neu == []
    assert pfad.read_text(encoding="utf-8") == erster_stand


def test_finde_f0_bevorzugt_den_gewuenschten_namen():
    ressourcen = [
        {"name": "andere-speech", "kind": "SpeechServices", "sku": {"name": "F0"}, "resourceGroup": "rg1"},
        {
            "name": "typefree-speech-f0",
            "kind": "SpeechServices",
            "sku": {"name": "F0"},
            "resourceGroup": "RG_AI_Portfolio_Free",
        },
    ]
    treffer, notiz = boot.finde_f0(ressourcen, "SpeechServices", "typefree-speech-f0")
    assert treffer is not None
    assert treffer["name"] == "typefree-speech-f0"
    assert notiz == "Name passt genau"


def test_finde_f0_nutzt_vorhandene_ressource_anderen_namens():
    ressourcen = [
        {"name": "vorhandene-vision", "kind": "ComputerVision", "sku": {"name": "F0"}, "resourceGroup": "rg1"},
        {"name": "teure-vision", "kind": "ComputerVision", "sku": {"name": "S1"}, "resourceGroup": "rg1"},
    ]
    treffer, notiz = boot.finde_f0(ressourcen, "ComputerVision", "screenshot-vision-f0")
    assert treffer is not None
    assert treffer["name"] == "vorhandene-vision"
    assert "wiederverwendet" in notiz


def test_finde_f0_ohne_treffer():
    assert boot.finde_f0([], "SpeechServices", "x") == (None, "")
    nur_s0 = [{"name": "x", "kind": "SpeechServices", "sku": {"name": "S0"}, "resourceGroup": "rg1"}]
    assert boot.finde_f0(nur_s0, "SpeechServices", "x") == (None, "")


def test_import_in_frischem_prozess_ohne_netzwerk_cli_oder_provisionierung(tmp_path):
    bootstrap = boot.__file__
    script = """
import importlib.util
import socket
import subprocess
import sys
import os

def fail(*args, **kwargs):
    raise AssertionError("blocked side effect was attempted")

socket.create_connection = fail
socket.socket.connect = fail
socket.socket.connect_ex = fail
subprocess.run = fail
subprocess.Popen = fail
os.system = fail
sys.exit = fail
sys.argv = ["bootstrap_azure_f0.py", "--apply"]
spec = importlib.util.spec_from_file_location("fresh_bootstrap", sys.argv[0])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert not hasattr(module, "_RUN_ON_IMPORT")
"""
    umgebung = os.environ.copy()
    umgebung.pop("AZURE_AUTH_MODE", None)
    umgebung.pop("OFFLINE_GUARD_PROJECT_ROOT", None)
    umgebung.pop("PYTHONPATH", None)
    ergebnis = subprocess.run(
        [sys.executable, "-c", script.replace('sys.argv[0]', repr(bootstrap))],
        cwd=tmp_path,
        env=umgebung,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert list(tmp_path.iterdir()) == []
