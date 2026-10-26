# Infinity Snap — Neural Multi-Gesture Cyberpunk Desktop Automator

Infinity Snap is an audio-reactive Windows desktop automator and folder monitoring engine. Using real-time microphone transient analysis, it classifies acoustic snap patterns and executes multi-action macros with an animated Cyberpunk terminal HUD.

---

## 1. Project Architecture

`main.py` serves as the central conductor connecting all subsystems:

```text
INFINITY SNAP/
│
├── main.py                     # Central conductor & plug-and-play entry point
├── config.json                 # Auto-generated or user configuration
├── config.example.json         # Example configuration template
├── requirements.txt            # Runtime dependencies (sounddevice, numpy, rich)
├── README.md                   # Complete documentation and operator guide
├── .gitignore                  # Git exclusions
│
├── core/                       # Clean modular architecture
│   ├── __init__.py
│   ├── audio_engine.py         # Multi-gesture acoustic listener, spectral filter & live VU meter
│   ├── action_router.py        # Handlers: 1 Snap (Purge), 2 Snaps (Workspace), 3 Snaps (Panic Mode)
│   ├── fs_monitor.py           # Win32 FindFirstChangeNotificationW folder observer & JIT validator
│   ├── hud.py                  # Cyberpunk HUD renderer (live VU, gesture state, payload stats)
│   └── config_manager.py       # Configuration loader, saver, and first-run setup wizard
│
├── archive/                    # Archived legacy modules and previous test assets
│   ├── test_folder.py
│   ├── mic_analyzer.py
│   ├── diagnostic_events.csv
│   └── test_files/
└── venv/                       # Python virtual environment
```

---

## 2. Multi-Gesture Acoustic Matrix

Infinity Snap accumulates snap transients within an intelligent time window:

| Gesture Pattern | Action Executed | Description |
| :--- | :--- | :--- |
| **1 Snap** | **Instant Folder Purge** | Immediately dispatches all eligible files & subfolders in the target sector to the Windows Recycle Bin using native `SHFileOperationW`. Zero permanent deletion fallback. |
| **2 Snaps in ~1s** | **Launch Workspace Macro** | Launches your primary developer workspace (e.g. VS Code, browser, or custom command configured in `config.json`). |
| **3 Snaps in ~1.5s** | **Panic Stealth Boss Mode** | Instantly minimizes all active desktop windows (`Win + D`) and mutes master audio volume (`VK_VOLUME_MUTE`). |

---

## 3. Cyberpunk HUD & Audio-Reactive VU Meter

The interface is rendered with `rich.live.Live` at 10 FPS, providing an animated visualizer:

```text
┌────────────── ⚡ INFINITY SNAP // NEURAL MULTI-GESTURE HUD ⚡ ──────────────┐
│                                                                             │
│   STATUS                 ::   ● ARMED  SURVEILLANCE ENGAGED ── Continuous   │
│                              monitoring active                              │
│   TARGET SECTOR          ::  C:\Users\...\Desktop\ENDGAME                   │
│   PURGE PROTOCOL         ::  NORMAL ── [Windows Desktop Recycle Bin /       │
│                              100% Recoverable]                              │
│   AUDIO SENSOR           ::  Microphone Array (Intel® Smart Sound)          │
│   SECTOR PAYLOAD         ::  80 Files │ 0 Directories (80 items ready)      │
│   LIVE AUDIO VU          ::  ███████░░░░░░░░░░░░░ -14.2 dBFS │ TRIGGER:     │
│                              0.50                                           │
│   GESTURE MATRIX         ::  1 Snap: Purge │ 2 Snaps: Workspace │ 3         │
│                              Snaps: Panic Lock                              │
│   GESTURE DETECTOR       ::  ● READY ── Listening for transients            │
│   LAST TELEMETRY         ::  System initialized and armed                   │
│                                                                             │
└─ [Ctrl+C] STOP SURVEILLANCE   │   WIN32 SH_ALLOWUNDO: ACTIVE (RECOVERABLE) ─┘
```

---

## 4. Getting Started (Plug and Play)

### Step 1: Activate Virtual Environment
Open PowerShell in the project directory:
```powershell
.\venv\Scripts\Activate.ps1
```

> **PowerShell Execution Policy Note:**  
> If script execution is disabled on your system, run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then re-run `.\venv\Scripts\Activate.ps1`.

### Step 2: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 3: Run (Plug and Play)
```powershell
python main.py
```
*No test modes or confirmation prompts. Launch and it immediately engages surveillance.*

---

## 5. Configuration & Commands

Configuration is loaded from `config.json`:
```json
{
    "monitoring_folder": "C:\\Users\\username\\Desktop\\ENDGAME",
    "action_mode": "NORMAL",
    "threshold": 0.50,
    "cooldown": 1.20,
    "workspace_cmd": "code .",
    "device": null
}
```

### Optional Command-Line Overrides:
```powershell
# Re-open the interactive setup wizard
python main.py --setup

# Override audio threshold sensitivity (0.05 to 0.95)
python main.py -t 0.55

# List all audio input sensors
python main.py -l

# Override gesture cooldown in seconds
python main.py -c 1.5
```

---

## 6. Security & Safety Firewalls

- **Strict Forbidden Paths**: Drive roots (`C:\`), Windows system folders (`C:\Windows`), Program Files, User Profile roots (`C:\Users\<user>`), Desktop/Documents root, and the project folder itself are strictly blocked by boundary firewalls.
- **Symlink / Junction Rejection**: Symbolic links, NTFS junctions, and reparse points are filtered out to prevent path traversal attacks.
- **Recoverable Recycle Bin Purge**: Powered by `ctypes.windll.shell32.SHFileOperationW` with `FO_DELETE` and `FOF_ALLOWUNDO`. No permanent deletion fallback (`os.remove`, `Path.unlink`, `shutil.rmtree`) exists anywhere in the codebase.
