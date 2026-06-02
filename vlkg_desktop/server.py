import os
import sys
import socket
import subprocess
import atexit
import signal
import time
import threading

STREAMLIT_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.py")


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class StreamlitServer:
    """Manages the Streamlit server as a managed subprocess.

    Starts the existing ``app.py`` on a random local port and
    provides lifecycle control (start, stop, restart, health-check).
    """

    def __init__(self, port=None):
        self.port = port or _find_free_port()
        self._process: subprocess.Popen | None = None
        self._ready = threading.Event()

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    @property
    def is_running(self):
        return self._process is not None and self._process.poll() is None

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def start(self, timeout=30):
        """Launch the Streamlit server on a background thread.

        Blocks until the server is ready (or *timeout* seconds elapse).
        """
        if self.is_running:
            print("Streamlit server is already running.")
            return

        env = os.environ.copy()
        env["STREAMLIT_SERVER_PORT"] = str(self.port)
        env["STREAMLIT_SERVER_ADDRESS"] = "127.0.0.1"
        env["STREAMLIT_SERVER_HEADLESS"] = "true"
        env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
        env["STREAMLIT_SERVER_ENABLE_CORS"] = "false"
        env["STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION"] = "false"

        print(f"Starting Streamlit server on {self.url} …")

        # Hide the terminal window on Windows
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        self._process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                STREAMLIT_SCRIPT,
                "--server.port",
                str(self.port),
                "--server.address",
                "127.0.0.1",
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
                "--server.enableCORS",
                "false",
                "--server.enableXsrfProtection",
                "false",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        atexit.register(self.stop)

        # Wait for "You can now view your Streamlit app" in stderr
        self._wait_for_ready(timeout)

    def _wait_for_ready(self, timeout):
        def _reader():
            for line in iter(self._process.stdout.readline, b""):
                decoded = line.decode("utf-8", errors="replace")
                print(f"[streamlit] {decoded}", end="")
                if "You can now view your Streamlit app" in decoded:
                    self._ready.set()

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        if not self._ready.wait(timeout=timeout):
            # Check if process died
            ret = self._process.poll()
            if ret is not None:
                stderr_out = self._process.stderr.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Streamlit server exited with code {ret}:\n{stderr_out}"
                )
            raise TimeoutError(
                f"Streamlit server did not become ready within {timeout}s"
            )

        print(f"Streamlit server ready at {self.url}")

    def stop(self):
        """Gracefully shut down the Streamlit server."""
        if self._process and self._process.poll() is None:
            print("Shutting down Streamlit server …")
            if sys.platform == "win32":
                self._process.terminate()
            else:
                self._process.send_signal(signal.SIGTERM)
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
        self._process = None
        atexit.unregister(self.stop)

    def restart(self, timeout=30):
        """Restart the Streamlit server."""
        self.stop()
        time.sleep(0.5)
        self.start(timeout=timeout)
