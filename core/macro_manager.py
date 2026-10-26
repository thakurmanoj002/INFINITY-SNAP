"""
Infinity Snap — Spatial Macro Binding Engine
============================================
Loads user-configured gesture mappings from `air_bindings.json` and executes
native Windows actions: URLs, Applications, Keyboard Hotkeys, and Media Controls.
"""

from ctypes import wintypes
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Callable, Dict, List, Optional
import webbrowser

user32 = ctypes.windll.user32

# Virtual Key Codes
VK_MAP = {
    "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C,
    "ctrl": 0x11, "control": 0x11,
    "alt": 0x12, "menu": 0x12,
    "shift": 0x10,
    "enter": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B,
    "space": 0x20,
    "tab": 0x09,
    "backspace": 0x08,
    "delete": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "play_pause": 0xB3,
    "next_track": 0xB0,
    "prev_track": 0xB1,
    "stop": 0xB2,
    "volume_mute": 0xAD, "mute": 0xAD,
    "volume_up": 0xAF,
    "volume_down": 0xAE,
}

# Add standard alphanumeric keys A-Z and 0-9
for c in range(ord('a'), ord('z') + 1):
    VK_MAP[chr(c)] = ord(chr(c).upper())
for n in range(10):
    VK_MAP[str(n)] = ord(str(n))

# Add function keys F1-F12
for f in range(1, 13):
    VK_MAP[f"f{f}"] = 0x70 + (f - 1)

KEYEVENTF_KEYUP = 0x0002

DEFAULT_BINDINGS = {
    "THUMB_UP": {
        "name": "Open YouTube",
        "type": "url",
        "target": "https://www.youtube.com"
    },
    "VICTORY": {
        "name": "Launch VS Code",
        "type": "app",
        "target": "code ."
    },
    "ROCK_ON": {
        "name": "Toggle Media Play/Pause",
        "type": "media",
        "target": "play_pause"
    },
    "ILOVEYOU": {
        "name": "Show Desktop",
        "type": "hotkey",
        "target": ["win", "d"]
    },
    "THUMB_DOWN": {
        "name": "Mute Master Audio",
        "type": "media",
        "target": "mute"
    }
}


class MacroManager:
    """Manages gesture-to-action bindings, hold confirmation, and dispatch."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        on_trigger_callback: Optional[Callable[[str, str], None]] = None,
        hold_time: float = 0.38,
        cooldown: float = 1.80,
    ):
        self.config_path = config_path or (Path(__file__).resolve().parent.parent / "air_bindings.json")
        self.example_path = self.config_path.parent / "air_bindings.example.json"
        self.on_trigger_callback = on_trigger_callback
        self.hold_time = hold_time
        self.cooldown = cooldown

        # State tracking
        self.bindings: Dict[str, dict] = {}
        self.active_candidate = "NONE"
        self.candidate_start_time = 0.0
        self.last_trigger_time = 0.0
        self.last_triggered_name = ""

        self._load_bindings()

    def _load_bindings(self):
        """Loads air_bindings.json, creating default file if missing."""
        # Always write example template
        try:
            with open(self.example_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_BINDINGS, f, indent=4)
        except Exception:
            pass

        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.bindings = json.load(f)
                return
            except Exception:
                pass

        # If not present or failed, create with default bindings
        self.bindings = DEFAULT_BINDINGS.copy()
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.bindings, f, indent=4)
        except Exception:
            pass

    def check_gesture(self, gesture: str) -> Optional[str]:
        """
        Evaluates a candidate gesture. If held continuously for hold_time and
        cooldown has passed, executes the mapped action asynchronously.
        Returns the action name if triggered, else None.
        """
        now = time.time()

        if gesture not in self.bindings:
            self.active_candidate = "NONE"
            self.candidate_start_time = 0.0
            return None

        # Cooldown check
        if (now - self.last_trigger_time) < self.cooldown:
            return None

        # Gesture continuity check
        if gesture != self.active_candidate:
            self.active_candidate = gesture
            self.candidate_start_time = now
            return None

        # Hold time check
        if (now - self.candidate_start_time) >= self.hold_time:
            self.last_trigger_time = now
            self.active_candidate = "NONE"
            self.candidate_start_time = 0.0

            action_data = self.bindings[gesture]
            action_name = action_data.get("name", gesture)
            self.last_triggered_name = action_name

            # Dispatch execution in background thread
            threading.Thread(
                target=self._execute_action,
                args=(action_data,),
                daemon=True,
            ).start()

            if self.on_trigger_callback:
                self.on_trigger_callback(gesture, action_name)

            return action_name

        return None

    def _execute_action(self, action_data: dict):
        """Executes the mapped action safely without blocking."""
        act_type = action_data.get("type", "").lower()
        target = action_data.get("target")

        try:
            if act_type == "url":
                if isinstance(target, str):
                    webbrowser.open(target)

            elif act_type in {"app", "shell"}:
                if isinstance(target, str):
                    subprocess.Popen(
                        target,
                        shell=True,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                    )

            elif act_type == "hotkey":
                if isinstance(target, list):
                    self._simulate_hotkey(target)
                elif isinstance(target, str):
                    self._simulate_hotkey([target])

            elif act_type == "media":
                if isinstance(target, str):
                    self._simulate_media_key(target)

        except Exception:
            pass

    def _simulate_hotkey(self, keys: List[str]):
        """Simulates native Windows key combination press and release."""
        if sys.platform != "win32":
            return

        vk_codes = []
        for k in keys:
            code = VK_MAP.get(k.lower())
            if code is not None:
                vk_codes.append(code)

        if not vk_codes:
            return

        # Press down in order
        for code in vk_codes:
            user32.keybd_event(code, 0, 0, 0)
        time.sleep(0.05)
        # Release in reverse order
        for code in reversed(vk_codes):
            user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)

    def _simulate_media_key(self, command: str):
        """Simulates native Windows multimedia key press."""
        if sys.platform != "win32":
            return

        cmd = command.lower()
        code = VK_MAP.get(cmd)
        if code is not None:
            user32.keybd_event(code, 0, 0, 0)
            user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)
