"""Reine Logik des Vorlesers: Stückeln, Umschalten, blockweise Ausgabe.

Kein Windows-Aufruf und kein Netz: Spieler, Sprachsynthese und Anzeige kommen von
außen herein. Logzeilen enthalten nie markierten Text, nur Längen und Fehlerarten.
"""
from __future__ import annotations

import enum
import itertools
import logging
import queue
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger('readfree')

ERST_MAX = 150
FOLGE_MAX = 280
ABKUERZUNGEN = (
    'z. B.', 'z.B.', 'd. h.', 'd.h.', 'bzw.', 'usw.', 'ca.', 'Dr.', 'Prof.',
    'Nr.', 'vs.', 'vgl.', 'inkl.', 'evtl.', 'e.g.', 'i.e.', 'etc.', 'Abb.', 'Tab.',
)
HINWEISE = {
    'passwort': 'Passwortfelder werden nicht vorgelesen.',
    'sicherung': 'Zwischenablage ließ sich nicht sichern, deshalb nichts kopiert.',
    'tasten': 'Bitte die Tasten loslassen und noch einmal drücken.',
}
HINWEIS_STANDARD = 'Keine Markierung gefunden.'


class Meldung(Exception):
    """Fehler, dessen Text dem Nutzer gezeigt werden darf (enthält nie Inhalte)."""


class Aktion(enum.Enum):
    STARTEN = 'starten'
    STOPPEN = 'stoppen'
    ERSETZEN = 'ersetzen'
    HINWEIS = 'hinweis'


@dataclass
class Auswahl:
    text: str
    rechteck: tuple | None = None
    quelle: str = ''
    grund: str = ''


def normalisiere(text: str) -> str:
    return ' '.join(text.split())


def entscheide(laeuft: bool, aktueller_text: str, auswahl: str) -> Aktion:
    neu = normalisiere(auswahl)
    if not laeuft:
        return Aktion.STARTEN if neu else Aktion.HINWEIS
    if not neu or neu == normalisiere(aktueller_text):
        return Aktion.STOPPEN
    return Aktion.ERSETZEN


def _wortweise(text: str, grenze: int) -> list[str]:
    """Teilt an Wortgrenzen; ein einzelnes überlanges Wort wird hart geteilt."""
    teile, laufend = [], ''
    for wort in text.split(' '):
        while len(wort) > grenze:
            if laufend:
                teile.append(laufend)
                laufend = ''
            teile.append(wort[:grenze])
            wort = wort[grenze:]
        if laufend and len(laufend) + 1 + len(wort) > grenze:
            teile.append(laufend)
            laufend = wort
        else:
            laufend = f'{laufend} {wort}' if laufend else wort
    if laufend:
        teile.append(laufend)
    return teile


def _einheiten(text: str, folge_max: int) -> list[str]:
    """Sätze; Überlanges zuerst an Satzzeichen, dann an Wortgrenzen geteilt."""
    geschuetzt = text
    for nummer, kuerzel in enumerate(ABKUERZUNGEN):
        geschuetzt = geschuetzt.replace(kuerzel, f'\x00{nummer}\x00')

    einheiten: list[str] = []
    for absatz in filter(str.strip, geschuetzt.splitlines()):
        for satz in re.split(r'(?<=[.!?])\s+', absatz.strip()):
            for nummer, kuerzel in enumerate(ABKUERZUNGEN):
                satz = satz.replace(f'\x00{nummer}\x00', kuerzel)
            satz = satz.strip()
            if not satz:
                continue
            if len(satz) <= folge_max:
                einheiten.append(satz)
                continue
            for teil in re.split(r'(?<=[,;:])\s+', satz):
                einheiten.extend(_wortweise(teil.strip(), folge_max))
    return einheiten


def stueckeln(text: str, erst_max: int = ERST_MAX, folge_max: int = FOLGE_MAX) -> list[str]:
    """Teilt in Blöcke; der erste ist kurz, damit Klaus schnell anfängt."""
    einheiten = _einheiten(text, folge_max)
    if einheiten and len(einheiten[0]) > erst_max:
        anfang = _wortweise(einheiten[0], erst_max)[0]
        rest = einheiten[0][len(anfang):].strip()
        einheiten[0:1] = [anfang] + ([rest] if rest else [])

    bloecke: list[str] = []
    laufend, grenze = '', erst_max
    for einheit in einheiten:
        if laufend and len(laufend) + 1 + len(einheit) > grenze:
            bloecke.append(laufend)
            laufend, grenze = einheit, folge_max
        else:
            laufend = f'{laufend} {einheit}' if laufend else einheit
        if len(laufend) >= grenze:
            bloecke.append(laufend)
            laufend, grenze = '', folge_max
    if laufend:
        bloecke.append(laufend)
    return bloecke


