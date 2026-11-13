"""Die Markierung des Vordergrundfensters holen.

Zuerst UI Automation (liest die Auswahl, ohne die Zwischenablage zu berühren).
Nur wenn das nichts liefert: Kopierbefehl senden, Zwischenablage vorher vollständig
sichern und danach zurückschreiben. Die Sicherung nutzt das erprobte Modul aus
typeFREE. Windows-Aufrufe werden erst bei Benutzung geladen; die Tests reichen
Attrappen hinein und berühren die echte Zwischenablage nie.
"""
from __future__ import annotations

import ctypes
import logging
import pathlib
import sys
import threading
import time
from dataclasses import dataclass

from kern import Auswahl

try:
    import zwischenablage
except ImportError:   # Start aus dem Repo: das Modul liegt bei typeFREE.
    _hier = pathlib.Path(__file__).resolve().parents
    sys.path[:0] = [str(_hier[2] / '02_Softwareentwicklung_IT' / 'typeFREE' / 'windows'),
                    str(_hier[1] / 'typefree' / 'windows')]   # Layout des Portfolios
    import zwischenablage

log = logging.getLogger('readfree')

CF_UNICODETEXT = 13
UIA_ZEITGRENZE = 0.8
ELTERN_STUFEN = 5

# Dort bricht Strg+C ohne Auswahl ein laufendes Programm ab; Strg+Einfg kopiert nur.
TERMINAL_KLASSEN = frozenset({
    'consolewindowclass', 'cascadia_hosting_window_class', 'mintty', 'putty', 'virtualconsoleclass',
})
TERMINAL_PROZESSE = frozenset({
    'code.exe', 'code - insiders.exe', 'cursor.exe', 'windsurf.exe', 'antigravity.exe',
    'claude.exe', 'codex.exe', 'hermes.exe', 'windowsterminal.exe', 'wezterm-gui.exe', 'alacritty.exe',
})


# Hier gehört das Fenster einem anderen Prozess als die kopierten Daten.
HILFSPROZESS_KLASSEN = frozenset({'ApplicationFrameWindow', 'ConsoleWindowClass'})


def kopierbefehl(klasse: str, prozess: str) -> str:
    if klasse.lower() in TERMINAL_KLASSEN or prozess.lower() in TERMINAL_PROZESSE:
        return 'strg_einfg'
    return 'strg_c'


def text_aus_bytes(daten: bytes) -> str:
    text = daten.decode('utf-16-le', errors='replace')
    return text.split('\0', 1)[0]


class Kopierer:
    """Kopierbefehl mit Sicherung und Wiederherstellung.

    `api_fabrik` liefert je Durchgang eine frische API (die echte gehört zu einem
    Öffnen/Schließen). Gehört die neue Ablage einem anderen Prozess als dem
    Vordergrundfenster oder kommt sie nicht zur Ruhe, hat jemand anders kopiert:
    Dann bleibt sie, wie sie ist. Ist der Besitz unbekannt, gilt die Kopie als unsere.
    """

    def __init__(self, api_fabrik, druecke, fenster_info, frist=0.5, ruhe=0.04,
                 vordergrund_pid=lambda: None, besitzer_pid=lambda: None):
        self._vordergrund_pid = vordergrund_pid
        self._besitzer_pid = besitzer_pid
        self._api_fabrik = api_fabrik
        self._druecke = druecke
        self._fenster_info = fenster_info
        self._frist = frist
        self._ruhe = ruhe

    def hole(self) -> Auswahl:
        api = self._api_fabrik()
        if not zwischenablage._oeffnen(api):
            return Auswahl('', grund='sicherung')
        try:
            sicherung = zwischenablage._sichern(api)
        finally:
            api.CloseClipboard()
        if not sicherung.vollstaendig:
            log.info('Zwischenablage nicht sicherbar: kein Kopierbefehl')
            return Auswahl('', grund='sicherung')

        vorher = api.GetClipboardSequenceNumber()
        ziel_pid = self._vordergrund_pid()
        self._druecke(kopierbefehl(*self._fenster_info()))
        if not self._warte_auf_kopie(api, vorher):
            return Auswahl('', grund='keine')
        return self._lesen_und_zurueckgeben(sicherung, ziel_pid)

    def _warte_auf_kopie(self, api, vorher) -> bool:
        ende = time.monotonic() + self._frist
        while time.monotonic() < ende:
            if api.GetClipboardSequenceNumber() != vorher:
                return True
            time.sleep(0.01)
        return api.GetClipboardSequenceNumber() != vorher

    def _ruhig_oeffnen(self):
        """Öffnet erst, wenn die Kopie fertig ist; gibt die offene API oder None zurück.

        Programme schreiben in mehreren Schüben, und Leeren und Schließen zählen die
        Nummer getrennt hoch (gemessen: über 20 ms verteilt, mit Lücke). Fertig ist
        die Kopie, wenn zwei Öffnungen nacheinander dieselbe Nummer sehen: Solange
        ein Programm schreibt, ist die Zwischenablage für uns gesperrt.
        """
        ende = time.monotonic() + self._frist
        letzte = None
        while True:
            api = self._api_fabrik()
            if zwischenablage._oeffnen(api):
                nummer = api.GetClipboardSequenceNumber()
                if nummer == letzte:
                    return api
                api.CloseClipboard()
                letzte = nummer
            if time.monotonic() >= ende:
                return None
            if self._ruhe:
                time.sleep(self._ruhe)

    def _ist_fremd(self, ziel_pid) -> bool:
        """Die Nummer sagt nicht, wer kopiert hat; der Besitzer der Ablage schon."""
        besitzer = self._besitzer_pid()
        return ziel_pid is not None and besitzer is not None and besitzer != ziel_pid

    def _lesen_und_zurueckgeben(self, sicherung, ziel_pid=None) -> Auswahl:
        api = self._ruhig_oeffnen()
        if api is None:
            log.warning('Zwischenablage kam nicht zur Ruhe: bleibt, wie sie ist')
            return Auswahl('', grund='keine')
        try:
            if self._ist_fremd(ziel_pid):
                log.warning('Kopie gehört einem anderen Programm: bleibt liegen')
                return Auswahl('', grund='keine')
            try:
                text = self._text_lesen(api)
            except Exception as fehler:   # Die Rückgabe darf daran nicht scheitern.
                log.warning('Kopierter Text nicht lesbar: %s', type(fehler).__name__)
                text = ''
            if not zwischenablage._zurueckschreiben(api, sicherung):
                log.warning('Zwischenablage nicht vollständig zurückgeschrieben')
        finally:
            api.CloseClipboard()
        return Auswahl(text, quelle='kopie') if text.strip() else Auswahl('', grund='keine')

    @staticmethod
    def _text_lesen(api) -> str:
        fmt = api.EnumClipboardFormats(0)
        while fmt:
            if fmt == CF_UNICODETEXT:
                return text_aus_bytes(api.lese(CF_UNICODETEXT, zwischenablage.MAX_GESAMT_BYTES))
            fmt = api.EnumClipboardFormats(fmt)
        return ''


