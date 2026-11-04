"""Interface (PySide6): biblioteca, tela de canto com barras de notas e resultado."""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QSlider, QSpinBox,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .pitch import (PitchTracker, db_to_gate, input_channels, level_db, list_input_devices,
                    note_name, refresh_devices)
from .player import Player
from .scoring import DIFFICULTY, Scorer, grade
from .song import Song, scan_library

STYLE = """
QWidget { background: #0b0f1a; color: #e6e9f2; font-size: 14px; }
QListWidget { background: #121829; border: 1px solid #222b45; border-radius: 8px; padding: 4px; }
QListWidget::item { padding: 10px; border-radius: 6px; }
QListWidget::item:selected { background: #2b4fd8; color: white; }
QPushButton { background: #1b2340; border: 1px solid #2c3760; border-radius: 8px; padding: 9px 14px; }
QPushButton:hover { background: #243057; }
QPushButton#primary { background: #2b6cff; border: none; font-weight: bold; font-size: 16px; padding: 12px; }
QPushButton#primary:hover { background: #4a82ff; }
QComboBox, QSpinBox { background: #121829; border: 1px solid #2c3760; border-radius: 6px; padding: 6px; }
QProgressBar { background: #121829; border: 1px solid #2c3760; border-radius: 6px; height: 10px; text-align: center; }
QProgressBar::chunk { background: #37e08a; border-radius: 5px; }
QLabel#h1 { font-size: 22px; font-weight: bold; }
QLabel#muted { color: #8791b0; }
QLabel#footer { color: #8791b0; font-size: 12px; padding: 6px 0 9px 0; }
"""


# Créditos exibidos no rodapé (edite aqui)
CREDITS_LABEL = "By:"
CREDITS_URL = "https://github.com/araujod08"


def _fmt_score(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _level_pct(rms: float) -> int:
    """Nível do mic em % numa escala de -60 dB a 0 dB (a mesma do portão de ruído)."""
    return int(max(0, min(100, (level_db(rms) + 60.0) / 60.0 * 100.0)))


def mic_error_text(detail: str) -> str:
    return ("Não consegui abrir o microfone.\n\n"
            "Confira se há um microfone conectado e ativado e se o Windows permite que apps "
            "de computador o usem (Configurações > Privacidade e segurança > Microfone). "
            "Depois clique em Recarregar e tente de novo.\n\n"
            f"Detalhe técnico: {detail}")


def audio_error_text(detail: str) -> str:
    return ("Não encontrei uma saída de áudio para tocar a música.\n\n"
            "Conecte caixas de som ou fones e confira se estão selecionados como saída padrão "
            "no Windows (ícone de som na barra de tarefas). Depois tente de novo.\n\n"
            f"Detalhe técnico: {detail}")


class _OpenSession(QThread):
    """Prepara microfone E áudio fora da thread da janela: no Windows, sem o dispositivo,
    cada abertura pode levar vários segundos e congelaria a interface."""
    ok = Signal(object)          # Player pronto
    failed = Signal(str, str)    # ("mic" | "audio", detalhe)

    def __init__(self, tracker: PitchTracker, song: Song, parent=None) -> None:
        super().__init__(parent)
        self.tracker, self.song = tracker, song

    def run(self) -> None:
        try:
            self.tracker.start()
        except Exception as e:  # noqa: BLE001
            self.failed.emit("mic", str(e))
            return
        try:
            player = Player()
            player.load(self.song.audio, self.song.duration + 1.5)
        except Exception as e:  # noqa: BLE001
            self.tracker.stop()
            self.failed.emit("audio", str(e))
            return
        self.ok.emit(player)


class _OpenMic(QThread):
    """Abre o microfone fora da thread da interface (no Windows isso pode demorar)."""
    ok = Signal()
    failed = Signal(str)

    def __init__(self, tracker: PitchTracker, parent=None) -> None:
        super().__init__(parent)
        self.tracker = tracker

    def run(self) -> None:
        try:
            self.tracker.start()
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))
        else:
            self.ok.emit()


