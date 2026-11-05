# Master-Schalter

A Windows tray app for working with several coding agents at once. It shows how much of the usage quota of
Claude Code and Codex is left, keeps track of which agent "owns" which project, and hands a project from one agent
to another with a technical handover package. The name is German for "master switch".

**Stack:** Python 3.12 · standard library for the core · `tkinter` (window) · `pystray` + Pillow (tray) · pytest

## What it does

- **Two bars in the taskbar:** Claude on the left, Codex on the right. The fill shows the 5-hour usage: normal
  colour up to 79 %, yellow from 80 %, red from a configurable threshold (default 97 %).
- **Roles per topic:** for each project it stores who plans, who builds and with which model
  (`masterwechsel profil <topic>`). Agents read this before they start work.
- **Handover assistant:** "topic X: old chat → new chat". It writes a handover package (technical metadata only),
  delivers it to the target chat, waits for an acknowledgement and logs every decision.
- **Automatic switch (off by default):** when Claude reaches its limit, the topic is handed over to Codex. It only
  runs after it has been switched on explicitly.

## Where the numbers come from

- **Codex** writes its quota into its own session files; only numeric values from 0 to 100 are accepted, anything
  else counts as "unknown" and never triggers a handover.
- **Claude Code** is measured through its OAuth usage endpoint. The access token is read at runtime, used only in
  memory and never stored or logged. This endpoint is unofficial and has changed before; the code handles the
  known variants and otherwise keeps the last value with its timestamp.

## Design decisions

- **Fail closed.** Unknown values, missing ownership markers or a failed acknowledgement stop the automatic path
  instead of guessing.
- **Locks per topic** so two agents never take over the same project at the same time.
- **Core without dependencies:** state, decisions and CLI use only the standard library; only the UI needs extra
  packages.
- **Data folder under `%USERPROFILE%`, not `%LOCALAPPDATA%`:** the Claude and Codex apps are MSIX packages whose
  child processes get a redirected `AppData\Local`, so each launcher would otherwise read a different state.

## Structure

```
src/master_schalter/
  signale.py, claude_messen.py   read and validate the quotas
  modi.py, rollen.py             roles per topic
  uebergabe.py, wechsel.py       handover package, switch under locks
  assistent*.py, postfach.py     handover assistant and mailbox
  automatik.py, codex_senden.py  automatic path
  fenster*.py, leiste.py, cli.py window, tray, command line
tests/                           pytest, synthetic files only
```

## Run it

Windows.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[leiste,dev]"
.\.venv\Scripts\pythonw.exe -m master_schalter.leiste    # tray icon
.\.venv\Scripts\masterwechsel.exe status                 # quotas in the console
.\.venv\Scripts\python.exe -m pytest -q                  # check command, also run by the pre-commit hook
```

Version 0.5.0. The code and comments are in German; that is the language I work in.

← [Back to overview](../../README.md)
