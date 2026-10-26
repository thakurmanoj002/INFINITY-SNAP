"""
Infinity Snap — Configuration Manager & First-Run Setup
=======================================================
Handles loading, saving, and the interactive cyberpunk setup wizard.
"""

import json
from pathlib import Path
import sys
import time
from typing import Optional

from rich import box
from rich.console import Console
from rich.panel import Panel

from core.fs_monitor import get_project_root, scan_eligible_items, validate_monitoring_folder

console = Console()
CONFIG_FILENAME = "config.json"
DEFAULT_THRESHOLD = 0.50
DEFAULT_COOLDOWN = 1.20


def get_config_path() -> Path:
    """Returns the canonical path to config.json."""
    return get_project_root() / CONFIG_FILENAME


def load_config() -> Optional[dict]:
    """Loads configuration data from config.json if valid."""
    cfg_path = get_config_path()
    if not cfg_path.is_file():
        return None
    try:
        with open(cfg_path, mode="r", encoding="utf-8") as f:
            data = json.load(f)
            if "monitoring_folder" in data:
                return data
    except Exception:
        return None
    return None


def save_config(config_data: dict) -> None:
    """Saves configuration dictionary to config.json."""
    cfg_path = get_config_path()
    with open(cfg_path, mode="w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4)


def run_first_time_setup() -> dict:
    """
    Interactive first-run terminal setup wizard with Cyberpunk styling.
    Prompts the user to configure monitoring folder, action mode, and detection settings.
    """
    if sys.stdout.isatty():
        console.clear()

    console.print(
        Panel(
            "[bold #00f0ff]◈ INFINITY SNAP // FIRST-RUN NEURAL SETUP ◈[/]\n"
            "[dim]Welcome operator. Configure your target sector surveillance and acoustic trigger thresholds.[/]",
            border_style="bright_cyan",
            box=box.DOUBLE,
            padding=(1, 2),
        )
    )

    # Step A: Monitoring Folder
    validated_folder: Optional[Path] = None
    while validated_folder is None:
        console.print(
            Panel(
                "[bold #ff007f]STEP 1: SELECT TARGET MONITORING SECTOR[/]\n"
                "[dim]Enter the absolute path of the folder you wish to monitor.[/]\n\n"
                "[bold #ffe600]Safety Directives:[/]\n"
                "  * Must be a dedicated user directory (e.g. C:\\Users\\...\\Desktop\\SnapTest).\n"
                "  * Drive roots (C:\\), Windows system files, Desktop root, User Profile root,\n"
                "    and project directories are strictly forbidden by boundary firewalls.",
                border_style="#ff007f",
                box=box.ROUNDED,
            )
        )
        user_path = input("Target Folder Path: ").strip()

        folder, err_msg = validate_monitoring_folder(user_path)
        if folder is None:
            console.print(f"\n[bold #ff0055]>> REJECTED:[/] [white]{err_msg}[/]\n")
            continue

        files, dirs = scan_eligible_items(folder)
        console.print(f"\n[bold #00ff66]Validated Sector:[/] [bold cyan]{folder}[/]")
        console.print(
            f"[dim]Current contents : {len(files)} eligible files, {len(dirs)} eligible subdirectories[/]"
        )
        confirm = input("Confirm this sector as active surveillance target? [y/N]: ").strip().lower()
        if confirm in ("y", "yes"):
            validated_folder = folder
            console.print("[bold #00ff66][+] Sector locked and confirmed.[/]\n")
        else:
            console.print("[yellow]Selection discarded. Please enter a path again.[/]\n")

    # Step B: Action Mode
    console.print(
        Panel(
            "[bold #ffe600]STEP 2: PURGE PROTOCOL SELECTION[/]\n\n"
            "[bold #00ff66][1] NORMAL Mode (Recommended):[/]\n"
            "    Dispatches eligible items directly to Windows Recycle Bin.\n"
            "    Zero permanent deletion fallback. Fully recoverable via Windows Explorer.\n\n"
            "[bold #ff007f][2] ADVANCED Mode:[/]\n"
            "    Labeled advanced mode. Executes using the same safe, recoverable Recycle Bin\n"
            "    protocol to prevent accidental loss.",
            border_style="#ffe600",
            box=box.ROUNDED,
        )
    )

    selected_mode = "NORMAL"
    mode_choice = input("Select Protocol [1 for NORMAL, 2 for ADVANCED] (default: 1): ").strip()
    if mode_choice == "2":
        selected_mode = "ADVANCED"
        console.print("[bold #ff007f][+] ADVANCED Protocol armed (Recycle Bin execution).[/]")
    else:
        selected_mode = "NORMAL"
        console.print("[bold #00ff66][+] NORMAL Protocol armed (Windows Recycle Bin).[/]")

    # Step C: Audio Settings
    console.print(
        Panel(
            "[bold #00f0ff]STEP 3: ACOUSTIC TRANSIENT SENSITIVITY[/]\n"
            "[dim]Analyzes short acoustic energy peaks from your microphone transducer.[/]\n"
            "[dim]Lower = more sensitive. Higher = requires louder, sharper transients.[/]",
            border_style="#00f0ff",
            box=box.ROUNDED,
        )
    )

    threshold = DEFAULT_THRESHOLD
    thresh_input = input(f"Peak trigger threshold (0.10 to 0.90, default {DEFAULT_THRESHOLD:.2f}): ").strip()
    if thresh_input:
        try:
            val = float(thresh_input)
            if 0.05 <= val <= 0.95:
                threshold = val
        except ValueError:
            pass

    config_data = {
        "monitoring_folder": str(validated_folder),
        "action_mode": selected_mode,
        "threshold": threshold,
        "cooldown": DEFAULT_COOLDOWN,
        "workspace_cmd": "code .",
        "device": None,
    }

    save_config(config_data)
    console.print("\n[bold #00ff66]✔ Configuration saved to config.json. Launching HUD...[/]\n")
    time.sleep(1.0)
    return config_data