# --------------------------------------------------------------------------- barras de notas
class NoteRoll(QWidget):
    PAST, FUTURE = 1.5, 5.0  # segundos visíveis antes/depois do "agora"

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(280)
        self.song: Song | None = None
        self.t = 0.0
        self.trace: list[tuple[float, float, bool]] = []  # (tempo-alvo, midi exibido, acertou)
        self.paused = False

    def reset(self, song: Song) -> None:
        self.song, self.t, self.trace, self.paused = song, -3.0, [], False
        self.update()

    def push(self, t: float, midi: float, hit: bool) -> None:
        self.trace.append((t, midi, hit))

    def set_time(self, t: float) -> None:
        self.t = t
        cutoff = t - self.PAST - 0.5
        if self.trace and self.trace[0][0] < cutoff:
            self.trace = [p for p in self.trace if p[0] >= cutoff]
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#0d1220"))
        song = self.song
        if song is None:
            return

        lo, hi = song.pitch_range
        lo_v, hi_v = lo - 2, hi + 2
        lanes = hi_v - lo_v + 1
        pad = 8.0
        lane_h = (h - 2 * pad) / lanes
        px_s = w / (self.PAST + self.FUTURE)
        now_x = self.PAST * px_s

        def x_of(t: float) -> float:
            return now_x + (t - self.t) * px_s

        def y_of(m: float) -> float:
            return pad + (hi_v - m) * lane_h

        # faixas de fundo (teclas pretas mais escuras)
        for i in range(lanes):
            m = hi_v - i
            black = (m % 12) in (1, 3, 6, 8, 10)
            p.fillRect(QRectF(0, pad + i * lane_h, w, lane_h),
                       QColor("#0a0e19" if black else "#111830"))

        # notas
        p.setPen(Qt.NoPen)
        for n in song.notes:
            if n.end < self.t - self.PAST or n.start > self.t + self.FUTURE:
                continue
            x1, x2 = x_of(n.start), x_of(n.end)
            width = max(x2 - x1, 3.0)
            if n.freestyle:
                p.setBrush(QColor(150, 150, 170, 60))
                p.drawRoundedRect(QRectF(x1, pad, width, h - 2 * pad), 6, 6)
                continue
            rect = QRectF(x1, y_of(n.midi) + lane_h * 0.1, width, lane_h * 0.8)
            base = QColor("#ffc233") if n.golden else QColor("#4f8cff")
            if n.end < self.t:
                base.setAlpha(110)
            p.setBrush(base)
            p.drawRoundedRect(rect, lane_h * 0.35, lane_h * 0.35)

        # linha "agora"
        p.setPen(QPen(QColor(255, 255, 255, 90), 2))
        p.drawLine(QPointF(now_x, 0), QPointF(now_x, h))

        # voz do cantor
        if self.trace:
            pen_w = max(4.0, lane_h * 0.5)
            prev = None
            for t, m, hit in self.trace:
                x, y = x_of(t), y_of(m) + lane_h / 2
                if prev is not None and t - prev[0] < 0.12:
                    p.setPen(QPen(QColor("#37e08a" if hit else "#ff7a59"), pen_w,
                                  Qt.SolidLine, Qt.RoundCap))
                    p.drawLine(QPointF(prev[1], prev[2]), QPointF(x, y))
                prev = (t, x, y)
            if prev is not None and self.t - prev[0] < 0.4:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("white"))
                p.drawEllipse(QPointF(prev[1], prev[2]), pen_w * 0.35, pen_w * 0.35)

        # contagem regressiva / pausa
        if self.t < 0 or self.paused:
            f = QFont()
            f.setPointSize(72 if self.t < 0 and not self.paused else 36)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(255, 255, 255, 220))
            txt = "PAUSADO" if self.paused else str(math.ceil(-self.t))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, txt)


