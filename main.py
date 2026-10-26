"""
Infinity Snap — Plug-and-Play Multi-Gesture Cyberpunk Desktop Automator
=======================================================================
Central connection hub connecting:
  - Multi-Gesture Audio Engine (1 snap = Panic Stealth Mode, 2 snaps = Instant Folder Purge)
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
from core.hotkey_manager import GlobalHotkeyManager
from core.air_desktop import AirDesktopController
from core.hud import build_hud_panel, print_audio_devices
from core.notification_manager import NotificationManager
from core.plugin_engine import PluginEngine
from core.tray_manager import TrayManager

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
    parser.add_argument(
        "--air-desktop",
        action="store_true",
        help="Run Apple Vision Pro spatial air mouse alongside acoustic snap surveillance",
    )
    parser.add_argument(
        "--cam-preview",
        action="store_true",
        help="Open Cyberpunk camera preview HUD window for air desktop controller",
    )
    parser.add_argument(
        "--cam-index",
        type=int,
        default=0,
        help="Select webcam device index (default: 0)",
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
    project_root = Path(__file__).resolve().parent

    # Operational state
    is_armed = True
    should_exit = False
    last_event = "System initialized and armed"

    # Air Desktop Spatial Tracking configuration
    enable_air_desktop = args.air_desktop or config.get("air_desktop", False)
    enable_preview = args.cam_preview or config.get("camera_preview", False)
    cam_idx = args.cam_index if args.cam_index is not None else int(config.get("camera_device", 0))

    # Initialize modular subsystems
    plugin_engine = PluginEngine(project_root)
    notification_manager = NotificationManager("Infinity Snap")
    fs_monitor = ContinuousFolderMonitor(monitor_dir)

    # Pure acoustic action router (100% separate from vision/air gestures)
    action_router = ActionRouter(
        config,
        plugin_engine=plugin_engine,
        notification_manager=notification_manager,
    )

    air_controller: Optional[AirDesktopController] = None
    if enable_air_desktop:
        try:
            air_controller = AirDesktopController(
                camera_index=cam_idx,
                enable_preview=enable_preview,
            )
        except Exception:
            air_controller = None

    def on_gesture_intercepted(count: int, peak: float, thresh: float):
        nonlocal last_event
        tray_manager.trigger_flash("ARMED" if is_armed else "PAUSED")
        result_msg = action_router.execute_gesture(count, peak, thresh)
        last_event = result_msg
        fs_monitor.reconcile()

    def toggle_arm_state():
        nonlocal is_armed, last_event
        is_armed = not is_armed
        audio_engine.set_armed(is_armed)
        if is_armed:
            tray_manager.set_state("ARMED")
            notification_manager.send_toast(
                "⚡ SENSOR ARMED",
                "Surveillance engaged. Listening for acoustic transients.",
            )
            last_event = "Sensor re-armed (Ctrl+Alt+S / Tray)"
        else:
            tray_manager.set_state("PAUSED")
            notification_manager.send_toast(
                "⚡ SENSOR MUTED (PAUSED)",
                "Microphone listening paused [Ctrl+Alt+S to resume].",
            )
            last_event = "Sensor muted/paused (Standby mode)"

    def toggle_air_desktop():
        nonlocal air_controller, last_event
        if air_controller and air_controller._running:
            air_controller.stop()
            air_controller = None
            notification_manager.send_toast("⚡ AIR DESKTOP OFF", "Spatial air mouse disengaged.")
            last_event = "Air Desktop Controller disengaged"
        else:
            try:
                air_controller = AirDesktopController(
                    camera_index=cam_idx,
                    enable_preview=enable_preview,
                )
                air_controller.start()
                notification_manager.send_toast("⚡ AIR DESKTOP ON", "Apple Vision Pro air mouse active.")
                last_event = "Air Desktop Controller engaged"
            except Exception as e:
                last_event = f"Air Desktop failed: {e}"

    def trigger_manual_single():
        nonlocal last_event
        tray_manager.trigger_flash("ARMED" if is_armed else "PAUSED")
        result_msg = action_router.handle_single_snap(1.0, threshold)
        last_event = result_msg

    def trigger_manual_double():
        nonlocal last_event
        tray_manager.trigger_flash("ARMED" if is_armed else "PAUSED")
        result_msg = action_router.handle_double_snap(1.0, threshold)
        last_event = result_msg
        fs_monitor.reconcile()

    def request_exit():
        nonlocal should_exit
        should_exit = True

    # Initialize Audio Engine
    audio_engine = MultiGestureAudioEngine(
        threshold=threshold,
        cooldown=cooldown,
        device=device,
        on_gesture_callback=on_gesture_intercepted,
    )

    # Initialize Windows System Tray & Global Hotkeys
    tray_manager = TrayManager(
        monitor_dir=monitor_dir,
        on_toggle_arm=toggle_arm_state,
        on_trigger_single=trigger_manual_single,
        on_trigger_double=trigger_manual_double,
        on_toggle_camera=toggle_air_desktop,
        on_exit=request_exit,
    )
    hotkey_manager = GlobalHotkeyManager(on_toggle=toggle_arm_state)

    # Start hardware listening and background threads
    fs_monitor.start()
    hotkey_manager.start()
    tray_manager.start()
    if air_controller:
        try:
            air_controller.start()
        except Exception:
            air_controller = None

    try:
        audio_engine.start()
    except Exception as err:
        console.print(f"\n[bold #ff0055][AUDIO ERROR][/] Unable to start audio stream: {err}")
        console.print("[dim]Check microphone access in Windows Privacy Settings.[/]\n")
        if air_controller:
            air_controller.stop()
        tray_manager.stop()
        hotkey_manager.stop()
        fs_monitor.stop()
        sys.exit(1)

    # Plug-and-play animated Cyberpunk HUD loop
    try:
        if sys.stdout.isatty():
            console.clear()
        with Live(console=console, refresh_per_second=10, transient=False) as live:
            while not should_exit:
                time.sleep(0.08)

                # Fetch real-time telemetry from audio engine, air controller & filesystem watcher
                live_peak, live_rms, live_dbfs, gesture_state = audio_engine.get_telemetry()
                f_count, d_count = fs_monitor.get_counts()

                air_active = bool(air_controller and air_controller._running)
                air_mode = air_controller.current_mode if air_active else "STANDBY"
                air_fps = air_controller.live_fps if air_active else 0.0

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
                    is_armed=is_armed,
                    air_active=air_active,
                    air_mode=air_mode,
                    air_fps=air_fps,
                )
                live.update(panel)

    except KeyboardInterrupt:
        console.print(
            "\n[bold #ff007f]⚡ DISENGAGED[/] [dim]──[/] [dim cyan]Infinity Snap shut down. Audio transducer, camera, and watcher released.[/]\n"
        )
    finally:
        if air_controller:
            air_controller.stop()
        tray_manager.stop()
        hotkey_manager.stop()
        audio_engine.stop()
        fs_monitor.stop()


if __name__ == "__main__":
    main()

