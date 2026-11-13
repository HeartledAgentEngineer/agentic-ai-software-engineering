"""Markierung holen: UIA zuerst, Kopier-Rückfall mit Wiederherstellung.

Die Zwischenablage ist hier immer eine Attrappe; alle Texte sind erfunden.
"""
import pytest

import erfassen
from erfassen import UiaErgebnis

CF_UNICODETEXT = 13
CF_DIB = 8
CF_BITMAP = 2
EIGENES_FORMAT = 0xC123


def utf16(text):
    return (text + '\0').encode('utf-16-le')


class FakeAblage:
    """Verhält sich wie die Windows-Zwischenablage; die Sequenznummer zählt mit."""

    def __init__(self, inhalt=None, oeffnen_klappt=True):
        self.inhalt = dict(inhalt or {})
        self.nummer = 100
        self.offen = False
        self.oeffnen_klappt = oeffnen_klappt
        self.nach_oeffnen = None

    def OpenClipboard(self):
        if not self.oeffnen_klappt:
            return False
        self.offen = True
        if self.nach_oeffnen:
            self.nach_oeffnen()
        return True

    def CloseClipboard(self):
        self.offen = False
        return True

    def EmptyClipboard(self):
        assert self.offen
        self.inhalt = {}
        self.nummer += 1
        return True

    def EnumClipboardFormats(self, vorher):
        formate = list(self.inhalt)
        if vorher == 0:
            return formate[0] if formate else 0
        stelle = formate.index(vorher) + 1
        return formate[stelle] if stelle < len(formate) else 0

    def GetClipboardSequenceNumber(self):
        return self.nummer

    def lese(self, fmt, limit):
        assert self.offen
        return self.inhalt[fmt]

    def setze(self, fmt, daten):
        assert self.offen
        self.inhalt[fmt] = daten
        self.nummer += 1
        return True

    def kopiere_von_aussen(self, text):
        self.inhalt = {CF_UNICODETEXT: utf16(text)}
        self.nummer += 5


def kopierer(ablage, klasse='Notepad', prozess='notepad.exe', bei_druck=None, frist=0.05):
    gedrueckt = []

    def druecke(kombination):
        gedrueckt.append(kombination)
        if bei_druck:
            bei_druck()

    k = erfassen.Kopierer(lambda: ablage, druecke, lambda: (klasse, prozess), frist=frist, ruhe=0.0)
    return k, gedrueckt


VORHER = {CF_UNICODETEXT: utf16('Alter Inhalt'), CF_DIB: b'BILDDATEN', EIGENES_FORMAT: b'\x01\x02'}


def test_kopie_liefert_text_und_stellt_alle_formate_wieder_her():
    ablage = FakeAblage(VORHER)
    k, gedrueckt = kopierer(ablage, bei_druck=lambda: ablage.kopiere_von_aussen('Markierter Satz'))
    auswahl = k.hole()
    assert auswahl.text == 'Markierter Satz' and auswahl.quelle == 'kopie'
    assert gedrueckt == ['strg_c']
    assert ablage.inhalt == VORHER
    assert not ablage.offen


def test_leere_ablage_ist_danach_wieder_leer():
    ablage = FakeAblage({})
    k, _ = kopierer(ablage, bei_druck=lambda: ablage.kopiere_von_aussen('Markierter Satz'))
    assert k.hole().text == 'Markierter Satz'
    assert ablage.inhalt == {}


def test_keine_markierung_laesst_die_ablage_unberuehrt():
    ablage = FakeAblage(VORHER)
    k, _ = kopierer(ablage)
    nummer = ablage.nummer
    auswahl = k.hole()
    assert auswahl.text == '' and auswahl.grund == 'keine'
    assert ablage.inhalt == VORHER and ablage.nummer == nummer


def test_unvollstaendige_sicherung_kopiert_gar_nicht():
    ablage = FakeAblage({CF_BITMAP: b'nur-gdi'})
    k, gedrueckt = kopierer(ablage, bei_druck=lambda: pytest.fail('darf nicht drücken'))
    auswahl = k.hole()
    assert auswahl.grund == 'sicherung' and gedrueckt == []
    assert ablage.inhalt == {CF_BITMAP: b'nur-gdi'}


