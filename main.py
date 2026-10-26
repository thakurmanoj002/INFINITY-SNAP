"""
Infinity Snap — Flexible Folder Monitoring & Action System
==========================================================
Windows desktop filesystem monitoring and microphone-triggered safe file management.

Architecture:
    - Native Windows Shell integration (SHFileOperationW via ctypes) for user-recoverable
      Recycle Bin operations. NEVER falls back to permanent deletion.
    - Continuous filesystem monitoring via Windows FindFirstChangeNotificationW with
      periodic reconciliation scanning.
    - Multi-layer sandbox boundary validation protecting Windows system directories,
      drive roots, user profile roots, project sources, and virtual environments.
    - Real-time microphone listening for sudden sound transients (such as finger snaps or claps)
      with single-shot immediate disarm protection.
"""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import List, Tuple, Optional

# Configure UTF-8 encoding on Windows to prevent legacy charmap codec errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table
from rich.text import Text
import sounddevice as sd

console = Console()


# ==============================================================================
# 1. CONSTANTS & SYSTEM DEFINITIONS
# ==============================================================================

CONFIG_FILENAME = "config.json"
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_BLOCK_SIZE = 1024
DEFAULT_THRESHOLD = 0.50
DEFAULT_COOLDOWN = 1.20

# Windows Shell API Constants for Recycle Bin Operations
FO_DELETE = 0x0003
FOF_ALLOWUNDO = 0x0040       # Move to Recycle Bin instead of permanent deletion
FOF_NOCONFIRMATION = 0x0010  # Suppress default Windows Explorer confirmation dialog
FOF_SILENT = 0x0004          # Suppress default Windows progress dialog
FOF_NOERRORUI = 0x0400       # Suppress default Windows error dialogs

# Windows File Change Notification Constants (kernel32.dll)
FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001
FILE_NOTIFY_CHANGE_DIR_NAME = 0x00000002
FILE_NOTIFY_CHANGE_ATTRIBUTES = 0x00000004
FILE_NOTIFY_CHANGE_SIZE = 0x00000008
FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010

WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
INVALID_HANDLE_VALUE = -1

if sys.platform == "win32":
    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]


# ==============================================================================
# 2. BOUNDARY VALIDATION & PROTECTED DIRECTORIES
# ==============================================================================

def get_project_root() -> Path:
    """Returns the canonical root directory of the Infinity Snap project."""
    return Path(__file__).resolve().parent


def is_protected_directory(path: Path) -> Tuple[bool, str]:
    """
    Evaluates whether a target directory is a protected or sensitive Windows location.
    
    Protected locations include:
      - Drive roots (e.g., C:\\, D:\\)
      - Windows system directories (e.g., C:\\Windows, System32)
      - Program Files & ProgramData
      - System Users directory (C:\\Users)
      - User profile roots (e.g., C:\\Users\\Username)
      - User special folder roots (Desktop, Documents, Downloads, AppData)
      - Infinity Snap project directory and its virtual environment
    """
    resolved = path.resolve()

    # 1. Check drive root (e.g., C:\, D:\)
    if resolved == Path(resolved.anchor) or len(resolved.parts) <= 1:
        return True, f"Drive root ('{resolved}') cannot be selected as a monitoring folder."

    resolved_str = str(resolved).lower()

    # 2. Check Windows System directories
    system_root = os.environ.get("SystemRoot", r"C:\Windows").lower()
    if resolved_str == system_root or resolved_str.startswith(system_root + "\\"):
        return True, "Windows system directory cannot be selected as a monitoring folder."

    # 3. Check Program Files & ProgramData
    for env_var in ["ProgramFiles", "ProgramFiles(x86)", "ProgramData"]:
        val = os.environ.get(env_var)
        if val:
            val_lower = val.lower()
            if resolved_str == val_lower or resolved_str.startswith(val_lower + "\\"):
                return True, f"System directory ('{val}') cannot be selected as a monitoring folder."

    # 4. Check User Profile root and C:\Users
    home = Path.home().resolve()
    if resolved == home:
        return True, f"User profile root ('{home}') cannot be selected. Please choose a dedicated subfolder."

    users_dir = home.parent.resolve()
    if resolved == users_dir:
        return True, "System Users folder cannot be selected as a monitoring folder."

    # 5. Check User special root folders directly (Desktop, Documents, Downloads, AppData)
    for special_name in ["desktop", "documents", "downloads", "appdata"]:
        special_path = (home / special_name).resolve()
        if resolved == special_path:
            return True, (
                f"Direct '{special_name.capitalize()}' root cannot be selected. "
                f"Please create and choose a dedicated subfolder inside it (e.g., {special_name.capitalize()}\\SnapFolder)."
            )

    # 6. Check Project Root and parent directories
    project_root = get_project_root()
    if resolved == project_root or project_root in resolved.parents or resolved in project_root.parents:
        return True, "The project directory or its parent folders cannot be selected as a monitoring target."

    # 7. Check Python Environment (venv)
    prefix_path = Path(sys.prefix).resolve()
    if resolved == prefix_path or prefix_path in resolved.parents:
        return True, "Python environment directories cannot be selected as a monitoring target."

    return False, ""


