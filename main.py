"""
Infinity Snap — Plug-and-Play Multi-Gesture Cyberpunk Desktop Automator
=======================================================================
Central connection hub connecting:
  - Multi-Gesture Audio Engine (1 snap = Purge, 2 snaps = Workspace, 3 snaps = Panic)
  - Audio-Reactive Cyberpunk HUD with Live Animated VU Meter
  - Win32 FindFirstChangeNotificationW Continuous Directory Watcher
  - Native Windows Shell SHFileOperationW Recycle Bin Purge Engine
"""

import argparse
from pathlib import Path
import sys
import time

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.live import Live

from core.action_router import ActionRouter
from core.audio_engine import MultiGestureAudioEngine
from core.config_manager import load_config, run_first_time_setup
from core.fs_monitor import ContinuousFolderMonitor, validate_monitoring_folder
from core.hud import build_hud_panel, print_audio_devices

console = Console()


def parse_arguments():
    """Parses optional command-line flags."""
    parser = argparse.ArgumentParser(
        description="Infinity Snap — Neural Multi-Gesture Cyberpunk Desktop Automator"
    )
    parser.add_argument(
        "--setup",
        "--reset-config",
        action="store_true",
        help="Reopen interactive setup wizard to configure monitoring folder and preferences",
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
        help="Override gesture detection cooldown in seconds",
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
    return parser.parse_args()


def main():
    """Plug-and-play entry point orchestrating all Infinity Snap subsystems."""
    args = parse_arguments()

    if args.list_devices:
        print_audio_devices()
        return

    # Load or initialize configuration
    config = load_config()
    if config is None or args.setup:
        config = run_first_time_setup()

    # Apply command-line overrides
    if args.threshold is not None:
        config["threshold"] = args.threshold
    if args.cooldown is not None:
        config["cooldown"] = args.cooldown
    if args.device is not None:
        try:
            config["device"] = int(args.device)
        except ValueError:
            config["device"] = args.device

    # Validate target directory
    monitor_dir_path = Path(config["monitoring_folder"]).resolve()
    validated_folder, err = validate_monitoring_folder(str(monitor_dir_path))
    if validated_folder is None:
        console.print(f"\n[bold #ff0055][FATAL CONFIG ERROR][/] Configured folder is invalid: {err}")
        console.print("[dim]Please run 'python main.py --setup' to reconfigure.[/]\n")
        sys.exit(1)

    monitor_dir = validated_folder
    action_mode = config.get("action_mode", "NORMAL")
    threshold = float(config.get("threshold", 0.50))
    cooldown = float(config.get("cooldown", 1.20))
    device = config.get("device")

    # Initialize subsystems
    action_router = ActionRouter(config)
    fs_monitor = ContinuousFolderMonitor(monitor_dir)

    # State tracking
    last_event = "System initialized and armed"

    def on_gesture_intercepted(count: int, peak: float, thresh: float):
        nonlocal last_event
        # Dispatch action based on snap count
        result_msg = action_router.execute_gesture(count, peak, thresh)
        last_event = result_msg
        # Reconcile directory count immediately after action
        fs_monitor.reconcile()

    # Initialize Multi-Gesture Audio Engine
    audio_engine = MultiGestureAudioEngine(
        threshold=threshold,
        cooldown=cooldown,
        device=device,
        on_gesture_callback=on_gesture_intercepted,
    )

    # Start hardware listening and filesystem observation
    fs_monitor.start()
    try:
        audio_engine.start()
    except Exception as err:
        console.print(f"\n[bold #ff0055][AUDIO ERROR][/] Unable to start audio stream: {err}")
        console.print("[dim]Check microphone access in Windows Privacy Settings.[/]\n")
        fs_monitor.stop()
        sys.exit(1)

    # Plug-and-play animated Cyberpunk HUD loop
    try:
        with Live(console=console, refresh_per_second=10, transient=False) as live:
            while True:
                time.sleep(0.08)

                # Fetch real-time telemetry from audio engine & filesystem watcher
                live_peak, live_rms, live_dbfs, gesture_state = audio_engine.get_telemetry()
                f_count, d_count = fs_monitor.get_counts()

                # Build updated Cyberpunk HUD frame
                panel = build_hud_panel(
                    monitor_dir=monitor_dir,
                    action_mode=action_mode,
                    device_name=audio_engine.device_name,
                    threshold=threshold,
                    file_count=f_count,
                    dir_count=d_count,
                    live_peak=live_peak,
                    live_dbfs=live_dbfs,
                    gesture_state=gesture_state,
                    last_event=last_event,
                    is_armed=True,
                )
                live.update(panel)

    except KeyboardInterrupt:
        console.print(
            "\n[bold #ff007f]⚡ DISENGAGED[/] [dim]──[/] [dim cyan]Infinity Snap shut down. Audio transducer and folder watcher released.[/]\n"
        )
    finally:
        audio_engine.stop()
        fs_monitor.stop()


if __name__ == "__main__":
    main()
