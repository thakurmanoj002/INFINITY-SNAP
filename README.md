# Infinity Snap — Flexible Folder Monitoring & Snap Action System

Infinity Snap is a Python-based audio transient analysis and Windows filesystem monitoring utility. It pairs continuous microphone listening with real-time directory observation to perform safe, controlled batch actions upon detecting sharp acoustic transients (such as finger snaps or sharp claps).

---

## 1. Project Overview & Active Architecture

The active project root contains only essential files:

```text
INFINITY SNAP/
│
├── main.py            # Primary application: Setup wizard, continuous watcher, audio detector & dashboard
├── requirements.txt   # Runtime dependencies (sounddevice, numpy, rich)
├── README.md          # Complete documentation and operator guide
│
├── config.json        # Auto-generated configuration file (created during setup)
│
├── archive/           # Archived legacy modules and previous phase assets
│   ├── test_folder.py
│   ├── mic_analyzer.py
│   ├── diagnostic_events.csv
│   └── test_files/
└── venv/              # Python virtual environment
```

---

## 2. Key Features

- **Cyberpunk Terminal HUD**: Powered by the `rich` Python library with neon color schemes (matrix green, electric cyan, hot magenta, cyber yellow), high-visibility panels, real-time transient sensitivity bar, and live status pills.
- **Continuous Windows Filesystem Monitoring**: Uses native Win32 API `FindFirstChangeNotificationW` (via `kernel32.dll`) combined with a 1.5-second periodic reconciliation scan to track newly created, renamed, or deleted files and directories in real time without polling loops or excessive CPU usage.
- **First-Run Interactive Setup Wizard**: Detects missing configuration on launch and guides the operator through folder selection, safety validation, action mode selection, and audio calibration.
- **Strict Protected Folder Boundaries**: Blocks hazardous directories (drive roots, Windows system directories, Program Files, user profile roots, root Desktop/Documents/Downloads, the project directory, and `venv`).
- **Instant Snap Deletion (Zero Confirmation)**: Files and subdirectories are purged directly to the Windows Recycle Bin on transient detection without interrupting the operator.
- **Seamless Continuous Listening**: Runs indefinitely after each snap event, updating telemetry counts automatically without requiring manual re-arming.
- **Native Windows Recycle Bin Integration**: Powered by `ctypes.windll.shell32.SHFileOperationW` with `FO_DELETE` and `FOF_ALLOWUNDO`. **Never uses permanent deletion (`os.remove`, `Path.unlink`, `shutil.rmtree`)**; all items remain fully recoverable in the Windows Recycle Bin.
- **JIT Symlink & Junction Protection**: Revalidates every target immediately before execution, refusing to follow symbolic links, NTFS junctions, or reparse points.

---

## 3. Getting Started (Windows PowerShell)

### Step 1: Activate Virtual Environment
Open Windows PowerShell in the project directory:
```powershell
.\venv\Scripts\Activate.ps1
```

> **PowerShell Execution Policy Note:**  
> If script execution is disabled, run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then re-run `.\venv\Scripts\Activate.ps1`.

### Step 2: Install Dependencies
```powershell
pip install -r requirements.txt
```

---

## 4. First-Run Setup & Configuration

When you run `python main.py` for the first time (or when `config.json` is missing), the interactive setup wizard will launch:

```powershell
python main.py
```

### Setup Questions:

1. **Monitoring Folder**: Enter an absolute path to an accessible folder (e.g., `C:\Users\username\Desktop\SnapTestFolder`).
   - If the directory does not exist, the setup wizard offers to create it.
   - The path is validated against strict protection rules.
2. **Action Mode**:
   - `[1] NORMAL (Default)`: Moves eligible target items to the Windows Recycle Bin with full recovery capability.
   - `[2] ADVANCED`: Displays explicit warnings regarding the dangers of permanent deletion; however, it executes using the same safe, recoverable Windows Recycle Bin operation to protect user data.
3. **Sound Detection Threshold**: Set a peak amplitude threshold from `0.05` to `0.95` (default: `0.55`).

### Reopening or Resetting Configuration
To rerun the setup wizard at any time and reconfigure your settings:
```powershell
python main.py --setup
```
*(or `python main.py --reset-config`)*

---

## 5. Safety Boundaries & Forbidden Directories

To prevent accidental data loss or operating system corruption, `is_protected_directory()` enforces strict path verification. The following locations are **explicitly blocked**:

