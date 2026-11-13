# readFREE

Select text in any Windows program, press **AltGr + Ö**, and it is read aloud. Alt + Ö and Alt + Shift + Ö work as
well. It is the counterpart to [typeFREE](../typefree/): there I speak instead of typing, here I listen instead of
reading.

**Stack:** Python · Win32 `RegisterHotKey` via `ctypes` · UI Automation (`comtypes`) · Win32 clipboard · MCI audio
playback · tkinter · `pystray` · text-to-speech through OpenRouter (`microsoft/mai-voice-2-flash`) · pytest

## Why I built it

Working with four or five AI chats in parallel produces a constant stream of text: questions, plans, outputs, and
all of it wants to be read. readFREE takes part of that load off my eyes. Select, press a key, listen: it moves the
input to a different sense, so the visual channel gets a break now and then.

## How it works

```
AltGr + Ö → read the selection (UI Automation; clipboard fallback) → split into blocks
          → speech for block 1 while at most two more are prepared → play, delete each audio file after playing
```

| Action | Result |
|---|---|
| Select text, press AltGr + Ö | Reading starts; a small window appears next to the selection |
| Press again, same selection or none | Stop |
| Select something else, press | The new selection replaces the current one |
| **Pause** / **Resume** button | Holds and continues |
| **Stop** button or tray menu | Stops; no further speech is requested |

- **Fast start:** the first block has at most 150 characters, so speech starts quickly; later blocks hold up to
  280 characters and are split at sentence boundaries, known abbreviations are protected. There is no length limit.
- **Bounded look-ahead:** besides the block that is playing, at most two more are requested. A stop therefore saves
  the rest of a long text (`Sitzung` in `kern.py`).
- **Reading the selection without touching the clipboard:** UI Automation is tried first. Password fields are
  detected there and never read.
- **Clipboard fallback that gives the clipboard back:** only if UI Automation returns nothing, the tool backs up
  the clipboard in all formats (module `zwischenablage.py` from typeFREE), sends a copy command and writes the
  backup back. Terminals get Ctrl+Insert instead of Ctrl+C, because Ctrl+C can stop a running program there. If the
  clipboard cannot be backed up completely, nothing is copied. If the new clipboard belongs to another process than
  the foreground window, or does not settle, another program copied in between and its content is left alone.
- **Window that does not steal focus:** the small control window uses `WS_EX_NOACTIVATE`, so typing continues in
  the program you were reading from.
- **Signal for other voice outputs:** while reading, a named mutex exists; a named event stops the output from
  outside. Other tools can use it to avoid talking over each other.

## Privacy

- The selected text is sent to the text-to-speech provider only after the key press.
- Logs contain lengths and error types, never text.
- Audio files are deleted after playing, leftovers on the next start.
- Limit: in the clipboard fallback the text can show up in the Windows clipboard history (Win+V), because the source
  program does the copying.

## Running it

Windows only. Python 3.12 with the packages in `requirements.txt`. The speech client is a small local module
outside this repository (it holds the API key handling); `ausgabe.py` loads it at runtime. The tests do not need it.

```powershell
powershell -ExecutionPolicy Bypass -File .\installieren.ps1             # copy, autostart (HKCU Run), start
powershell -ExecutionPolicy Bypass -File .\installieren.ps1 -Entfernen  # way back: stop, remove autostart and folder
```

`-OhneAutostart` installs without autostart; the autostart entry can also be switched off in the Task Manager.

## Tests

```powershell
python -m pytest -q tests
```

88 tests with fakes for the clipboard, the hotkey API, the player and the speech client; no network, no real
clipboard. Covered: splitting, start/stop/replace decisions, look-ahead and stop in the two worker threads, pause,
clipboard backup and restore, foreign-copy detection, password fields, and that no text reaches the log.

`rauchtest_live.py` is a manual smoke test with real windows: a WPF test window, UI Automation, password field,
clipboard fallback with restore, focus of the control window, and MCI playback of silent audio. It needs ffmpeg
from the speech client, so it does not run in CI.

**Not automated:** the real key press, the real voice, and whether Alt + Shift + Ö also switches the keyboard
layout (Windows uses Alt + Shift for that; AltGr + Ö and Alt + Ö are not affected).

## Known limits

- The keys sit on Ö in the German layout (`VK_OEM_3`, measured); in the US layout this is the key left of 1.
- Store apps and classic consoles write the clipboard from a helper process, so ownership cannot be checked there;
  the copy then counts as the tool's own. If another program copies within roughly 100 ms after that, its content
  would be reset. UI Automation is tried first, so the clipboard usually stays untouched.
- Programs running as administrator can block the copy command.
- Opening an audio file through MCI takes 0.4 to 1.5 s (measured); a stop in exactly that moment takes effect after.
- Code identifiers and comments are in German, like the rest of my daily tools.

## How it was built

Planned by Claude, plan and result reviewed by a model of another family (DeepSeek through Hermes) until both were
approved; tests were written before the code. A live smoke test caught a real bug before release: WPF writes the
clipboard in two bursts about 20 ms apart. The first version took the second burst for a copy by another program,
and the real clipboard was overwritten once during testing. Now two consecutive opens of the clipboard must see the
same sequence number before anything is read or restored.
