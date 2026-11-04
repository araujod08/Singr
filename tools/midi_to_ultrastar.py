"""Converte a melodia vocal de um arquivo MIDI em um song.txt (UltraStar).

Uso:
  pip install pretty_midi
  python tools/midi_to_ultrastar.py musica.mid --listar
  python tools/midi_to_ultrastar.py musica.mid --track 1 --saida songs/minha-musica \
      --titulo "Minha Música" --artista "Fulano" --audio playback.mp3

Depois copie o playback (mp3/ogg/wav) para a mesma pasta. Se o MIDI não tiver letra,
as sílabas saem como "~" e você edita o song.txt (ou usa o editor Yass/UltraStar Creator).
"""
import argparse
from pathlib import Path

import pretty_midi


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("midi")
    ap.add_argument("--listar", action="store_true", help="lista as trilhas e sai")
    ap.add_argument("--track", type=int, help="índice da trilha com a melodia vocal")
    ap.add_argument("--saida", default="songs/nova-musica")
    ap.add_argument("--titulo", default="Sem título")
    ap.add_argument("--artista", default="")
    ap.add_argument("--audio", default="playback.mp3")
    ap.add_argument("--bpm", type=float, default=240.0, help="resolução (beats UltraStar/min)")
    ap.add_argument("--pausa-linha", type=float, default=0.7,
                    help="silêncio (s) que separa duas linhas de letra")
    a = ap.parse_args()

    pm = pretty_midi.PrettyMIDI(a.midi)
    if a.listar or a.track is None:
        for i, inst in enumerate(pm.instruments):
            print(f"[{i}] {inst.name or '(sem nome)'}  programa={inst.program}  "
                  f"notas={len(inst.notes)}")
        return

    notes = sorted(pm.instruments[a.track].notes, key=lambda n: n.start)
    if not notes:
        raise SystemExit("Trilha vazia.")
    # monofônico: corta a nota que se sobrepõe à próxima
    spans = []
    for i, n in enumerate(notes):
        end = n.end if i == len(notes) - 1 else min(n.end, notes[i + 1].start)
        if end > n.start:
            spans.append([n.start, end, n.pitch, "~"])

    # letras do MIDI (se houver): associa cada uma à nota que começa mais perto
    for ly in pm.lyrics:
        best = min(spans, key=lambda s: abs(s[0] - ly.time))
        if abs(best[0] - ly.time) < 0.15:
            txt = ly.text.strip().strip("/\\")
            best[3] = txt[:-1] if txt.endswith("-") else txt + " "   # "-" = sílaba continua

    beat = 15.0 / a.bpm
    out = [f"#TITLE:{a.titulo}", f"#ARTIST:{a.artista}", f"#MP3:{a.audio}",
           f"#BPM:{a.bpm:g}", "#GAP:0"]
    prev_end = None
    for s0, s1, pitch, text in spans:
        b0 = round(s0 / beat)
        dur = max(1, round((s1 - s0) / beat))
        if prev_end is not None and s0 - prev_end >= a.pausa_linha:
            out.append(f"- {b0}")
        out.append(f": {b0} {dur} {pitch - 60} {text}")
        prev_end = s1
    out.append("E")

    dest = Path(a.saida)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "song.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Gerado {dest / 'song.txt'} ({len(spans)} notas). Copie o áudio para {dest}/")


if __name__ == "__main__":
    main()