@dataclass
class UiaErgebnis:
    text: str = ''
    rechteck: tuple | None = None
    passwort: bool = False


def erfasse(uia_lesen, kopierer) -> Auswahl:
    try:
        ergebnis = uia_lesen()
    except Exception as fehler:
        log.info('UI Automation fehlgeschlagen: %s', type(fehler).__name__)
        ergebnis = None
    if ergebnis is not None:
        if ergebnis.passwort:
            return Auswahl('', grund='passwort')
        if ergebnis.text.strip():
            return Auswahl(ergebnis.text, ergebnis.rechteck, 'uia')
    return kopierer.hole()


def mit_zeitgrenze(funktion, sekunden):
    """UI Automation kann in fremden Programmen hängen: nie länger darauf warten."""
    ablage = []
    fehler = []

    def lauf():
        try:
            ablage.append(funktion())
        except Exception as ausnahme:
            fehler.append(ausnahme)

    faden = threading.Thread(target=lauf, name='uia-lesen', daemon=True)
    faden.start()
    faden.join(sekunden)
    if fehler:
        raise fehler[0]
    return ablage[0] if ablage else None


def rechteck_aus(werte) -> tuple | None:
    """Fasst die Zeilen-Rechtecke (x, y, b, h, …) zu einem umschließenden zusammen."""
    if not werte or len(werte) < 4:
        return None
    links, oben, rechts, unten = None, None, None, None
    for stelle in range(0, len(werte) - 3, 4):
        x, y, breite, hoehe = werte[stelle:stelle + 4]
        links = x if links is None else min(links, x)
        oben = y if oben is None else min(oben, y)
        rechts = x + breite if rechts is None else max(rechts, x + breite)
        unten = y + hoehe if unten is None else max(unten, y + hoehe)
    return (links, oben, rechts - links, unten - oben)


def warte_auf_losgelassen(unten, frist=0.8, takt=0.01) -> bool:
    ende = time.monotonic() + frist
    while unten():
        if time.monotonic() >= ende:
            return False
        time.sleep(takt)
    return True


# ── Echte Windows-Anbindung (in den Tests nicht geladen) ─────────────────────

UIA_TEXT_PATTERN = 10014
_UIA_CLSID = '{ff48dba4-60ef-4201-aa87-54103eef594e}'
VK_MENU, VK_SHIFT, VK_CONTROL, VK_INSERT, VK_C, VK_OEM_3 = 0x12, 0x10, 0x11, 0x2D, 0x43, 0xC0
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x1, 0x2
PROCESS_QUERY_LIMITED = 0x1000
MODIFIKATOR_TASTEN = (VK_MENU, VK_CONTROL, VK_SHIFT, VK_OEM_3)   # AltGr meldet Strg + Alt.


