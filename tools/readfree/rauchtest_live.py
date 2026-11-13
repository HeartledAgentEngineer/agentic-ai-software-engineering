"""Rauchtest mit echten Windows-Fenstern, ohne Netz und nur mit erfundenem Text.

Prüft in einem eigenen WPF-Testfenster: UI Automation, Passwortfeld, Kopier-Rückfall
samt unveränderter Zwischenablage, Fokus beim Einblenden des Anzeige-Fensters und
echte MCI-Wiedergabe einer stummen Datei. Der Kopierbefehl wird nur gesendet, wenn
das Testfenster wirklich im Vordergrund liegt. Keine Inhalte in der Ausgabe.

Aufruf: python rauchtest_live.py
Exit-Code 0 = alles bestanden.
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import ausgabe
import erfassen
import fenster
import kern
from erfassen import zwischenablage as za

PROBE = 'Das ist ein erfundener Probesatz für den Rauchtest.'
TITEL = 'Rauchtest Markierung'
ergebnisse: list[tuple[str, bool]] = []


def melde(name: str, ok: bool) -> None:
    ergebnisse.append((name, ok))
    print(('OK    ' if ok else 'FEHLER'), name, flush=True)


FENSTER_SKRIPT = r"""
Add-Type -AssemblyName PresentationFramework
$w = New-Object System.Windows.Window
$w.Title = '%s'; $w.Width = 520; $w.Height = 180; $w.Topmost = $true
$p = New-Object System.Windows.Controls.StackPanel
$t = New-Object System.Windows.Controls.TextBox; $t.Text = '%s'
$k = New-Object System.Windows.Controls.PasswordBox; $k.Password = 'erfunden'
[void]$p.Children.Add($t); [void]$p.Children.Add($k); $w.Content = $p
$w.Add_ContentRendered({ $w.Activate() | Out-Null; if ('%s' -eq 'text') { [void]$t.Focus(); $t.SelectAll() } else { [void]$k.Focus() } })
[void]$w.ShowDialog()
""".strip()


def vordergrund_titel() -> str:
    user32 = ctypes.windll.user32
    puffer = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(user32.GetForegroundWindow(), puffer, 256)
    return puffer.value


def warte_auf_vordergrund(frist=15.0) -> bool:
    """Windows lässt Hintergrundprozesse nicht aktivieren, daher SwitchToThisWindow."""
    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.SwitchToThisWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    ende = time.monotonic() + frist
    while time.monotonic() < ende:
        if vordergrund_titel() == TITEL:
            return True
        hwnd = user32.FindWindowW(None, TITEL)
        if hwnd:
            user32.SwitchToThisWindow(hwnd, 1)
        time.sleep(0.25)
    return False


def testfenster(modus: str) -> subprocess.Popen:
    skript = FENSTER_SKRIPT % (TITEL, PROBE, modus)
    return subprocess.Popen(['powershell', '-NoProfile', '-STA', '-Command', skript],
                            creationflags=subprocess.CREATE_NO_WINDOW)


def ablage_stand():
    api = za.standard_api()
    assert za._oeffnen(api), 'Zwischenablage belegt'
    try:
        return za._sichern(api)
    finally:
        api.CloseClipboard()


def ablage_setzen(formate) -> None:
    api = za.standard_api()
    assert za._oeffnen(api), 'Zwischenablage belegt'
    try:
        assert za._zurueckschreiben(api, za.Snapshot(list(formate)))
    finally:
        api.CloseClipboard()


def pruefe_kopie() -> None:
    """Erfundener Vorinhalt in zwei Formaten: Er muss die Kopie überstehen."""
    probe_format = za.standard_api().RegisterClipboardFormat('Rauchtest.Probeformat')
    vorinhalt = {13: 'Erfundener Vorinhalt'.encode('utf-16-le') + b'\0\0', probe_format: b'PROBE-BYTES'}
    ablage_setzen(vorinhalt.items())
    if vordergrund_titel() != TITEL:
        melde('Fenster für den Kopierbefehl im Vordergrund', False)
        return
    kopierer = erfassen.Kopierer(za.standard_api, erfassen.druecke, erfassen.fenster_info,
                                 vordergrund_pid=erfassen.vordergrund_pid, besitzer_pid=erfassen.besitzer_pid)
    auswahl = kopierer.hole()
    melde('Kopier-Rückfall liest die Markierung', auswahl.text == PROBE)
    time.sleep(0.2)
    nachher = dict(ablage_stand().formate)
    melde('Vorinhalt ist in beiden Formaten zurück',
          nachher.get(13, b'').startswith(vorinhalt[13]) and nachher.get(probe_format, b'').startswith(b'PROBE-BYTES'))


def pruefe_erfassung(anzeige) -> None:
    prozess = testfenster('text')
    try:
        if not warte_auf_vordergrund():
            melde('Testfenster im Vordergrund', False)
            return
        time.sleep(0.5)
        melde('Testfenster im Vordergrund', True)

        ergebnis = erfassen.uia_lesen()
        melde('UI Automation liest die Markierung', bool(ergebnis) and ergebnis.text == PROBE)
        melde('UI Automation liefert ein Rechteck', bool(ergebnis) and ergebnis.rechteck is not None)

        anzeige.start(ergebnis.rechteck if ergebnis else None)
        anzeige.fortschritt(1, 3)
        time.sleep(0.6)
        melde('Anzeige nimmt keinen Fokus', vordergrund_titel() == TITEL)
        anzeige.verbergen()
        time.sleep(0.2)

        echter_stand = ablage_stand()
        if not echter_stand.vollstaendig:
            melde('Kopier-Rückfall (Zwischenablage nicht sicherbar, übersprungen)', True)
            return
        try:
            pruefe_kopie()
        finally:
            ablage_setzen(echter_stand.formate)   # Immer, auch wenn der Test scheitert.
    finally:
        prozess.kill()
        prozess.wait()


def pruefe_passwort() -> None:
    """Zählt nur Messungen, bei denen der Fokus wirklich im Testfenster lag."""
    for _versuch in range(3):
        prozess = testfenster('passwort')
        try:
            if not warte_auf_vordergrund():
                continue
            time.sleep(0.5)
            ergebnis = erfassen.uia_lesen()
            if vordergrund_titel() == TITEL:
                melde('Passwortfeld wird erkannt', bool(ergebnis) and ergebnis.passwort)
                return
        finally:
            prozess.kill()
            prozess.wait()
    melde('Passwort-Testfenster im Vordergrund', False)


def pruefe_wiedergabe() -> None:
    client = ausgabe.lade_client()
    with tempfile.TemporaryDirectory() as ordner_text:
        ordner = Path(ordner_text)
        stumm = ordner / 'stumm.mp3'
        subprocess.run([client.ffmpeg_pfad(), '-v', 'error', '-y', '-f', 'lavfi', '-i',
                        'anullsrc=r=24000:cl=mono', '-t', '1.2', '-q:a', '9', str(stumm)],
                       check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        daten = stumm.read_bytes()
        arbeit = ordner / 'audio'
        arbeit.mkdir()

        meldungen = []
        sitzung = kern.Sitzung(['a', 'b'], lambda _block: daten, ausgabe.MciSpieler, arbeit,
                               lambda art, nr, gesamt: meldungen.append(art))
        beginn = time.monotonic()
        sitzung.starten()
        fertig = sitzung.warten(10)
        dauer = time.monotonic() - beginn
        melde('MCI spielt zwei Blöcke nacheinander',
              fertig and meldungen[-1] == 'ende' and meldungen.count('block') == 2 and dauer >= 1.8)
        melde('Audio-Dateien sind gelöscht', list(arbeit.iterdir()) == [])

        meldungen = []
        sitzung = kern.Sitzung(['a', 'b', 'c'], lambda _block: daten, ausgabe.MciSpieler, arbeit,
                               lambda art, nr, gesamt: meldungen.append(art))
        sitzung.starten()
        # Das Öffnen der Datei dauert gemessen 0,4 bis 1,5 s: erst ab dem Abspielen messen.
        frist = time.monotonic() + 5
        while 'block' not in meldungen and time.monotonic() < frist:
            time.sleep(0.02)
        sitzung.pause_umschalten()
        time.sleep(0.3)
        sitzung.pause_umschalten()
        time.sleep(0.2)
        beginn = time.monotonic()
        sitzung.stoppen()
        fertig = sitzung.warten(3)
        melde('Stopp beendet in unter 0,5 s', fertig and time.monotonic() - beginn < 0.5)
        melde('Pause und Weiter kommen an', 'pause' in meldungen and 'weiter' in meldungen)
        time.sleep(0.2)
        melde('Nach Stopp keine Reste', list(arbeit.iterdir()) == [])


def ablauf(anzeige) -> None:
    try:
        erfassen.uia_vorbereiten()
        pruefe_erfassung(anzeige)
        pruefe_passwort()
        pruefe_wiedergabe()
    except Exception as fehler:
        melde(f'Rauchtest abgebrochen: {type(fehler).__name__}', False)
    finally:
        anzeige.beenden()


def main() -> int:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    anzeige = fenster.Anzeige(lambda: None, lambda: None)
    threading.Thread(target=ablauf, args=(anzeige,), daemon=True).start()
    anzeige.laufen()
    fehlgeschlagen = [name for name, ok in ergebnisse if not ok]
    print(f'{len(ergebnisse) - len(fehlgeschlagen)} von {len(ergebnisse)} bestanden')
    return 1 if fehlgeschlagen or not ergebnisse else 0


if __name__ == '__main__':
    sys.exit(main())
