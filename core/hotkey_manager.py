"""
Infinity Snap — Global OS-Level Hotkey Manager
==============================================
Registers and listens for the global Windows hotkey (Ctrl + Alt + S)
using native Win32 RegisterHotKey API. Allows instant muting/pausing
of microphone surveillance from anywhere in the OS without needing window focus.
"""

import ctypes
from ctypes import wintypes
import sys
import threading
from typing import Callable, Optional

# Win32 Constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_S = 0x53
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 9001


class GlobalHotkeyManager:
    """Manages global Windows keyboard shortcut (Ctrl + Alt + S) to toggle listening state."""

    def __init__(self, on_toggle: Callable[[], None]):
        self.on_toggle = on_toggle
        self._thread: Optional[threading.Thread] = None
        self._thread_id: int = 0
        self._running = False
        self._is_registered = False

    def start(self):
        """Starts the background message loop to listen for global hotkeys."""
        if sys.platform != "win32":
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._msg_loop,
            name="InfinitySnap-GlobalHotkeyThread",
            daemon=True,
        )
        self._thread.start()

    def _msg_loop(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()

        # Register Ctrl + Alt + S
        success = user32.RegisterHotKey(
            None,
            HOTKEY_ID,
            MOD_CONTROL | MOD_ALT | MOD_NOREPEAT,
            VK_S,
        )
        if not success:
            # Fallback without MOD_NOREPEAT for compatibility
            success = user32.RegisterHotKey(
                None,
                HOTKEY_ID,
                MOD_CONTROL | MOD_ALT,
                VK_S,
            )

        self._is_registered = bool(success)

        msg = wintypes.MSG()
        while self._running:
            res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if res <= 0:
                break
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                try:
                    if self.on_toggle:
                        self.on_toggle()
                except Exception:
                    pass

            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._is_registered:
            user32.UnregisterHotKey(None, HOTKEY_ID)

    def stop(self):
        """Unregisters hotkey and halts the background thread."""
        self._running = False
        if sys.platform == "win32" and self._thread_id != 0:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
