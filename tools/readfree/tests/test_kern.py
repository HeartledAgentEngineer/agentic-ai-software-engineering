"""Stückeln, Umschalten und Vorlauf. Alle Texte sind erfunden."""
import logging
import threading
import time

import pytest

import kern
from kern import Aktion, entscheide, stueckeln


# ── Stückeln ─────────────────────────────────────────────────────────────────

def test_erster_block_ist_kurz_und_folgende_bleiben_unter_der_grenze():
    text = ' '.join(f'Das ist der erfundene Satz Nummer {i} für den Test.' for i in range(40))
    bloecke = stueckeln(text)
    assert len(bloecke[0]) <= 150
    assert all(len(b) <= 280 for b in bloecke)
    assert ' '.join(bloecke) == text


def test_abkuerzungen_teilen_keinen_satz():
    text = 'Wir nehmen z. B. einen Apfel. Dann folgt der zweite Satz.'
    assert stueckeln(text, erst_max=30, folge_max=40)[0].startswith('Wir nehmen z. B. einen Apfel.')


def test_langer_satz_ohne_satzzeichen_wird_an_wortgrenzen_geteilt():
    text = ' '.join(['Wort'] * 300)
    bloecke = stueckeln(text)
    assert all(len(b) <= 280 for b in bloecke)
    assert ' '.join(bloecke) == text


def test_ueberlanges_einzelwort_wird_hart_geteilt():
    bloecke = stueckeln('x' * 700)
    assert all(len(b) <= 280 for b in bloecke)
    assert ''.join(bloecke) == 'x' * 700


@pytest.mark.parametrize('leer', ['', '   ', '\n\n'])
def test_leerer_text_ergibt_keine_bloecke(leer):
    assert stueckeln(leer) == []


# ── Entscheidung beim Tastendruck ────────────────────────────────────────────

@pytest.mark.parametrize('laeuft, aktuell, auswahl, erwartet', [
    (False, '', 'Neuer Text', Aktion.STARTEN),
    (False, '', '', Aktion.HINWEIS),
    (False, '', '   ', Aktion.HINWEIS),
    (True, 'Alter Text', '', Aktion.STOPPEN),
    (True, 'Alter Text', 'Alter Text', Aktion.STOPPEN),
    (True, 'Alter  Text\n', 'Alter Text', Aktion.STOPPEN),
    (True, 'Alter Text', 'Anderer Text', Aktion.ERSETZEN),
])
def test_entscheide(laeuft, aktuell, auswahl, erwartet):
    assert entscheide(laeuft, aktuell, auswahl) is erwartet


# ── Sitzung ──────────────────────────────────────────────────────────────────

class FakeSpieler:
    """Spielt, bis `freigabe` gesetzt ist, oder sofort durch."""

    def __init__(self, protokoll, freigabe=None):
        self.protokoll = protokoll
        self.freigabe = freigabe
        self.aktuell = None

    def oeffnen(self, pfad):
        self.aktuell = pfad

    def spielen(self):
        self.protokoll.append(('spielen', self.aktuell.read_bytes()))

    def laeuft(self):
        return bool(self.freigabe) and not self.freigabe.is_set()

    def pausieren(self):
        self.protokoll.append(('pause', None))

    def fortsetzen(self):
        self.protokoll.append(('weiter', None))

    def stoppen(self):
        self.protokoll.append(('stopp', None))

    def schliessen(self):
        self.protokoll.append(('zu', None))


def baue(tmp_path, bloecke, erzeuge=None, freigabe=None, **weiter):
    protokoll, meldungen, erzeugt = [], [], []

    def standard(block):
        erzeugt.append(block)
        return block.encode()

    sitzung = kern.Sitzung(
        bloecke, erzeuge or standard, lambda: FakeSpieler(protokoll, freigabe), tmp_path,
        lambda art, nr, gesamt: meldungen.append((art, nr, gesamt)), takt=0.005, **weiter)
    return sitzung, protokoll, meldungen, erzeugt


def warte_bis(bedingung, frist=3.0):
    ende = time.monotonic() + frist
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.005)
    return False


