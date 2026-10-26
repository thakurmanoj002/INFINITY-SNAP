"""
Infinity Snap — Filesystem Monitoring & Safety Engine
=====================================================
Windows filesystem observer using native kernel32 FindFirstChangeNotificationW
and safe Win32 SHFileOperationW Recycle Bin integration.
"""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys
import threading
import time
from typing import List, Tuple, Optional

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

console = Console()

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


def get_project_root() -> Path:
    """Returns the canonical root directory of the Infinity Snap project."""
    return Path(__file__).resolve().parent.parent


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

    # 6. Check Project Root and virtual environment
    proj_root = get_project_root().resolve()
    if resolved == proj_root:
        return True, "Project directory itself cannot be selected as a monitoring target."

    try:
        resolved.relative_to(proj_root)
        return True, "Folders inside the project directory cannot be selected as monitoring targets."
    except ValueError:
        pass

    # 7. Check if folder contains virtualenv markers
    if (resolved / "Scripts" / "python.exe").exists() or (resolved / "pyvenv.cfg").exists():
        return True, "A Python virtual environment directory cannot be selected as a monitoring folder."

    return False, ""


def validate_monitoring_folder(path_input: str) -> Tuple[Optional[Path], str]:
    """Validates the operator's input monitoring folder against safety boundaries."""
    if not path_input or not path_input.strip():
        return None, "Path cannot be empty."

    candidate = Path(path_input.strip()).expanduser()

    if not candidate.is_absolute():
        try:
            candidate = candidate.resolve()
        except Exception as e:
            return None, f"Could not resolve relative path: {e}"

    if not candidate.exists():
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return None, f"Target directory does not exist and could not be created: {e}"

    if not candidate.is_dir():
        return None, f"Path '{candidate}' is not a directory."

    if not os.access(candidate, os.R_OK | os.W_OK):
        return None, f"Permission denied: Directory '{candidate}' is not readable and writable."

    is_blocked, reason = is_protected_directory(candidate)
    if is_blocked:
        return None, reason

    return candidate, ""


def revalidate_target_item(target: Path, monitor_dir: Path) -> Path:
    """
    Just-In-Time (JIT) safety verification immediately before moving an item to Recycle Bin:
      1. Item is strictly located inside the approved monitoring folder.
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


def recycle_item(target: Path, monitor_dir: Path) -> bool:
    """
    Moves a single validated item (file or directory) to the Windows Recycle Bin
    using native SHFileOperationW.
    
    Guarantees:
      - Uses FO_DELETE with FOF_ALLOWUNDO.
      - NEVER falls back to permanent deletion (no os.remove, no Path.unlink, no rmtree).
      - Checks Windows Shell API return code and fAnyOperationsAborted.
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

    return True


def execute_batch_recycle(items: List[Path], monitor_dir: Path) -> dict:
    """
    Safely processes a batch of validated items into the Windows Recycle Bin
    using native Windows Shell SHFileOperationW silently without disrupting the live HUD.
    """
    summary = {
        "requested": len(items),
        "succeeded": [],
        "failed": [],
        "skipped": [],
    }

    if not items:
        return summary

    for item in items:
        try:
            success = recycle_item(item, monitor_dir)
            if success:
                summary["succeeded"].append(item.name)
            else:
                summary["failed"].append(item.name)
                break
        except Exception:
            summary["failed"].append(item.name)
            break

    attempted = set(summary["succeeded"] + summary["failed"])
    summary["skipped"] = [it.name for it in items if it.name not in attempted]
    return summary


def scan_eligible_items(monitor_dir: Path) -> Tuple[List[Path], List[Path]]:
    """
    Discovers all eligible regular files and regular subdirectories directly
    inside the approved monitoring folder.
    Skips symlinks, junctions, and reparse points.
    """
    eligible_files: List[Path] = []
    eligible_dirs: List[Path] = []

    if not monitor_dir.is_dir():
        return eligible_files, eligible_dirs

    try:
        for entry in os.scandir(monitor_dir):
            try:
                if entry.is_symlink() or os.path.islink(entry.path):
                    continue

                st = entry.stat(follow_symlinks=False)
                if hasattr(st, "st_reparse_tag") and st.st_reparse_tag != 0:
                    continue

                p = Path(entry.path)
                if entry.is_file(follow_symlinks=False):
                    eligible_files.append(p)
                elif entry.is_dir(follow_symlinks=False):
                    eligible_dirs.append(p)
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        pass

    return sorted(eligible_files, key=lambda x: x.name.lower()), sorted(eligible_dirs, key=lambda x: x.name.lower())


class ContinuousFolderMonitor:
    """
    Continuous background filesystem watcher using Win32 FindFirstChangeNotificationW
    with a 1.5-second periodic reconciliation scan.
    """

    def __init__(self, monitor_dir: Path):
        self.monitor_dir = monitor_dir.resolve()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.file_count = 0
        self.dir_count = 0
        self.reconcile()

    def start(self):
        """Starts the background change notification thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watcher_loop,
            name="InfinitySnap-Win32Watcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        """Signals the watcher to stop and waits for the thread to exit."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def reconcile(self):
        """Performs a direct scan of the directory to ensure exact counts."""
        files, dirs = scan_eligible_items(self.monitor_dir)
        with self._lock:
            self.file_count = len(files)
            self.dir_count = len(dirs)

    def get_counts(self) -> Tuple[int, int]:
        """Returns the current (file_count, dir_count)."""
        with self._lock:
            return self.file_count, self.dir_count

    def _watcher_loop(self):
        """Native Windows change-notification loop."""
        if sys.platform != "win32":
            while not self._stop_event.is_set():
                time.sleep(1.5)
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
            False,
            filter_flags,
        )

        if handle == INVALID_HANDLE_VALUE or handle == 0:
            while not self._stop_event.is_set():
                time.sleep(1.5)
                self.reconcile()
            return

        try:
            while not self._stop_event.is_set():
                wait_status = kernel32.WaitForSingleObject(handle, 1500)
                if self._stop_event.is_set():
                    break

                if wait_status == WAIT_OBJECT_0:
                    self.reconcile()
                    if not kernel32.FindNextChangeNotification(handle):
                        break
                elif wait_status == WAIT_TIMEOUT:
                    self.reconcile()
        finally:
            kernel32.FindCloseChangeNotification(handle)
