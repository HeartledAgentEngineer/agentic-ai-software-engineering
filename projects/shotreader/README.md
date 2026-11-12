# ShotReader

Screenshots read aloud: take a screenshot of a passage (`Win + Shift + S`), and ShotReader recognises the text
locally (German or English) and reads it out with a natural neural voice (*Klaus*, German). I built it for exam preparation (long multiple-choice
questions and explanations in practice tests) so I can listen instead of reading on the screen for hours.
Until November 2026 it was called *Screenshot-Vorleser*.

**Stack:** PowerShell 5.1 · Windows Forms · Windows OCR (`Windows.Media.Ocr`, on the device) · text-to-speech through
OpenRouter (`microsoft/mai-voice-2-flash`) · ffmpeg for faster playback · Windows Media Player COM for streaming

## How it works

```
screenshot → clipboard → image or text? → OCR on the device (de-DE / en-US) → text box (check it)
→ split into sentence chunks → each chunk: POST /api/v1/audio/speech → MP3 → playlist starts with chunk 1
```

- **Text recognition stays on the machine.** Only the recognised text leaves the PC, never the image.
- **Fast start:** the text is cut at sentence boundaries; the first chunk is kept short (at most 150 characters, the
  rest up to 280), so the voice can start while the next chunks are still being generated.
- **Speed 1× – 3×** with unchanged pitch. The Windows player gives no sound above 2× (measured), so above 2× the audio
  files are additionally sped up 1.5× with ffmpeg and the player handles the rest.
- **Automatic mode** watches the clipboard (`GetClipboardSequenceNumber`) and reads every new screenshot.

## The speech call

`shotreader_tts.py` uses the small OpenRouter text-to-speech client from my agent setup (`openrouter_mai.py`, not part
of this repository). The request itself is the OpenAI-compatible speech endpoint:

```
POST https://openrouter.ai/api/v1/audio/speech
Authorization: Bearer <key>            # dedicated key with its own spending limit
{"model": "microsoft/mai-voice-2-flash", "voice": "de-DE-Klaus:MAI-Voice-2", "input": "<chunk>", "response_format": "mp3"}
→ MP3 bytes
```

The key is read from a local `.env`, never from the script. A dedicated reading key makes the cost of reading aloud
visible separately; without it the tool stops instead of silently using the general key.

## Decisions and lessons

- **Only real screenshots trigger automatic reading.** The first version read *every* image that reached the
  clipboard. Copying in Excel, Word, OneNote, Teams or a browser also puts a picture of the selection there, and my
  dictation tool [typeFREE](../typefree/) briefly writes to the clipboard and then restores the previous content. The
  tool started reading "at random", mostly while pasting. Now:
  - a clipboard that holds text, HTML, files or an application format next to the image is not a screenshot
    (`Test-NurBild`), nor is anything carrying typeFREE's own marker;
  - the tool remembers the fingerprints of the last 30 images, not only the last one, so a screenshot that comes back
    (typeFREE restore, clipboard history `Win + V`) stays silent;
  - the fingerprint uses only the colour values (24 bit, no alpha channel, no row padding), so the same image in a
    different clipboard format counts as the same.
- **Decisions are logged without content:** time, decision, clipboard format names and the start of the fingerprint go
  to `%LOCALAPPDATA%\hermes\werkzeuge\shotreader.log` (last 1,000 lines). If it ever triggers unexpectedly again, the
  log shows which rule let it through. A live reproduction of the original bug was not possible while the tool itself
  was watching the clipboard; the fix is based on the code analysis, and the log is there to confirm it.
- **Measure before assuming:** the 2× limit of the Windows player was measured, not taken from documentation.

## Run and test

```powershell
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File .\ShotReader.ps1             # window
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File .\ShotReader.ps1 -AutoStart  # automatic mode on
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ShotReader.ps1 -Test            # self-test, exit code 0 = ok
```

The self-test checks the speed rules, the clipboard-format rule, the fingerprint (stable, independent of pixel format,
different sizes differ), the decision rules, the 30-image memory, the local OCR engine on a rendered test image, and
local speech synthesis. It does not call OpenRouter and needs no key. It runs in CI on a Windows runner.

[← Back to the overview](../../README.md)
