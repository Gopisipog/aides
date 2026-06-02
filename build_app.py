#!/usr/bin/env python3
"""Build standalone V-LKG Desktop executable with PyInstaller.

Usage:
    python build_app.py                  # Build with default options
    python build_app.py --debug          # Build with console window
    python build_app.py --clean          # Clean build cache first
    python build_app.py --no-upx         # Disable UPX compression
"""

import argparse
import os
import shutil
import subprocess
import sys

_project_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(_project_root)

APP_NAME = "V-LKG Desktop"
MAIN_SCRIPT = "desktop_app.py"
ICON_PATH = os.path.join(_project_root, "vlkg_desktop", "assets", "app.ico")


def _ensure_icon():
    """Generate a .ico if none exists (requires Pillow)."""
    if os.path.exists(ICON_PATH):
        return
    try:
        from PIL import Image, ImageDraw

        os.makedirs(os.path.dirname(ICON_PATH), exist_ok=True)
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill="#2196F3", outline="#1565C0", width=2)
        draw.line([20, 38, 32, 22, 44, 38], fill="white", width=4)
        # PyInstaller needs .ico on Windows
        img.save(ICON_PATH, format="ICO", sizes=[(64, 64)])
        print(f"Generated app icon: {ICON_PATH}")
    except ImportError:
        print("Pillow not installed — skipping icon generation.")


def _parse_args():
    parser = argparse.ArgumentParser(description="Build V-LKG Desktop executable")
    parser.add_argument("--debug", action="store_true", help="Keep console window open")
    parser.add_argument("--clean", action="store_true", help="Remove build cache first")
    parser.add_argument("--no-upx", action="store_true", help="Disable UPX compression")
    return parser.parse_args()


def main():
    args = _parse_args()

    print("Building V-LKG Desktop executable …")
    print(f"{'=' * 50}")

    # Ensure PyInstaller is available
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Install with: pip install pyinstaller")
        sys.exit(1)

    # Clean previous builds
    for d in ["build", "dist"]:
        if os.path.exists(d) and args.clean:
            shutil.rmtree(d, ignore_errors=True)
            print(f"Removed {d}/")

    _ensure_icon()

    # Build the PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "V-LKG Desktop",
        "--onefile",
        "--add-data", f"app.py{os.pathsep}.",
        "--add-data", f"src{os.pathsep}src",
        "--add-data", f"vlkg_desktop{os.pathsep}vlkg_desktop",
        "--add-data", f"data{os.pathsep}data",
        "--add-data", f".streamlit{os.pathsep}.streamlit",
        "--hidden-import", "sounddevice",
        "--hidden-import", "soundfile",
        "--hidden-import", "whisper",
        "--hidden-import", "easyocr",
        "--hidden-import", "sentence_transformers",
        "--hidden-import", "neo4j",
        "--hidden-import", "pystray",
        "--hidden-import", "PIL._tkinter_finder",
        "--collect-all", "streamlit",
        "--collect-all", "whisper",
        "--collect-data", "py2neo",
    ]

    if os.path.exists(ICON_PATH):
        cmd.extend(["--icon", ICON_PATH])
    if args.debug:
        cmd.append("--console")
    else:
        cmd.append("--noconsole")
    if args.no_upx:
        cmd.append("--noupx")

    cmd.append(MAIN_SCRIPT)

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=_project_root)

    if result.returncode == 0:
        print(f"\nBuild successful!")
        print(f"Executable: {os.path.join(_project_root, 'dist', 'V-LKG Desktop.exe')}")
    else:
        print(f"\nBuild failed with code {result.returncode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