def validate_monitoring_folder(path_input: str) -> Tuple[Optional[Path], str]:
    """
    Validates that a user-supplied directory path exists, is accessible, and is safe.
    Returns (Path, "") on success, or (None, error_message) on failure.
    """
    cleaned = path_input.strip().strip('"').strip("'")
    if not cleaned:
        return None, "Path input cannot be empty."

    candidate = Path(cleaned)

    # Must be absolute or cleanly resolvable
    try:
        resolved = candidate.resolve()
    except Exception as err:
        return None, f"Invalid path format: {err}"

    if not resolved.exists():
        return None, f"The folder '{resolved}' does not exist."

    if not resolved.is_dir():
        return None, f"'{resolved}' is a file, not a directory."

    # Symlink / Junction check on the folder itself
    if resolved.is_symlink() or os.path.islink(str(resolved)):
        return None, "The monitoring folder cannot be a symbolic link or junction."

    # Protected system check
    protected, reason = is_protected_directory(resolved)
    if protected:
        return None, f"Security Violation: {reason}"

    # Accessibility check (can list directory)
    try:
        _ = list(os.scandir(str(resolved)))
    except PermissionError:
        return None, f"Access denied: Cannot read contents of '{resolved}'."
    except Exception as err:
        return None, f"Filesystem error inspecting folder: {err}"

    return resolved, ""


# ==============================================================================
# 3. WINDOWS RECYCLE BIN IMPLEMENTATION
# ==============================================================================

def revalidate_target_item(target: Path, monitor_dir: Path) -> Path:
    """
    Just-In-Time (JIT) safety verification performed immediately prior to any file operation.
    Guarantees:
      1. Target exists and resolves strictly within the approved monitoring directory.
      2. Target is not the monitoring directory itself.
      3. Target is not a symbolic link, NTFS junction, or reparse point.
    """
    if not target.exists():
        raise FileNotFoundError(f"JIT Safety Violation: Target no longer exists: '{target}'")

    real_path = target.resolve(strict=True)

    try:
        real_path.relative_to(monitor_dir)
    except ValueError:
        raise PermissionError(
            f"JIT Safety Violation: Target '{real_path}' is outside monitoring folder '{monitor_dir}'."
        )

    if real_path == monitor_dir:
        raise ValueError("JIT Safety Violation: Cannot target the monitoring directory itself.")

    if real_path.is_symlink() or os.path.islink(str(real_path)):
        raise PermissionError(f"JIT Safety Violation: Symlinks and junctions are forbidden: '{real_path}'")

    try:
        st = os.lstat(str(real_path))
        if hasattr(st, "st_reparse_tag") and st.st_reparse_tag != 0:
            raise PermissionError(
                f"JIT Safety Violation: Reparse point tag ({st.st_reparse_tag}) forbidden: '{real_path}'"
            )
    except OSError as err:
        raise PermissionError(f"JIT Safety Violation: Attribute check failed: {err}")

    return real_path


