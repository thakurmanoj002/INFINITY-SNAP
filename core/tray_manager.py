"""
Infinity Snap — Windows System Tray Manager
===========================================
Runs a Cyberpunk status icon in the Windows taskbar system notification tray.
Displays dynamic glowing icons (Cyan = Armed, Amber = Paused, Magenta = Triggered),
offers right-click macro controls, and handles background execution.
"""

import os
from pathlib import Path
import sys
import threading
import time
from typing import Callable, Optional

from PIL import Image, ImageDraw
import pystray


def create_cyberpunk_icon(state: str = "ARMED") -> Image.Image:
    """
    Renders an in-memory 64x64 RGBA Cyberpunk status emblem:
      - ARMED: Glowing Neon Cyan ring with Matrix Green core.
      - PAUSED: Warning Amber ring with diagonal standby cross.
      - TRIGGERED: High-voltage Neon Magenta flash.
    """
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if state.upper() == "ARMED":
        # Outer glow ring (Cyan)
        draw.ellipse([4, 4, 60, 60], outline=(0, 240, 255, 180), width=3)
        draw.ellipse([8, 8, 56, 56], outline=(0, 240, 255, 255), width=4)
        # Inner active power core (Matrix Green)
        draw.ellipse([22, 22, 42, 42], fill=(0, 255, 102, 255))
        draw.ellipse([28, 28, 36, 36], fill=(255, 255, 255, 255))
    elif state.upper() == "TRIGGERED":
        # Outer pulse ring (Magenta)
        draw.ellipse([3, 3, 61, 61], outline=(255, 0, 127, 200), width=4)
        draw.ellipse([8, 8, 56, 56], outline=(255, 0, 85, 255), width=5)
        # Core detonation flash (Hot Pink)
        draw.ellipse([18, 18, 46, 46], fill=(255, 0, 85, 255))
        draw.ellipse([26, 26, 38, 38], fill=(255, 255, 255, 255))
    else:  # PAUSED / MUTED
        # Warning Amber standby ring
        draw.ellipse([6, 6, 58, 58], outline=(255, 230, 0, 220), width=4)
        # Slashed mute bar
        draw.line([16, 48, 48, 16], fill=(255, 230, 0, 255), width=5)
        draw.ellipse([24, 24, 40, 40], outline=(255, 230, 0, 180), width=2)

    return img


class TrayManager:
    """Manages the Windows taskbar system notification tray icon and context actions."""

    def __init__(
        self,
        monitor_dir: Path,
        on_toggle_arm: Callable[[], None],
        on_trigger_single: Optional[Callable[[], None]] = None,
        on_trigger_double: Optional[Callable[[], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
    ):
        self.monitor_dir = Path(monitor_dir).resolve()
        self.on_toggle_arm = on_toggle_arm
        self.on_trigger_single = on_trigger_single
        self.on_trigger_double = on_trigger_double
        self.on_exit = on_exit

        self.current_state = "ARMED"
        self._icon: Optional[pystray.Icon] = None

    def start(self):
        """Initializes and runs the system tray icon detached in a background thread."""
        menu = self._build_menu()
        self._icon = pystray.Icon(
            name="InfinitySnap",
            icon=create_cyberpunk_icon("ARMED"),
            title="Infinity Snap // SURVEILLANCE ARMED",
            menu=menu,
        )
        self._icon.run_detached()

    def _build_menu(self) -> pystray.Menu:
        """Constructs the right-click tray context menu."""
        return pystray.Menu(
            pystray.MenuItem(
                lambda text: f"Infinity Snap: [{self.current_state}]",
                action=None,
                enabled=False,
            ),
            pystray.MenuItem(
                "Toggle Mute / Arm (Ctrl+Alt+S)",
                action=self._action_toggle_arm,
                default=True,
            ),
            pystray.MenuItem(
                "Open Monitored Sector",
                action=self._action_open_folder,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Trigger Panic Stealth (1 Snap)",
                action=self._action_trigger_single,
            ),
            pystray.MenuItem(
                "Trigger Folder Purge (2 Snaps)",
                action=self._action_trigger_double,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Exit Infinity Snap",
                action=self._action_exit,
            ),
        )

    def set_state(self, state: str):
        """Updates the icon appearance and title according to state ('ARMED', 'PAUSED', 'TRIGGERED')."""
        self.current_state = state
        if self._icon:
            self._icon.icon = create_cyberpunk_icon(state)
            self._icon.title = f"Infinity Snap // {state.upper()}"

    def trigger_flash(self, return_state: str = "ARMED"):
        """Briefly flashes the icon to Magenta before returning to return_state."""
        def _flash_worker():
            self.set_state("TRIGGERED")
            time.sleep(1.0)
            self.set_state(return_state)

        threading.Thread(target=_flash_worker, daemon=True).start()

    def _action_toggle_arm(self, icon, item):
        if self.on_toggle_arm:
            self.on_toggle_arm()

    def _action_open_folder(self, icon, item):
        try:
            if sys.platform == "win32":
                os.startfile(str(self.monitor_dir))
        except Exception:
            pass

    def _action_trigger_single(self, icon, item):
        if self.on_trigger_single:
            self.on_trigger_single()

    def _action_trigger_double(self, icon, item):
        if self.on_trigger_double:
            self.on_trigger_double()

    def _action_exit(self, icon, item):
        if self.on_exit:
            self.on_exit()
        self.stop()

    def stop(self):
        """Removes the icon from the system tray."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
