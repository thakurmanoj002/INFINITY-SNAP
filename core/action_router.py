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

    def __init__(
        self,
        config: dict,
        plugin_engine: Optional[object] = None,
        notification_manager: Optional[object] = None,
        vision_engine: Optional[object] = None,
        multimodal_fusion: bool = False,
    ):
        self.config = config
        self.monitor_dir = Path(config["monitoring_folder"]).resolve()
        self.action_mode = config.get("action_mode", "NORMAL")
        self.plugin_engine = plugin_engine
        self.notification_manager = notification_manager
        self.vision_engine = vision_engine
        self.multimodal_fusion = multimodal_fusion

    def execute_gesture(self, snap_count: int, peak_amplitude: float, threshold: float) -> str:
        """Dispatches action according to registered snap count, with optional visual verification."""
        # Multimodal fusion check
        if self.multimodal_fusion and self.vision_engine and self.vision_engine.is_camera_active:
            if not self.vision_engine.is_snap_posture_recent(window_seconds=1.2):
                return "Multimodal Guard: Audio snap rejected (Visual hand snap posture required)"

        if snap_count == 1:
            return self.handle_single_snap(peak_amplitude, threshold)
        elif snap_count >= 2:
            return self.handle_double_snap(peak_amplitude, threshold)
        return "Unknown gesture"

    def handle_air_gesture(self, gesture_name: str, confidence: float) -> str:
        """Dispatches spatial camera air gestures (Apple Vision Pro Mode)."""
        if gesture_name == "CLOSED_FIST":
            return self.handle_single_snap(confidence, 0.50)
        elif gesture_name == "PINCH":
            if self.notification_manager:
                self.notification_manager.send_toast(
                    "⚡ SPATIAL AIR PINCH",
                    "Optical hand pinch recognized (Apple Vision Pro Mode).",
                )
            if self.plugin_engine:
                self.plugin_engine.dispatch_gesture("pinch", 1, confidence, 0.50, self.monitor_dir)
            return f"Air Gesture: Pinch Confirmed ({confidence:.0%})"
        elif gesture_name == "VICTORY":
            if self.notification_manager:
                self.notification_manager.send_toast(
                    "⚡ VICTORY GESTURE",
                    "Peace/Victory spatial gesture recognized.",
                )
            return f"Air Gesture: Victory Recognized ({confidence:.0%})"
        return f"Air Gesture: {gesture_name}"

    def handle_single_snap(self, peak_amplitude: float, threshold: float) -> str:
        """
        1 Snap Action: Emergency Panic Stealth Boss Mode.
        Minimizes all desktop windows (Win + D), mutes master audio volume,
        dispatches custom plugins, and sends a native Windows Action Center toast.
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

        # 3. Dispatch user plugins
        plugin_info = ""
        if self.plugin_engine:
            dispatched = self.plugin_engine.dispatch_gesture(
                "single_snap", 1, peak_amplitude, threshold, self.monitor_dir
            )
            if dispatched:
                plugin_info = f" [Plugins: {', '.join(dispatched)}]"

        # 4. Native Windows Toast
        if self.notification_manager:
            self.notification_manager.send_toast(
                "⚡ PANIC STEALTH ENGAGED",
                "Desktop windows minimized & master volume muted.",
            )

        return f"1 Snap: Panic Activated (Windows Minimized & Audio Muted){plugin_info}"

    def handle_double_snap(self, peak_amplitude: float, threshold: float) -> str:
        """
        2 Snaps Action: Instant Recycle Bin purge of the monitored folder.
        Purges target sector, triggers double snap plugins, and posts toast notification.
        """
        files, dirs = scan_eligible_items(self.monitor_dir)
        total_targets = files + dirs

        # Dispatch plugins even if sector is already empty
        plugin_info = ""
        if self.plugin_engine:
            dispatched = self.plugin_engine.dispatch_gesture(
                "double_snap", 2, peak_amplitude, threshold, self.monitor_dir
            )
            if dispatched:
                plugin_info = f" [Plugins: {', '.join(dispatched)}]"

        if not total_targets:
            if self.notification_manager:
                self.notification_manager.send_toast(
                    "⚡ FOLDER PURGE TRIGGERED",
                    "Target sector is already clean (0 items).",
                )
            return f"2 Snaps: Zero items in target sector{plugin_info}"

        summary = execute_batch_recycle(total_targets, self.monitor_dir)
        success_count = len(summary["succeeded"])
        fail_count = len(summary["failed"])

        if self.notification_manager:
            self.notification_manager.send_toast(
                "⚡ FOLDER PURGE COMPLETE",
                f"Moved {success_count} items from sector to Recycle Bin.",
            )

        if fail_count == 0:
            return f"2 Snaps: Purged {success_count} items to Recycle Bin (Recoverable){plugin_info}"
        else:
            return f"2 Snaps: Purged {success_count} items ({fail_count} failed){plugin_info}"

