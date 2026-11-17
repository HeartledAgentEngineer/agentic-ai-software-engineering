# Cross-model review — recorded demo

Two real runs of [`pruefkreis.py`](../pruefkreis.py) on 2026-11-17: a sample plan with one deliberately wrong claim
gets an objection with the code line as evidence; after a one-line fix, a fresh run approves it. Nothing here is
staged or edited — the blocks below are the tool's output as printed, with one local folder path masked (see
[How this was recorded](#how-this-was-recorded)).

| | Round 1 | Round 2 |
|---|---|---|
| Template | [`demo_plan.md`](../demo/demo_plan.md), Fassung 1 — claim 2 wrong on purpose | Fassung 2 — claim 2 corrected |
| Verdict | `URTEIL: EINWAND`, exit code 1 | `URTEIL: FREI`, exit code 0 |
| Reviewer | Hermes · `deepseek/deepseek-v4.1-flash` via OpenRouter | same model, fresh session |
| Duration · cost | 79.5 s · 0.0024 USD | 51.5 s · 0.0035 USD |

The plan was written by Claude (`--master claude`), so the reviewer comes from another model family. Codex — the
usual reviewer — had used up its weekly quota that day, so Hermes was chosen explicitly with `--pruefer hermes`.

## 1. The planted error

Claim 2 of the template says `0 = FREI, 1 = error, 2 = EINWAND`. The code says otherwise
(`pruefkreis.py`, line 597):

```python
return {"frei": 0, "einwand": 1}.get(ergebnis["status"], 2)
```

## 2. Round 1 — objection

```text
$ export PRUEFKREIS_DIR=<protocol-dir>
python projects/cross-model-review/pruefkreis.py pruefen --vorlage projects/cross-model-review/demo/demo_plan.md \
    --thema demo-exit-codes --pruefer hermes --master claude --zeitgrenze 1200
## Runde 1 · 2026-11-17 12:45 · Pruefer hermes · Vorlage `projects/cross-model-review/demo/demo_plan.md`

**Status: EINWAND**
Modell: deepseek/deepseek-v4.1-flash · Planfassung: 1
Master: claude (angegeben)
Hermes-Sitzung: `local-cabb11132481b6ba18a07cba47ec2ca96478b94139e52d9371838ce2f684f050`
Kosten: 0.0024 USD
Dauer: 79.5 s

Prüfrunde 1 zu projects/cross-model-review/demo/demo_plan.md (Fassung 1).

Kein Pruefjournal vorhanden — Datei ist 16 Zeilen, kein Abschnitt zu frueheren Einwaenden. Also keine Altpunkte zu pruefen; ich verifiziere die vier Behauptungen direkt am Code.

Behauptung 1 (nur letzte nichtleere Zeile zaehlt, sonst Fehler, nie FREI):
pruefkreis.py:221 nimmt genau die letzte nichtleere Zeile; :75 URTEIL_MUSTER erzwingt `^URTEIL:\s*(FREI|EINWAND)\s*$`; :541-542 setzt bei fehlender Zeile status=fehler. Korrekt.

Behauptung 2 (0=FREI, 1=Fehler, 2=EINWAND):
FALSCH. pruefkreis.py:597 gibt `{"frei": 0, "einwand": 1}.get(status, 2)` zurueck, d.h. 1=EINWAND und 2=Fehler. Die Zuordnung in der Behauptung ist vertauscht. Bestaetigt auch im eigenen Modul-Docstring :52 ("0 = FREI, 1 = EINWAND, 2 = Fehler"). Konkreter Fehler.

Behauptung 3 (--pruefer codex --sensibel vor jedem Lauf abgelehnt):
pruefkreis.py:183-186 wirft PruefkreisFehler, wenn sensibel und pruefer=="codex"; der Aufruf passiert in _pruefen bei :506, der Prueferlauf startet erst bei :519. Korrekt.

Behauptung 4 (Hermes-Lauf mit -t file,todo, Modell und Anbieter explizit):
pruefkreis.py:256-258 setzt `-t file,todo`, `-m HERMES_MODELL` (:70) und `--provider HERMES_ANBIETER` (:71). Korrekt.

Ergebnis: drei von vier Behauptungen stimmen, Behauptung 2 widerspricht dem Code. Da der Plan ausdruecklich sagt, der Aufrufer solle sich auf genau diese vier Zusagen verlassen, ist die vertauschte Exit-Code-Zusage ein sachlicher Fehler und muss korrigiert werden.

URTEIL: EINWAND

Protokoll: <protocol-dir>\demo-exit-codes.md
$ echo $?
1
```

## 3. The fix

One claim corrected; the version number goes up and a one-line review journal records the objection, so the next
reviewer checks whether it was resolved.

```diff
--- a/projects/cross-model-review/demo/demo_plan.md
+++ b/projects/cross-model-review/demo/demo_plan.md
@@ -1,2 +1,2 @@
-# Demo plan: the contract a caller of pruefkreis.py relies on — Fassung 1
+# Demo plan: the contract a caller of pruefkreis.py relies on — Fassung 2
 
@@ -13,4 +13,8 @@
    (surrounding whitespace is ignored); anything else makes the round an error, never an approval.
-2. Exit codes of `pruefkreis.py pruefen`: 0 = `FREI`, 1 = error, 2 = `EINWAND`.
+2. Exit codes of `pruefkreis.py pruefen`: 0 = `FREI`, 1 = `EINWAND`, 2 = error.
 3. `--pruefer codex --sensibel` is rejected before any review starts.
 4. A Hermes review runs with the toolset `-t file,todo`, and model and provider are passed explicitly.
+
+## Review journal
+
+- Round 1: EINWAND — claim 2 had exit codes 1 and 2 swapped (`pruefkreis.py:597`). Corrected in Fassung 2.
```

## 4. Round 2 — approval

```text
$ export PRUEFKREIS_DIR=<protocol-dir>
python projects/cross-model-review/pruefkreis.py pruefen --vorlage projects/cross-model-review/demo/demo_plan.md \
    --thema demo-exit-codes --pruefer hermes --master claude --zeitgrenze 1200
## Runde 2 · 2026-11-17 12:47 · Pruefer hermes · Vorlage `projects/cross-model-review/demo/demo_plan.md`

**Status: FREI**
Modell: deepseek/deepseek-v4.1-flash · Planfassung: 2
Master: claude (angegeben)
Hermes-Sitzung: `local-712234551142e48cf8adbc8585c1c72e61cc232ca66e787a6397a4d111b69ec7`
Kosten: 0.0035 USD
Dauer: 51.5 s

Prüfrunde 2, Datei projects/cross-model-review/demo/demo_plan.md (Fassung 2). Gelesen: demo_plan.md, pruefkreis.py, AGENTS.md.

Früherer Einwand (Journal, Runde 1): Claim 2 — Exit-Codes 1 und 2 vertauscht (pruefkreis.py:597).
Status: erledigt. pruefkreis.py:597 lautet jetzt {"frei": 0, "einwand": 1}.get(status, 2). Docstring pruefkreis.py:52 deckt sich.

Eigene Prüfung der vier Claims am Code:

Claim 1 (nur letzte nichtleere Zeile, exakt URTEIL: FREI/EINWAND, sonst Fehler):
pruefkreis.py:219-225 (urteil_lesen): filtert leere Zeilen, prüft nur zeilen[-1] gegen URTEIL_MUSTER.
pruefkreis.py:75: ^URTEIL:\s*(FREI|EINWAND)\s*$ (Zeilen werden zuvor gestrippt -> umgebende Leerzeichen ignoriert).
pruefkreis.py:541-542: urteil is None -> status fehler. Keine Freigabe ohne gültige Schlusszeile. Bestätigt.

Claim 2 (0=FREI, 1=EINWAND, 2=Fehler):
pruefkreis.py:597 (Mapping) und pruefkreis.py:594 (PruefkreisFehler -> 2). Bestätigt.

Claim 3 (--pruefer codex --sensibel vor jedem Lauf abgelehnt):
pruefkreis.py:183-186 wirft PruefkreisFehler, aufgerufen in pruefer_waehlen; Aufruf erfolgt pruefkreis.py:506, deutlich vor Programmsuche (:513) und Lauf (:519). Bestätigt.

Claim 4 (Hermes-Lauf mit -t file,todo, Modell und Anbieter explizit):
pruefkreis.py:256-258: "-t","file,todo","-m",HERMES_MODELL,"--provider",HERMES_ANBIETER. Werte pruefkreis.py:70-71 (deepseek/deepseek-v4.1-flash, openrouter). Bestätigt.

Nebenbefund ohne Fehlerfolge: URTEIL_MUSTER erlaubt auch "URTEIL:FREI" ohne Leerzeichen (pruefkreis.py:75); die Formulierung "(surrounding whitespace is ignored)" deckt das nicht wörtlich, ändert aber nichts an der Zusage an den Aufrufer. Kein Einwand.

Keine neuen Fehler gefunden; der Runden-1-Einwand ist behoben, alle vier Behauptungen am Code belegt.

URTEIL: FREI

Protokoll: <protocol-dir>\demo-exit-codes.md
$ echo $?
0
```

The reviewer writes that line 597 "now" reads as it does — the code did not change between the rounds; only the
claim in the template did.

## How this was recorded

- Both runs were started from the repository root on Windows (Git Bash, Python 3.12) with the command shown.
  `PRUEFKREIS_DIR` pointed to a folder outside the repository, so the protocol file did not land in the repo.
- **Masking rule — the only change to the output:** the absolute path of that folder is replaced by
  `<protocol-dir>`. It appears in the last line of each run.
- The protocol blocks (from `## Runde` to `URTEIL`) are identical to the protocol file the tool wrote, after the
  same masking; this was compared by script before the commit.
- The reviewer answers in German because the review prompt asks for it.

## Try it yourself

With Hermes installed and signed in (or Codex: `--pruefer codex`), from the repository root:

```bash
python projects/cross-model-review/pruefkreis.py pruefen --vorlage projects/cross-model-review/demo/demo_plan.md \
    --thema demo-exit-codes --pruefer hermes --master claude
```

The model's wording will differ from run to run; the verdict line and the exit code are what a caller relies on.
Without a reviewer installed, the offline test suite covers the same rules — see the
[README](../README.md#check-it-yourself).

← [Back to the project](../README.md)
