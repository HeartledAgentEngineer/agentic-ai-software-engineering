"""Idempotent bootstrap of the free-tier (F0) Azure resources for azure_free_core.

Creates — only what is missing — in subscription scope:

* resource group ``RG_AI_Portfolio_Free`` (region ``swedencentral``)
* ``typefree-speech-f0``   kind ``SpeechServices``  SKU ``F0`` (STT + neural TTS)
* ``screenshot-vision-f0`` kind ``ComputerVision``  SKU ``F0`` (Image Analysis Read)

Existing F0 resources of the same kind are reused (preferring the exact
desired name) instead of creating duplicates. The endpoints and keys are
fetched with the Azure CLI and written into the module-local ``.env``;
foreign entries such as ``OPENROUTER_API_KEY`` or ``GITHUB_TOKEN`` are never
touched. Nothing is ever printed that contains a key value.

Usage::

    python bootstrap_azure_f0.py --pruefen     # read-only preview, changes nothing
    python bootstrap_azure_f0.py               # apply (idempotent)

Undo (manual, nothing here deletes anything)::

    az cognitiveservices account delete -n typefree-speech-f0 -g RG_AI_Portfolio_Free
    az cognitiveservices account delete -n screenshot-vision-f0 -g RG_AI_Portfolio_Free
    az group delete -n RG_AI_Portfolio_Free --yes
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RG_NAME = "RG_AI_Portfolio_Free"
LOCATION = "swedencentral"
SPEECH_NAME = "typefree-speech-f0"
VISION_NAME = "screenshot-vision-f0"
ENV_PATH = Path(__file__).resolve().with_name(".env")

_KV_MUSTER = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)=")


class BootstrapFehler(RuntimeError):
    """Something went wrong with the Azure CLI call chain."""


def _az_programm() -> str:
    """Path of the Azure CLI launcher.

    Under Windows the CLI is the batch shim ``az.cmd``; ``shutil.which`` finds
    it via PATHEXT, which a bare CreateProcess lookup would miss.
    """
    return shutil.which("az") or shutil.which("az.cmd") or "az"


def az(*args: str) -> str:
    """Run the Azure CLI and return stdout; raise BootstrapFehler on failure."""
    befehl = [_az_programm(), *args, "--only-show-errors"]
    try:
        ergebnis = subprocess.run(
            befehl, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError as exc:
        raise BootstrapFehler(
            "Azure CLI (az) nicht gefunden. Installation: winget install -e --id Microsoft.AzureCLI"
        ) from exc
    if ergebnis.returncode != 0:
        fehler = (ergebnis.stderr or "").strip() or f"Exit-Code {ergebnis.returncode}"
        raise BootstrapFehler(f"az {' '.join(args)}: {fehler}")
    return ergebnis.stdout or ""


def session_pruefen() -> None:
    """Make sure an active Azure CLI session exists (az login)."""
    try:
        az("account", "show", "-o", "json")
    except BootstrapFehler as exc:
        raise BootstrapFehler(
            "Keine aktive Azure-Anmeldung. Bitte zuerst ausführen:  az login\nDetails: " + str(exc)
        ) from exc


def vorhandene_ressourcen() -> list[dict]:
    """All Cognitive Services accounts of the current subscription."""
    rohdaten = az("cognitiveservices", "account", "list", "-o", "json")
    try:
        daten = json.loads(rohdaten or "[]")
    except json.JSONDecodeError as exc:
        raise BootstrapFehler("Antwort von 'az cognitiveservices account list' ist kein JSON.") from exc
    return daten if isinstance(daten, list) else []


def finde_f0(ressourcen: list[dict], kind: str, wunschname: str) -> tuple[dict | None, str]:
    """Find an F0 resource: prefer the exact desired name, else any F0 of this kind."""
    kandidaten = [
        r
        for r in ressourcen
        if (r.get("kind") or "").lower() == kind.lower()
        and ((r.get("sku") or {}).get("name") or "").upper() == "F0"
    ]
    for r in kandidaten:
        if (r.get("name") or "").lower() == wunschname.lower():
            return r, "Name passt genau"
    if kandidaten:
        return kandidaten[0], "vorhandene F0-Ressource wiederverwendet"
    return None, ""


def env_aktualisieren(pfad: Path, werte: dict[str, str]) -> list[str]:
    """Update ``KEY=value`` lines in place, append missing keys, keep everything else.

    Foreign keys (OPENROUTER_API_KEY, GITHUB_TOKEN, ...) and comments remain
    byte for byte as they were. Returns the names of newly appended keys.
    Atomic write via a temporary file; running twice changes nothing.
    """
    pfad = Path(pfad)
    zeilen: list[str] = []
    if pfad.is_file():
        zeilen = pfad.read_text(encoding="utf-8").splitlines()
    ergebnis: list[str] = []
    gefunden: set[str] = set()
    for zeile in zeilen:
        treffer = _KV_MUSTER.match(zeile)
        if treffer and treffer.group("name") in werte:
            name = treffer.group("name")
            ergebnis.append(f"{name}={werte[name]}")
            gefunden.add(name)
        else:
            ergebnis.append(zeile)
    neu_hinzugefuegt = [name for name in werte if name not in gefunden]
    if neu_hinzugefuegt:
        if ergebnis and ergebnis[-1].strip():
            ergebnis.append("")
        ergebnis.append(f"# --- Azure Free Core (automatisch ergänzt {datetime.now():%Y-%m-%d %H:%M}) ---")
        ergebnis.extend(f"{name}={werte[name]}" for name in neu_hinzugefuegt)
    zwischendatei = pfad.with_name(pfad.name + ".tmp")
    with zwischendatei.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(ergebnis) + "\n")
    os.replace(zwischendatei, pfad)
    return neu_hinzugefuegt


def _zugangsdaten_holen(name: str, resource_group: str) -> dict:
    """Key + endpoint + resource id of an account (values stay in memory)."""
    keys = json.loads(az("cognitiveservices", "account", "keys", "list", "-n", name, "-g", resource_group, "-o", "json"))
    konto = json.loads(az("cognitiveservices", "account", "show", "-n", name, "-g", resource_group, "-o", "json"))
    return {
        "key": (keys.get("key1") or "").strip(),
        "endpoint": ((konto.get("properties") or {}).get("endpoint") or "").strip(),
        "id": (konto.get("id") or "").strip(),
    }


def stelle_sicher(*, pruefen: bool, env_pfad: Path) -> int:
    """The whole idempotent flow: check, plan, create what is missing, write the .env."""
    session_pruefen()
    ressourcen = vorhandene_ressourcen()

    plan: list[dict] = []
    for kind, wunschname, kurz in (
        ("SpeechServices", SPEECH_NAME, "Speech F0 (STT/TTS)"),
        ("ComputerVision", VISION_NAME, "Vision F0 (OCR)"),
    ):
        gefunden, notiz = finde_f0(ressourcen, kind, wunschname)
        if gefunden:
            plan.append(
                {
                    "kind": kind,
                    "name": gefunden.get("name"),
                    "rg": gefunden.get("resourceGroup"),
                    "aktion": "vorhanden",
                    "notiz": notiz,
                    "kurz": kurz,
                }
            )
        else:
            plan.append({"kind": kind, "name": wunschname, "rg": RG_NAME, "aktion": "anlegen", "notiz": "", "kurz": kurz})

    print("Plan:")
    for eintrag in plan:
        if eintrag["aktion"] == "vorhanden":
            print(f"  - {eintrag['kurz']}: vorhanden — {eintrag['name']} ({eintrag['rg']}) [{eintrag['notiz']}]")
        else:
            print(f"  - {eintrag['kurz']}: fehlt — wird angelegt: {eintrag['name']} in {RG_NAME}/{LOCATION}")

    if pruefen:
        print("Prüflauf — es wurde nichts angelegt und nichts geschrieben.")
        return 0

    if any(e["aktion"] == "anlegen" for e in plan):
        print(f"Lege Ressourcengruppe an/aktualisiere sie: {RG_NAME} ({LOCATION})")
        az("group", "create", "-n", RG_NAME, "-l", LOCATION, "-o", "json")

    for eintrag in plan:
        if eintrag["aktion"] != "anlegen":
            continue
        print(f"Lege an: {eintrag['name']} ({eintrag['kind']}, SKU F0) …  das dauert ein paar Sekunden.")
        try:
            az(
                "cognitiveservices", "account", "create",
                "-n", eintrag["name"], "-g", RG_NAME, "-l", LOCATION,
                "--kind", eintrag["kind"], "--sku", "F0", "--yes", "-o", "json",
            )
        except BootstrapFehler as exc:
            raise BootstrapFehler(
                f"Anlegen von {eintrag['name']} fehlgeschlagen. Ist im Abo bereits eine "
                f"F0-Ressource dieses Typs vorhanden (es ist nur eine erlaubt), reicht ein "
                f"erneuter Lauf dieses Skripts.\nDetails: {exc}"
            ) from exc

    # Fresh list, so reused and created resources are read the same way.
    ressourcen = vorhandene_ressourcen()
    werte: dict[str, str] = {}
    for kind, wunschname, kurz in (
        ("SpeechServices", SPEECH_NAME, "Speech"),
        ("ComputerVision", VISION_NAME, "Vision"),
    ):
        gefunden, _ = finde_f0(ressourcen, kind, wunschname)
        if not gefunden:
            raise BootstrapFehler(f"{kurz}-Ressource nach dem Anlegen nicht gefunden — bitte im Portal prüfen.")
        daten = _zugangsdaten_holen(gefunden["name"], gefunden["resourceGroup"])
        if not daten["key"]:
            raise BootstrapFehler(f"Kein Schlüssel für {gefunden['name']} erhalten.")
        if kurz == "Speech":
            werte["AZURE_SPEECH_KEY"] = daten["key"]
            werte["AZURE_SPEECH_REGION"] = LOCATION
            werte["AZURE_SPEECH_ENDPOINT"] = daten["endpoint"]
            werte["AZURE_SPEECH_RESOURCE_ID"] = daten["id"]
        else:
            werte["AZURE_VISION_KEY"] = daten["key"]
            werte["AZURE_VISION_ENDPOINT"] = daten["endpoint"]

    neu = env_aktualisieren(env_pfad, werte)
    print()
    print(f".env aktualisiert: {env_pfad}")
    print(f"  Schlüssel/Werte geschrieben: {len(werte)} (Werte werden nicht angezeigt)")
    if neu:
        print(f"  Neu ergänzt: {', '.join(neu)}")
    else:
        print("  Neu ergänzt: nichts (war schon alles vorhanden — Lauf ist idempotent)")
    print()
    print("Fertig. Nächster Schritt:  .venv/Scripts/python.exe test_smoke.py")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Legt die kostenlosen F0-Ressourcen (Speech, Vision) an und schreibt die .env."
    )
    parser.add_argument("--pruefen", action="store_true", help="nur lesen und anzeigen — nichts anlegen, nichts schreiben")
    parser.add_argument("--env-pfad", type=Path, default=ENV_PATH, help="Ziel-.env (Standard: neben diesem Skript)")
    args = parser.parse_args(argv)
    try:
        return stelle_sicher(pruefen=args.pruefen, env_pfad=args.env_pfad)
    except BootstrapFehler as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