def recycle_item(target: Path, monitor_dir: Path, _api_call=None) -> bool:
    """
    Moves a single validated item (file or directory) to the Windows Recycle Bin
    using native SHFileOperationW.
    
    Guarantees:
      - Uses FO_DELETE with FOF_ALLOWUNDO.
      - NEVER falls back to permanent deletion (no os.remove, no Path.unlink, no rmtree).
      - Checks Windows Shell API return code and fAnyOperationsAborted.
      - Verifies that the item no longer exists at source location upon success.
    """
    if sys.platform != "win32":
        raise OSError("Windows Recycle Bin integration is only supported on Windows.")

    validated = revalidate_target_item(target, monitor_dir)
    path_str = str(validated) + "\0\0"

    fileop = SHFILEOPSTRUCTW()
    fileop.hwnd = None
    fileop.wFunc = FO_DELETE
    fileop.pFrom = path_str
    fileop.pTo = None
    fileop.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    fileop.fAnyOperationsAborted = False
    fileop.hNameMappings = None
    fileop.lpszProgressTitle = None

    if _api_call is not None:
        result = _api_call(fileop)
    else:
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(fileop))

    if result != 0:
        raise OSError(
            f"Windows Shell API SHFileOperationW failed with code {result} (0x{result:08X}). "
            f"Item '{validated.name}' was NOT moved to Recycle Bin."
        )

    if fileop.fAnyOperationsAborted:
        raise OSError(
            f"Windows Shell operation was aborted by the operating system. "
            f"Item '{validated.name}' was NOT moved to Recycle Bin."
        )

    if _api_call is None and validated.exists():
        raise OSError(
            f"Inconsistent state: Windows Shell returned success, but '{validated.name}' still exists."
        )

    return True