def test_belegte_ablage_kopiert_gar_nicht():
    ablage = FakeAblage(VORHER, oeffnen_klappt=False)
    k, gedrueckt = kopierer(ablage)
    assert k.hole().grund == 'sicherung' and gedrueckt == []


def test_kopie_in_mehreren_schueben_wird_gelesen_und_zurueckgestellt():
    """Gemessen an WPF: Leeren und Schließen zählen die Nummer getrennt hoch."""
    ablage = FakeAblage(VORHER)
    aufrufe = []

    def nach_oeffnen():
        aufrufe.append(1)
        if len(aufrufe) == 2:      # Der zweite Schub kommt, bevor wir öffnen konnten.
            ablage.kopiere_von_aussen('Markierter Satz')

    ablage.nach_oeffnen = nach_oeffnen
    k, _ = kopierer(ablage, bei_druck=lambda: ablage.kopiere_von_aussen('Erster Schub'))
    assert k.hole().text == 'Markierter Satz'
    assert ablage.inhalt == VORHER


def besitz_kopierer(ablage, ziel, besitzer, bei_druck):
    k = erfassen.Kopierer(lambda: ablage, lambda _kombi: bei_druck(), lambda: ('Notepad', 'notepad.exe'),
                          frist=0.05, ruhe=0.0, vordergrund_pid=lambda: ziel, besitzer_pid=lambda: besitzer)
    return k


def test_einmalige_fremde_kopie_bleibt_liegen_und_wird_nicht_gelesen():
    ablage = FakeAblage(VORHER)
    k = besitz_kopierer(ablage, 111, 222, lambda: ablage.kopiere_von_aussen('Von anderer App'))
    auswahl = k.hole()
    assert auswahl.text == '' and auswahl.grund == 'keine'
    assert ablage.inhalt == {CF_UNICODETEXT: utf16('Von anderer App')}
    assert not ablage.offen


def test_kopie_des_vordergrundprogramms_wird_zurueckgestellt():
    ablage = FakeAblage(VORHER)
    k = besitz_kopierer(ablage, 111, 111, lambda: ablage.kopiere_von_aussen('Markierter Satz'))
    assert k.hole().text == 'Markierter Satz'
    assert ablage.inhalt == VORHER


@pytest.mark.parametrize('ziel, besitzer', [(None, 222), (111, None), (None, None)])
def test_unbekannter_besitz_gilt_als_eigene_kopie(ziel, besitzer):
    ablage = FakeAblage(VORHER)
    k = besitz_kopierer(ablage, ziel, besitzer, lambda: ablage.kopiere_von_aussen('Markierter Satz'))
    assert k.hole().text == 'Markierter Satz'
    assert ablage.inhalt == VORHER


def test_lesefehler_stellt_trotzdem_zurueck():
    class KaputteAblage(FakeAblage):
        def lese(self, fmt, limit):
            if self.inhalt.get(CF_UNICODETEXT) == utf16('Markierter Satz'):
                raise OSError('Lesefehler')
            return super().lese(fmt, limit)

    ablage = KaputteAblage(VORHER)
    k, _ = kopierer(ablage, bei_druck=lambda: ablage.kopiere_von_aussen('Markierter Satz'))
    assert k.hole().grund == 'keine'
    assert ablage.inhalt == VORHER and not ablage.offen


def test_laufend_fremdes_kopieren_bleibt_liegen():
    ablage = FakeAblage(VORHER)
    aufrufe = []

    def nach_oeffnen():
        aufrufe.append(1)
        if len(aufrufe) >= 2:      # Die Nummer kommt nie zur Ruhe.
            ablage.kopiere_von_aussen(f'Von anderer App {len(aufrufe)}')

    ablage.nach_oeffnen = nach_oeffnen
    k, _ = kopierer(ablage, bei_druck=lambda: ablage.kopiere_von_aussen('Markierter Satz'))
    auswahl = k.hole()
    assert auswahl.text == ''
    assert erfassen.text_aus_bytes(ablage.inhalt[CF_UNICODETEXT]).startswith('Von anderer App')
    assert not ablage.offen


