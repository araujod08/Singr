"""Transforma músicas (mp3/wav/ogg/flac/m4a) em pastas prontas para o Karaokê.

Como usar (o jeito fácil é o criar_musicas.bat, que chama este script):
  1. Coloque o áudio ORIGINAL (com a voz) na pasta de músicas, de preferência como
     "Artista - Título.mp3".
  2. (Opcional) Coloque a letra em texto com o MESMO nome: "Artista - Título.txt".
  3. Rode:  python audio_to_ultrastar.py --songs <pasta de músicas>

Para cada áudio novo ele:
  - separa voz e instrumental com o demucs (o instrumental vira o playback.mp3);
  - mede o pitch da voz (librosa.pyin) e agrupa em notas;
  - escreve o song.txt, com a sua letra distribuída sobre as notas (se houver letra.txt).
Depois, para adicionar ou corrigir a letra, edite o letra.txt dentro da pasta da música e rode
de novo: só a letra é refeita (rápido, sem separar o áudio outra vez).

Pré-requisitos: ffmpeg no PATH e `pip install -r requirements-tools.txt` (Python 3.11 a 3.14).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from bisect import bisect_left
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import letras_pt  # noqa: E402

AUDIO_EXTS = (".mp3", ".wav", ".ogg", ".flac", ".m4a")
ANALISE = "analise.json"
LETRA = "letra.txt"


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
def extract_features(vocals: Path, hop: int = 256, sr: int = 22050
                     ) -> tuple[np.ndarray, float, list[list[float]]]:
    """Retorna (pitch MIDI por quadro, duração do quadro, ataques [[tempo, força 0-1], ...])."""
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

    # ataques de sílaba (usados para dividir notas quando a letra tem mais sílabas que notas)
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    pico = float(env.max()) or 1.0
    picos = librosa.util.peak_pick(env, pre_max=3, post_max=3, pre_avg=5, post_avg=5,
                                   delta=0.03 * pico, wait=5)
    tempos = librosa.times_like(env, sr=sr, hop_length=hop)
    onsets = [[float(tempos[i]), float(env[i] / pico)] for i in picos]
    return midi, hop / sr, onsets


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


# ------------------------------------------------------------------ letra automática (opcional)
def transcribe_words(vocals: Path, lang: str) -> list[tuple[float, float, str]]:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit("Para --whisper instale: pip install faster-whisper")
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


# ------------------------------------------------------------------ arquivos
def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def is_song_txt(path: Path) -> bool:
    return "#BPM" in read_text(path).upper()


def find_lyrics(folder: Path) -> Path | None:
    """letra.txt, ou qualquer .txt da pasta que não seja um song.txt (sem #BPM)."""
    if (folder / LETRA).exists():
        return folder / LETRA
    return next((p for p in sorted(folder.glob("*.txt")) if not is_song_txt(p)), None)


def split_name(stem: str) -> tuple[str, str]:
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", stem.strip()


def read_header(song_txt: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in read_text(song_txt).splitlines():
        if line.startswith("#"):
            k, _, v = line[1:].partition(":")
            meta[k.strip().upper()] = v.strip()
        else:
            break
    return meta


def write_song(folder: Path, title: str, artist: str, audio_name: str,
               lines: list[list[list]], bpm: float) -> None:
    beat = 15.0 / bpm
    out = [f"#TITLE:{title}", f"#ARTIST:{artist}", f"#MP3:{audio_name}",
           f"#BPM:{bpm:g}", "#GAP:0", "#CREATOR:audio_to_ultrastar"]
    prev_end = 0
    for li, line in enumerate(lines):
        for ni, (s, e, pitch, text) in enumerate(line):
            b0 = max(round(s / beat), prev_end)
            dur = max(1, round((e - s) / beat))
            if ni == 0 and li > 0:
                out.append(f"- {b0}")
            out.append(f": {b0} {dur} {pitch - 60} {text}")
            prev_end = b0 + dur
    out.append("E")
    (folder / "song.txt").write_text("\n".join(out) + "\n", encoding="utf-8")


def save_analysis(folder: Path, notes: list[list], onsets: list) -> None:
    data = {"notas": [[n[0], n[1], n[2]] for n in notes], "onsets": onsets}
    (folder / ANALISE).write_text(json.dumps(data), encoding="utf-8")


def load_analysis(folder: Path) -> tuple[list[list], list]:
    data = json.loads((folder / ANALISE).read_text(encoding="utf-8"))
    return [[s, e, p, "~"] for s, e, p in data["notas"]], data["onsets"]


# ------------------------------------------------------------------ montagem do song.txt
def build(folder: Path, title: str, artist: str, audio_name: str, notes: list[list],
          onsets: list, letra: Path | None, a: argparse.Namespace) -> None:
    lines = None
    if letra is not None:
        lyric = letras_pt.ler_letra(read_text(letra))
        n_sil = sum(len(l) for l in lyric)
        print(f"   letra: {len(lyric)} linhas, {n_sil} sílabas | áudio: {len(notes)} notas")
        if n_sil and not (0.5 * n_sil <= len(notes) <= 1.8 * n_sil):
            print("   AVISO: o número de notas detectadas é bem diferente do de sílabas;"
                  " a sincronia da letra pode ficar fraca (confira se a letra é desta versão).")
        try:
            lines = letras_pt.alinhar_letra(notes, lyric, onsets)
        except ValueError as e:
            print(f"   AVISO: não consegui distribuir a letra ({e}). Gerando sem letra.")
    if lines is None:
        lines = letras_pt.agrupar_por_pausa(notes, a.pausa_linha)
    write_song(folder, title, artist, audio_name, lines, a.bpm)
    pitches = [n[2] for ln in lines for n in ln]
    print(f"   {sum(len(l) for l in lines)} notas em {len(lines)} linhas, extensão "
          f"{min(pitches)}-{max(pitches)} (MIDI) -> {folder / 'song.txt'}")


# ------------------------------------------------------------------ tarefas
def find_jobs(songs_dir: Path, refazer: bool) -> list[tuple[str, Path]]:
    jobs: list[tuple[str, Path]] = []
    for p in sorted(songs_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            jobs.append(("novo", p))
        elif p.is_dir():
            has_song = any(is_song_txt(t) for t in p.glob("*.txt"))
            audios = [f for f in sorted(p.iterdir())
                      if f.suffix.lower() in AUDIO_EXTS and f.stem not in ("playback", "vocals")]
            if refazer and (p / ANALISE).exists() and audios:
                for old in (p / "song.txt", p / ANALISE):
                    old.unlink(missing_ok=True)
                jobs.append(("novo", audios[0]))
            elif not has_song and audios:
                jobs.append(("novo", audios[0]))
            elif has_song and (p / "song.txt").exists():
                letra = find_lyrics(p)
                if letra is None:
                    continue
                if not (p / ANALISE).exists():
                    continue  # música de outra origem: não mexemos
                if letra.stat().st_mtime > (p / "song.txt").stat().st_mtime:
                    jobs.append(("letra", p))
    return jobs


def process_new(audio: Path, songs_dir: Path, a: argparse.Namespace) -> None:
    if audio.parent == songs_dir:  # arquivo solto: cria a pasta da música
        folder = songs_dir / audio.stem
        folder.mkdir(exist_ok=True)
        original = folder / f"original{audio.suffix.lower()}"
        shutil.move(str(audio), original)
        for ext in (".txt", ".TXT"):  # letra solta com o mesmo nome do áudio
            loose = songs_dir / (audio.stem + ext)
            if loose.exists() and not is_song_txt(loose):
                shutil.move(str(loose), folder / LETRA)
                break
        name = audio.stem
    else:
        folder, original = audio.parent, audio
        name = folder.name if audio.stem == "original" else audio.stem
    artist, title = split_name(name)
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
    midi, dt, onsets = extract_features(vocals)
    notes = frames_to_notes(midi, dt)
    fix_octaves(notes)
    if not notes:
        print("   nenhuma nota encontrada (a gravação tem voz?). Pulando.")
        return
    save_analysis(folder, notes, onsets)

    letra = find_lyrics(folder)
    if letra is None and a.whisper:
        print("3/3 transcrevendo a letra (Whisper)...")
        assign_words(notes, transcribe_words(vocals, a.idioma))
        write_song(folder, title, artist, playback.name,
                   letras_pt.agrupar_por_pausa(notes, a.pausa_linha), a.bpm)
        print(f"   -> {folder / 'song.txt'}")
    else:
        print("3/3 " + ("aplicando a letra..." if letra else
                        "sem letra (coloque um .txt com o mesmo nome do áudio)"))
        build(folder, title, artist, playback.name, notes, onsets, letra, a)
    if not (a.manter_voz or a.sem_separar):
        vocals.unlink(missing_ok=True)


def process_lyrics(folder: Path, a: argparse.Namespace) -> None:
    meta = read_header(folder / "song.txt")
    title = meta.get("TITLE", folder.name)
    artist = meta.get("ARTIST", "")
    print(f"\n=== {artist + ' - ' if artist else ''}{title}  (só a letra)")
    notes, onsets = load_analysis(folder)
    build(folder, title, artist, meta.get("MP3", "playback.mp3"), notes, onsets,
          find_lyrics(folder), a)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--songs", default="songs", help="pasta das músicas (padrão: songs)")
    ap.add_argument("--whisper", action="store_true",
                    help="sem letra em texto, tenta transcrever (Whisper; erra bastante)")
    ap.add_argument("--idioma", default="pt", help="idioma do Whisper (padrão: pt)")
    ap.add_argument("--device", help="cpu ou cuda (demucs); padrão: automático")
    ap.add_argument("--bpm", type=float, default=240.0, help="resolução da grade de notas")
    ap.add_argument("--pausa-linha", type=float, default=0.7,
                    help="sem letra: silêncio (s) que separa duas linhas")
    ap.add_argument("--manter-voz", action="store_true", help="não apaga o vocals.wav")
    ap.add_argument("--sem-separar", action="store_true",
                    help="reaproveita vocals.wav e playback.* que já estão na pasta")
    ap.add_argument("--refazer", action="store_true",
                    help="refaz tudo (separação e notas) das músicas já criadas por este script")
    a = ap.parse_args()

    songs_dir = Path(a.songs)
    if not songs_dir.exists():
        raise SystemExit(f"Pasta não encontrada: {songs_dir}")
    jobs = find_jobs(songs_dir, a.refazer)
    if not jobs:
        print(f"Nada novo em {songs_dir}/.\n"
              "  - áudio novo: coloque o .mp3/.wav na pasta (e a letra .txt com o mesmo nome)\n"
              "  - letra nova ou corrigida: edite o letra.txt dentro da pasta da música")
        return
    if any(k == "novo" for k, _ in jobs) and not a.sem_separar and not shutil.which("ffmpeg"):
        print("Aviso: ffmpeg não encontrado no PATH; o demucs precisa dele para ler mp3.")
    for kind, path in jobs:
        try:
            if kind == "novo":
                process_new(path, songs_dir, a)
            else:
                process_lyrics(path, a)
        except Exception as e:  # noqa: BLE001 - uma música com erro não derruba as outras
            print(f"   ERRO em {path.name}: {e}")


if __name__ == "__main__":
    main()