def uia_vorbereiten() -> None:
    """Lädt comtypes im Mehrfaden-Modus; erzeugt beim ersten Mal die Typbibliothek."""
    sys.coinit_flags = 0   # COINIT_MULTITHREADED, muss vor dem Import stehen.
    import comtypes.client
    comtypes.client.GetModule('UIAutomationCore.dll')


def _uia_lesen_roh() -> UiaErgebnis:
    import comtypes
    import comtypes.client
    from comtypes.gen import UIAutomationClient as uiac

    comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
    uia = comtypes.client.CreateObject(_UIA_CLSID, interface=uiac.IUIAutomation)
    element = uia.GetFocusedElement()
    if not element:
        return UiaErgebnis()
    if element.CurrentIsPassword:
        return UiaErgebnis(passwort=True)

    pruefer = uia.ControlViewWalker
    for _ in range(ELTERN_STUFEN + 1):
        muster = element.GetCurrentPattern(UIA_TEXT_PATTERN)
        if muster:
            return _auswahl_lesen(muster.QueryInterface(uiac.IUIAutomationTextPattern))
        element = pruefer.GetParentElement(element)
        if not element:
            break
    return UiaErgebnis()


def _auswahl_lesen(muster) -> UiaErgebnis:
    bereiche = muster.GetSelection()
    if not bereiche:
        return UiaErgebnis()
    texte, rechtecke = [], []
    for stelle in range(bereiche.Length):
        bereich = bereiche.GetElement(stelle)
        texte.append(bereich.GetText(-1))
        rechtecke.extend(bereich.GetBoundingRectangles() or ())
    return UiaErgebnis(text='\n'.join(t for t in texte if t), rechteck=rechteck_aus(rechtecke))


def uia_lesen() -> UiaErgebnis | None:
    return mit_zeitgrenze(_uia_lesen_roh, UIA_ZEITGRENZE)


def _taste(vk, loslassen=False, erweitert=False) -> None:
    flags = (KEYEVENTF_KEYUP if loslassen else 0) | (KEYEVENTF_EXTENDEDKEY if erweitert else 0)
    ctypes.windll.user32.keybd_event(vk, 0, flags, 0)


def druecke(kombination: str) -> None:
    einfg = kombination == 'strg_einfg'
    vk = VK_INSERT if einfg else VK_C
    _taste(VK_CONTROL)
    _taste(vk, erweitert=einfg)
    _taste(vk, loslassen=True, erweitert=einfg)
    _taste(VK_CONTROL, loslassen=True)


def fenster_info() -> tuple[str, str]:
    """(Fensterklasse, Prozessname) des Vordergrundfensters."""
    from ctypes import wintypes

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    hwnd = user32.GetForegroundWindow()
    klasse = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, klasse, 256)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    prozess = ''
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid.value)
    if handle:
        pfad = ctypes.create_unicode_buffer(1024)
        laenge = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, pfad, ctypes.byref(laenge)):
            prozess = pfad.value.rsplit('\\', 1)[-1]
        kernel32.CloseHandle(handle)
    return klasse.value, prozess


def _pid_von(hwnd) -> int | None:
    from ctypes import wintypes

    if not hwnd:
        return None
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value or None


def vordergrund_pid() -> int | None:
    """Prozess des Vordergrundfensters; None, wo ein Hilfsprozess die Ablage besitzt."""
    from ctypes import wintypes

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    klasse, _ = fenster_info()
    if klasse in HILFSPROZESS_KLASSEN:
        return None
    return _pid_von(user32.GetForegroundWindow())


def besitzer_pid() -> int | None:
    from ctypes import wintypes

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetClipboardOwner.restype = wintypes.HWND
    return _pid_von(user32.GetClipboardOwner())


def tasten_unten() -> bool:
    abfrage = ctypes.windll.user32.GetAsyncKeyState
    return any(abfrage(vk) & 0x8000 for vk in MODIFIKATOR_TASTEN)


class WartenderKopierer:
    """Sendet den Kopierbefehl erst, wenn alle Tasten der Kombination oben sind."""

    def __init__(self, kopierer, unten=tasten_unten):
        self._kopierer = kopierer
        self._unten = unten

    def hole(self) -> Auswahl:
        if not warte_auf_losgelassen(self._unten):
            return Auswahl('', grund='tasten')
        return self._kopierer.hole()


def echter_erfasser():
    kopierer = WartenderKopierer(Kopierer(
        zwischenablage.standard_api, druecke, fenster_info,
        vordergrund_pid=vordergrund_pid, besitzer_pid=besitzer_pid))
    return lambda: erfasse(uia_lesen, kopierer)
