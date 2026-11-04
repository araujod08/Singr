"""Transforma músicas (mp3/wav/ogg/flac/m4a) em pastas prontas para o Karaokê.

Como usar:
  1. Jogue os áudios (gravação ORIGINAL, com a voz) dentro de songs/
     (soltos ou em pastas). Nome sugerido:  "Artista - Título.mp3"
  2. Rode:  python tools/audio_to_ultrastar.py
  3. Para cada música ele:
       - separa voz e instrumental com o demucs (o instrumental vira o playback.mp3)
       - mede o pitch da voz (librosa.pyin) e agrupa em notas
       - escreve o song.txt (letra opcional com --letra)
  4. Abra o app. Revise no Yass Reloaded se quiser (erros de nota e letra são normais).

Pré-requisitos: ffmpeg no PATH e `pip install -r requirements-tools.txt`.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from bisect import bisect_left
from pathlib import Path

import numpy as np

AUDIO_EXTS = (".mp3", ".wav", ".ogg", ".flac", ".m4a")


# ------------------------------------------------------------------ separação
def separate(audio: Path, workdir: Path, device: str | None) -> tuple[Path, Path]:
    cmd = [sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs",
           "-o", str(workdir)]
    if device:
        cmd += ["-d", device]
    cmd.append(str(audio))
    subprocess.run(cmd, check=True)
    out = workdir / "htdemucs" / audio.stem
    return out / "vocals.wav", out / "no_vocals.wav"


def encode_playback(wav: Path, dest_dir: Path) -> Path:
    if shutil.which("ffmpeg"):
        out = dest_dir / "playback.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                        "-codec:a", "libmp3lame", "-q:a", "2", str(out)], check=True)
        return out
    out = dest_dir / "playback.wav"
    shutil.copy(wav, out)
    return out


# ------------------------------------------------------------------ pitch -> notas
def extract_pitch(vocals: Path, hop: int = 256, sr: int = 22050) -> tuple[np.ndarray, float]:
    import librosa

    y, sr = librosa.load(str(vocals), sr=sr, mono=True)
    f0, voiced, _ = librosa.pyin(
        y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C6"),
        sr=sr, frame_length=2048, hop_length=hop)
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
    n = min(len(f0), len(rms))
    f0, voiced, rms = f0[:n], voiced[:n], rms[:n]
    ok = voiced & ~np.isnan(f0) & (rms > max(rms.max() * 0.03, 1e-4))
    midi = np.full(n, np.nan)
    midi[ok] = librosa.hz_to_midi(f0[ok])
    return midi, hop / sr


def _rle(q: np.ndarray) -> list[list[int]]:
    runs, s = [], 0
    for i in range(1, len(q) + 1):
        if i == len(q) or q[i] != q[s]:
            runs.append([int(q[s]), s, i])
            s = i
    return runs


def _absorb_short(runs: list[list[int]], min_frames: int) -> list[list[int]]:
    """Funde trechos curtos (vibrato, oscilações) no vizinho de pitch mais próximo."""
    while len(runs) > 1:
        i = min(range(len(runs)), key=lambda k: runs[k][2] - runs[k][1])
        if runs[i][2] - runs[i][1] >= min_frames:
            break
        cand = [j for j in (i - 1, i + 1) if 0 <= j < len(runs)]
        j = min(cand, key=lambda j: (abs(runs[j][0] - runs[i][0]), -(runs[j][2] - runs[j][1])))
        lo, hi = min(i, j), max(i, j)
        runs[lo:hi + 1] = [[runs[j][0], runs[lo][1], runs[hi][2]]]
        k = 0
        while k < len(runs) - 1:  # une vizinhos com o mesmo pitch
            if runs[k][0] == runs[k + 1][0]:
                runs[k] = [runs[k][0], runs[k][1], runs[k + 1][2]]
                del runs[k + 1]
            else:
                k += 1
    return runs


def frames_to_notes(midi: np.ndarray, dt: float, min_note: float = 0.10,
                    max_gap: float = 0.12) -> list[list]:
    """Retorna [[início_s, fim_s, pitch_midi, texto], ...]."""
    from scipy.ndimage import median_filter

    v = np.flatnonzero(~np.isnan(midi))
    if v.size == 0:
        return []
    gap_frames = max(1, int(max_gap / dt))
    min_frames = max(2, round(min_note / dt))
    notes: list[list] = []
    for g in np.split(v, np.flatnonzero(np.diff(v) > gap_frames) + 1):
        a, b = int(g[0]), int(g[-1]) + 1
        seg = midi[a:b].copy()
        nan = np.isnan(seg)
        if nan.any():
            seg[nan] = np.interp(np.flatnonzero(nan), np.flatnonzero(~nan), seg[~nan])
        seg = median_filter(seg, size=7, mode="nearest")
        runs = _absorb_short(_rle(np.round(seg).astype(int)), min_frames)
        for value, s, e in runs:
            if e - s >= min_frames:
                notes.append([(a + s) * dt, (a + e) * dt, value, "~"])
    return notes


def fix_octaves(notes: list[list]) -> None:
    """Corrige saltos de ±1 oitava isolados (erro comum do pyin)."""
    orig = [n[2] for n in notes]
    for i, n in enumerate(notes):
        nb = orig[max(0, i - 3):i] + orig[i + 1:i + 4]
        if len(nb) < 2:
            continue
        d = orig[i] - float(np.median(nb))
        if abs(d) >= 10.5 and abs(abs(d) - 12) <= 2:
            n[2] = orig[i] - 12 * round(d / 12)


# ------------------------------------------------------------------ letra (opcional)
def transcribe_words(vocals: Path, lang: str) -> list[tuple[float, float, str]]:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit("Para --letra instale: pip install faster-whisper")
    model = WhisperModel("small", device="auto", compute_type="int8")
    segments, _ = model.transcribe(str(vocals), language=lang, word_timestamps=True,
                                   vad_filter=True)
    return [(w.start, w.end, w.word.strip()) for s in segments for w in (s.words or [])]


def assign_words(notes: list[list], words: list[tuple[float, float, str]]) -> None:
    """Coloca cada palavra na nota que começa junto dela; as demais ficam como '~'."""
    starts = [n[0] for n in notes]
    for ws, we, text in words:
        if not text:
            continue
        i = bisect_left(starts, ws - 0.12)
        if i < len(notes) and notes[i][0] < we and notes[i][3] == "~":
            notes[i][3] = text + " "


# ------------------------------------------------------------------ escrita
def write_song(folder: Path, title: str, artist: str, audio_name: str,
               notes: list[list], bpm: float, line_pause: float) -> None:
    beat = 15.0 / bpm
    out = [f"#TITLE:{title}", f"#ARTIST:{artist}", f"#MP3:{audio_name}",
           f"#BPM:{bpm:g}", "#GAP:0", "#CREATOR:audio_to_ultrastar"]
    prev_end_s, prev_end_b = None, 0
    for s, e, pitch, text in notes:
        b0 = max(round(s / beat), prev_end_b)
        dur = max(1, round((e - s) / beat))
        if prev_end_s is not None and s - prev_end_s >= line_pause:
            out.append(f"- {b0}")
        out.append(f": {b0} {dur} {pitch - 60} {text}")
        prev_end_s, prev_end_b = e, b0 + dur
    out.append("E")
    (folder / "song.txt").write_text("\n".join(out) + "\n", encoding="utf-8")


def split_name(stem: str) -> tuple[str, str]:
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", stem.strip()


# ------------------------------------------------------------------ orquestração
def find_jobs(songs_dir: Path) -> list[Path]:
    jobs = []
    for p in sorted(songs_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            jobs.append(p)
        elif p.is_dir() and not any(p.glob("*.txt")):
            audios = [f for f in sorted(p.iterdir())
                      if f.suffix.lower() in AUDIO_EXTS and f.stem != "playback"]
            if audios:
                jobs.append(audios[0])
    return jobs


def process(audio: Path, songs_dir: Path, a: argparse.Namespace) -> None:
    if audio.parent == songs_dir:  # arquivo solto: cria a pasta da música
        folder = songs_dir / audio.stem
        folder.mkdir(exist_ok=True)
        original = folder / f"original{audio.suffix.lower()}"
        shutil.move(str(audio), original)
    else:
        folder, original = audio.parent, audio
    # numa nova execução o áudio já se chama original.*: usa o nome da pasta
    artist, title = split_name(folder.name if audio.stem == "original" else audio.stem)
    print(f"\n=== {artist + ' - ' if artist else ''}{title}")

    if a.sem_separar:
        vocals = folder / "vocals.wav"
        playback = next(folder.glob("playback.*"))
        if not vocals.exists():
            raise SystemExit(f"--sem-separar precisa de {vocals}")
    else:
        print("1/3 separando voz e instrumental (demora alguns minutos)...")
        tmp = folder / "_tmp"
        v, nv = separate(original, tmp, a.device)
        playback = encode_playback(nv, folder)
        vocals = folder / "vocals.wav"
        shutil.copy(v, vocals)
        shutil.rmtree(tmp, ignore_errors=True)

    print("2/3 extraindo a melodia...")
    midi, dt = extract_pitch(vocals)
    notes = frames_to_notes(midi, dt)
    fix_octaves(notes)
    if not notes:
        print("   nenhuma nota encontrada (a gravação tem voz?). Pulando.")
        return

    if a.letra:
        print("3/3 transcrevendo a letra (Whisper)...")
        assign_words(notes, transcribe_words(vocals, a.idioma))
    else:
        print("3/3 sem letra (use --letra para tentar transcrever)")

    write_song(folder, title, artist, playback.name, notes, a.bpm, a.pausa_linha)
    if not (a.manter_voz or a.sem_separar):
        vocals.unlink(missing_ok=True)
    pitches = [n[2] for n in notes]
    print(f"   {len(notes)} notas, extensão {min(pitches)}–{max(pitches)} (MIDI) -> {folder / 'song.txt'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--songs", default="songs", help="pasta das músicas (padrão: songs)")
    ap.add_argument("--letra", action="store_true", help="tenta transcrever a letra (Whisper)")
    ap.add_argument("--idioma", default="pt", help="idioma da letra (padrão: pt)")
    ap.add_argument("--device", help="cpu ou cuda (demucs); padrão: automático")
    ap.add_argument("--bpm", type=float, default=240.0, help="resolução da grade de notas")
    ap.add_argument("--pausa-linha", type=float, default=0.7,
                    help="silêncio (s) que separa duas linhas de letra")
    ap.add_argument("--manter-voz", action="store_true", help="não apaga o vocals.wav")
    ap.add_argument("--sem-separar", action="store_true",
                    help="reaproveita vocals.wav e playback.* que já estão na pasta")
    a = ap.parse_args()

    songs_dir = Path(a.songs)
    if not songs_dir.exists():
        raise SystemExit(f"Pasta não encontrada: {songs_dir}")
    if not a.sem_separar and not shutil.which("ffmpeg"):
        print("Aviso: ffmpeg não encontrado no PATH; o demucs precisa dele para ler mp3.")
    jobs = find_jobs(songs_dir)
    if not jobs:
        print(f"Nenhum áudio novo em {songs_dir}/. (Pastas com song.txt são ignoradas.)")
        return
    for audio in jobs:
        try:
            process(audio, songs_dir, a)
        except Exception as e:  # noqa: BLE001 - uma música com erro não derruba as outras
            print(f"   ERRO em {audio.name}: {e}")


if __name__ == "__main__":
    main()
