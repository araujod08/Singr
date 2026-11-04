"""Gera a música de demonstração (escala de Dó) em songs/demo-escala-de-do/."""
import wave
from pathlib import Path

import numpy as np

SR = 22050
BPM = 120          # UltraStar: 1 beat = 15/BPM s = 0.125 s
GAP_MS = 1000

pitches = [0, 2, 4, 5, 7, 9, 11, 12, 11, 9, 7, 5, 4, 2, 0]
syll = ["Dó ", "Ré ", "Mi ", "Fá ", "Sol ", "Lá ", "Si ", "Dó ", "Si ", "Lá ", "Sol ", "Fá ",
        "Mi ", "Ré ", "Dó"]

out = Path(__file__).resolve().parent.parent / "songs" / "demo-escala-de-do"
out.mkdir(parents=True, exist_ok=True)

lines = ["#TITLE:Escala de Dó (demo)", "#ARTIST:Karaokê", "#MP3:playback.wav",
         f"#BPM:{BPM}", f"#GAP:{GAP_MS}"]
beat = 0
notes = []  # (start_beat, dur_beat, pitch)
for i, (p, s) in enumerate(zip(pitches, syll)):
    dur = 16 if i == len(pitches) - 1 else 6
    kind = "*" if i in (7, 14) else ":"
    lines.append(f"{kind} {beat} {dur} {p} {s}")
    notes.append((beat, dur, p))
    beat += 8
    if (i + 1) % 4 == 0 and i != len(pitches) - 1:
        lines.append(f"- {beat}")
lines.append("E")
(out / "song.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

# áudio: pad de acordes + melodia-guia bem baixinha
beat_s = 15 / BPM
total = GAP_MS / 1000 + beat * beat_s + 1.5
t = np.arange(int(total * SR)) / SR
audio = np.zeros_like(t)

chords = [(130.81, 164.81, 196.0), (174.61, 220.0, 261.63), (196.0, 246.94, 293.66),
          (130.81, 164.81, 196.0), (130.81, 164.81, 196.0)]
for k, chord in enumerate(chords):
    a, b = k * 4.0, (k + 1) * 4.0
    seg = (t >= a) & (t < b)
    env = np.minimum(1, (t[seg] - a) / 0.3) * np.minimum(1, (b - t[seg]) / 0.3)
    for f in chord:
        audio[seg] += 0.05 * env * np.sin(2 * np.pi * f * t[seg])

for start, dur, p in notes:
    s0 = GAP_MS / 1000 + start * beat_s
    s1 = s0 + dur * beat_s
    seg = (t >= s0) & (t < s1)
    f = 261.63 * 2 ** (p / 12)
    env = np.minimum(1, (t[seg] - s0) / 0.03) * np.minimum(1, (s1 - t[seg]) / 0.08)
    audio[seg] += 0.10 * env * np.sin(2 * np.pi * f * t[seg])

audio = np.clip(audio, -1, 1)
with wave.open(str(out / "playback.wav"), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((audio * 32767).astype("<i2").tobytes())
print("Demo gerada em", out)