# --------------------------------------------------------------------------- letra
class LyricsView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(130)
        self.song: Song | None = None
        self.t = 0.0

    def set_song(self, song: Song) -> None:
        self.song, self.t = song, -3.0
        self.update()

    def set_time(self, t: float) -> None:
        self.t = t
        self.update()

    def _draw_line(self, p: QPainter, line, y: float, size: int, active: bool) -> None:
        font = QFont()
        font.setBold(True)
        while True:
            font.setPointSize(size)
            fm = QFontMetrics(font)
            widths = [fm.horizontalAdvance(n.text) for n in line.notes]
            total = sum(widths)
            if total <= self.width() - 40 or size <= 12:
                break
            size -= 1
        p.setFont(font)
        x = (self.width() - total) / 2
        base_y = y + (fm.ascent() - fm.descent()) / 2
        base = QColor("#d6dcf0") if active else QColor("#5d6684")
        for n, wd in zip(line.notes, widths):
            p.setPen(base)
            p.drawText(QPointF(x, base_y), n.text)
            if active:
                frac = min(1.0, max(0.0, (self.t - n.start) / max(n.duration, 1e-3)))
                if frac > 0:
                    p.save()
                    p.setClipRect(QRectF(x, 0, wd * frac, self.height()))
                    p.setPen(QColor("#ffd24a"))
                    p.drawText(QPointF(x, base_y), n.text)
                    p.restore()
            x += wd

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        if not self.song or not self.song.lines:
            return
        lines = self.song.lines
        idx = next((i for i, l in enumerate(lines) if self.t < l.end + 0.35), len(lines))
        h = self.height()
        if idx < len(lines):
            self._draw_line(p, lines[idx], h * 0.33, 30, True)
        if idx + 1 < len(lines):
            self._draw_line(p, lines[idx + 1], h * 0.75, 20, False)


# --------------------------------------------------------------------------- tela de canto
class PlayScreen(QWidget):
    finished = Signal(object)
    aborted = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.title = QLabel("")
        self.title.setObjectName("h1")
        self.combo = QLabel("")
        self.combo.setStyleSheet("color:#ffd24a; font-size:18px; font-weight:bold;")
        self.score_lbl = QLabel("0")
        self.score_lbl.setStyleSheet("font-size:40px; font-weight:bold; color:#37e08a;")
        self.score_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.level.setFixedWidth(90)
        hint = QLabel("Espaço: pausar   ·   Esc: sair")
        hint.setObjectName("muted")

        head = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(self.title)
        left.addWidget(self.combo)
        head.addLayout(left, 1)
        head.addWidget(QLabel("mic"))
        head.addWidget(self.level)
        head.addSpacing(16)
        head.addWidget(self.score_lbl)

        self.roll = NoteRoll()
        self.lyrics = LyricsView()
        lay = QVBoxLayout(self)
        lay.addLayout(head)
        lay.addWidget(self.roll, 1)
        lay.addWidget(self.lyrics)
        lay.addWidget(hint, 0, Qt.AlignCenter)

        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.song: Song | None = None
        self.player: Player | None = None
        self.tracker: PitchTracker | None = None
        self.scorer: Scorer | None = None
        self._last = 0.0

    def begin(self, song: Song, opts: dict, tracker: PitchTracker, player: Player) -> None:
        """Microfone e áudio já vêm abertos (ver MainWindow._start)."""
        self._cleanup()
        self.song = song
        self.tracker = tracker
        self.player = player
        self.scorer = Scorer(song, opts["tolerance"], opts["latency"])
        self.title.setText(song.label)
        self.score_lbl.setText("0")
        self.combo.setText("")
        self.roll.reset(song)
        self.lyrics.set_song(song)
        self._ref_center = sum(song.pitch_range) / 2
        self.player.start(lead_in=3.0)
        self._last = time.perf_counter()
        self.timer.start()
        self.setFocus()

    def _cleanup(self) -> None:
        self.timer.stop()
        if self.tracker:
            self.tracker.stop()
            self.tracker = None
        if self.player:
            self.player.stop()
            self.player = None

    def _tick(self) -> None:
        if not (self.player and self.tracker and self.scorer):
            return
        now = time.perf_counter()
        dt, self._last = now - self._last, now
        if self.player.paused:
            return
        self.player.update()
        t = self.player.time()
        sung = self.tracker.midi
        if t >= 0:
            note, hit = self.scorer.update(t, dt, sung)
            if sung is not None:
                ref = note.midi if note else self._ref_center
                shown = sung - 12 * round((sung - ref) / 12)  # dobra p/ a oitava da nota
                self.roll.push(t - self.scorer.latency, shown, hit)
            self.score_lbl.setText(_fmt_score(self.scorer.score))
            c = self.scorer.combo
            self.combo.setText(f"Combo x{c}" if c >= 2 else "")
        self.roll.set_time(t)
        self.lyrics.set_time(t)
        self.level.setValue(_level_pct(self.tracker.level))
        if self.player.finished:
            self._finish()

    def _finish(self) -> None:
        scorer, song = self.scorer, self.song
        scorer.finish()
        self._cleanup()
        self.finished.emit({
            "song": song, "score": scorer.score,
            "precision": scorer.precision, "best_combo": scorer.best_combo,
        })

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key_Escape:
            self._cleanup()
            self.aborted.emit()
        elif e.key() == Qt.Key_Space and self.player:
            if self.player.paused:
                self.player.resume()
                self._last = time.perf_counter()
            else:
                self.player.pause()
            self.roll.paused = self.player.paused
            self.roll.update()
        else:
            super().keyPressEvent(e)

    def shutdown(self) -> None:
        self._cleanup()


