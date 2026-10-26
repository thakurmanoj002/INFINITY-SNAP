"""
Infinity Snap — Action Router
=============================
Maps multi-gesture sound patterns (1 snap, 2 snaps) to desktop actions:
  - 1 Snap:  Panic Stealth Boss Mode (Minimizes all windows + mutes master audio).
  - 2 Snaps: Instant Folder Purge (Recycle Bin via native Win32 SHFileOperationW).
"""

import ctypes
import os
from pathlib import Path
import sys

# Configure UTF-8 encoding on Windows to prevent legacy charmap codec errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import time
from typing import Optional

from rich import box
from rich.console import Console
from rich.panel import Panel

from core.fs_monitor import execute_batch_recycle, scan_eligible_items

console = Console()

# Win32 Virtual Key Constants
VK_LWIN = 0x5B
VK_D = 0x44
KEYEVENTF_KEYUP = 0x0002
VK_VOLUME_MUTE = 0xAD


class ActionRouter:
    """Dispatches multi-gesture triggers to corresponding desktop automation routines."""

    def __init__(self, config: dict):
        self.config = config
        self.monitor_dir = Path(config["monitoring_folder"]).resolve()
        self.action_mode = config.get("action_mode", "NORMAL")

    def execute_gesture(self, snap_count: int, peak_amplitude: float, threshold: float) -> str:
        """Dispatches action according to registered snap count."""
        if snap_count == 1:
            return self.handle_single_snap(peak_amplitude, threshold)
        elif snap_count >= 2:
            return self.handle_double_snap(peak_amplitude, threshold)
        return "Unknown gesture"

    def handle_single_snap(self, peak_amplitude: float, threshold: float) -> str:
        """
        1 Snap Action: Emergency Panic Stealth Boss Mode.
        Minimizes all desktop windows (Win + D) and mutes master audio volume.
        """
        if sys.platform == "win32":
            user32 = ctypes.windll.user32

            # 1. Simulate Win + D (Minimize all windows)
            user32.keybd_event(VK_LWIN, 0, 0, 0)
            user32.keybd_event(VK_D, 0, 0, 0)
            user32.keybd_event(VK_D, 0, KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)

            # 2. Simulate Master Volume Mute (VK_VOLUME_MUTE)
            user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
            user32.keybd_event(VK_VOLUME_MUTE, 0, KEYEVENTF_KEYUP, 0)

        return "1 Snap: Panic Activated (Windows Minimized & Audio Muted)"

    def handle_double_snap(self, peak_amplitude: float, threshold: float) -> str:
        """
        2 Snaps Action: Instant Recycle Bin purge of the monitored folder.
        """
        files, dirs = scan_eligible_items(self.monitor_dir)
        total_targets = files + dirs

        if not total_targets:
            return "2 Snaps: Zero items in target sector"

        summary = execute_batch_recycle(total_targets, self.monitor_dir)
        success_count = len(summary["succeeded"])
        fail_count = len(summary["failed"])

        if fail_count == 0:
            return f"2 Snaps: Purged {success_count} items to Recycle Bin (Recoverable)"
        else:
            return f"2 Snaps: Purged {success_count} items ({fail_count} failed)"