def test_bloecke_laufen_in_reihenfolge_und_dateien_verschwinden(tmp_path):
    sitzung, protokoll, meldungen, _ = baue(tmp_path, ['eins', 'zwei', 'drei'])
    sitzung.starten()
    assert sitzung.warten(3)
    assert [d for a, d in protokoll if a == 'spielen'] == [b'eins', b'zwei', b'drei']
    assert meldungen[-1] == ('ende', 0, 3)
    assert list(tmp_path.iterdir()) == []


def test_vorlauf_holt_hoechstens_zwei_bloecke_voraus(tmp_path):
    freigabe = threading.Event()
    sitzung, _, _, erzeugt = baue(tmp_path, [f'b{i}' for i in range(10)], freigabe=freigabe)
    sitzung.starten()
    assert warte_bis(lambda: len(erzeugt) == 3)
    time.sleep(0.05)
    assert len(erzeugt) == 3   # einer spielt, zwei warten
    sitzung.stoppen()
    assert sitzung.warten(3)


def test_stopp_fordert_nichts_mehr_an_und_raeumt_auf(tmp_path):
    freigabe = threading.Event()
    sitzung, protokoll, meldungen, erzeugt = baue(tmp_path, [f'b{i}' for i in range(10)], freigabe=freigabe)
    sitzung.starten()
    assert warte_bis(lambda: len(erzeugt) == 3)
    sitzung.stoppen()
    assert sitzung.warten(3)
    assert len(erzeugt) == 3
    assert ('stopp', None) in protokoll and ('zu', None) in protokoll
    assert meldungen[-1][0] == 'gestoppt'
    assert warte_bis(lambda: list(tmp_path.iterdir()) == [])


def test_pause_und_weiter_erreichen_den_spieler(tmp_path):
    freigabe = threading.Event()
    sitzung, protokoll, _, _ = baue(tmp_path, ['eins'], freigabe=freigabe)
    sitzung.starten()
    assert warte_bis(lambda: any(a == 'spielen' for a, _ in protokoll))
    sitzung.pause_umschalten()
    assert warte_bis(lambda: ('pause', None) in protokoll)
    assert sitzung.pausiert
    sitzung.pause_umschalten()
    assert warte_bis(lambda: ('weiter', None) in protokoll)
    freigabe.set()
    assert sitzung.warten(3)


def test_fehler_beim_erzeugen_beendet_mit_fehlermeldung(tmp_path):
    def kaputt(block):
        raise RuntimeError('netz')

    sitzung, _, meldungen, _ = baue(tmp_path, ['eins'], erzeuge=kaputt)
    sitzung.starten()
    assert sitzung.warten(3)
    assert meldungen[-1][0] == 'fehler'


def test_stopp_von_aussen_beendet_die_ausgabe(tmp_path):
    freigabe = threading.Event()
    signal = threading.Event()
    sitzung, _, meldungen, _ = baue(tmp_path, ['eins'], freigabe=freigabe, von_aussen_gestoppt=signal.is_set)
    sitzung.starten()
    signal.set()
    assert sitzung.warten(3)
    assert meldungen[-1][0] == 'gestoppt'


# ── Vorleser: Umschalten über den Tastendruck ────────────────────────────────

class FakeAnzeige:
    def __init__(self):
        self.ereignisse = []

    def start(self, rechteck):
        self.ereignisse.append(('start', rechteck))

    def fortschritt(self, nr, gesamt):
        self.ereignisse.append(('block', nr, gesamt))

    def pause(self, pausiert):
        self.ereignisse.append(('pause', pausiert))

    def verbergen(self):
        self.ereignisse.append(('weg',))

    def hinweis(self, text, rechteck=None):
        self.ereignisse.append(('hinweis', text))


class FakeSitzung:
    def __init__(self, bloecke):
        self.bloecke = bloecke
        self.laeuft = False
        self.gestoppt = False
        self.pausen = 0
        self.pausiert = False

    def starten(self):
        self.laeuft = True

    def stoppen(self):
        self.gestoppt = True
        self.laeuft = False

    def pause_umschalten(self):
        self.pausen += 1
        self.pausiert = not self.pausiert

    def warten(self, frist=None):
        return True


def vorleser(auswahlen):
    sitzungen = []
    anzeige = FakeAnzeige()
    folge = iter(auswahlen)

    def fabrik(bloecke, melde):
        sitzung = FakeSitzung(bloecke)
        sitzung.melde = melde
        sitzungen.append(sitzung)
        return sitzung

    v = kern.Vorleser(lambda: next(folge), lambda t: t, fabrik, anzeige)
    return v, sitzungen, anzeige


