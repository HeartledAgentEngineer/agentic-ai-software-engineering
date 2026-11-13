"""Convert stdin text to Klaus speech using the existing OpenRouter TTS client with fast chunk streaming."""
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(os.environ['LOCALAPPDATA']) / 'hermes'
spec = importlib.util.spec_from_file_location('mai', ROOT / 'tts' / 'openrouter_mai.py')
mai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mai)


def stueckeln_fein(text: str, erst_max: int = 150, folge_max: int = 280) -> list[str]:
    """Feines Chunking an Satzgrenzen: Erstes Stueck extra kurz fuer minimale Latenz (< 1.5s)."""
    abbrs = [
        'z. B.', 'z.B.', 'd. h.', 'd.h.', 'bzw.', 'usw.', 'ca.', 'Dr.', 'Prof.',
        'Nr.', 'vs.', 'vgl.', 'inkl.', 'evtl.', 'e.g.', 'i.e.', 'etc.', 'Abb.', 'Tab.'
    ]
    temp = text
    for i, a in enumerate(abbrs):
        temp = temp.replace(a, f'__ABBR_{i}__')

    raw_paras = [p.strip() for p in temp.splitlines() if p.strip()]
    units = []
    for p in raw_paras:
        parts = re.split(r'(?<=[.!?])\s+', p)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(part) > folge_max:
                subparts = re.split(r'(?<=[,;:])\s+', part)
                for sp in subparts:
                    sp = sp.strip()
                    if sp:
                        units.append(sp)
            else:
                units.append(part)

    restored_units = []
    for u in units:
        for i, a in enumerate(abbrs):
            u = u.replace(f'__ABBR_{i}__', a)
        restored_units.append(u)

    chunks = []
    current = ''
    limit = erst_max
    for u in restored_units:
        if current and (len(current) + len(u) + 1 > limit):
            chunks.append(current)
            current = u
            limit = folge_max
        else:
            current = f'{current} {u}'.strip() if current else u
            if len(current) >= limit:
                chunks.append(current)
                current = ''
                limit = folge_max
    if current:
        chunks.append(current)
    return chunks


def beschleunigen(quelle: Path, ziel: Path, tempo: float) -> None:
    """Aendert das Tempo einer MP3 mit ffmpeg, die Tonhoehe bleibt gleich."""
    subprocess.run(
        [mai.ffmpeg_pfad(), '-v', 'error', '-y', '-i', str(quelle), '-filter:a', f'atempo={tempo}',
         '-c:a', 'libmp3lame', '-q:a', '3', str(ziel)],
        check=True, capture_output=True,
    )


def main():
    args = sys.argv[1:]
    tempo = 1.0
    if len(args) == 3 and args[1] == '--tempo':
        tempo = float(args[2])
        args = args[:1]
    if len(args) != 1:
        raise SystemExit('Output path required')
    if not 0.5 <= tempo <= 2.0:
        raise SystemExit('Tempo muss zwischen 0.5 und 2.0 liegen')
    text = sys.stdin.buffer.read().decode('utf-8-sig').strip()
    if not text:
        raise SystemExit('Kein Text zum Vorlesen')
    # Never silently fall back to the general chat key.
    env = mai.ENV.read_text(encoding='utf-8', errors='ignore')
    dedicated = next((line.split('=', 1)[1].strip().strip('"\'') for line in env.splitlines() if line.startswith('OPENROUTER_TTS_KEY=')), '')
    if not dedicated:
        raise SystemExit('Der Vorlese-Schluessel OPENROUTER_TTS_KEY fehlt')
    output = Path(args[0])
    chunks = stueckeln_fein(mai.vorbereiten(text))
    if not chunks:
        raise SystemExit('Kein Text zum Vorlesen')

    # Session directory for streaming audio parts
    session_dir = output.parent / f'session_{output.stem}'
    session_dir.mkdir(parents=True, exist_ok=True)

    pieces = []
    for index, chunk in enumerate(chunks):
        part = session_dir / f'{index:04d}.mp3'
        audio = mai.sprechen(chunk, dedicated, mai.MODELL, mai.STIMME)
        if tempo == 1.0:
            part.write_bytes(audio)
        else:
            roh = session_dir / f'{index:04d}.roh.mp3'
            roh.write_bytes(audio)
            beschleunigen(roh, part, tempo)
            roh.unlink(missing_ok=True)
        pieces.append(part)
        # Flush immediately so the player can start playing Chunk 0 in < 1.5s
        print(f'CHUNK:{part.resolve()}', flush=True)

    # Produce the concatenated single audio file as well
    if len(pieces) == 1:
        output.write_bytes(pieces[0].read_bytes())
    else:
        listing = session_dir / 'list.txt'
        listing.write_text('\n'.join("file '" + p.as_posix() + "'" for p in pieces), encoding='utf-8')
        subprocess.run([mai.ffmpeg_pfad(), '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing), '-c', 'copy', str(output)], check=True, capture_output=True)

    if not output.exists() or output.stat().st_size == 0:
        raise SystemExit('Audiodatei ist leer')
    print('OK', flush=True)


if __name__ == '__main__':
    main()