def test_kopie_ohne_textformat_gilt_als_keine_markierung_und_wird_zurueckgestellt():
    ablage = FakeAblage(VORHER)

    def nur_bild():
        ablage.inhalt = {CF_DIB: b'ANDERES-BILD'}
        ablage.nummer += 1

    k, _ = kopierer(ablage, bei_druck=nur_bild)
    assert k.hole().grund == 'keine'
    assert ablage.inhalt == VORHER


@pytest.mark.parametrize('klasse, prozess, erwartet', [
    ('ConsoleWindowClass', 'cmd.exe', 'strg_einfg'),
    ('CASCADIA_HOSTING_WINDOW_CLASS', 'WindowsTerminal.exe', 'strg_einfg'),
    ('mintty', 'mintty.exe', 'strg_einfg'),
    ('Chrome_WidgetWin_1', 'Code.exe', 'strg_einfg'),
    ('Chrome_WidgetWin_1', 'code.EXE', 'strg_einfg'),
    ('Chrome_WidgetWin_1', 'Cursor.exe', 'strg_einfg'),
    ('Chrome_WidgetWin_1', 'comet.exe', 'strg_c'),
    ('Notepad', 'notepad.exe', 'strg_c'),
])
def test_terminals_bekommen_strg_einfg(klasse, prozess, erwartet):
    assert erfassen.kopierbefehl(klasse, prozess) == erwartet


# ── Reihenfolge UIA → Kopie ──────────────────────────────────────────────────

class ZaehlKopierer:
    def __init__(self):
        self.aufrufe = 0

    def hole(self):
        self.aufrufe += 1
        return erfassen.Auswahl('Aus der Kopie', quelle='kopie')


def test_uia_treffer_braucht_keine_kopie():
    k = ZaehlKopierer()
    auswahl = erfassen.erfasse(lambda: UiaErgebnis(text='Aus UIA', rechteck=(1, 2, 3, 4)), k)
    assert auswahl.text == 'Aus UIA' and auswahl.quelle == 'uia' and auswahl.rechteck == (1, 2, 3, 4)
    assert k.aufrufe == 0


def test_passwortfeld_bricht_ohne_rueckfall_ab():
    k = ZaehlKopierer()
    auswahl = erfassen.erfasse(lambda: UiaErgebnis(passwort=True), k)
    assert auswahl.text == '' and auswahl.grund == 'passwort'
    assert k.aufrufe == 0


@pytest.mark.parametrize('ergebnis', [None, UiaErgebnis(text='   ')])
def test_leeres_uia_faellt_auf_kopie_zurueck(ergebnis):
    k = ZaehlKopierer()
    assert erfassen.erfasse(lambda: ergebnis, k).text == 'Aus der Kopie'
    assert k.aufrufe == 1


def test_uia_ausnahme_faellt_auf_kopie_zurueck():
    def kaputt():
        raise OSError('com')

    k = ZaehlKopierer()
    assert erfassen.erfasse(kaputt, k).text == 'Aus der Kopie'


def test_zeitgrenze_liefert_none_bei_haenger():
    import threading
    halt = threading.Event()
    try:
        assert erfassen.mit_zeitgrenze(lambda: halt.wait(5), 0.02) is None
    finally:
        halt.set()


def test_zeitgrenze_liefert_ergebnis():
    assert erfassen.mit_zeitgrenze(lambda: 'ok', 1.0) == 'ok'


# ── Rechteck und Warten auf die Tasten ───────────────────────────────────────

def test_rechteck_umfasst_alle_zeilen():
    assert erfassen.rechteck_aus((10, 20, 100, 15, 5, 40, 50, 15)) == (5, 20, 105, 35)


@pytest.mark.parametrize('leer', [None, (), (1, 2, 3)])
def test_rechteck_ohne_daten(leer):
    assert erfassen.rechteck_aus(leer) is None


def test_tasten_losgelassen():
    zustaende = iter([True, True, False])
    assert erfassen.warte_auf_losgelassen(lambda: next(zustaende), frist=1.0, takt=0.0)


def test_tasten_bleiben_gedrueckt():
    assert not erfassen.warte_auf_losgelassen(lambda: True, frist=0.02, takt=0.001)
