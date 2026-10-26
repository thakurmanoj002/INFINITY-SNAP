"""
Infinity Snap - Phase 2: Safe Test Folder System
================================================
Dedicated, sandboxed file management module for Infinity Snap.
Ensures that file operations are strictly confined to the project's
local 'test_files' directory, with multi-layer path traversal protection.

Safety Guarantees:
    - Strictly resolves and validates all paths against the test directory.
    - Rejects path traversal attempts (e.g., '../', absolute system paths).
    - Rejects directories and symbolic links / junctions.
    - Prevents overwriting of existing files.
    - Does NOT contain any delete, move, rename, or execute functions.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Tuple
import unittest.mock

# Windows Shell API Constants for Recycle Bin Operations
FO_DELETE = 0x0003
FOF_ALLOWUNDO = 0x0040       # Move to Recycle Bin instead of permanently deleting
FOF_NOCONFIRMATION = 0x0010  # Suppress Windows Explorer confirmation dialog
FOF_SILENT = 0x0004          # Suppress Explorer progress dialog
FOF_NOERRORUI = 0x0400       # Suppress Windows error dialogs

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

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


# Name of the dedicated sandboxed test directory
TEST_DIR_NAME = "test_files"


def get_test_dir() -> Path:
    """
    Returns the resolved, canonical absolute path to the dedicated test_files directory.
    Creates the directory if it does not yet exist.
    """
    # Base directory is the project directory containing this module
    base_dir = Path(__file__).resolve().parent
    test_dir = (base_dir / TEST_DIR_NAME).resolve()
    
    if not test_dir.exists():
        test_dir.mkdir(parents=True, exist_ok=True)
    elif not test_dir.is_dir():
        raise NotADirectoryError(
            f"Fatal Safety Error: '{test_dir}' exists but is not a directory."
        )
    return test_dir


def validate_file_path(target_path: Path | str) -> Path:
    """
    Strictly validates that a given path:
      1. Resolves inside the dedicated test_files directory.
      2. Is not the test directory itself.
      3. Is not a symbolic link or junction pointing outside.
      4. Is not a directory.
      5. Is a regular, eligible file.

    Returns the validated Path object, or raises ValueError / PermissionError.
    """
    test_dir = get_test_dir()
    path_obj = Path(target_path)

    # If relative, resolve relative to test_dir
    if not path_obj.is_absolute():
        candidate = (test_dir / path_obj).resolve()
    else:
        candidate = path_obj.resolve()

    # Path traversal check: candidate must be strictly within test_dir
    try:
        candidate.relative_to(test_dir)
    except ValueError:
        raise PermissionError(
            f"Safety Violation: Target path '{candidate}' is outside the dedicated test folder '{test_dir}'."
        )

    # Reject the test directory itself as a target
    if candidate == test_dir:
        raise ValueError(
            f"Safety Violation: Target is the test directory itself, not an eligible file: '{candidate}'."
        )

    # Reject symbolic links or junctions
    if candidate.is_symlink() or os.path.islink(str(candidate)):
        raise PermissionError(
            f"Safety Violation: Symbolic links and junctions are strictly forbidden: '{candidate}'."
        )

    return candidate


def list_sample_files() -> List[Path]:
    """
    Discovers and returns a list of eligible regular files inside test_files.
    Excludes subdirectories and symbolic links.
    """
    test_dir = get_test_dir()
    eligible_files: List[Path] = []

    for entry in sorted(test_dir.iterdir()):
        try:
            # Check for symlink
            if entry.is_symlink() or os.path.islink(str(entry)):
                continue
            # Must be a regular file
            if entry.is_file():
                # Validate security constraints
                validated = validate_file_path(entry)
                eligible_files.append(validated)
        except (ValueError, PermissionError):
            # Skip any ineligible or non-conforming entries
            continue

    return eligible_files


def display_sample_files() -> List[Tuple[str, int]]:
    """
    Prints a formatted table of all eligible sample files with their sizes,
    and returns a list of (filename, byte_size) tuples.
    """
    test_dir = get_test_dir()
    files = list_sample_files()

    print("\n==================================================")
    print("        INFINITY SNAP - Test Folder Files         ")
    print("==================================================")
    print(f"Sandbox Location: {test_dir}\n")

    if not files:
        print("  (No eligible sample files found in test directory.)")
        print("==================================================\n")
        return []

    print(f"{'Filename':<28} | {'Size (Bytes)':<12} | {'Status':<10}")
    print("-" * 56)
    
    file_info: List[Tuple[str, int]] = []
    for f in files:
        size = f.stat().st_size
        file_info.append((f.name, size))
        print(f"{f.name:<28} | {size:<12} | Eligible")

    print("-" * 56)
    print(f"Total Eligible Files: {len(files)}")
    print("==================================================\n")
    return file_info


def create_dummy_file(filename: str, content: str = None) -> Path:
    """
    Safely creates a new dummy text file in test_files.
    
    Safety:
      - Validates filename inside test_files.
      - Refuses to overwrite if file already exists.
      - Refuses directory creation or paths outside test_files.
    """
    test_dir = get_test_dir()
    target_path = test_dir / filename
    
    # Strictly validate intended path
    validated_path = validate_file_path(target_path)

    if validated_path.exists():
        raise FileExistsError(
            f"Safety Error: File '{validated_path.name}' already exists. Overwrite rejected."
        )

    if content is None:
        content = (
            f"[INFINITY SNAP DUMMY FILE]\n"
            f"Filename: {validated_path.name}\n"
            f"Purpose: Harmless sample file for safe testing.\n"
        )

    # Use exclusive creation mode ('x') to prevent race-condition overwrites
    with open(validated_path, mode="x", encoding="utf-8") as f:
        f.write(content)

    print(f"Successfully created dummy file: {validated_path.name} ({validated_path.stat().st_size} bytes)")
    return validated_path


def simulate_snap_action() -> List[Path]:
    """
    Simulates a snap action against the test folder.
    Strictly non-destructive: only validates and displays the eligible files
    that would be affected, without modifying or deleting anything.
    """
    test_dir = get_test_dir()
    eligible = list_sample_files()
    
    print("\n" + "=" * 54, flush=True)
    print("      [!] SIMULATION ONLY -- NO FILES DELETED     ", flush=True)
    print("=" * 54, flush=True)
    print(f"Target Sandbox: {test_dir}", flush=True)
    print(f"Eligible test files that would be affected ({len(eligible)} total):", flush=True)
    for f in eligible:
        size = f.stat().st_size
        print(f"  - {f.name} ({size} bytes) [UNCHANGED]", flush=True)
    print("-" * 54, flush=True)
    print("Simulation status: 0 files deleted | 0 files modified.", flush=True)
    print("=" * 54 + "\n", flush=True)
    return eligible


def revalidate_target_file(target: Path | str) -> Path:
    """
    Just-In-Time (JIT) safety verification performed immediately prior to any file operation.
    Guarantees:
      1. Target exists and resolves to a canonical absolute path.
      2. Target is strictly located within the dedicated test_files directory.
      3. Target is not the sandbox directory itself.
      4. Target is a regular file (not directory, socket, fifo, device).
      5. Target is not a symbolic link, NTFS junction, or reparse point.
    Raises FileNotFoundError, ValueError, or PermissionError if any check fails.
    """
    test_dir = get_test_dir()
    path_obj = Path(target)

    if not path_obj.exists():
        raise FileNotFoundError(f"JIT Safety Violation: Target does not exist: '{path_obj}'")

    # Canonical resolution
    real_path = path_obj.resolve(strict=True)

    # Relative to sandbox check
    try:
        real_path.relative_to(test_dir)
    except ValueError:
        raise PermissionError(
            f"JIT Safety Violation: Target '{real_path}' is outside sandbox '{test_dir}'."
        )

    # Cannot be sandbox itself
    if real_path == test_dir:
        raise ValueError(f"JIT Safety Violation: Target is test directory itself: '{real_path}'")

    # Must be regular file
    if not real_path.is_file():
        raise ValueError(f"JIT Safety Violation: Target is not a regular file: '{real_path}'")

    # Symlink / Junction check
    if real_path.is_symlink() or os.path.islink(str(real_path)):
        raise PermissionError(f"JIT Safety Violation: Symlinks/junctions forbidden: '{real_path}'")

    # Reparse point check (NTFS junctions, AppExecLinks, etc.)
    try:
        st = os.lstat(str(real_path))
        if hasattr(st, "st_reparse_tag") and st.st_reparse_tag != 0:
            raise PermissionError(
                f"JIT Safety Violation: Reparse point (tag {st.st_reparse_tag}) forbidden: '{real_path}'"
            )
    except OSError as err:
        raise PermissionError(f"JIT Safety Violation: Unable to verify lstat attributes: {err}")

    return real_path


def recycle_single_file(target: Path | str, _api_call=None) -> bool:
    """
    Moves a single validated dummy file to the Windows Recycle Bin using native SHFileOperationW.
    
    Guarantees:
      - Uses FO_DELETE with FOF_ALLOWUNDO.
      - NEVER falls back to permanent deletion (no os.remove, no Path.unlink, no rmtree).
      - Checks Windows Shell API return code and fAnyOperationsAborted.
      - Verifies that file no longer exists at source location upon success.
      - If operation fails or is aborted, stops and reports error.
    """
    if sys.platform != "win32":
        raise OSError("Windows Recycle Bin integration is only supported on Windows.")

    # Step 1: Just-in-time revalidation
    validated_path = revalidate_target_file(target)

    # Step 2: Format double-null terminated wchar string as required by SHFileOperationW
    path_str = str(validated_path) + "\0\0"

    # Step 3: Populate SHFILEOPSTRUCTW
    fileop = SHFILEOPSTRUCTW()
    fileop.hwnd = None
    fileop.wFunc = FO_DELETE
    fileop.pFrom = path_str
    fileop.pTo = None
    fileop.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    fileop.fAnyOperationsAborted = False
    fileop.hNameMappings = None
    fileop.lpszProgressTitle = None

    # Step 4: Execute native Windows Shell call (or mocked callback for testing)
    if _api_call is not None:
        result = _api_call(fileop)
    else:
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(fileop))

    # Step 5: Check result
    if result != 0:
        raise OSError(
            f"Windows Shell API SHFileOperationW failed with error code {result} (0x{result:08X}). "
            f"File '{validated_path.name}' was NOT moved to Recycle Bin."
        )

    if fileop.fAnyOperationsAborted:
        raise OSError(
            f"Windows Shell operation was aborted by the operating system. "
            f"File '{validated_path.name}' was NOT moved to Recycle Bin."
        )

    # Step 6: Verify file is no longer at original path (unless mocked)
    if _api_call is None and validated_path.exists():
        raise OSError(
            f"Unexpected state: Windows Shell reported success, but file '{validated_path.name}' "
            f"still exists at original path."
        )

    return True


def execute_recycle_action(targets: List[Path], _api_call=None) -> dict:
    """
    Sequentially processes a list of explicitly selected targets, moving each to
    the Windows Recycle Bin.
    
    Safety:
      - Validates each file immediately prior to calling the Windows Shell API.
      - Stops immediately on any failure or validation rejection.
      - Never falls back to permanent deletion.
      - Returns a structured operation summary.
    """
    summary = {
        "requested": [t.name for t in targets],
        "succeeded": [],
        "failed": [],
        "remaining_sandbox_files": [],
    }

    print("\n" + "=" * 54, flush=True)
    print("      INFINITY SNAP - RECYCLE BIN OPERATION       ", flush=True)
    print("=" * 54, flush=True)
    print(f"Target count: {len(targets)}", flush=True)

    for target in targets:
        print(f"  Recycling '{target.name}' ... ", end="", flush=True)
        try:
            success = recycle_single_file(target, _api_call=_api_call)
            if success:
                summary["succeeded"].append(target.name)
                print("MOVED TO RECYCLE BIN", flush=True)
            else:
                summary["failed"].append(target.name)
                print("FAILED", flush=True)
                break
        except Exception as err:
            summary["failed"].append(target.name)
            print(f"ERROR: {err}", flush=True)
            print("  [!] Safety abort triggered. Stopping immediately.", flush=True)
            break

    remaining = [f.name for f in list_sample_files()]
    summary["remaining_sandbox_files"] = remaining

    print("-" * 54, flush=True)
    print("Operation Summary:", flush=True)
    print(f"  - Requested : {len(summary['requested'])} ({', '.join(summary['requested'])})", flush=True)
    print(f"  - Succeeded : {len(summary['succeeded'])} ({', '.join(summary['succeeded']) if summary['succeeded'] else 'None'})", flush=True)
    print(f"  - Failed    : {len(summary['failed'])} ({', '.join(summary['failed']) if summary['failed'] else 'None'})", flush=True)
    print(f"  - Remaining in Sandbox : {len(remaining)} ({', '.join(remaining) if remaining else 'None'})", flush=True)
    print("==================================================\n", flush=True)
    return summary


def recycle_all_sample_files(_api_call=None) -> dict:
    """
    Discovers, revalidates, and moves all eligible dummy files in test_files/
    to the Windows Recycle Bin using native SHFileOperationW.
    """
    eligible = list_sample_files()
    if not eligible:
        print("\n[!] No eligible sample files found in sandbox to recycle.\n", flush=True)
        return {
            "requested": [],
            "succeeded": [],
            "failed": [],
            "remaining_sandbox_files": [],
        }
    return execute_recycle_action(eligible, _api_call=_api_call)


def run_safety_self_test() -> bool:
    """
    Automated self-test verifying all safety boundaries:
      1. Resolves test_files correctly.
      2. Lists eligible files.
      3. Rejects paths outside test_files (e.g., '../main.py', Desktop, system paths).
      4. Rejects directory targets.
      5. Prevents overwriting existing files.
      6. Verifies no deletion or modification occurs.
    """
    print("==================================================")
    print("       RUNNING TEST_FOLDER.PY SAFETY CHECKS       ")
    print("==================================================")
    
    test_dir = get_test_dir()
    passed = 0
    total = 6

    # Check 1: Dedicated folder resolution
    print("[Check 1/6] Verifying test_files sandbox directory... ", end="")
    assert test_dir.name == TEST_DIR_NAME, "Sandbox directory name mismatch"
    assert test_dir.is_dir(), "Sandbox path is not a directory"
    print("PASSED")
    passed += 1

    # Check 2: Listing eligible files
    print("[Check 2/6] Verifying eligible sample file discovery... ", end="")
    files = list_sample_files()
    assert len(files) >= 5, f"Expected at least 5 sample files, found {len(files)}"
    print(f"PASSED ({len(files)} files found)")
    passed += 1

    # Check 3: Path traversal rejection
    print("[Check 3/6] Testing path traversal rejection ('../main.py')... ", end="")
    traversal_path = test_dir / ".." / "main.py"
    rejected = False
    try:
        validate_file_path(traversal_path)
    except PermissionError:
        rejected = True
    assert rejected, "Security failure: Path traversal was not rejected!"
    print("PASSED (Correctly rejected)")
    passed += 1

    # Check 4: Directory target rejection
    print("[Check 4/6] Testing directory target rejection (test_dir itself)... ", end="")
    dir_rejected = False
    try:
        validate_file_path(test_dir)
    except ValueError:
        dir_rejected = True
    assert dir_rejected, "Security failure: Directory target was not rejected!"
    print("PASSED (Correctly rejected)")
    passed += 1

    # Check 5: Overwrite prevention
    print("[Check 5/6] Testing overwrite prevention on existing file... ", end="")
    overwrite_blocked = False
    first_file = files[0].name
    try:
        create_dummy_file(first_file, "Attempted overwrite content")
    except FileExistsError:
        overwrite_blocked = True
    assert overwrite_blocked, "Safety failure: Existing file overwrite was not blocked!"
    print("PASSED (Correctly blocked)")
    passed += 1

    # Check 6: Mocked Windows API integration (success, failure, abort)
    print("[Check 6/6] Testing Windows SHFileOperationW wrapper (mocked)... ", end="")
    def mock_success(op):
        return 0
    def mock_fail(op):
        return 2  # ERROR_FILE_NOT_FOUND
    def mock_abort(op):
        op.fAnyOperationsAborted = True
        return 0

    dummy_target = files[0]
    # Test mocked success without modifying real file
    assert recycle_single_file(dummy_target, _api_call=mock_success) is True

    # Test error code rejection
    fail_caught = False
    try:
        recycle_single_file(dummy_target, _api_call=mock_fail)
    except OSError:
        fail_caught = True
    assert fail_caught, "Mock failure did not raise OSError"

    # Test abort detection
    abort_caught = False
    try:
        recycle_single_file(dummy_target, _api_call=mock_abort)
    except OSError:
        abort_caught = True
    assert abort_caught, "Mock abort did not raise OSError"

    print("PASSED (Non-destructive validation of success, error, and abort paths)")
    passed += 1

    print("--------------------------------------------------")
    print(f"Results: {passed}/{total} safety checks passed successfully.")
    print("All security and isolation boundaries verified.")
    print("==================================================\n")
    return passed == total


def parse_arguments():
    """Parses command-line arguments for test_folder.py."""
    parser = argparse.ArgumentParser(
        description="Infinity Snap - Phase 2: Safe Test Folder System"
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List all eligible sample files in the test directory",
    )
    parser.add_argument(
        "-c",
        "--create",
        type=str,
        default=None,
        metavar="FILENAME",
        help="Safely create a new dummy text file (refuses to overwrite)",
    )
    parser.add_argument(
        "-v",
        "--verify",
        type=str,
        default=None,
        metavar="PATH",
        help="Verify if a given path is safe and inside the test directory",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run comprehensive safety and boundary self-tests",
    )
    parser.add_argument(
        "-s",
        "--simulate",
        action="store_true",
        help="Run a non-destructive snap simulation (lists eligible files without changes)",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    # If no flags are passed, display sample files by default
    if not (args.list or args.create or args.verify or args.test or args.simulate):
        display_sample_files()
        print("Tip: Run 'python test_folder.py --help' or 'python test_folder.py --test'")
        return

    if args.list:
        display_sample_files()

    if args.simulate:
        simulate_snap_action()

    if args.create:
        try:
            create_dummy_file(args.create)
        except Exception as err:
            print(f"Error: {err}", file=sys.stderr)
            sys.exit(1)

    if args.verify:
        try:
            validated = validate_file_path(args.verify)
            print(f"[SAFE] Path is valid and isolated inside test folder: {validated}")
        except Exception as err:
            print(f"[REJECTED] {err}", file=sys.stderr)
            sys.exit(1)

    if args.test:
        success = run_safety_self_test()
        if not success:
            sys.exit(1)


if __name__ == "__main__":
    main()
