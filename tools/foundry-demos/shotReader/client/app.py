"""shotReader — Azure Edition: client (clipboard/image → OCR + speech).

Examples (server running on port 8103)::

    ./.venv/Scripts/python.exe shotReader/client/app.py --bild screenshot.png
    ./.venv/Scripts/python.exe shotReader/client/app.py          # Bild aus der Zwischenablage
    ./.venv/Scripts/python.exe shotReader/client/app.py --bild b.png --nicht-abspielen

The image never leaves the local network: it goes to the local server, which
calls Azure with its own credentials. Clipboard access uses PIL/pillow.
"""

from __future__ import annotations

import argparse
import base64
import sys
import tempfile
from io import BytesIO
from pathlib import Path

import httpx

STANDARD_SERVER = "http://127.0.0.1:8103"
BILD_ENDUNGEN = (".png", ".jpg", ".jpeg", ".bmp", ".gif")


def _bild_aus_zwischenablage() -> bytes:
    try:
        from PIL import ImageGrab
    except ImportError as exc:
        raise SystemExit(
            "PIL/pillow fehlt — installieren mit: pip install -r shared_core/requirements_azure.txt"
        ) from exc
    klammer = ImageGrab.grabclipboard()
    if klammer is None:
        raise SystemExit("Die Zwischenablage enthält kein Bild.")
    if isinstance(klammer, list):  # kopierte Dateien statt Bilddaten
        bilder = [p for p in klammer if str(p).lower().endswith(BILD_ENDUNGEN)]
        if not bilder:
            raise SystemExit("Die Zwischenablage enthält keine Bilddatei.")
        return Path(bilder[0]).read_bytes()
    puffer = BytesIO()
    klammer.save(puffer, format="PNG")
    return puffer.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="shotReader — Azure Edition (Client)")
    parser.add_argument("--bild", type=str, default=None, help="Bilddatei; ohne Angabe: Zwischenablage")
    parser.add_argument("--stimme", type=str, default="de-DE-ConradNeural")
    parser.add_argument("--tempo", type=str, default="+0%")
    parser.add_argument("--server", type=str, default=STANDARD_SERVER)
    parser.add_argument("--token", type=str, default=None)
    parser.add_argument("--audio", type=str, default=None, help="WAV-Datei behalten (Pfad)")
    parser.add_argument("--nicht-abspielen", action="store_true", help="nur lesen, nicht hören")
    args = parser.parse_args(argv)

    bild = Path(args.bild).read_bytes() if args.bild else _bild_aus_zwischenablage()
    kopf = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    try:
        antwort = httpx.post(
            f"{args.server.rstrip('/')}/api/v1/ocr-und-vorlesen",
            files={"bild": ("screenshot.png", bild, "image/png")},
            data={"stimme": args.stimme, "tempo": args.tempo},
            headers=kopf,
            timeout=120.0,
        )
    except httpx.HTTPError as fehler:
        print(f"FEHLER: Server nicht erreichbar ({fehler}).")
        return 2
    if antwort.status_code != 200:
        print(f"FEHLER {antwort.status_code}: {antwort.text}")
        return 1
    daten = antwort.json()
    print(f"Erkannter Text ({len(daten.get('text', ''))} Zeichen):")
    print(daten.get("text") or "(kein Text erkannt)")
    if daten.get("hinweis"):
        print(f"Hinweis: {daten['hinweis']}")
    audio_b64 = daten.get("audio_base64")
    if not audio_b64:
        return 0
    audio = base64.b64decode(audio_b64)
    behalten = False
    if args.audio:
        ziel = Path(args.audio)
        ziel.write_bytes(audio)
        behalten = True
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as datei:
            datei.write(audio)
            ziel = Path(datei.name)
    print(f"Audio: {len(audio)} Bytes, Stimme {daten.get('stimme')}")
    if not args.nicht_abspielen and sys.platform == "win32":
        import winsound

        winsound.PlaySound(str(ziel), winsound.SND_FILENAME)
    if not behalten:
        ziel.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
