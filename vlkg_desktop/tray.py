import sys
import threading

try:
    import pystray
    from PIL import Image, ImageDraw
    _HAS_TRAY = True
except ImportError:
    _HAS_TRAY = False


_ICON_SIZE = 64


def _create_default_icon():
    """Generate a simple coloured-circle app icon (64×64 PNG)."""
    img = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill="#2196F3", outline="#1565C0", width=2)
    # Draw a rough "V" shape as a simple letter
    draw.line([20, 38, 32, 22, 44, 38], fill="white", width=4)
    return img


def _create_menu_items(on_show=None, on_hide=None, on_quit=None):
    items = []

    if on_show:
        items.append(pystray.MenuItem("Show Window", on_show, default=True))
    if on_hide:
        items.append(pystray.MenuItem("Hide Window", on_hide))

    items.append(pystray.Menu.SEPARATOR)
    items.append(
        pystray.MenuItem(
            "Open in Browser",
            lambda: __import__("webbrowser").open(
                "http://127.0.0.1:8501"
            ),
        )
    )
    items.append(pystray.Menu.SEPARATOR)

    if on_quit:
        items.append(pystray.MenuItem("Quit", on_quit))

    return items


class SystemTray:
    """System tray icon with a context menu.

    Runs on a background daemon thread so it doesn't block the main loop.
    """

    def __init__(self, on_show=None, on_hide=None, on_quit=None):
        self._icon = None
        self._thread = None
        self._on_show = on_show
        self._on_hide = on_hide
        self._on_quit = on_quit

    def start(self):
        if not _HAS_TRAY:
            print("System tray unavailable — install pystray + Pillow.")
            return

        menu = _create_menu_items(self._on_show, self._on_hide, self._on_quit)
        icon_img = _create_default_icon()

        self._icon = pystray.Icon(
            "vlkg",
            icon_img,
            "V-LKG Desktop",
            menu,
        )

        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        print("System tray icon active.")

    def stop(self):
        if self._icon:
            self._icon.stop()
            self._icon = None
            print("System tray icon removed.")

    def notify(self, title, message, duration=5):
        """Show a desktop notification."""
        if self._icon and hasattr(self._icon, "notify"):
            try:
                self._icon.notify(message, title)
            except Exception:
                pass
