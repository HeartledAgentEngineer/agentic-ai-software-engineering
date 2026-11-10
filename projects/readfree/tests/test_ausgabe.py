"""TTS-Anbindung, MCI-Befehle und Fensterposition. Kein Netz, kein Audio."""
import types

import pytest

import ausgabe
import fenster


def env_datei(tmp_path, inhalt):
    pfad = tmp_path / '.env'
    pfad.write_text(inhalt, encoding='utf-8')
    return pfad


def test_nur_der_vorlese_schluessel_gilt(tmp_path):
    pfad = env_datei(tmp_path, 'OPENROUTER_API_KEY=allgemein\nOPENROUTER_TTS_KEY="vorlesen"\n')
    assert ausgabe.tts_schluessel(pfad) == 'vorlesen'


def test_kein_rueckfall_auf_den_allgemeinen_schluessel(tmp_path):
    pfad = env_datei(tmp_path, 'OPENROUTER_API_KEY=allgemein\n')
    with pytest.raises(ausgabe.TtsFehler):
        ausgabe.tts_schluessel(pfad)


def fake_mai(sprechen):
    return types.SimpleNamespace(MODELL='modell', STIMME='stimme', sprechen=sprechen, vorbereiten=str.strip)


def test_erzeuge_reicht_modell_und_stimme_durch():
    aufrufe = []

    def sprechen(text, schluessel, modell, stimme):
        aufrufe.append((text, schluessel, modell, stimme))
        return b'mp3'

    tts = ausgabe.KlausTts(fake_mai(sprechen), 'k')
    assert tts.erzeuge('Ein Satz.') == b'mp3'
    assert aufrufe == [('Ein Satz.', 'k', 'modell', 'stimme')]


def test_systemexit_des_clients_wird_zu_tts_fehler_ohne_text():
    def sprechen(text, *rest):
        raise SystemExit(f'OpenRouter lehnte ab: {text}')

    tts = ausgabe.KlausTts(fake_mai(sprechen), 'k')
    with pytest.raises(ausgabe.TtsFehler) as fehler:
        tts.erzeuge('Erfundener Inhalt ABC')
    assert 'Erfundener Inhalt ABC' not in str(fehler.value)


def test_leere_antwort_ist_ein_fehler():
    tts = ausgabe.KlausTts(fake_mai(lambda *a: b''), 'k')
    with pytest.raises(ausgabe.TtsFehler):
        tts.erzeuge('Ein Satz.')


class FakeMci:
    def __init__(self, status='playing', fehler=0):
        self.befehle = []
        self.status = status
        self.fehler = fehler

    def __call__(self, befehl):
        self.befehle.append(befehl)
        if ' mode' in befehl:
            return 0, self.status
        return self.fehler, ''


def test_mci_befehlsfolge(tmp_path):
    mci = FakeMci()
    spieler = ausgabe.MciSpieler(mci)
    pfad = tmp_path / 'mit leerzeichen.mp3'
    spieler.oeffnen(pfad)
    spieler.spielen()
    assert spieler.laeuft()
    spieler.pausieren()
    spieler.fortsetzen()
    spieler.stoppen()
    spieler.schliessen()
    alias = spieler.alias
    assert mci.befehle[0] == f'open "{pfad}" type mpegvideo alias {alias}'
    assert mci.befehle[1:] == [f'play {alias}', f'status {alias} mode', f'pause {alias}',
                               f'resume {alias}', f'stop {alias}', f'close {alias}']


def test_mci_gestoppt_heisst_fertig(tmp_path):
    spieler = ausgabe.MciSpieler(FakeMci(status='stopped'))
    spieler.oeffnen(tmp_path / 'a.mp3')
    assert not spieler.laeuft()


def test_mci_pausiert_zaehlt_als_laufend(tmp_path):
    spieler = ausgabe.MciSpieler(FakeMci(status='paused'))
    spieler.oeffnen(tmp_path / 'a.mp3')
    assert spieler.laeuft()


def test_mci_fehler_beim_oeffnen_wirft(tmp_path):
    spieler = ausgabe.MciSpieler(FakeMci(fehler=263))
    with pytest.raises(ausgabe.TtsFehler):
        spieler.oeffnen(tmp_path / 'a.mp3')


def test_zwei_spieler_haben_verschiedene_alias():
    assert ausgabe.MciSpieler(FakeMci()).alias != ausgabe.MciSpieler(FakeMci()).alias


# ── Fensterposition ──────────────────────────────────────────────────────────

BEREICH = (0, 0, 1920, 1040)


def test_fenster_liegt_unter_der_markierung():
    assert fenster.position((100, 200, 300, 40), (5, 5), 260, 50, BEREICH) == (100, 248)


def test_fenster_weicht_nach_oben_aus():
    x, y = fenster.position((100, 1000, 300, 30), (5, 5), 260, 50, BEREICH)
    assert y == 942 and x == 100


def test_ohne_rechteck_gilt_der_mauszeiger():
    assert fenster.position(None, (500, 400), 260, 50, BEREICH) == (500, 424)


def test_fenster_bleibt_im_arbeitsbereich():
    x, y = fenster.position(None, (1900, 1030), 260, 50, BEREICH)
    assert 0 <= x <= 1920 - 260 and 0 <= y <= 1040 - 50


def test_fenster_auf_linkem_monitor_mit_negativen_koordinaten():
    x, y = fenster.position((-1500, 100, 200, 20), (0, 0), 260, 50, (-1920, 0, 0, 1040))
    assert (x, y) == (-1500, 128)
