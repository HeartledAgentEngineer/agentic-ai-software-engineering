"""typeFREE — Azure Edition: Windows client for the dictation service.

Examples (server running on port 8101)::

    ./.venv/Scripts/python.exe TypeFree/client/app.py --datei probe.wav
    ./.venv/Scripts/python.exe TypeFree/client/app.py --mikrofon --sekunden 8
    ./.venv/Scripts/python.exe TypeFree/client/app.py --mikrofon --hotkey "alt+a" --einfuegen

The client talks only to its own server (HTTP); the server talks to Azure.
Microphone and hotkey need ``sounddevice`` and ``keyboard`` — if they are
missing the client says so and the file mode still works.

Sign-in: the client holds no key. It signs the user in with Entra ID (MSAL,
``shared_core/client_auth.py``) and sends the access token to its server; the
server's own Azure identity is ``DefaultAzureCredential`` (Managed Identity).
"""

from __future__ import annotations

import argparse
import ctypes
import io
import sys
import threading
import time
import wave
from ctypes import wintypes
from pathlib import Path

import httpx

# shared_core liegt eine Ebene über dem App-Ordner; der Client nutzt daraus nur
# client_auth (MSAL), kein Azure-SDK.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_core.client_auth import AnmeldungFehlgeschlagen, auth_kopf  # noqa: E402

STANDARD_SERVER = "http://127.0.0.1:8101"


def _aufnehmen(*, sekunden: float | None, hotkey: str | None, samplerate: int = 16000) -> bytes:
    """Record 16 kHz mono PCM from the default microphone and return a WAV in memory."""
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise SystemExit("Mikrofon-Modus braucht 'sounddevice' (pip install sounddevice).") from exc
    stop = threading.Event()
    if hotkey:
        try:
            import keyboard
        except ImportError as exc:
            raise SystemExit("Hotkey-Modus braucht 'keyboard' (pip install keyboard).") from exc
        print(f"Aufnahme läuft — Hotkey '{hotkey}' erneut drücken zum Beenden.")
        keyboard.add_hotkey(hotkey, stop.set)
    else:
        print("Aufnahme läuft — Enter drücken zum Beenden.")
        threading.Thread(target=lambda: (input(), stop.set()), daemon=True).start()
    puffer = io.BytesIO()
    with wave.open(puffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(samplerate)
        start = time.monotonic()
        with sd.RawInputStream(samplerate=samplerate, channels=1, dtype="int16") as strom:
            while not stop.is_set():
                if sekunden is not None and time.monotonic() - start >= sekunden:
                    break
                daten, _ueberlauf = strom.read(512)
                wav.writeframes(bytes(daten))
    return puffer.getvalue()


def _in_zwischenablage(text: str) -> None:
    """Put text into the Windows clipboard as CF_UNICODETEXT (no extra package)."""
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    kern = ctypes.windll.kernel32
    user = ctypes.windll.user32
    kern.GlobalAlloc.restype = wintypes.HGLOBAL
    kern.GlobalLock.restype = ctypes.c_void_p
    daten = (text + "\0").encode("utf-16-le")
    speicher = kern.GlobalAlloc(GMEM_MOVEABLE, len(daten))
    zeiger = kern.GlobalLock(speicher)
    ctypes.memmove(zeiger, daten, len(daten))
    kern.GlobalUnlock(speicher)
    for _ in range(20):
        if user.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("Zwischenablage ist belegt.")
    try:
        user.EmptyClipboard()
        if not user.SetClipboardData(CF_UNICODETEXT, speicher):
            raise RuntimeError("SetClipboardData ist fehlgeschlagen.")
    finally:
        user.CloseClipboard()


def _strg_v() -> None:
    """Send Ctrl+V to the active window (auto-paste)."""
    VK_CONTROL, VK_V, KEYUP = 0x11, 0x56, 0x0002
    user = ctypes.windll.user32
    user.keybd_event(VK_CONTROL, 0, 0, 0)
    user.keybd_event(VK_V, 0, 0, 0)
    time.sleep(0.05)
    user.keybd_event(VK_V, 0, KEYUP, 0)
    user.keybd_event(VK_CONTROL, 0, KEYUP, 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="typeFREE — Azure Edition (Client)")
    quelle = parser.add_mutually_exclusive_group(required=True)
    quelle.add_argument("--datei", type=str, help="WAV-Datei transkribieren (Demo/Test)")
    quelle.add_argument("--mikrofon", action="store_true", help="vom Standard-Mikrofon aufnehmen")
    parser.add_argument("--sekunden", type=float, default=None, help="Aufnahmedauer (sonst: Enter beendet)")
    parser.add_argument("--hotkey", type=str, default=None, help="globaler Hotkey zum Beenden, z. B. 'alt+a'")
    parser.add_argument("--kontext", type=str, default="", help="bereits vorhandener Text als Kontext der Glättung")
    parser.add_argument("--server", type=str, default=STANDARD_SERVER, help="Server-URL")
    parser.add_argument("--einfuegen", action="store_true", help="Ergebnis in die Zwischenablage legen und Strg+V senden")
    args = parser.parse_args(argv)

    if args.datei:
        wav_bytes = Path(args.datei).read_bytes()
    else:
        wav_bytes = _aufnehmen(sekunden=args.sekunden, hotkey=args.hotkey)

    try:
        kopf = auth_kopf()
    except AnmeldungFehlgeschlagen as fehler:
        print(f"FEHLER: {fehler}")
        return 2
    try:
        antwort = httpx.post(
            f"{args.server.rstrip('/')}/api/v1/dictate",
            files={"audio": ("diktat.wav", wav_bytes, "audio/wav")},
            data={"context": args.kontext},
            headers=kopf,
            timeout=120.0,
        )
    except httpx.HTTPError as fehler:
        print(f"FEHLER: Server nicht erreichbar ({fehler}). Läuft der Dienst auf {args.server}?")
        return 2
    if antwort.status_code != 200:
        print(f"FEHLER {antwort.status_code}: {antwort.text}")
        return 1
    daten = antwort.json()
    print()
    print(f"Rohtext:   {daten.get('rohtext', '')}")
    if daten.get("geglaettet"):
        print(f"Geglättet: {daten['text']}  [{daten.get('provider')} / {daten.get('model')}]")
    else:
        print(f"Text:      {daten.get('text', '')}")
    if daten.get("hinweis"):
        print(f"Hinweis:   {daten['hinweis']}")
    if args.einfuegen and daten.get("text"):
        _in_zwischenablage(daten["text"])
        _strg_v()
        print("In das aktive Fenster eingefügt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