def test_erster_druck_startet():
    v, sitzungen, anzeige = vorleser([kern.Auswahl('Ein erfundener Satz.', rechteck=(1, 2, 3, 4))])
    v.tastendruck()
    assert sitzungen[0].laeuft and sitzungen[0].bloecke == ['Ein erfundener Satz.']
    assert ('start', (1, 2, 3, 4)) in anzeige.ereignisse


def test_zweiter_druck_mit_gleicher_markierung_stoppt():
    v, sitzungen, anzeige = vorleser([kern.Auswahl('Gleicher Satz.'), kern.Auswahl('Gleicher Satz.')])
    v.tastendruck()
    v.tastendruck()
    assert sitzungen[0].gestoppt and len(sitzungen) == 1
    assert ('weg',) in anzeige.ereignisse


def test_zweiter_druck_ohne_markierung_stoppt():
    v, sitzungen, _ = vorleser([kern.Auswahl('Ein Satz.'), kern.Auswahl('', grund='keine')])
    v.tastendruck()
    v.tastendruck()
    assert sitzungen[0].gestoppt and len(sitzungen) == 1


def test_andere_markierung_ersetzt():
    v, sitzungen, _ = vorleser([kern.Auswahl('Erster Satz.'), kern.Auswahl('Zweiter Satz.')])
    v.tastendruck()
    v.tastendruck()
    assert sitzungen[0].gestoppt and sitzungen[1].laeuft
    assert sitzungen[1].bloecke == ['Zweiter Satz.']


def test_ausgabe_verstummt_schon_waehrend_der_erfassung():
    beim_erfassen = []
    v, sitzungen, _ = vorleser([])

    def erfasse():
        if sitzungen:
            beim_erfassen.append(sitzungen[0].pausiert)
            return kern.Auswahl('')
        return kern.Auswahl('Ein Satz.')

    v._erfasse = erfasse
    v.tastendruck()
    v.tastendruck()
    assert beim_erfassen == [True]


@pytest.mark.parametrize('grund, teil', [('passwort', 'Passwort'), ('keine', 'Markierung'), ('sicherung', 'Zwischenablage')])
def test_ohne_text_kommt_ein_hinweis_und_nichts_wird_gesendet(grund, teil):
    v, sitzungen, anzeige = vorleser([kern.Auswahl('', grund=grund)])
    v.tastendruck()
    assert sitzungen == []
    hinweise = [e[1] for e in anzeige.ereignisse if e[0] == 'hinweis']
    assert hinweise and teil in hinweise[0]


def test_fehler_beim_erfassen_laesst_keine_stumme_ausgabe_zurueck():
    v, sitzungen, anzeige = vorleser([])

    def erfasse():
        if sitzungen:
            raise OSError('kaputt')
        return kern.Auswahl('Ein Satz.')

    v._erfasse = erfasse
    v.tastendruck()
    v.tastendruck()
    assert sitzungen[0].gestoppt
    assert anzeige.ereignisse[-1][0] == 'hinweis'


def test_veraltete_sitzung_verbirgt_die_anzeige_nicht():
    v, sitzungen, anzeige = vorleser([kern.Auswahl('Erster Satz.'), kern.Auswahl('Zweiter Satz.')])
    v.tastendruck()
    v.tastendruck()
    anzeige.ereignisse.clear()
    sitzungen[0].melde('gestoppt', 0, 1)
    assert anzeige.ereignisse == []


def test_ende_verbirgt_die_anzeige():
    v, sitzungen, anzeige = vorleser([kern.Auswahl('Ein Satz.')])
    v.tastendruck()
    sitzungen[0].melde('ende', 0, 1)
    assert anzeige.ereignisse[-1] == ('weg',)


def test_logs_enthalten_keinen_markierten_text(caplog):
    geheim = 'Streng erfundener Inhalt XYZ'
    v, _, _ = vorleser([kern.Auswahl(geheim)])
    with caplog.at_level(logging.DEBUG):
        v.tastendruck()
    assert caplog.records
    assert geheim not in caplog.text
