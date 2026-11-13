"""Kleines schwebendes Fenster nahe der Markierung: Pause/Weiter und Stopp.

Das Fenster nimmt der Anwendung nie den Fokus (`WS_EX_NOACTIVATE`), deshalb sind
die Knöpfe Beschriftungen mit Klick-Bindung statt Schaltflächen. tkinter läuft im
Hauptfaden; andere Fäden reichen Aufträge über eine Warteschlange herein.
"""
from __future__ import annotations

import ctypes
import queue

ABSTAND = 8
MAUS_ABSTAND = 24
HINWEIS_MS = 3000
HINTERGRUND = '#1e1f24'
TEXTFARBE = '#ffffff'
KNOPF = '#3a3c44'
KNOPF_HOVER = '#555863'


def position(rechteck, maus, breite, hoehe, bereich) -> tuple[int, int]:
    """Unter der Markierung, bei Platzmangel darüber; sonst am Mauszeiger."""
    links, oben, rechts, unten = bereich
    if rechteck is not None:
        x, y_oben, _, h = rechteck
        y = y_oben + h + ABSTAND
        if y + hoehe > unten:
            y = y_oben - ABSTAND - hoehe
    else:
        x, y = maus[0], maus[1] + MAUS_ABSTAND
    x = max(links, min(x, rechts - breite))
    y = max(oben, min(y, unten - hoehe))
    return int(x), int(y)


def _arbeitsbereich(x: int, y: int) -> tuple[int, int, int, int]:
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                    ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]

    user32 = ctypes.WinDLL('user32')
    user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MonitorInfo)]
    monitor = user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(MonitorInfo)
    user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    r = info.rcWork
    return r.left, r.top, r.right, r.bottom


class Anzeige:
    """Fadensicher: alle öffentlichen Methoden stellen nur Aufträge ein."""

    def __init__(self, bei_pause, bei_stopp):
        self._auftraege: queue.Queue = queue.Queue()
        self._bei_pause = bei_pause
        self._bei_stopp = bei_stopp
        self._hinweis_timer = None
        self._rechteck = None

    # Von beliebigen Fäden aufrufbar
    def start(self, rechteck):
        self._auftraege.put(('start', rechteck))

    def fortschritt(self, nummer, gesamt):
        self._auftraege.put(('fortschritt', nummer, gesamt))

    def pause(self, pausiert):
        self._auftraege.put(('pause', pausiert))

    def verbergen(self):
        self._auftraege.put(('verbergen',))

    def hinweis(self, text, rechteck=None):
        self._auftraege.put(('hinweis', text, rechteck))

    def beenden(self):
        self._auftraege.put(('beenden',))

    # Nur im Hauptfaden
    def laufen(self):
        self._aufbauen()
        self.root.after(30, self._abarbeiten)
        self.root.mainloop()

    def _aufbauen(self):
        import tkinter as tk

        self.root = root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes('-topmost', True)
        root.configure(bg=HINTERGRUND)
        self._rahmen = tk.Frame(root, bg=HINTERGRUND, padx=10, pady=7)
        self._rahmen.pack()
        self._status = tk.Label(self._rahmen, text='', bg=HINTERGRUND, fg=TEXTFARBE,
                                font=('Segoe UI', 10), anchor='w')
        self._status.pack(side='left', padx=(0, 10))
        self._knopf_pause = self._knopf('Pause', self._bei_pause)
        self._knopf_stopp = self._knopf('Stopp', self._bei_stopp)
        root.update_idletasks()
        self._nicht_aktivierbar()

    def _knopf(self, text, aktion):
        import tkinter as tk

        knopf = tk.Label(self._rahmen, text=text, bg=KNOPF, fg=TEXTFARBE, padx=10, pady=3,
                         font=('Segoe UI', 9, 'bold'), cursor='hand2')
        knopf.bind('<Button-1>', lambda _ereignis: aktion())
        knopf.bind('<Enter>', lambda _ereignis: knopf.configure(bg=KNOPF_HOVER))
        knopf.bind('<Leave>', lambda _ereignis: knopf.configure(bg=KNOPF))
        knopf.pack(side='left', padx=(4, 0))
        return knopf

    def _nicht_aktivierbar(self):
        from ctypes import wintypes

        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = 0x08000000, 0x00000080
        user32 = ctypes.WinDLL('user32')
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        stil = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, stil | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)

    def _abarbeiten(self):
        try:
            while True:
                auftrag = self._auftraege.get_nowait()
                if auftrag[0] == 'beenden':
                    self.root.destroy()
                    return
                getattr(self, '_' + auftrag[0])(*auftrag[1:])
        except queue.Empty:
            pass
        self.root.after(30, self._abarbeiten)

    def _hinweis_abbrechen(self):
        if self._hinweis_timer is not None:
            self.root.after_cancel(self._hinweis_timer)
            self._hinweis_timer = None

    def _knoepfe(self, sichtbar):
        for knopf in (self._knopf_pause, self._knopf_stopp):
            if sichtbar:
                knopf.pack(side='left', padx=(4, 0))
            else:
                knopf.pack_forget()

    def _zeigen(self, rechteck):
        root = self.root
        root.update_idletasks()
        breite, hoehe = root.winfo_reqwidth(), root.winfo_reqheight()
        maus = root.winfo_pointerxy()
        anker = (rechteck[0], rechteck[1]) if rechteck else maus
        x, y = position(rechteck, maus, breite, hoehe, _arbeitsbereich(*anker))
        root.geometry(f'+{x}+{y}')
        root.deiconify()
        root.attributes('-topmost', True)

    def _start(self, rechteck):
        self._hinweis_abbrechen()
        self._rechteck = rechteck
        self._knoepfe(True)
        self._knopf_pause.configure(text='Pause')
        self._status.configure(text='Klaus setzt an …')
        self._zeigen(rechteck)

    def _fortschritt(self, nummer, gesamt):
        self._status.configure(text=f'Klaus liest: Block {nummer} von {gesamt}')

    def _pause(self, pausiert):
        self._knopf_pause.configure(text='Weiter' if pausiert else 'Pause')
        if pausiert:
            self._status.configure(text='Pausiert')

    def _verbergen(self):
        self._hinweis_abbrechen()
        self.root.withdraw()

    def _hinweis(self, text, rechteck):
        self._hinweis_abbrechen()
        self._knoepfe(False)
        self._status.configure(text=text)
        self._zeigen(rechteck)
        self._hinweis_timer = self.root.after(HINWEIS_MS, self._verbergen)
