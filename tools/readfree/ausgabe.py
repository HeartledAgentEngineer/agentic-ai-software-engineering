"""Sprachsynthese über den vorhandenen Klaus-Client und Abspielen per MCI."""
from __future__ import annotations

import ctypes
import importlib.util
import itertools
import os
import pathlib

from kern import Meldung

_alias_nummern = itertools.count(1)
KLAUS_BELEGT = 'Local\\Klaus.Sprachausgabe'
KLAUS_STOPP = 'Local\\Klaus.Sprachausgabe.Stopp'


class TtsFehler(Meldung):
    """Vorlesen unmöglich. Der Text nennt nie den markierten Inhalt."""


def hermes_ordner() -> pathlib.Path:
    return pathlib.Path(os.environ['LOCALAPPDATA']) / 'hermes'


def lade_client(pfad=None):
    pfad = pathlib.Path(pfad or hermes_ordner() / 'tts' / 'openrouter_mai.py')
    if not pfad.exists():
        raise TtsFehler('Der Klaus-Client openrouter_mai.py fehlt.')
    spec = importlib.util.spec_from_file_location('openrouter_mai', pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def tts_schluessel(env_datei) -> str:
    """Nur der eigene Vorlese-Schlüssel, nie der allgemeine Chat-Schlüssel."""
    try:
        zeilen = pathlib.Path(env_datei).read_text(encoding='utf-8', errors='ignore').splitlines()
    except OSError as fehler:
        raise TtsFehler('Die Schlüsseldatei ist nicht lesbar.') from fehler
    for zeile in zeilen:
        if zeile.startswith('OPENROUTER_TTS_KEY='):
            wert = zeile.split('=', 1)[1].strip().strip('"\'')
            if wert:
                return wert
    raise TtsFehler('Der Vorlese-Schlüssel OPENROUTER_TTS_KEY fehlt.')


class KlausTts:
    def __init__(self, client, schluessel):
        self._client = client
        self._schluessel = schluessel

    def vorbereiten(self, text: str) -> str:
        return self._client.vorbereiten(text)

    def erzeuge(self, block: str) -> bytes:
        try:
            daten = self._client.sprechen(block, self._schluessel, self._client.MODELL, self._client.STIMME)
        except SystemExit:   # So meldet der Client Fehler; die Meldung kann Inhalte enthalten.
            raise TtsFehler('OpenRouter hat die Sprachausgabe abgelehnt.') from None
        if not daten:
            raise TtsFehler('OpenRouter lieferte keine Audiodaten.')
        return daten


def echtes_tts() -> KlausTts:
    client = lade_client()
    return KlausTts(client, tts_schluessel(client.ENV))


def _mci_senden(befehl: str) -> tuple[int, str]:
    puffer = ctypes.create_unicode_buffer(256)
    fehler = ctypes.windll.winmm.mciSendStringW(befehl, puffer, 255, None)
    return fehler, puffer.value


class MciSpieler:
    """Spielt eine MP3-Datei. Alle Aufrufe müssen aus demselben Faden kommen."""

    def __init__(self, mci=_mci_senden):
        self._mci = mci
        self.alias = f'klaus{next(_alias_nummern)}'

    def _pflicht(self, befehl: str) -> None:
        fehler, _ = self._mci(befehl)
        if fehler:
            raise TtsFehler(f'Audio-Wiedergabe fehlgeschlagen (MCI {fehler}).')

    def oeffnen(self, pfad) -> None:
        self._pflicht(f'open "{pfad}" type mpegvideo alias {self.alias}')

    def spielen(self) -> None:
        self._pflicht(f'play {self.alias}')

    def laeuft(self) -> bool:
        _, zustand = self._mci(f'status {self.alias} mode')
        return zustand.lower() in ('playing', 'paused', 'seeking', 'not ready')

    def pausieren(self) -> None:
        self._mci(f'pause {self.alias}')

    def fortsetzen(self) -> None:
        self._mci(f'resume {self.alias}')

    def stoppen(self) -> None:
        self._mci(f'stop {self.alias}')

    def schliessen(self) -> None:
        self._mci(f'close {self.alias}')


class KlausSignal:
    """Gemeinsames Signal gegen überlagerte Klaus-Ausgaben.

    Der Mutex `Local\\Klaus.Sprachausgabe` existiert, solange vorgelesen wird. Das
    Ereignis `Local\\Klaus.Sprachausgabe.Stopp` (automatisch zurückgesetzt) beendet
    die Ausgabe von außen.
    """

    def __init__(self):
        from ctypes import wintypes
        self._k = ctypes.WinDLL('kernel32', use_last_error=True)
        self._k.CreateMutexW.restype = wintypes.HANDLE
        self._k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self._k.CreateEventW.restype = wintypes.HANDLE
        self._k.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        self._k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self._k.WaitForSingleObject.restype = wintypes.DWORD
        self._k.CloseHandle.argtypes = [wintypes.HANDLE]
        self._ereignis = self._k.CreateEventW(None, False, False, KLAUS_STOPP)

    def belegen(self):
        return self._k.CreateMutexW(None, False, KLAUS_BELEGT)

    def freigeben(self, handle) -> None:
        if handle:
            self._k.CloseHandle(handle)

    def stopp_gesetzt(self) -> bool:
        return bool(self._ereignis) and self._k.WaitForSingleObject(self._ereignis, 0) == 0