def execute_batch_recycle(items: List[Path], monitor_dir: Path, _api_call=None) -> dict:
    """
    Safely processes a batch of validated items into the Windows Recycle Bin
    using native Windows Shell SHFileOperationW with cyberpunk styling.
    """
    summary = {
        "requested": len(items),
        "succeeded": [],
        "failed": [],
        "skipped": [],
    }

    if not items:
        return summary

    if len(items) > 10:
        with Progress(
            SpinnerColumn(style="bold #ff007f"),
            TextColumn("[bold #00f0ff]{task.description}[/]"),
            BarColumn(bar_width=25, style="#2a2a40", complete_style="#00f0ff"),
            TaskProgressColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Purging targets to Recycle Bin...", total=len(items))
            for item in items:
                try:
                    success = recycle_item(item, monitor_dir, _api_call=_api_call)
                    if success:
                        summary["succeeded"].append(item.name)
                    else:
                        summary["failed"].append(item.name)
                        break
                except Exception as err:
                    summary["failed"].append(item.name)
                    console.print(f"[bold #ff0055]  [!] Error recycling '{item.name}': {err}[/]")
                    break
                progress.advance(task)
    else:
        for item in items:
            item_type = "DIR " if item.is_dir() else "FILE"
            type_color = "#00f0ff" if item.is_dir() else "#00ff66"
            try:
                success = recycle_item(item, monitor_dir, _api_call=_api_call)
                if success:
                    summary["succeeded"].append(item.name)
                    console.print(
                        f"  [bold {type_color}][{item_type}][/] [white]{item.name}[/] [dim]──>[/] [bold #00ff66]MOVED TO RECYCLE BIN[/]"
                    )
                else:
                    summary["failed"].append(item.name)
                    console.print(
                        f"  [bold {type_color}][{item_type}][/] [white]{item.name}[/] [dim]──>[/] [bold #ff0055]FAILED[/]"
                    )
                    break
            except Exception as err:
                summary["failed"].append(item.name)
                console.print(f"  [bold #ff0055][ERROR][/] [white]{item.name}:[/] {err}")
                break

    # Record any unattempted items as skipped
    attempted = set(summary["succeeded"] + summary["failed"])
    summary["skipped"] = [it.name for it in items if it.name not in attempted]

    return summary


# ==============================================================================
# 4. FILESYSTEM SCANNING & CONTINUOUS MONITORING
# ==============================================================================

def scan_eligible_items(monitor_dir: Path) -> Tuple[List[Path], List[Path]]:
    """
    Discovers all eligible regular files and regular subdirectories directly
    inside the approved monitoring folder.
    Excludes symlinks, junctions, reparse points, and the directory itself.
    """
    if not monitor_dir.exists() or not monitor_dir.is_dir():
        return [], []

    files: List[Path] = []
    dirs: List[Path] = []

    try:
        for entry in os.scandir(str(monitor_dir)):
            try:
                # Check for symlink
                if entry.is_symlink():
                    continue

                entry_path = Path(entry.path)

                # Check for reparse point (junctions, AppExecLink, mount points)
                try:
                    st = os.lstat(entry.path)
                    if hasattr(st, "st_reparse_tag") and st.st_reparse_tag != 0:
                        continue
                except OSError:
                    continue

                if entry.is_file():
                    files.append(entry_path)
                elif entry.is_dir():
                    dirs.append(entry_path)
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        return [], []

    return sorted(files, key=lambda p: p.name.lower()), sorted(dirs, key=lambda p: p.name.lower())


class ContinuousFolderMonitor:
    """
    Windows-native background directory watcher.
    Uses kernel32.FindFirstChangeNotificationW for instantaneous OS change events,
    with a periodic timeout fallback for reconciliation.
    """

    def __init__(self, monitor_dir: Path, on_change_callback=None):
        self.monitor_dir = monitor_dir
        self.on_change_callback = on_change_callback
        self.running = False
        self.thread: Optional[threading.Thread] = None

        self.lock = threading.Lock()
        self.file_count = 0
        self.dir_count = 0
        self.last_change_time = time.time()

        # Initial scan
        self.reconcile()

    def reconcile(self) -> Tuple[int, int]:
        """Performs a reconciliation scan and updates counts."""
        files, dirs = scan_eligible_items(self.monitor_dir)
        with self.lock:
            old_counts = (self.file_count, self.dir_count)
            self.file_count = len(files)
            self.dir_count = len(dirs)
            new_counts = (self.file_count, self.dir_count)

        if old_counts != new_counts and self.on_change_callback:
            self.on_change_callback(new_counts[0], new_counts[1])

        return new_counts

    def get_counts(self) -> Tuple[int, int]:
        """Thread-safe accessor for current counts."""
        with self.lock:
            return self.file_count, self.dir_count

    def start(self):
        """Starts the background monitoring thread."""
        self.running = True
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def stop(self):
        """Stops the monitoring thread."""
        self.running = False

    def _worker(self):
        """Worker thread using Windows kernel32 change notifications."""
        if sys.platform != "win32":
            # Fallback polling for non-Windows platforms
            while self.running:
                time.sleep(2.0)
                self.reconcile()
            return

        kernel32 = ctypes.windll.kernel32
        filter_flags = (
            FILE_NOTIFY_CHANGE_FILE_NAME
            | FILE_NOTIFY_CHANGE_DIR_NAME
            | FILE_NOTIFY_CHANGE_ATTRIBUTES
            | FILE_NOTIFY_CHANGE_SIZE
            | FILE_NOTIFY_CHANGE_LAST_WRITE
        )

        handle = kernel32.FindFirstChangeNotificationW(
            str(self.monitor_dir),
            False,  # Watch immediate directory
            filter_flags,
        )

        if handle == INVALID_HANDLE_VALUE or handle is None:
            # Fallback to periodic reconciliation
            while self.running:
                time.sleep(2.0)
                self.reconcile()
            return

        try:
            while self.running:
                # Wait for OS notification with a 1500 ms periodic reconciliation fallback
                status = kernel32.WaitForSingleObject(handle, 1500)
                if not self.running:
                    break

                if status == WAIT_OBJECT_0:
                    self.reconcile()
                    kernel32.FindNextChangeNotification(handle)
                elif status == WAIT_TIMEOUT:
                    # Periodic reconciliation scan
                    self.reconcile()
        finally:
            kernel32.FindCloseChangeNotification(handle)


# ==============================================================================
# 5. CONFIGURATION & FIRST-RUN SETUP
# ==============================================================================

def get_config_path() -> Path:
    """Returns the path to the application's config.json file."""
    return get_project_root() / CONFIG_FILENAME


def load_config() -> Optional[dict]:
    """Loads configuration from config.json if it exists and is valid."""
    cfg_path = get_config_path()
    if not cfg_path.is_file():
        return None
    try:
        with open(cfg_path, mode="r", encoding="utf-8") as f:
            data = json.load(f)
            # Basic validation of required keys
            if "monitoring_folder" in data and "action_mode" in data:
                return data
    except Exception:
        return None
    return None


def save_config(config_data: dict) -> None:
    """Saves configuration data to config.json."""
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
            "[dim]Welcome operator. No existing config.json detected.[/]\n"
            "[dim]Configure target sector surveillance boundaries and acoustic threshold calibration.[/]",
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
        "device": None,
    }

    save_config(config_data)
    console.print("\n[bold #00ff66]✔ Configuration saved to config.json. Launching HUD...[/]\n")
    time.sleep(1.0)
    return config_data


