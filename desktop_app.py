#!/usr/bin/env python3
"""V-LKG Desktop Application — native window + system tray.

Usage:
    python desktop_app.py                  # Launch with native window
    python desktop_app.py --no-window      # Tray-only (background server)
    python desktop_app.py --port 8501      # Use a specific port
    python desktop_app.py --no-neo4j       # Skip Neo4j auto-start
"""

import argparse
import os
import sys
import threading
import webbrowser

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from vlkg_desktop.server import StreamlitServer
from vlkg_desktop.tray import SystemTray
from vlkg_desktop import __app_name__, __version__


def _parse_args():
    parser = argparse.ArgumentParser(description=f"{__app_name__} v{__version__}")
    parser.add_argument(
        "--port", type=int, default=None, help="Streamlit server port (default: random)"
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Run tray-only without a native window",
    )
    parser.add_argument(
        "--no-neo4j",
        action="store_true",
        help="Skip automatic Neo4j startup",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Open in the system browser instead of a native window",
    )
    return parser.parse_args()


def main():
    args = _parse_args()

    print(f"{__app_name__} v{__version__}")
    print(f"{'=' * 40}")

    if not args.no_neo4j:
        try:
            from vlkg_desktop.neo4j_manager import Neo4jManager
            nm = Neo4jManager()
            nm.ensure_running(timeout=60)
        except Exception as e:
            print(f"Neo4j auto-start skipped: {e}")
    else:
        print("Neo4j auto-start disabled (--no-neo4j).")

    server = StreamlitServer(port=args.port)
    try:
        server.start(timeout=45)
    except Exception as e:
        print(f"FATAL: Could not start Streamlit server: {e}", file=sys.stderr)
        sys.exit(1)

    tray_quit_flag = [False]

    def on_show():
        _show_window(server.url)

    def on_hide():
        pass

    def on_quit():
        tray_quit_flag[0] = True
        server.stop()
        if not args.no_neo4j:
            try:
                nm.stop()
            except Exception:
                pass
        os._exit(0)

    tray = SystemTray(on_show=on_show, on_hide=on_hide, on_quit=on_quit)
    tray.start()

    if args.no_window:
        print(f"\nServer running at {server.url}")
        print("Press Ctrl+C to stop.\n")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            server.stop()
    elif args.browser:
        print(f"Opening {server.url} in browser …")
        webbrowser.open(server.url)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            server.stop()
    else:
        _show_window(server.url)

    tray.stop()


def _show_window(url):
    try:
        import webview
        window = webview.create_window(
            title=__app_name__,
            url=url,
            width=1280,
            height=860,
            min_size=(900, 600),
            resizable=True,
            fullscreen=False,
            text_select=True,
            zoomable=True,
            confirm_close=True,
        )
        webview.start(
            gui="edgechromium",
            private_mode=False,
            debug=False,
        )
    except ImportError:
        print(
            "pywebview not installed. Falling back to system browser.\n"
            "Install with: pip install pywebview"
        )
        webbrowser.open(url)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    except Exception as e:
        print(f"Native window error: {e}")
        print(f"Falling back to browser at {url}")
        webbrowser.open(url)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
