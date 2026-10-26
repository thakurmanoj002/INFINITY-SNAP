"""
Infinity Snap — Native Windows 10/11 Notification Toasts
=========================================================
Delivers native Windows Action Center toast notifications for snap actions,
stealth engagements, and sensor mute/arm toggles.
"""

import sys
import threading
from typing import Optional


class NotificationManager:
    """Delivers native Windows 10/11 toast notifications."""

    def __init__(self, app_name: str = "Infinity Snap"):
        self.app_name = app_name
        self._toaster = None
        self._available = False
        self._init_toaster()

    def _init_toaster(self):
        """Initializes windows_toasts WindowsToaster."""
        if sys.platform == "win32":
            try:
                from windows_toasts import WindowsToaster
                self._toaster = WindowsToaster(self.app_name)
                self._available = True
            except Exception:
                self._available = False

    def send_toast(self, title: str, body: str):
        """Dispatches a toast notification asynchronously in a background thread."""
        if not self._available or not self._toaster:
            return

        threading.Thread(
            target=self._send_toast_worker,
            args=(title, body),
            daemon=True,
        ).start()

    def _send_toast_worker(self, title: str, body: str):
        try:
            from windows_toasts import Toast
            toast = Toast()
            toast.text_fields = [title, body]
            self._toaster.show_toast(toast)
        except Exception:
            pass
