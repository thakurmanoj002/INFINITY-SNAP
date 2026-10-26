"""
Infinity Snap — Action Router
=============================
Maps multi-gesture sound patterns (1 snap, 2 snaps, 3 snaps) to desktop actions:
  - 1 Snap: Purge target folder directly to Windows Recycle Bin.
  - 2 Snaps: Launch primary developer workspace / custom desktop macro.
  - 3 Snaps: Panic Stealth Mode (Minimize all windows + mute master audio).
"""

import ctypes
import os
from pathlib import Path
import subprocess
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
        self.workspace_cmd = config.get("workspace_cmd", "code .")

    def execute_gesture(self, snap_count: int, peak_amplitude: float, threshold: float) -> str:
        """Dispatches action according to registered snap count."""
        if snap_count == 1:
            return self.handle_single_snap(peak_amplitude, threshold)
        elif snap_count == 2:
            return self.handle_double_snap(peak_amplitude, threshold)
        elif snap_count >= 3:
            return self.handle_triple_snap(peak_amplitude, threshold)
        return "Unknown gesture"

    def handle_single_snap(self, peak_amplitude: float, threshold: float) -> str:
        """
        1 Snap Action: Instant Recycle Bin purge of the monitored folder.
        """
        files, dirs = scan_eligible_items(self.monitor_dir)
        total_targets = files + dirs

        if not total_targets:
            console.print(
                Panel(
                    f"[bold #00f0ff]>>> 1 SNAP DETECTED (PEAK: {peak_amplitude:.2f} >= {threshold:.2f}) <<<[/]\n"
                    f"[dim #00f0ff]Sector '{self.monitor_dir}' contains zero eligible items. Purge skipped.[/]",
                    title="[bold #00f0ff]◈ SINGLE SNAP // FOLDER PURGE ◈[/]",
                    border_style="#00f0ff",
                    box=box.ROUNDED,
                )
            )
            return "1 Snap: Zero items to recycle"

        console.print(
            Panel(
                f"[bold white on #ff0055] ⚡ 1 SNAP DETECTED [/] [bold #ff0055]>> PEAK: {peak_amplitude:.2f} >= THRESHOLD: {threshold:.2f}[/]\n"
                f"[bold #00f0ff]Target Sector :[/] [white]{self.monitor_dir}[/]\n"
                f"[bold #00f0ff]Purge Payload :[/] [bold #00ff66]{len(files)} Files[/], [bold #00f0ff]{len(dirs)} Directories[/] [dim]({len(total_targets)} total items)[/]\n"
                f"[bold #00f0ff]Purge Protocol:[/] [bold #ffe600]{self.action_mode} (INSTANT RECYCLE BIN PURGE)[/]",
                title="[bold #ff0055]◈ 1 SNAP // FOLDER PURGE ◈[/]",
                border_style="#ff0055",
                box=box.DOUBLE,
            )
        )

        summary = execute_batch_recycle(total_targets, self.monitor_dir)
        success_count = len(summary["succeeded"])
        fail_count = len(summary["failed"])

        if fail_count == 0:
            console.print(
                Panel(
                    f"[bold #00ff66]✔ ZERO-DAY PURGE COMPLETE[/] [dim]──[/] [bold white]{success_count}[/] items moved to Windows Recycle Bin.\n"
                    f"[dim]Failed: 0 | Win32 SH_ALLOWUNDO: 100% Recoverable | System Remaining Armed[/]",
                    border_style="#00ff66",
                    box=box.ROUNDED,
                )
            )
        else:
            console.print(
                Panel(
                    f"[bold #ff0055]⚠ PURGE COMPLETED WITH WARNINGS[/]\n"
                    f"[bold #00ff66]Succeeded:[/] {success_count} | [bold #ff0055]Failed:[/] {fail_count} | [bold #ffe600]Skipped:[/] {len(summary['skipped'])}",
                    border_style="#ff0055",
                    box=box.ROUNDED,
                )
            )

        return f"1 Snap: Purged {success_count} items to Recycle Bin"

    def handle_double_snap(self, peak_amplitude: float, threshold: float) -> str:
        """
        2 Snaps Action: Launch Primary Developer Workspace / Macro.
        """
        console.print(
            Panel(
                f"[bold black on #00f0ff] ⚡⚡ 2 SNAPS DETECTED [/] [bold #00f0ff]>> PEAK: {peak_amplitude:.2f} >= THRESHOLD: {threshold:.2f}[/]\n"
                f"[bold #ffe600]Action Protocol:[/] [white]LAUNCH PRIMARY WORKSPACE[/]\n"
                f"[bold #ffe600]Command         :[/] [cyan]{self.workspace_cmd}[/]",
                title="[bold #00f0ff]◈ DOUBLE SNAP // WORKSPACE MACRO ◈[/]",
                border_style="#00f0ff",
                box=box.DOUBLE,
            )
        )

        try:
            # Spawn workspace process detached
            subprocess.Popen(
                self.workspace_cmd,
                shell=True,
                cwd=str(self.monitor_dir),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            msg = f"2 Snaps: Workspace launched ({self.workspace_cmd})"
        except Exception as e:
            msg = f"2 Snaps: Failed to launch workspace: {e}"
            console.print(f"[bold #ff0055]Error launching workspace: {e}[/]")

        return msg

    def handle_triple_snap(self, peak_amplitude: float, threshold: float) -> str:
        """
        3 Snaps Action: Emergency Panic Stealth Mode.
        Minimizes all desktop windows (Win + D) and mutes master audio volume.
        """
        console.print(
            Panel(
                f"[bold white on #ff0055] 🚨🚨🚨 3 SNAPS DETECTED [/] [bold #ff0055]>> PEAK: {peak_amplitude:.2f} >= THRESHOLD: {threshold:.2f}[/]\n"
                f"[bold #ffe600]Protocol Engaged:[/] [bold #ff0055]PANIC STEALTH BOSS MODE[/]\n"
                f"[dim]1. Minimizing all active desktop windows (Win + D)...\n"
                f"2. Toggling master audio volume mute...[/]",
                title="[bold #ff0055]◈ TRIPLE SNAP // EMERGENCY PANIC PROTOCOL ◈[/]",
                border_style="#ff0055",
                box=box.HEAVY,
            )
        )

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

        return "3 Snaps: Stealth Panic Activated (Windows Minimized & Audio Muted)"
