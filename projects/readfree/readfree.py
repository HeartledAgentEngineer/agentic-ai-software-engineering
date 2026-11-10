"""readFREE: markierten Text mit Klaus vorlesen. Tray-Programm mit AltGr + Ö, Alt + Ö oder Alt + Shift + Ö.

Start:   pythonw readfree.py
Prüfen:  python readfree.py --pruefen
         (lädt alles, belegt die Tastenkombination kurz und beendet sich, ohne etwas zu senden)
"""
from __future__ import annotations

import ctypes
import logging
import logging.handlers
import os
import pathlib
import shutil
import sys
import threading
from ctypes import wintypes

import ausgabe
import erfassen
import fenster
import kern

log = logging.getLogger('readfree')

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
VK_OEM_3 = 0xC0      # Ö im deutschen Layout (gemessen mit VkKeyScanExW)
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
HOTKEY_ID = 1
# Der echte Griff ist AltGr + Ö; Windows meldet AltGr als Strg + Alt (wie bei typeFREE).
KOMBINATIONEN = (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, MOD_ALT | MOD_NOREPEAT, MOD_ALT | MOD_SHIFT | MOD_NOREPEAT)
EINZELINSTANZ = 'Local\\readFREE.Einzelinstanz'
ERROR_ALREADY_EXISTS = 183
ENDE_ARTEN = ('ende', 'gestoppt', 'fehler')


def daten_ordner() -> pathlib.Path:
    return pathlib.Path(os.environ['LOCALAPPDATA']) / 'hermes' / 'cache' / 'readfree'


def log_einrichten(ordner: pathlib.Path) -> None:
    ordner.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        ordner / 'readfree.log', maxBytes=200_000, backupCount=1, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def audio_ordner_leeren(ordner: pathlib.Path) -> None:
    """Reste eines abgestürzten Laufs: Audio soll nicht liegen bleiben."""
    shutil.rmtree(ordner, ignore_errors=True)
    ordner.mkdir(parents=True, exist_ok=True)


class Hotkey:
    """Eigener Faden mit Nachrichtenschleife; RegisterHotKey ist fadengebunden."""

    def __init__(self, bei_druck, user32=None):
        self._bei_druck = bei_druck
        if user32 is None:
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
            user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self._user32 = user32
        self._bereit = threading.Event()
        self._faden_id = 0
        self.belegt = False

    def starten(self, frist=3.0) -> bool:
        threading.Thread(target=self._schleife, name='hotkey', daemon=True).start()
        self._bereit.wait(frist)
        return self.belegt

    def beenden(self) -> None:
        if self._faden_id:
            self._user32.PostThreadMessageW(self._faden_id, WM_QUIT, 0, 0)

    def _anmelden(self) -> bool:
        """Meldet alle Kombinationen an; eine freie genügt zum Bedienen."""
        frei = [bool(self._user32.RegisterHotKey(None, kennung, mods, VK_OEM_3))
                for kennung, mods in enumerate(KOMBINATIONEN, HOTKEY_ID)]
        return any(frei)

    def _abmelden(self) -> None:
        for kennung, _ in enumerate(KOMBINATIONEN, HOTKEY_ID):
            self._user32.UnregisterHotKey(None, kennung)

    def _schleife(self) -> None:
        self._faden_id = ctypes.windll.kernel32.GetCurrentThreadId()
        self.belegt = self._anmelden()
        self._bereit.set()
        if not self.belegt:
            return
        nachricht = wintypes.MSG()
        while self._user32.GetMessageW(ctypes.byref(nachricht), None, 0, 0) > 0:
            if nachricht.message == WM_HOTKEY:
                threading.Thread(target=self._bei_druck, name='tastendruck', daemon=True).start()
        self._abmelden()


def baue_sitzung_fabrik(tts_holen, signal, ordner):
    def fabrik(bloecke, melde):
        tts = tts_holen()
        handle = signal.belegen()

        def melde_mit_freigabe(art, nummer, gesamt):
            if art in ENDE_ARTEN:
                signal.freigeben(handle)
            melde(art, nummer, gesamt)

        return kern.Sitzung(bloecke, tts.erzeuge, ausgabe.MciSpieler, ordner,
                            melde_mit_freigabe, von_aussen_gestoppt=signal.stopp_gesetzt)
    return fabrik


def tray_starten(vorleser, beenden):
    import pystray
    from PIL import Image, ImageDraw

    bild = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    malen = ImageDraw.Draw(bild)
    malen.ellipse((4, 4, 60, 60), fill=(47, 110, 186, 255))
    malen.polygon([(16, 26), (26, 26), (40, 14), (40, 50), (26, 38), (16, 38)], fill='white')
    menue = pystray.Menu(
        pystray.MenuItem('readFREE: AltGr + Ö', None, enabled=False),
        pystray.MenuItem(lambda _eintrag: 'Status: liest vor' if vorleser.laeuft else 'Status: bereit',
                         None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Stopp', lambda: vorleser.stoppen()),
        pystray.MenuItem('Beenden', lambda: beenden()),
    )
    icon = pystray.Icon('readfree', bild, 'readFREE: Klaus liest vor', menue)
    icon.run_detached()
    return icon


def einzelinstanz():
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    handle = kernel32.CreateMutexW(None, False, EINZELINSTANZ)
    return handle, ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def pruefen() -> int:
    """Selbsttest ohne Netz: Module, UI Automation, Tastenkombination."""
    erfassen.uia_vorbereiten()
    ausgabe.KlausSignal()
    hotkey = Hotkey(lambda: None)
    frei = hotkey.starten()
    hotkey.beenden()
    print('UI Automation: geladen')
    print('Tastenkombination AltGr + Ö / Alt + Ö / Alt + Shift + Ö:', 'frei' if frei else 'BELEGT')
    return 0 if frei else 1


def main() -> int:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    if '--pruefen' in sys.argv:
        return pruefen()

    handle, erste = einzelinstanz()
    if not erste:
        return 0
    daten = daten_ordner()
    audio = daten / 'audio'
    log_einrichten(daten)
    audio_ordner_leeren(audio)
    erfassen.uia_vorbereiten()

    tts_zwischenspeicher = []

    def tts_holen():
        if not tts_zwischenspeicher:
            tts_zwischenspeicher.append(ausgabe.echtes_tts())
        return tts_zwischenspeicher[0]

    anzeige = fenster.Anzeige(lambda: vorleser.pause_umschalten(), lambda: vorleser.stoppen())
    vorleser = kern.Vorleser(
        erfassen.echter_erfasser(),
        lambda text: tts_holen().vorbereiten(text),
        baue_sitzung_fabrik(tts_holen, ausgabe.KlausSignal(), audio),
        anzeige,
    )
    hotkey = Hotkey(vorleser.tastendruck)
    icon_halter = {}

    def beenden():
        hotkey.beenden()
        vorleser.stoppen()
        icon = icon_halter.get('icon')
        if icon is not None:
            icon.stop()
        anzeige.beenden()

    icon_halter['icon'] = tray_starten(vorleser, beenden)
    if hotkey.starten():
        log.info('Bereit: Tastenkombination belegt')
    else:
        log.warning('Tastenkombination ist schon belegt')
        anzeige.hinweis('AltGr + Ö ist von einem anderen Programm belegt.')
    anzeige.laufen()
    audio_ordner_leeren(audio)
    del handle
    return 0


if __name__ == '__main__':
    sys.exit(main())