_nummern = itertools.count(1)


class Sitzung:
    """Eine Vorlese-Ausgabe: ein Faden holt Blöcke, einer spielt sie.

    Vor jeder Anforderung wird ein Platz belegt und erst beim Abspielen frei:
    außer dem laufenden Block liegen höchstens `vorlauf` Blöcke bereit. Ein Stopp
    fordert deshalb nichts mehr an, ein gerade laufender Aufruf wird verworfen.
    Alle Spieler-Aufrufe laufen im Wiedergabe-Faden (MCI ist fadengebunden).
    """

    def __init__(self, bloecke, erzeuge, spieler_fabrik, ordner, melde=None,
                 vorlauf=2, takt=0.05, von_aussen_gestoppt=None):
        self.bloecke = list(bloecke)
        self._erzeuge = erzeuge
        self._spieler_fabrik = spieler_fabrik
        self._ordner = Path(ordner)
        self._melde = melde or (lambda *_: None)
        self._takt = takt
        self._von_aussen = von_aussen_gestoppt or (lambda: False)
        self._kennung = f'sitzung{next(_nummern)}'
        self._plaetze = threading.Semaphore(vorlauf)
        self._fertig: queue.Queue = queue.Queue()
        self._stopp = threading.Event()
        self._pause = threading.Event()
        self._erledigt = threading.Event()
        self.fehler: BaseException | None = None

    @property
    def laeuft(self) -> bool:
        return not self._erledigt.is_set()

    @property
    def pausiert(self) -> bool:
        return self._pause.is_set()

    def starten(self) -> None:
        threading.Thread(target=self._holen, name='klaus-holen', daemon=True).start()
        threading.Thread(target=self._wiedergeben, name='klaus-spielen', daemon=True).start()

    def stoppen(self) -> None:
        self._stopp.set()

    def pause_umschalten(self) -> None:
        if self._pause.is_set():
            self._pause.clear()
        else:
            self._pause.set()

    def warten(self, frist=None) -> bool:
        return self._erledigt.wait(frist)

    def _holen(self) -> None:
        try:
            for nummer, block in enumerate(self.bloecke, 1):
                while not self._plaetze.acquire(timeout=self._takt):
                    if self._stopp.is_set():
                        return
                if self._stopp.is_set():
                    return
                daten = self._erzeuge(block)
                if self._stopp.is_set():
                    return
                pfad = self._ordner / f'{self._kennung}_{nummer:04d}.mp3'
                pfad.write_bytes(daten)
                self._fertig.put((nummer, pfad))
        except (Exception, SystemExit) as fehler:
            self.fehler = fehler
            log.warning('Block nicht erzeugt: %s', type(fehler).__name__)
        finally:
            self._fertig.put(None)
            if self._stopp.is_set():
                self._aufraeumen()

    def _wiedergeben(self) -> None:
        art = 'ende'
        try:
            spieler = self._spieler_fabrik()
            while not self._stopp_noetig():
                try:
                    eintrag = self._fertig.get(timeout=self._takt)
                except queue.Empty:
                    continue
                if eintrag is None:
                    break
                nummer, pfad = eintrag
                self._plaetze.release()
                try:
                    self._spielen(spieler, nummer, pfad)
                finally:
                    pfad.unlink(missing_ok=True)
        except Exception as fehler:
            self.fehler = fehler
            log.warning('Wiedergabe fehlgeschlagen: %s', type(fehler).__name__)
        if self._stopp.is_set():
            art = 'gestoppt'
            self._aufraeumen()
        elif self.fehler is not None:
            art = 'fehler'
            self._stopp.set()
            self._aufraeumen()
        self._erledigt.set()
        self._melde(art, 0, len(self.bloecke))

    def _stopp_noetig(self) -> bool:
        if not self._stopp.is_set() and self._von_aussen():
            self._stopp.set()
        return self._stopp.is_set()

    def _spielen(self, spieler, nummer, pfad) -> None:
        spieler.oeffnen(pfad)
        try:
            spieler.spielen()
            self._melde('block', nummer, len(self.bloecke))
            pausiert = False
            while True:
                if self._stopp_noetig():
                    spieler.stoppen()
                    return
                if self._pause.is_set() != pausiert:
                    pausiert = not pausiert
                    (spieler.pausieren if pausiert else spieler.fortsetzen)()
                    self._melde('pause' if pausiert else 'weiter', nummer, len(self.bloecke))
                if not pausiert and not spieler.laeuft():
                    return
                time.sleep(self._takt)
        finally:
            spieler.schliessen()

    def _aufraeumen(self) -> None:
        for pfad in self._ordner.glob(f'{self._kennung}_*.mp3'):
            try:
                pfad.unlink(missing_ok=True)
            except OSError:
                pass   # Der Wiedergabe-Faden löscht sie nach dem Schließen selbst.


