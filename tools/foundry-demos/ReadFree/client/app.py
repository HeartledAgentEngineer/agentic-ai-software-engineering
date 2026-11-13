"""readFREE — Azure Edition: client for the text-to-speech service.

Examples (server running on port 8102)::

    ./.venv/Scripts/python.exe ReadFree/client/app.py "Hallo, ich lese vor."
    ./.venv/Scripts/python.exe ReadFree/client/app.py --datei text.txt --tempo +15%
    ./.venv/Scripts/python.exe ReadFree/client/app.py "Test" --nicht-abspielen --ausgabe probe.wav

The client sends text to its own server; the SSML and the Azure call happen on
the server side. Playback uses ``winsound`` (Windows only).
"""

from __future__ import annotations

import argparse
import io
import sys
import tempfile
import wave
from pathlib import Path

import httpx

STANDARD_SERVER = "http://127.0.0.1:8102"


def _dauer_sekunden(wav_bytes: bytes) -> float:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as datei:
            return datei.getnframes() / float(datei.getframerate())
    except wave.Error:
        return 0.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="readFREE — Azure Edition (Client)")
    parser.add_argument("text", nargs="?", help="Text; ohne Angabe wird --datei oder stdin gelesen")
    parser.add_argument("--datei", type=str, default=None, help="Textdatei vorlesen")
    parser.add_argument("--stimme", type=str, default="de-DE-ConradNeural")
    parser.add_argument("--tempo", type=str, default="+0%", help="SSML-Tempo, z. B. '+15%%'")
    parser.add_argument("--server", type=str, default=STANDARD_SERVER)
    parser.add_argument("--token", type=str, default=None)
    parser.add_argument("--ausgabe", type=str, default=None, help="WAV-Datei behalten (Pfad)")
    parser.add_argument("--nicht-abspielen", action="store_true", help="nur erzeugen, nicht hören")
    args = parser.parse_args(argv)

    if args.text:
        text = args.text
    elif args.datei:
        text = Path(args.datei).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    text = text.strip()
    if not text:
        print("FEHLER: kein Text übergeben.")
        return 2

    kopf = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    try:
        antwort = httpx.post(
            f"{args.server.rstrip('/')}/api/v1/speak",
            json={"text": text, "stimme": args.stimme, "tempo": args.tempo},
            headers=kopf,
            timeout=60.0,
        )
    except httpx.HTTPError as fehler:
        print(f"FEHLER: Server nicht erreichbar ({fehler}).")
        return 2
    if antwort.status_code != 200:
        print(f"FEHLER {antwort.status_code}: {antwort.text}")
        return 1
    audio = antwort.content
    behalten = False
    if args.ausgabe:
        ziel = Path(args.ausgabe)
        ziel.write_bytes(audio)
        behalten = True
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as datei:
            datei.write(audio)
            ziel = Path(datei.name)
    print(
        f"{len(text)} Zeichen → {_dauer_sekunden(audio):.1f} s Audio, {len(audio)} Bytes, "
        f"Stimme {antwort.headers.get('X-Stimme', args.stimme)}"
    )
    if not args.nicht_abspielen and sys.platform == "win32":
        import winsound

        winsound.PlaySound(str(ziel), winsound.SND_FILENAME)
    if not behalten:
        ziel.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
