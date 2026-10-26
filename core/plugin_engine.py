"""
Infinity Snap — Custom Script & Plugin Engine
=============================================
Discovers and executes user-defined scripts (.bat, .ps1, .py, .cmd, .exe)
when gesture triggers occur. Allows triggering external webhooks, smart
devices, IoT automations, or custom scripts asynchronously without blocking.
"""

import os
from pathlib import Path
import subprocess
import sys
from typing import Dict, List, Optional


class PluginEngine:
    """Discovers and runs asynchronous user plugins for single and double snap events."""

    SUPPORTED_EXTENSIONS = {".bat", ".cmd", ".ps1", ".py", ".exe"}

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.plugins_dir = self.project_root / "plugins"
        self._ensure_plugin_directories()

    def _ensure_plugin_directories(self):
        """Creates the default plugins folder hierarchy if not already present."""
        (self.plugins_dir / "single_snap").mkdir(parents=True, exist_ok=True)
        (self.plugins_dir / "double_snap").mkdir(parents=True, exist_ok=True)

    def discover_plugins(self, gesture: str) -> List[Path]:
        """
        Discovers all executable plugin files for the specified gesture ('single_snap' or 'double_snap').
        Checks both `plugins/<gesture>/` and root files named `plugins/on_<gesture>.*`.
        """
        plugins: List[Path] = []
        target_dir = self.plugins_dir / gesture

        if target_dir.is_dir():
            for item in target_dir.iterdir():
                if item.is_file() and item.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                    # Ignore example templates ending with .example
                    if not item.name.endswith(".example"):
                        plugins.append(item)

        # Also check plugins/on_<gesture>.* in the plugins root
        prefix = f"on_{gesture}"
        for item in self.plugins_dir.iterdir():
            if item.is_file() and item.stem.lower() == prefix:
                if item.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                    plugins.append(item)

        return sorted(plugins)

    def dispatch_gesture(
        self,
        gesture: str,
        snap_count: int,
        peak: float,
        threshold: float,
        monitor_dir: Path,
    ) -> List[str]:
        """
        Dispatches all matching plugins for the gesture in background subprocesses.
        Injects context telemetry into process environment variables.
        Returns the list of dispatched plugin names.
        """
        plugins = self.discover_plugins(gesture)
        if not plugins:
            return []

        # Prepare environment variables passed to plugins
        env = os.environ.copy()
        env["INFINITY_GESTURE"] = gesture.upper()
        env["INFINITY_SNAP_COUNT"] = str(snap_count)
        env["INFINITY_PEAK"] = f"{peak:.4f}"
        env["INFINITY_THRESHOLD"] = f"{threshold:.4f}"
        env["INFINITY_TARGET_DIR"] = str(monitor_dir)

        dispatched: List[str] = []
        for plugin in plugins:
            try:
                cmd = self._build_execution_command(plugin)
                subprocess.Popen(
                    cmd,
                    env=env,
                    cwd=str(self.project_root),
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                dispatched.append(plugin.name)
            except Exception:
                pass

        return dispatched

    def _build_execution_command(self, script_path: Path) -> List[str]:
        """Builds proper shell/interpreter command invocation based on script file type."""
        ext = script_path.suffix.lower()
        path_str = str(script_path.resolve())

        if ext == ".ps1":
            return [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                path_str,
            ]
        elif ext == ".py":
            return [sys.executable, path_str]
        elif ext in {".bat", ".cmd"}:
            return ["cmd.exe", "/c", path_str]
        else:
            return [path_str]
