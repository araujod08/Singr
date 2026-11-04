"""Pontuação: compara a nota cantada com a nota esperada no tempo da música."""
from __future__ import annotations

from bisect import bisect_right

from .song import Note, Song

# tolerância (em cents) para acerto cheio; até 2x isso vale meio ponto
DIFFICULTY = {"Fácil": 80.0, "Normal": 55.0, "Difícil": 35.0}


def fold_diff(sung: float, target: float) -> float:
    """Diferença em semitons ignorando a oitava (resultado em [-6, 6])."""
    d = (sung - target) % 12.0
    return d - 12.0 if d > 6.0 else d


def score_frame(sung: float, target: float, tolerance: float) -> float:
    cents = abs(fold_diff(sung, target)) * 100.0
    if cents <= tolerance:
        return 1.0
    if cents <= tolerance * 2:
        return 0.5
    return 0.0


def grade(score: int) -> str:
    if score >= 9000:
        return "Lendário!"
    if score >= 7500:
        return "Excelente"
    if score >= 5500:
        return "Muito bom"
    if score >= 3500:
        return "Bom"
    if score >= 1500:
        return "Dá pra melhorar"
    return "Continue praticando"


class Scorer:
    def __init__(self, song: Song, tolerance: float = 55.0, latency: float = 0.15):
        self.notes: list[Note] = song.sung_notes
        self._starts = [n.start for n in self.notes]
        self.tolerance = tolerance
        self.latency = latency  # s: atraso entre ouvir a música e a voz chegar ao mic

        self.total = sum(n.duration * (2.0 if n.golden else 1.0) for n in self.notes)
        self.note_time = sum(n.duration for n in self.notes)
        self.earned = 0.0
        self.hit_time = 0.0
        self.combo = 0
        self.best_combo = 0
        self._cur = -1
        self._acc = [0.0, 0.0]  # [tempo acertado, tempo total] da nota atual

    @property
    def score(self) -> int:
        if self.total <= 0:
            return 0
        return max(0, min(10000, round(self.earned / self.total * 10000)))

    @property
    def precision(self) -> float:
        return self.hit_time / self.note_time if self.note_time > 0 else 0.0

    def note_at(self, song_time: float) -> tuple[int, Note | None]:
        t = song_time - self.latency
        i = bisect_right(self._starts, t) - 1
        if i >= 0 and t <= self.notes[i].end:
            return i, self.notes[i]
        return -1, None

    def _close_note(self) -> None:
        if self._cur < 0:
            return
        hit, tot = self._acc
        if tot > 0 and hit / tot >= 0.6:
            self.combo += 1
            self.best_combo = max(self.best_combo, self.combo)
        else:
            self.combo = 0
        self._cur = -1
        self._acc = [0.0, 0.0]

    def update(self, song_time: float, dt: float, sung_midi: float | None
               ) -> tuple[Note | None, bool]:
        """Chame a cada frame. Retorna (nota-alvo atual, acertou neste frame)."""
        dt = max(0.0, min(dt, 0.1))
        i, note = self.note_at(song_time)
        if i != self._cur:
            self._close_note()
            self._cur = i
        if note is None:
            return None, False

        weight = 2.0 if note.golden else 1.0
        s = score_frame(sung_midi, note.midi, self.tolerance) if sung_midi is not None else 0.0
        self.earned += dt * weight * s
        self._acc[1] += dt
        if s >= 1.0:
            self.hit_time += dt
            self._acc[0] += dt
        elif s > 0:
            self._acc[0] += dt * s
        return note, s > 0

    def finish(self) -> None:
        self._close_note()
