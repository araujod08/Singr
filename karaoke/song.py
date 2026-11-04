"""Leitura de músicas no formato UltraStar (.txt) e varredura da pasta songs/."""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

AUDIO_EXTS = (".mp3", ".ogg", ".wav", ".flac", ".m4a")
IMAGE_EXTS = (".jpg", ".jpeg", ".png")


@dataclass
class Note:
    start: float  # segundos
    end: float
    midi: int
    text: str
    kind: str = ":"  # ":" normal, "*" dourada, "F"/"R"/"G" livre (não pontua)

    @property
    def freestyle(self) -> bool:
        return self.kind in ("F", "R", "G")

    @property
    def golden(self) -> bool:
        return self.kind == "*"

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Line:
    notes: list[Note]

    @property
    def start(self) -> float:
        return self.notes[0].start

    @property
    def end(self) -> float:
        return self.notes[-1].end


@dataclass
class Song:
    folder: Path
    title: str
    artist: str
    audio: Path | None
    cover: Path | None
    lines: list[Line]

    @cached_property
    def notes(self) -> list[Note]:
        return [n for line in self.lines for n in line.notes]

    @cached_property
    def sung_notes(self) -> list[Note]:
        return sorted((n for n in self.notes if not n.freestyle), key=lambda n: n.start)

    @cached_property
    def pitch_range(self) -> tuple[int, int]:
        ms = [n.midi for n in self.sung_notes] or [60]
        return min(ms), max(ms)

    @cached_property
    def duration(self) -> float:
        return max((line.end for line in self.lines), default=0.0)

    @property
    def key(self) -> str:
        return self.folder.name

    @property
    def label(self) -> str:
        return f"{self.artist} — {self.title}" if self.artist else self.title


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def load_song(txt: Path) -> Song:
    meta: dict[str, str] = {}
    raw_lines: list[list[tuple[str, int, int, int, str]]] = []
    current: list[tuple[str, int, int, int, str]] = []

    for line in _read_text(txt).splitlines():
        if not line.strip():
            continue
        if line.startswith("#"):
            key, _, value = line[1:].partition(":")
            meta[key.strip().upper()] = value.strip()
            continue
        c = line[0]
        if c == "E":
            break
        if c in ":*FRG":
            parts = line.split(" ", 4)
            if len(parts) < 4:
                continue
            try:
                beat, dur, pitch = int(parts[1]), int(parts[2]), int(parts[3])
            except ValueError:
                continue
            text = parts[4] if len(parts) > 4 else ""
            current.append((c, beat, dur, pitch, text))
        elif c == "-":
            if current:
                raw_lines.append(current)
                current = []
    if current:
        raw_lines.append(current)

    if "BPM" not in meta:
        raise ValueError(f"{txt}: tag #BPM ausente")
    bpm = float(meta["BPM"].replace(",", "."))
    gap = float(meta.get("GAP", "0").replace(",", ".")) / 1000.0
    beat_sec = 15.0 / bpm  # em UltraStar, 1 beat = 1/4 de tempo

    def sec(beat: int) -> float:
        return gap + beat * beat_sec

    lines: list[Line] = []
    for raw in raw_lines:
        notes = [
            Note(
                start=sec(beat),
                end=max(sec(beat + dur), sec(beat) + 0.02),
                midi=60 + pitch,  # pitch 0 = C4 = MIDI 60
                text=text,
                kind=kind,
            )
            for kind, beat, dur, pitch, text in raw
        ]
        lines.append(Line(notes))

    folder = txt.parent
    audio = None
    for tag in ("MP3", "AUDIO"):
        if tag in meta and (folder / meta[tag]).exists():
            audio = folder / meta[tag]
            break
    if audio is None:
        audio = next(
            (p for p in sorted(folder.iterdir()) if p.suffix.lower() in AUDIO_EXTS), None
        )
    cover = None
    if "COVER" in meta and (folder / meta["COVER"]).exists():
        cover = folder / meta["COVER"]
    else:
        cover = next(
            (p for p in sorted(folder.iterdir()) if p.suffix.lower() in IMAGE_EXTS), None
        )

    return Song(
        folder=folder,
        title=meta.get("TITLE", folder.name),
        artist=meta.get("ARTIST", ""),
        audio=audio,
        cover=cover,
        lines=lines,
    )


def scan_library(root: Path) -> tuple[list[Song], list[str]]:
    """Procura músicas em root/<pasta>/*.txt. Retorna (músicas, erros)."""
    songs: list[Song] = []
    errors: list[str] = []
    if not root.exists():
        return songs, errors
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        for txt in sorted(folder.glob("*.txt")):
            try:
                if "#BPM" not in _read_text(txt).upper():
                    continue
                songs.append(load_song(txt))
                break
            except Exception as e:  # noqa: BLE001 - mostramos o erro ao usuário
                errors.append(f"{folder.name}: {e}")
    songs.sort(key=lambda s: s.label.lower())
    return songs, errors
