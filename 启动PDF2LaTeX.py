"""PDF2LaTeX one-click launcher for Windows.

Run with any Python installation, including Anaconda:
    python 启动PDF2LaTeX.py
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
REQUIREMENTS = ROOT / "backend" / "requirements.txt"
APP = ROOT / "backend" / "app_enhanced.py"
REQUIRED_MODULES = ("flask", "flask_socketio", "pdfplumber", "cv2", "pytesseract", "dotenv")


def ensure_virtualenv() -> None:
    if VENV_PYTHON.exists():
        return
    print("[1/3] Creating project virtual environment (.venv)...")
    venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")


def dependencies_ready() -> bool:
    return all(importlib.util.find_spec(module) is not None for module in REQUIRED_MODULES)


def install_dependencies() -> None:
    print("[2/3] Installing project dependencies. This may take a few minutes...")
    subprocess.check_call([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([str(VENV_PYTHON), "-m", "pip", "install", "-r", str(REQUIREMENTS)])


def main() -> None:
    if "--run-app" not in sys.argv:
        ensure_virtualenv()
        # Re-execute this launcher inside .venv, even if it was started by Anaconda.
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(Path(__file__).resolve()), "--run-app"])

    if not dependencies_ready():
        install_dependencies()
    else:
        print("[2/3] Project dependencies are ready.")

    print("[3/3] Starting PDF2LaTeX...")
    print("Open http://127.0.0.1:5000 in your browser. Press Ctrl+C to stop.")
    subprocess.run([sys.executable, str(APP)], cwd=ROOT, check=False)


if __name__ == "__main__":
    main()