# --------------------------------------------------------------------------- resultado
class ResultScreen(QWidget):
    again = Signal()
    back = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.song_lbl = QLabel("")
        self.song_lbl.setObjectName("muted")
        self.song_lbl.setAlignment(Qt.AlignCenter)
        self.score = QLabel("0")
        self.score.setAlignment(Qt.AlignCenter)
        self.score.setStyleSheet("font-size:96px; font-weight:bold; color:#37e08a;")
        self.grade = QLabel("")
        self.grade.setAlignment(Qt.AlignCenter)
        self.grade.setStyleSheet("font-size:30px; font-weight:bold; color:#ffd24a;")
        self.stats = QLabel("")
        self.stats.setAlignment(Qt.AlignCenter)
        self.stats.setObjectName("muted")
        self.record = QLabel("")
        self.record.setAlignment(Qt.AlignCenter)
        again = QPushButton("Cantar de novo")
        again.setObjectName("primary")
        back = QPushButton("Voltar às músicas")
        again.clicked.connect(self.again)
        back.clicked.connect(self.back)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(again)
        row.addWidget(back)
        row.addStretch()
        lay = QVBoxLayout(self)
        lay.addStretch()
        for wdg in (self.song_lbl, self.score, self.grade, self.stats, self.record):
            lay.addWidget(wdg)
        lay.addSpacing(24)
        lay.addLayout(row)
        lay.addStretch()

    def show_result(self, r: dict, is_record: bool, previous: int) -> None:
        self.song_lbl.setText(r["song"].label)
        self.score.setText(_fmt_score(r["score"]))
        self.grade.setText(grade(r["score"]))
        self.stats.setText(
            f"Precisão {r['precision'] * 100:.0f}%   ·   Maior combo x{r['best_combo']}")
        if is_record:
            self.record.setText("★ Novo recorde! ★")
            self.record.setStyleSheet("color:#ffd24a; font-size:18px; font-weight:bold;")
        else:
            self.record.setText(f"Recorde: {_fmt_score(previous)}")
            self.record.setStyleSheet("color:#8791b0;")