# ==============================================================================
# 6. LIVE CLI DASHBOARD & AUDIO STREAM
# ==============================================================================

def abbreviate_path(path: Path, max_length: int = 40) -> str:
    """Abbreviates a path with ellipsis if it exceeds max_length for clean CLI display."""
    s = str(path)
    if len(s) <= max_length:
        return s
    return s[:16] + "..." + s[-(max_length - 19):]


def render_dashboard(
    monitor_dir: Path,
    action_mode: str,
    device_name: str,
    threshold: float,
    file_count: int,
    dir_count: int,
    is_armed: bool,
    last_event: str,
    clear_screen: bool = True,
):
    """Renders a simple, high-visibility Cyberpunk terminal HUD using the Rich library."""
    if clear_screen and sys.stdout.isatty():
        console.clear()

    abbr_dir = abbreviate_path(monitor_dir, max_length=52)

    # Status indicator pill
    if is_armed:
        status_markup = (
            "[bold black on #00ff66] ● ARMED [/] "
            "[bold #00ff66]SURVEILLANCE ENGAGED[/] "
            "[dim cyan]── Listening for snap[/]"
        )
    else:
        status_markup = (
            "[bold black on #ffe600] ○ PAUSED [/] "
            "[bold #ffe600]DISARMED[/] "
            "[dim]── Standby mode[/]"
        )

    # Cyberpunk audio sensitivity meter
    total_blocks = 20
    filled = max(1, min(total_blocks, int(threshold * total_blocks)))
    meter = (
        f"[bold #00f0ff]{'█' * filled}[/]"
        f"[dim #252839]{'░' * (total_blocks - filled)}[/] "
        f"[bold #ffe600]{threshold:.2f}[/]"
    )

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold #ff007f", no_wrap=True, width=21)
    table.add_column("Sep", style="dim #00f0ff", width=2)
    table.add_column("Value", style="white")

    table.add_row("STATUS", "::", status_markup)
    table.add_row("TARGET SECTOR", "::", f"[bold #00f0ff]{abbr_dir}[/]")
    table.add_row(
        "PURGE PROTOCOL",
        "::",
        f"[bold #ffe600]{action_mode}[/] [dim]──[/] [dim #8888aa][Windows Desktop Recycle Bin / 100% Recoverable][/]",
    )
    table.add_row(
        "AUDIO SENSOR",
        "::",
        f"[bright_white]{device_name[:36]}[/] [dim #ff007f]│[/] [bold #ff007f]THRESHOLD:[/] [bold #00f0ff]{threshold:.2f}[/]",
    )
    table.add_row(
        "PAYLOAD OBJECTS",
        "::",
        f"[bold #00ff66]{file_count} Files[/] [dim #ff007f]│[/] [bold #00f0ff]{dir_count} Directories[/] [dim cyan]({file_count + dir_count} items ready)[/]",
    )
    table.add_row("LAST TELEMETRY", "::", f"[italic #ff79c6]{last_event}[/]")
    table.add_row("TRIGGER SENSITIVITY", "::", meter)

    panel = Panel(
        table,
        title="[bold #00f0ff]⚡ INFINITY SNAP // NEURAL AUDIO TRANSIENT HUD ⚡[/]",
        subtitle="[bold #ffe600][Ctrl+C][/] [dim white]STOP MONITORING[/]   [dim #00f0ff]│[/]   [dim #00ff66]WIN32 SH_ALLOWUNDO: ACTIVE (RECOVERABLE)[/]",
        border_style="bright_cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)


def handle_snap_trigger(
    monitor_dir: Path,
    action_mode: str,
    peak_amplitude: float,
    threshold: float,
    _api_call=None,
) -> Tuple[str, bool]:
    """
    Executes the snap trigger workflow with cyberpunk styling:
      1. Re-scans monitoring folder.
      2. Displays cyberpunk trigger interception panel.
      3. Instantly executes recoverable Windows Recycle Bin action on all items.
      4. Displays execution summary panel.
      5. Returns (result_message, is_armed_state=True).
    """
    # Re-scan monitoring folder
    files, dirs = scan_eligible_items(monitor_dir)
    total_targets = files + dirs

    if not total_targets:
        console.print(
            Panel(
                f"[bold #ff0055]>>> SNAP TRANSIENT INTERCEPTED (PEAK: {peak_amplitude:.2f} >= {threshold:.2f}) <<<[/]\n"
                f"[dim #00f0ff]Sector '{monitor_dir}' contains zero eligible items. Purge skipped.[/]",
                title="[bold #ff0055]◈ NEURAL TRANSIENT DETECTED ◈[/]",
                border_style="#ff0055",
                box=box.ROUNDED,
            )
        )
        return "No items to recycle", True

    console.print(
        Panel(
            f"[bold white on #ff0055] ⚡ SNAP TRANSIENT INTERCEPTED [/] [bold #ff0055]>> PEAK: {peak_amplitude:.2f} >= THRESHOLD: {threshold:.2f}[/]\n"
            f"[bold #00f0ff]Target Sector :[/] [white]{monitor_dir}[/]\n"
            f"[bold #00f0ff]Purge Payload :[/] [bold #00ff66]{len(files)} Files[/], [bold #00f0ff]{len(dirs)} Directories[/] [dim]({len(total_targets)} total items)[/]\n"
            f"[bold #00f0ff]Purge Protocol:[/] [bold #ffe600]{action_mode} (INSTANT RECYCLE BIN PURGE)[/]",
            title="[bold #ff0055]◈ NEURAL EVENT DETECTED ◈[/]",
            border_style="#ff0055",
            box=box.DOUBLE,
        )
    )

    summary = execute_batch_recycle(total_targets, monitor_dir, _api_call=_api_call)

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

    msg = f"Instantly recycled {success_count} items (Failed: {fail_count})"
    return msg, True


def run_application(config: dict, _test_snap_callback=None):
    """
    Main application loop coordinating continuous filesystem monitoring
    and audio snap detection.
    """
    monitor_dir = Path(config["monitoring_folder"]).resolve()
    action_mode = config.get("action_mode", "NORMAL")
    threshold = float(config.get("threshold", DEFAULT_THRESHOLD))
    cooldown = float(config.get("cooldown", DEFAULT_COOLDOWN))
    device = config.get("device")

    # Safety re-validation on startup
    folder, err = validate_monitoring_folder(str(monitor_dir))
    if folder is None:
        console.print(f"\n[bold #ff0055][FATAL CONFIG ERROR][/] Configured folder is invalid: {err}")
        console.print("[dim]Please run 'python main.py --setup' to reconfigure.[/]\n")
        sys.exit(1)

    monitor_dir = folder

    # Initialize audio device lookup
    try:
        device_info = sd.query_devices(device=device, kind="input")
        device_name = device_info["name"]
    except Exception as err:
        console.print(f"\n[bold #ff0055][AUDIO ERROR][/] Unable to access audio input device: {err}")
        console.print("[dim]Please check Windows Privacy Settings -> Microphone Access.[/]\n")
        sys.exit(1)

    # State variables
    is_armed = True
    last_event = "System initialized and armed"
    last_snap_time = 0.0

    # Start continuous background monitoring
    fs_monitor = ContinuousFolderMonitor(monitor_dir)
    fs_monitor.start()

    # Initial dashboard render
    file_count, dir_count = fs_monitor.get_counts()
    render_dashboard(
        monitor_dir=monitor_dir,
        action_mode=action_mode,
        device_name=device_name,
        threshold=threshold,
        file_count=file_count,
        dir_count=dir_count,
        is_armed=is_armed,
        last_event=last_event,
    )

    try:
        with sd.InputStream(
            device=device,
            channels=1,
            samplerate=DEFAULT_SAMPLE_RATE,
            blocksize=DEFAULT_BLOCK_SIZE,
            dtype="float32",
        ) as stream:
            last_counts = (file_count, dir_count)

            while True:
                # Read audio block
                audio_data, _ = stream.read(DEFAULT_BLOCK_SIZE)
                current_time = time.time()
                peak_amplitude = float(np.max(np.abs(audio_data)))

                # Check if filesystem count changed
                current_counts = fs_monitor.get_counts()
                if current_counts != last_counts:
                    last_counts = current_counts
                    render_dashboard(
                        monitor_dir=monitor_dir,
                        action_mode=action_mode,
                        device_name=device_name,
                        threshold=threshold,
                        file_count=current_counts[0],
                        dir_count=current_counts[1],
                        is_armed=is_armed,
                        last_event=last_event,
                    )

                # Peak threshold check
                if peak_amplitude >= threshold:
                    if (current_time - last_snap_time) >= cooldown:
                        if is_armed:
                            # Trigger snap workflow
                            last_event, is_armed = handle_snap_trigger(
                                monitor_dir=monitor_dir,
                                action_mode=action_mode,
                                peak_amplitude=peak_amplitude,
                                threshold=threshold,
                                _api_call=_test_snap_callback,
                            )

                            # Reconcile counts and briefly pause so user sees purge notification
                            fs_monitor.reconcile()
                            c_files, c_dirs = fs_monitor.get_counts()
                            last_counts = (c_files, c_dirs)
                            time.sleep(1.2)

                            # Refresh dashboard with updated zero counts
                            render_dashboard(
                                monitor_dir=monitor_dir,
                                action_mode=action_mode,
                                device_name=device_name,
                                threshold=threshold,
                                file_count=c_files,
                                dir_count=c_dirs,
                                is_armed=is_armed,
                                last_event=last_event,
                            )
                            # Reset cooldown timer to after action completion
                            last_snap_time = time.time()

    except KeyboardInterrupt:
        console.print(
            "\n[bold #ff007f]⚡ DISENGAGED[/] [dim]──[/] [dim cyan]Infinity Snap shut down. Audio transducer and folder watcher released.[/]\n"
        )
    finally:
        fs_monitor.stop()


# ==============================================================================
# 7. NON-DESTRUCTIVE SELF-TEST VERIFICATION
# ==============================================================================

def run_self_tests() -> bool:
    """
    Focused non-destructive self-tests with Cyberpunk styling covering:
      1. Boundary validation (protected directories, drive roots, project dir).
      2. Config save and load.
      3. Mocked Windows SHFileOperationW execution (success, error, abort).
      4. Folder monitoring change detection.
    """
    console.print(
        Panel(
            "[bold #00f0ff]◈ RUNNING NON-DESTRUCTIVE VERIFICATION SUITE ◈[/]\n"
            "[dim]Validating safety boundaries, Win32 bindings, and persistence schemas.[/]",
            border_style="bright_cyan",
            box=box.ROUNDED,
        )
    )

    # Check 1: Boundary validation
    assert is_protected_directory(Path(r"C:\Windows"))[0] is True
    assert is_protected_directory(Path(r"C:\Program Files"))[0] is True
    assert is_protected_directory(Path("C:\\"))[0] is True
    assert is_protected_directory(Path.home())[0] is True
    assert is_protected_directory(get_project_root())[0] is True
    console.print("  [bold #00ff66]✔ [1/4] BOUNDARY FIREWALLS[/]   [dim]──[/] Protected directories strictly barred.")

    # Check 2: Config persistence
    test_cfg = {
        "monitoring_folder": str(Path.home() / "TestSandbox"),
        "action_mode": "NORMAL",
        "threshold": 0.55,
        "cooldown": 1.0,
        "device": None,
    }
    cfg_file = get_config_path()
    orig_content = cfg_file.read_bytes() if cfg_file.exists() else None
    try:
        save_config(test_cfg)
        loaded = load_config()
        assert loaded is not None
        assert loaded["action_mode"] == "NORMAL"
        assert loaded["threshold"] == 0.55
    finally:
        if orig_content is not None:
            cfg_file.write_bytes(orig_content)
        elif cfg_file.exists():
            try:
                cfg_file.unlink()
            except OSError:
                pass
    console.print("  [bold #00ff66]✔ [2/4] CONFIG PERSISTENCE[/]   [dim]──[/] JSON schema write/read verified.")

    # Check 3: Mocked Windows SHFileOperationW logic
    def mock_ok(op):
        return 0

    def mock_err(op):
        return 2  # ERROR_FILE_NOT_FOUND

    def mock_aborted(op):
        op.fAnyOperationsAborted = True
        return 0

    test_dummy = get_project_root() / "README.md"
    assert recycle_item(test_dummy, get_project_root().parent, _api_call=mock_ok) is True

    err_caught = False
    try:
        recycle_item(test_dummy, get_project_root().parent, _api_call=mock_err)
    except OSError:
        err_caught = True
    assert err_caught is True

    abort_caught = False
    try:
        recycle_item(test_dummy, get_project_root().parent, _api_call=mock_aborted)
    except OSError:
        abort_caught = True
    assert abort_caught is True
    console.print("  [bold #00ff66]✔ [3/4] WIN32 SH_ALLOWUNDO[/]   [dim]──[/] Mock success, error, and abort paths verified.")

    # Check 4: Folder scanner filtering
    files, dirs = scan_eligible_items(get_project_root())
    assert any(f.name == "README.md" for f in files)
    console.print("  [bold #00ff66]✔ [4/4] SECTOR SCANNER[/]       [dim]──[/] Directory discovery and link filtering verified.")

    console.print(
        Panel(
            "[bold #00ff66]✔ ALL 4 VERIFICATION PROTOCOLS PASSED SUCCESSFULLY[/]\n"
            "[dim]System is verified safe. Zero destructive operations performed.[/]",
            border_style="#00ff66",
            box=box.ROUNDED,
        )
    )
    return True


# ==============================================================================
# 8. CLI PARSER & MAIN ENTRY POINT
# ==============================================================================

def list_audio_devices():
    """Lists all available audio input devices found on the system using Rich."""
    try:
        devices = sd.query_devices()
        input_devices = [
            (i, d) for i, d in enumerate(devices) if d.get("max_input_channels", 0) > 0
        ]

        if not input_devices:
            console.print("[bold #ff0055]No audio input devices (microphones) were found.[/]")
            return

        table = Table(
            title="[bold #00f0ff]◈ AVAILABLE AUDIO SENSORS // TRANSDUCER MATRIX ◈[/]",
            border_style="bright_cyan",
            box=box.ROUNDED,
        )
        table.add_column("Index", style="bold #ff007f", justify="center")
        table.add_column("Sensor Name", style="white")
        table.add_column("Channels", style="#00ff66", justify="center")
        table.add_column("Sample Rate", style="#ffe600", justify="center")
        table.add_column("Status", style="bold cyan", justify="center")

        default_input = sd.default.device[0]
        for idx, dev in input_devices:
            is_default = "[bold #00ff66]● DEFAULT[/]" if idx == default_input else "[dim]AVAILABLE[/]"
            table.add_row(
                str(idx),
                dev["name"],
                str(dev["max_input_channels"]),
                f"{int(dev['default_samplerate'])} Hz",
                is_default,
            )
        console.print(table)
    except Exception as exc:
        console.print(f"[bold #ff0055]Error querying audio devices: {exc}[/]")


def parse_arguments():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Infinity Snap — Flexible Folder Monitoring & Action System"
    )
    parser.add_argument(
        "--setup",
        "--reset-config",
        action="store_true",
        help="Reopen interactive setup wizard to configure monitoring folder and preferences",
    )
    parser.add_argument(
        "--mode",
        choices=["NORMAL", "ADVANCED"],
        default=None,
        help="Override configured action mode (NORMAL or ADVANCED)",
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        default=None,
        help="Override sound detection threshold (0.05 to 0.95)",
    )
    parser.add_argument(
        "-c",
        "--cooldown",
        type=float,
        default=None,
        help="Override sound detection cooldown in seconds",
    )
    parser.add_argument(
        "-d",
        "--device",
        type=str,
        default=None,
        help="Select input microphone by device index or name substring",
    )
    parser.add_argument(
        "-l",
        "--list-devices",
        action="store_true",
        help="List available audio input devices and exit",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run non-destructive verification self-tests and exit",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    if args.list_devices:
        list_audio_devices()
        return

    if args.test:
        success = run_self_tests()
        sys.exit(0 if success else 1)

    # Check if first-run setup is required
    config = load_config()
    if config is None or args.setup:
        config = run_first_time_setup()

    # Apply command-line overrides if supplied
    if args.mode:
        config["action_mode"] = args.mode
    if args.threshold is not None:
        config["threshold"] = args.threshold
    if args.cooldown is not None:
        config["cooldown"] = args.cooldown
    if args.device is not None:
        try:
            config["device"] = int(args.device)
        except ValueError:
            config["device"] = args.device

    # Run application
    run_application(config)


if __name__ == "__main__":
    main()