| Forbidden Location | Reason / Protection Scope |
| :--- | :--- |
| **Drive Roots** (`C:\`, `D:\`, etc.) | Prevents targeting entire system or storage volumes. |
| **System Directories** (`C:\Windows`, `System32`) | Protects core Windows OS files and drivers. |
| **Program Files** (`Program Files`, `Program Files (x86)`) | Prevents tampering with installed software binaries. |
| **User Profile Root** (`C:\Users\<user>`) | Protects the user's primary identity directory. |
| **Root Desktop, Documents, Downloads** | Prevents selecting general user personal folders. |
| **Project Root & Virtual Environment** | Prevents deleting the `INFINITY SNAP` codebase or `venv`. |

*Allowed:* Any dedicated, user-created subfolder (such as `C:\Users\<user>\Desktop\SnapSandbox` or `D:\Scratch\SnapDir`).

---

## 6. Dashboard & Controls

Once configured, launching `python main.py` opens the live Cyberpunk HUD:

```text
┌───────────── ⚡ INFINITY SNAP // NEURAL AUDIO TRANSIENT HUD ⚡ ─────────────┐
│                                                                             │
│   STATUS                 ::   ● ARMED  SURVEILLANCE ENGAGED ── Listening    │
│                              for snap                                       │
│   TARGET SECTOR          ::  C:\Users\...\Desktop\ENDGAME                   │
│   PURGE PROTOCOL         ::  NORMAL ── [Windows Desktop Recycle Bin /       │
│                              100% Recoverable]                              │
│   AUDIO SENSOR           ::  Microphone Array (Intel® Smart Sound │         │
│                              THRESHOLD: 0.50                                │
│   PAYLOAD OBJECTS        ::  80 Files │ 0 Directories (80 items ready)      │
│   LAST TELEMETRY         ::  System initialized and armed                   │
│   TRIGGER SENSITIVITY    ::  ██████████░░░░░░░░░░ 0.50                      │
│                                                                             │
└── [Ctrl+C] STOP MONITORING   │   WIN32 SH_ALLOWUNDO: ACTIVE (RECOVERABLE) ──┘
```

### Controls:
- **`Ctrl+C`**: Cleanly disengages and exits the application, stopping audio streams and directory watchers.

---

## 7. Snap Action Workflow (Continuous Mode)

1. **Sound Spike Detected**: When the microphone registers an amplitude exceeding the threshold:
   - Evaluates against the cooldown interval (e.g., 1.0s) to prevent double-triggering on reverberations.
2. **JIT Scan & Revalidation**: The system re-scans the monitored directory, filtering out junctions and symlinks, and identifies the exact candidate items.
3. **Instant Execution (Zero Confirmation)**: Selected files and directories are transferred immediately to the Windows Recycle Bin using native `SHFileOperationW`.
4. **Continuous Operation**: A summary of succeeded, failed, and skipped items is printed. The system updates the live dashboard count and **immediately continues listening** for subsequent snaps without pausing or requiring manual re-arming.

---

## 8. CLI Command-Line Reference

You can override configuration settings directly from the terminal without editing `config.json`:

```powershell
# Run the interactive setup wizard
python main.py --setup

# Override action mode for a single run
python main.py --mode ADVANCED

# Override sound detection threshold (0.05 to 0.95)
python main.py -t 0.60

# Override detection cooldown in seconds
python main.py -c 2.0

# List all available microphone input devices
python main.py --list-devices

# Select a specific microphone by ID or substring
python main.py -d "Microphone"

# Run non-destructive self-tests
python main.py --test
```

---

## 9. Non-Destructive Self-Test Suite

To verify that boundary safety, configuration loading, Windows Shell API binding, and directory scanning are operating correctly without moving or deleting any user files:

```powershell
python main.py --test
```

**Output:**
```text
============================================================
       RUNNING NON-DESTRUCTIVE VERIFICATION SUITE       
========================================================
[Check 1/4] Boundary validation rules... PASSED
[Check 2/4] Configuration load/save schema... PASSED
[Check 3/4] Native Windows Shell API wrapper with mocks... PASSED
[Check 4/4] Folder scanner logic... PASSED
--------------------------------------------------------
All 4 verification checks passed successfully.
========================================================
```

---

## 10. Archived Components

Legacy phase scripts and earlier testing files have been safely archived in the `archive/` folder:
- `archive/test_folder.py`: Phase 2 and Phase 4 sandboxed test-folder manager.
- `archive/mic_analyzer.py`: Standalone live microphone acoustic diagnostic utility and CSV logger.
- `archive/test_files/`: Sample dummy text files (`sample_01.txt` through `sample_05.txt`).
- `archive/diagnostic_events.csv`: Acoustic transient calibration logs.
