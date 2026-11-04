import sys
from pathlib import Path

from karaoke.ui import run


def app_dir() -> Path:
    # no .exe (PyInstaller) a pasta songs/ fica ao lado do executável
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _taskbar_identity() -> None:
    """Windows: agrupa a janela sob o ícone do Karaokê na barra de tarefas."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Karaoke.App")
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    _taskbar_identity()
    sys.exit(run(app_dir() / "songs"))