class Vorleser:
    """Setzt den Tastendruck in Starten, Stoppen oder Ersetzen um."""

    def __init__(self, erfasse, vorbereiten, sitzung_fabrik, anzeige):
        self._erfasse = erfasse
        self._vorbereiten = vorbereiten
        self._sitzung_fabrik = sitzung_fabrik
        self._anzeige = anzeige
        self._sitzung = None
        self._text = ''
        self._sperre = threading.Lock()

    @property
    def laeuft(self) -> bool:
        return self._sitzung is not None and self._sitzung.laeuft

    def tastendruck(self) -> None:
        if not self._sperre.acquire(blocking=False):
            return   # Die vorige Erfassung läuft noch.
        try:
            self._verarbeite_druck()
        except Meldung as meldung:
            log.info('Hinweis gezeigt: %s', type(meldung).__name__)
            self._anzeige.hinweis(str(meldung))
        except Exception as fehler:
            log.warning('Tastendruck fehlgeschlagen: %s', type(fehler).__name__)
            self.stoppen()   # Sonst bliebe eine beim Druck pausierte Ausgabe stumm stehen.
            self._anzeige.hinweis('Vorlesen ist fehlgeschlagen.')
        finally:
            self._sperre.release()

    def _verarbeite_druck(self) -> None:
        sitzung = self._sitzung if self.laeuft else None
        if sitzung is not None and not sitzung.pausiert:
            sitzung.pause_umschalten()   # Sofort still, auch wenn die Erfassung dauert.
        auswahl = self._erfasse()
        aktion = entscheide(sitzung is not None, self._text, auswahl.text)
        log.info('Tastendruck: %s, %d Zeichen, Quelle %s',
                 aktion.value, len(auswahl.text), auswahl.quelle or auswahl.grund or '-')
        if aktion is Aktion.HINWEIS:
            self._anzeige.hinweis(HINWEISE.get(auswahl.grund, HINWEIS_STANDARD), auswahl.rechteck)
        elif aktion is Aktion.STOPPEN:
            self.stoppen()
        else:
            if sitzung is not None:
                sitzung.stoppen()
                self._sitzung = None
            self._starten(auswahl)

    def _starten(self, auswahl: Auswahl) -> None:
        bloecke = stueckeln(self._vorbereiten(auswahl.text))
        if not bloecke:
            self._anzeige.verbergen()
            self._anzeige.hinweis(HINWEIS_STANDARD, auswahl.rechteck)
            return
        halter = {}

        def melde(art, nummer, gesamt):
            self._ereignis(halter.get('sitzung'), art, nummer, gesamt)

        sitzung = self._sitzung_fabrik(bloecke, melde)
        halter['sitzung'] = sitzung
        self._sitzung = sitzung
        self._text = auswahl.text
        log.info('Vorlesen startet: %d Zeichen, %d Blöcke', len(auswahl.text), len(bloecke))
        self._anzeige.start(auswahl.rechteck)
        sitzung.starten()

    def _ereignis(self, sitzung, art, nummer, gesamt) -> None:
        if sitzung is not self._sitzung:
            return   # Eine ersetzte Sitzung darf die neue Anzeige nicht schließen.
        if art == 'block':
            self._anzeige.fortschritt(nummer, gesamt)
        elif art in ('pause', 'weiter'):
            self._anzeige.pause(art == 'pause')
        elif art == 'fehler':
            self._sitzung = None
            self._anzeige.hinweis('Klaus konnte nicht weiterlesen.')
        else:
            self._sitzung = None
            self._anzeige.verbergen()

    def stoppen(self) -> None:
        sitzung, self._sitzung = self._sitzung, None
        if sitzung is not None:
            sitzung.stoppen()
        self._anzeige.verbergen()

    def pause_umschalten(self) -> None:
        if self.laeuft:
            self._sitzung.pause_umschalten()
