import sys
from pathlib import Path

from karaoke.ui import run


def app_dir() -> Path:
    # no .exe (PyInstaller) a pasta songs/ fica ao lado do executável
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


if __name__ == "__main__":
    sys.exit(run(app_dir() / "songs"))
