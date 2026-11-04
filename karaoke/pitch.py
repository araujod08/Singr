"""Captura do microfone e detecção de pitch (YIN, implementado com FFT)."""
from __future__ import annotations

import threading
from collections import deque

import numpy as np

NOTE_NAMES = ["Dó", "Dó#", "Ré", "Ré#", "Mi", "Fá", "Fá#", "Sol", "Sol#", "Lá", "Lá#", "Si"]


def freq_to_midi(f: float) -> float:
    return 69.0 + 12.0 * np.log2(f / 440.0)


def note_name(midi: float) -> str:
    r = int(round(midi))
    cents = int(round((midi - r) * 100))
    return f"{NOTE_NAMES[r % 12]}{r // 12 - 1} ({cents:+d}¢)"


def yin(x: np.ndarray, sr: float, fmin: float = 80.0, fmax: float = 1000.0,
        threshold: float = 0.15) -> float | None:
    """Estima a frequência fundamental de um bloco de áudio. None = sem pitch."""
    n = len(x)
    tau_max = min(int(sr / fmin), n // 2)
    tau_min = max(2, int(sr / fmax))
    w = n - tau_max
    if w <= tau_max // 2:
        return None

    # função de diferença d(tau) via FFT (O(n log n) em vez de O(n²))
    nfft = 1 << (n + w - 1).bit_length()
    a = np.fft.rfft(x[:w], nfft)
    b = np.fft.rfft(x, nfft)
    acf = np.fft.irfft(np.conj(a) * b, nfft)[:tau_max]
    cs = np.concatenate(([0.0], np.cumsum(x * x)))
    taus = np.arange(tau_max)
    d = cs[w] + (cs[taus + w] - cs[taus]) - 2.0 * acf
    d[0] = 0.0

    # diferença média normalizada cumulativa
    cmnd = np.ones(tau_max)
    cmnd[1:] = d[1:] * taus[1:] / np.maximum(np.cumsum(d[1:]), 1e-12)

    below = np.nonzero(cmnd[tau_min:tau_max - 1] < threshold)[0]
    if below.size == 0:
        return None
    tau = int(below[0]) + tau_min
    while tau + 1 < tau_max - 1 and cmnd[tau + 1] < cmnd[tau]:
        tau += 1

    t = float(tau)
    if 1 <= tau < tau_max - 1:  # interpolação parabólica
        s0, s1, s2 = cmnd[tau - 1], cmnd[tau], cmnd[tau + 1]
        denom = s0 - 2.0 * s1 + s2
        if denom != 0:
            t += 0.5 * (s0 - s2) / denom
    return sr / t


def input_channels(device: int | None) -> int:
    """Quantos canais de entrada o dispositivo tem (None = padrão do sistema)."""
    try:
        import sounddevice as sd

        return max(1, int(sd.query_devices(device, "input")["max_input_channels"]))
    except Exception:  # noqa: BLE001
        return 1


def refresh_devices() -> None:
    """Relê a lista de dispositivos (o PortAudio guarda a lista do momento em que abriu)."""
    try:
        import sounddevice as sd

        sd._terminate()
        sd._initialize()
    except Exception:  # noqa: BLE001
        pass


def level_db(rms: float) -> float:
    return 20.0 * float(np.log10(max(rms, 1e-6)))


def db_to_gate(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def list_input_devices() -> list[tuple[int, str]]:
    try:
        import sounddevice as sd

        apis = sd.query_hostapis()
        out = []
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                out.append((i, f"{dev['name']} ({apis[dev['hostapi']]['name']})"))
        return out
    except Exception:  # noqa: BLE001
        return []


class PitchTracker:
    """Lê o microfone continuamente; `.midi` traz a nota atual (float) ou None."""

    WINDOW = 2048

    def __init__(self, device: int | None = None, gate: float = 0.012, channel: int = 0):
        self.device = device
        self.gate = gate  # amplitude RMS mínima para considerar que há voz
        self.channel = channel  # canal de entrada (0 = entrada 1)
        self._ch = 0
        self.level = 0.0
        self._buf = np.zeros(self.WINDOW, dtype=np.float32)
        self._hist: deque[float | None] = deque(maxlen=3)
        self._lock = threading.Lock()
        self._stream = None
        self.sr = 44100.0

    def start(self) -> None:
        import sounddevice as sd

        info = sd.query_devices(self.device, "input")
        self.sr = float(info["default_samplerate"])
        self._ch = max(0, min(self.channel, int(info["max_input_channels"]) - 1))
        self._stream = sd.InputStream(
            device=self.device, samplerate=self.sr, channels=self._ch + 1,
            blocksize=1024, dtype="float32", callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    def _callback(self, indata, frames, time_info, status) -> None:
        x = indata[:, self._ch]
        n = len(x)
        if n >= self.WINDOW:
            self._buf = x[-self.WINDOW:].copy()
        else:
            self._buf = np.roll(self._buf, -n)
            self._buf[-n:] = x
        rms = float(np.sqrt(np.mean(self._buf[-1024:] ** 2)))
        self.level = rms
        midi = None
        if rms >= self.gate:
            f = yin(self._buf.astype(np.float64), self.sr)
            if f:
                midi = float(freq_to_midi(f))
        with self._lock:
            self._hist.append(midi)

    @property
    def midi(self) -> float | None:
        with self._lock:
            vals = [v for v in self._hist if v is not None]
        if len(vals) < 2:
            return None
        return float(np.median(vals))