# --------------------------------------------------------------------------- biblioteca
class LibraryScreen(QWidget):
    start_requested = Signal(object, object)  # song, opts (dict com mic, canal, portão, ...)

    def __init__(self, songs_dir: Path, settings: QSettings) -> None:
        super().__init__()
        self.songs_dir, self.settings = songs_dir, settings
        self._tester: PitchTracker | None = None
        self._opening: _OpenMic | None = None

        title = QLabel("Karaokê")
        title.setObjectName("h1")
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self._sing())
        self.empty = QLabel("")
        self.empty.setObjectName("muted")
        self.empty.setWordWrap(True)

        self.mic = QComboBox()
        self.mic.addItem("Padrão do sistema", None)
        for idx, name in list_input_devices():
            self.mic.addItem(name, idx)
        saved = settings.value("mic", "")
        i = self.mic.findText(saved)
        if i >= 0:
            self.mic.setCurrentIndex(i)

        self.chan = QComboBox()
        self.gate = QSlider(Qt.Horizontal)
        self.gate.setRange(-60, -20)  # dB; menor = mais sensível
        self.gate.setValue(int(settings.value("gate_db", -38)))
        self.gate_lbl = QLabel()
        self.gate_lbl.setObjectName("muted")
        self.gate_lbl.setWordWrap(True)
        self.db_lbl = QLabel("")
        self.db_lbl.setObjectName("muted")
        self.db_lbl.setAlignment(Qt.AlignCenter)
        self._refresh_channels(restore=int(settings.value("channel", 0)))
        self._on_gate(self.gate.value())
        self.mic.currentIndexChanged.connect(lambda _: self._refresh_channels())
        self.chan.currentIndexChanged.connect(lambda _: self._tester and self.stop_test())
        self.gate.valueChanged.connect(self._on_gate)

        self.diff = QComboBox()
        self.diff.addItems(DIFFICULTY.keys())
        self.diff.setCurrentText(settings.value("difficulty", "Normal"))
        self.lat = QSpinBox()
        self.lat.setRange(0, 800)
        self.lat.setSingleStep(10)
        self.lat.setSuffix(" ms")
        self.lat.setValue(int(settings.value("latency", 150)))

        self.test_btn = QPushButton("Testar microfone")
        self.test_btn.clicked.connect(self._toggle_test)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.note_lbl = QLabel("—")
        self.note_lbl.setStyleSheet("font-size:20px; font-weight:bold;")
        self.note_lbl.setAlignment(Qt.AlignCenter)

        sing = QPushButton("Cantar  ▶")
        sing.setObjectName("primary")
        sing.clicked.connect(self._sing)
        open_btn = QPushButton("Abrir pasta de músicas")
        open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.songs_dir))))
        reload_btn = QPushButton("Recarregar")
        reload_btn.clicked.connect(self._reload_all)

        side = QVBoxLayout()
        for text, wdg in (("Microfone", self.mic), ("Canal de entrada", self.chan),
                          ("Dificuldade", self.diff), ("Calibração de latência", self.lat)):
            lbl = QLabel(text)
            lbl.setObjectName("muted")
            side.addWidget(lbl)
            side.addWidget(wdg)
        side.addWidget(self.gate_lbl)
        side.addWidget(self.gate)
        side.addSpacing(8)
        side.addWidget(self.test_btn)
        side.addWidget(self.level)
        side.addWidget(self.db_lbl)
        side.addWidget(self.note_lbl)
        side.addStretch()
        side.addWidget(sing)
        side.addWidget(open_btn)
        side.addWidget(reload_btn)
        side_w = QWidget()
        side_w.setLayout(side)
        side_w.setFixedWidth(280)

        body = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(self.list, 1)
        left.addWidget(self.empty)
        body.addLayout(left, 1)
        body.addWidget(side_w)
        lay = QVBoxLayout(self)
        lay.addWidget(title)
        lay.addLayout(body, 1)

        self._poll = QTimer(self)
        self._poll.setInterval(50)
        self._poll.timeout.connect(self._poll_mic)
        self.reload()

    def _refresh_channels(self, restore: int = 0) -> None:
        if self._tester:
            self.stop_test()
        n = input_channels(self.mic.currentData())
        self.chan.blockSignals(True)
        self.chan.clear()
        for i in range(n):
            self.chan.addItem(f"Entrada {i + 1}", i)
        self.chan.setCurrentIndex(restore if 0 <= restore < n else 0)
        self.chan.blockSignals(False)

    def _on_gate(self, db: int) -> None:
        self.gate_lbl.setText(f"Portão de ruído: {db} dB   (menor = mais sensível)")
        if self._tester:
            self._tester.gate = db_to_gate(db)  # vale ao vivo durante o teste

    def reload(self) -> None:
        self.list.clear()
        songs, errors = scan_library(self.songs_dir)
        for s in songs:
            best = int(self.settings.value(f"best/{s.key}", 0))
            suffix = f"      recorde {_fmt_score(best)}" if best else ""
            item = QListWidgetItem(f"{s.label}{suffix}")
            item.setData(Qt.UserRole, s)
            self.list.addItem(item)
        if songs:
            self.list.setCurrentRow(0)
        msgs = []
        if not songs:
            msgs.append(f"Nenhuma música encontrada. Coloque pastas com song.txt + áudio em:\n"
                        f"{self.songs_dir}")
        if self.mic.count() <= 1:  # só "Padrão do sistema": nenhum dispositivo de entrada listado
            msgs.append("Nenhum microfone detectado. Conecte um e clique em Recarregar.")
        msgs += [f"Erro em {e}" for e in errors]
        self.empty.setText("\n".join(msgs))

    def _reload_all(self) -> None:
        """Botão Recarregar: relê os microfones e as músicas."""
        self.stop_test()
        refresh_devices()
        previous = self.mic.currentText()
        self.mic.blockSignals(True)
        self.mic.clear()
        self.mic.addItem("Padrão do sistema", None)
        for idx, name in list_input_devices():
            self.mic.addItem(name, idx)
        i = self.mic.findText(previous)
        self.mic.setCurrentIndex(i if i >= 0 else 0)
        self.mic.blockSignals(False)
        self._refresh_channels()
        self.reload()

    def stop_test(self) -> None:
        self._poll.stop()
        if self._tester:
            self._tester.stop()
            self._tester = None
        self.test_btn.setText("Testar microfone")
        self.level.setValue(0)
        self.db_lbl.setText("")
        self.note_lbl.setText("—")

    def _toggle_test(self) -> None:
        if self._tester:
            self.stop_test()
            return
        if self._opening:
            return
        tr = PitchTracker(device=self.mic.currentData(), gate=db_to_gate(self.gate.value()),
                          channel=self.chan.currentData() or 0)
        self.test_btn.setText("Abrindo microfone...")
        self.test_btn.setEnabled(False)
        worker = _OpenMic(tr, self)
        self._opening = worker

        def ok() -> None:
            self._opening = None
            self._tester = tr
            self.test_btn.setEnabled(True)
            self.test_btn.setText("Parar teste")
            self._poll.start()

        def fail(msg: str) -> None:
            self._opening = None
            self.test_btn.setEnabled(True)
            self.test_btn.setText("Testar microfone")
            QMessageBox.warning(self, "Microfone", mic_error_text(msg))

        worker.ok.connect(ok)
        worker.failed.connect(fail)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _poll_mic(self) -> None:
        if not self._tester:
            return
        rms = self._tester.level
        self.level.setValue(_level_pct(rms))
        below = "   ·   abaixo do portão" if rms < self._tester.gate else ""
        self.db_lbl.setText(f"{level_db(rms):.0f} dB{below}")
        m = self._tester.midi
        self.note_lbl.setText(note_name(m) if m is not None else "—")

    def _sing(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self.stop_test()
        self.settings.setValue("mic", self.mic.currentText())
        self.settings.setValue("difficulty", self.diff.currentText())
        self.settings.setValue("latency", self.lat.value())
        self.settings.setValue("channel", self.chan.currentData() or 0)
        self.settings.setValue("gate_db", self.gate.value())
        self.start_requested.emit(item.data(Qt.UserRole), {
            "device": self.mic.currentData(),
            "channel": self.chan.currentData() or 0,
            "gate": db_to_gate(self.gate.value()),
            "tolerance": DIFFICULTY[self.diff.currentText()],
            "latency": self.lat.value() / 1000.0,
        })


# --------------------------------------------------------------------------- janela principal
class MainWindow(QMainWindow):
    def __init__(self, songs_dir: Path) -> None:
        super().__init__()
        self.setWindowTitle("Karaokê")
        self.resize(1100, 720)
        self.settings = QSettings("KaraokeGospel", "Karaoke")
        self._last_args: tuple | None = None
        self._worker: _OpenMic | None = None

        self.stack = QStackedWidget()
        self.library = LibraryScreen(songs_dir, self.settings)
        self.play = PlayScreen()
        self.result = ResultScreen()
        for s in (self.library, self.play, self.result):
            self.stack.addWidget(s)

        self.footer = QLabel(
            f'{CREDITS_LABEL} <a href="{CREDITS_URL}"><span style="text-decoration:none; '
            f'color:#7f9bff;">{CREDITS_URL}</span></a>')
        self.footer.setObjectName("footer")
        self.footer.setAlignment(Qt.AlignCenter)
        self.footer.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.footer.setOpenExternalLinks(True)  # clique abre o GitHub no navegador
        central = QWidget()
        box = QVBoxLayout(central)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        box.addWidget(self.stack, 1)
        box.addWidget(self.footer)
        self.setCentralWidget(central)
        self.stack.currentChanged.connect(
            lambda _: self.footer.setHidden(self.stack.currentWidget() is self.play))

        self.library.start_requested.connect(self._start)
        self.play.finished.connect(self._finished)
        self.play.aborted.connect(self._to_library)
        self.result.again.connect(lambda: self._start(*self._last_args))
        self.result.back.connect(self._to_library)

    def _start(self, song, opts) -> None:
        if self._worker:
            return
        self._last_args = (song, opts)
        tracker = PitchTracker(device=opts["device"], gate=opts["gate"], channel=opts["channel"])
        self._set_busy(True)
        worker = _OpenSession(tracker, song, self)
        self._worker = worker
        worker.ok.connect(lambda player: self._session_ready(song, opts, tracker, player))
        worker.failed.connect(self._session_failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _set_busy(self, busy: bool) -> None:
        self.stack.setEnabled(not busy)
        self.setWindowTitle("Karaokê" + (" - preparando microfone e áudio..." if busy else ""))

    def _session_ready(self, song, opts, tracker, player) -> None:
        self._worker = None
        self._set_busy(False)
        try:
            self.play.begin(song, opts, tracker, player)
        except Exception as e:  # noqa: BLE001
            tracker.stop()
            QMessageBox.critical(self, "Erro ao iniciar", f"Não consegui iniciar a música:\n{e}")
            self._to_library()
            return
        self.stack.setCurrentWidget(self.play)

    def _session_failed(self, kind: str, detail: str) -> None:
        self._worker = None
        self._set_busy(False)
        if kind == "mic":
            QMessageBox.critical(self, "Microfone", mic_error_text(detail))
        else:
            QMessageBox.critical(self, "Saída de áudio", audio_error_text(detail))
        self._to_library()

    def _finished(self, r: dict) -> None:
        key = f"best/{r['song'].key}"
        previous = int(self.settings.value(key, 0))
        is_record = r["score"] > previous
        if is_record:
            self.settings.setValue(key, r["score"])
        self.result.show_result(r, is_record, previous)
        self.stack.setCurrentWidget(self.result)

    def _to_library(self) -> None:
        self.library.reload()
        self.stack.setCurrentWidget(self.library)

    def closeEvent(self, e) -> None:  # noqa: N802
        for w in (self._worker, self.library._opening):
            if w is not None:
                w.wait(5000)  # deixa a abertura do microfone terminar antes de fechar
        self.play.shutdown()
        self.library.stop_test()
        super().closeEvent(e)


def resource_path(rel: str) -> Path:
    """Acha arquivos embutidos: na pasta do projeto ou, no .exe, dentro do pacote."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / rel


def run(songs_dir: Path) -> int:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    icon = resource_path("assets/icon.png")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    songs_dir.mkdir(parents=True, exist_ok=True)
    win = MainWindow(songs_dir)
    win.show()
    return app.exec()
