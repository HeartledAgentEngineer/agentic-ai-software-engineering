"""Die Tastenkombinationen. Der echte Griff ist AltGr + Ö; Windows meldet AltGr als Strg + Alt."""
import readfree as mv


class FakeUser32:
    def __init__(self, frei=(True, True, True)):
        self.frei = list(frei)
        self.angemeldet = []
        self.abgemeldet = []

    def RegisterHotKey(self, hwnd, kennung, mods, vk):
        self.angemeldet.append((kennung, mods, vk))
        return self.frei[len(self.angemeldet) - 1]

    def UnregisterHotKey(self, hwnd, kennung):
        self.abgemeldet.append(kennung)
        return 1


def test_alt_oe_und_alt_shift_oe_werden_angemeldet():
    user32 = FakeUser32()
    assert mv.Hotkey(lambda: None, user32=user32)._anmelden()
    mods = {m & ~mv.MOD_NOREPEAT for _, m, _ in user32.angemeldet}
    assert mods == {mv.MOD_CONTROL | mv.MOD_ALT, mv.MOD_ALT, mv.MOD_ALT | mv.MOD_SHIFT}
    assert all(vk == mv.VK_OEM_3 for _, _, vk in user32.angemeldet)
    assert all(m & mv.MOD_NOREPEAT for _, m, _ in user32.angemeldet)
    assert len({k for k, _, _ in user32.angemeldet}) == 3


def test_eine_freie_kombination_reicht():
    assert mv.Hotkey(lambda: None, user32=FakeUser32((False, True, False)))._anmelden()


def test_alle_belegt_meldet_fehlschlag():
    assert not mv.Hotkey(lambda: None, user32=FakeUser32((False, False, False)))._anmelden()


def test_abmelden_gibt_beide_frei():
    user32 = FakeUser32()
    hotkey = mv.Hotkey(lambda: None, user32=user32)
    hotkey._anmelden()
    hotkey._abmelden()
    assert sorted(user32.abgemeldet) == sorted(k for k, _, _ in user32.angemeldet)


def test_kopierbefehl_wartet_auch_auf_altgr():
    import erfassen
    assert erfassen.VK_CONTROL in erfassen.MODIFIKATOR_TASTEN
    assert erfassen.VK_MENU in erfassen.MODIFIKATOR_TASTEN


def test_name_readfree_an_allen_laufzeitstellen(monkeypatch, tmp_path):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    assert mv.EINZELINSTANZ == 'Local\\readFREE.Einzelinstanz'
    assert mv.daten_ordner() == tmp_path / 'hermes' / 'cache' / 'readfree'
