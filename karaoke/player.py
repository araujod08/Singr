"""Tocador do playback + relógio da música (com contagem regressiva e pausa)."""
from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402


# Se o driver padrão (WASAPI) não achar a saída de áudio, tenta estes antes de desistir
FALLBACK_DRIVERS = ("directsound", "winmm")


def init_mixer() -> None:
    """Inicia o mixer; tenta drivers alternativos se o padrão falhar. Pode demorar: use em thread."""
    if pygame.mixer.get_init():
        return
    first: pygame.error | None = None
    previous = os.environ.get("SDL_AUDIODRIVER")
    for driver in (None, *FALLBACK_DRIVERS):
        if driver:
            os.environ["SDL_AUDIODRIVER"] = driver
        try:
            pygame.mixer.init()
            return
        except pygame.error as e:
            first = first or e
            pygame.mixer.quit()
    if previous is None:
        os.environ.pop("SDL_AUDIODRIVER", None)
    else:
        os.environ["SDL_AUDIODRIVER"] = previous
    raise first  # type: ignore[misc]


class Player:
    def __init__(self) -> None:
        init_mixer()
        self._audio: Path | None = None
        self._end_time = 0.0
        self._started = False
        self._t0 = 0.0
        self._paused_at: float | None = None

    def load(self, audio: Path | None, end_time: float) -> None:
        self._audio = audio
        self._end_time = end_time
        if audio:
            pygame.mixer.music.load(str(audio))

    def start(self, lead_in: float = 3.0) -> None:
        self._started = False
        self._paused_at = None
        self._t0 = time.perf_counter() + lead_in  # tempo da música começa em -lead_in

    def update(self) -> None:
        """Dispara o áudio quando a contagem regressiva termina."""
        if self._paused_at is None and not self._started and self.time() >= 0:
            if self._audio:
                pygame.mixer.music.play()
            self._started = True
            self._t0 = time.perf_counter()

    def time(self) -> float:
        ref = self._paused_at if self._paused_at is not None else time.perf_counter()
        return ref - self._t0

    @property
    def paused(self) -> bool:
        return self._paused_at is not None

    def pause(self) -> None:
        if self._paused_at is None:
            self._paused_at = time.perf_counter()
            if self._started:
                pygame.mixer.music.pause()

    def resume(self) -> None:
        if self._paused_at is not None:
            self._t0 += time.perf_counter() - self._paused_at
            self._paused_at = None
            if self._started:
                pygame.mixer.music.unpause()

    @property
    def finished(self) -> bool:
        if not self._started or self.paused:
            return False
        t = self.time()
        if self._audio and t > 1.0 and not pygame.mixer.music.get_busy():
            return True
        return t > self._end_time

    def stop(self) -> None:
        try:
            pygame.mixer.music.stop()
        except pygame.error:
            pass
