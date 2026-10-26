"""
Infinity Snap - Phase 1.5: Live Microphone Diagnostic Analyzer
==============================================================
Standalone diagnostic tool designed to analyze acoustic characteristics
(Peak, RMS, dBFS, Crest Factor, and Noise Floor) of transient sounds
such as finger snaps, hand claps, and ambient background noise.

Architecture Note:
    This tool is standalone and independent. It does NOT modify or import
    main.py, nor does it perform any destructive actions or file deletions.

Dependencies:
    - sounddevice
    - numpy
    - Python standard libraries: csv, time, datetime, sys, argparse, queue
"""

import argparse
import csv
import datetime
import os
import queue
import sys
import threading
import time
import numpy as np
import sounddevice as sd


# Audio & Analysis Defaults
DEFAULT_SAMPLE_RATE = 44100   # 44.1 kHz standard audio rate
DEFAULT_BLOCK_SIZE = 1024     # ~23.2 ms chunk
DEFAULT_TRANSIENT_THRESHOLD = 0.35  # Peak amplitude to flag a transient (0.0 to 1.0)
DEFAULT_COOLDOWN = 0.8        # Seconds to wait between transient events
DEFAULT_CSV_FILE = "diagnostic_events.csv"
DBFS_FLOOR = -96.0            # Safe noise floor for 16-bit dynamic range / log calculation


def list_audio_devices():
    """Lists all available audio input devices on the system."""
    try:
        devices = sd.query_devices()
        input_devices = [
            (i, d) for i, d in enumerate(devices) if d.get("max_input_channels", 0) > 0
        ]

        if not input_devices:
            print("No audio input devices (microphones) were found.")
            return

        print("\nAvailable Audio Input Devices:")
        print("--------------------------------------------------")
        default_input = sd.default.device[0]
        for idx, dev in input_devices:
            is_default = " (System Default)" if idx == default_input else ""
            print(f"  [{idx}] {dev['name']}{is_default}")
        print("--------------------------------------------------\n")
    except Exception as exc:
        print(f"Error querying audio devices: {exc}")


def print_troubleshooting_tips():
    """Displays troubleshooting tips for Windows microphone access."""
    print("\n--- Troubleshooting Tips for Windows ---")
    print("1. Check Windows Privacy Settings:")
    print("   Open Settings -> Privacy & Security -> Microphone.")
    print("   Make sure 'Microphone access' is ON.")
    print("   Make sure 'Let desktop apps access your microphone' is ON.")
    print("2. Check Microphone Connection:")
    print("   Ensure your microphone is plugged in, unmuted, and active.")
    print("3. List Available Devices:")
    print("   Run: python mic_analyzer.py --list-devices")
    print("   Select a device with: python mic_analyzer.py --device <ID>")
    print("----------------------------------------\n")


def calculate_dbfs(rms: float) -> float:
    """
    Calculates dBFS (Decibels relative to Full Scale) from normalized RMS amplitude.
    
    Note on Accuracy:
        dBFS is a digital signal measurement where 0.0 dBFS represents maximum unclipped
        digital amplitude. It is NOT calibrated physical sound pressure (dB SPL).
    """
    if rms <= 1e-5:
        return DBFS_FLOOR
    dbfs = 20.0 * np.log10(rms)
    return max(float(dbfs), DBFS_FLOOR)


class DiagnosticSession:
    """Manages audio streaming, live metrics, and event logging."""

    def __init__(
        self,
        threshold: float,
        cooldown: float,
        device=None,
        output_file: str = DEFAULT_CSV_FILE,
        session_label: str = None,
        interactive: bool = False,
    ):
        self.threshold = threshold
        self.cooldown = cooldown
        self.device = device
        self.output_file = output_file
        self.session_label = session_label
        self.interactive = interactive

        # Running noise floor estimate (exponential moving average of RMS)
        self.noise_floor_rms = 0.01
        self.alpha_noise = 0.05  # Smooth tracking for background noise

        # Transient timing
        self.last_transient_time = 0.0

        # Event storage
        self.recorded_events = []
        self.init_csv()

        # Thread communication for interactive labeling
        self.event_queue = queue.Queue()
        self.running = True

    def init_csv(self):
        """Initializes the CSV output file with standard headers if it does not exist."""
        file_exists = os.path.isfile(self.output_file)
        if not file_exists:
            with open(self.output_file, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "label",
                    "peak_amplitude",
                    "rms_amplitude",
                    "dbfs",
                    "noise_floor_rms",
                    "crest_factor",
                    "peak_to_noise_ratio",
                ])

    def log_event_to_csv(self, event: dict):
        """Appends a single diagnostic event to the CSV log."""
        try:
            with open(self.output_file, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    event["timestamp"],
                    event["label"],
                    f"{event['peak']:.4f}",
                    f"{event['rms']:.4f}",
                    f"{event['dbfs']:.2f}",
                    f"{event['noise_floor']:.4f}",
                    f"{event['crest_factor']:.2f}",
                    f"{event['peak_to_noise_ratio']:.2f}",
                ])
            self.recorded_events.append(event)
        except Exception as err:
            print(f"\n[Warning] Failed to write event to CSV: {err}", flush=True)

    def prompt_user_for_label(self, event: dict) -> str:
        """Prompts user to classify the captured transient event."""
        print(f"\n>>> TRANSIENT DETECTED at {event['timestamp'].split('T')[1]} <<<", flush=True)
        print(f"    Peak: {event['peak']:.3f} | RMS: {event['rms']:.3f} | dBFS: {event['dbfs']:.1f} dBFS", flush=True)
        print(f"    Crest Factor: {event['crest_factor']:.2f} | Noise Floor: {event['noise_floor']:.4f}", flush=True)
        print("    Classify sound -> [s] SNAP  |  [c] CLAP  |  [n] NOISE  |  [Enter] Skip: ", end="", flush=True)
        
        try:
            choice = input().strip().lower()
            if choice == "s":
                return "SNAP"
            elif choice == "c":
                return "CLAP"
            elif choice == "n":
                return "NOISE"
            elif choice:
                # Custom label entered by user
                return choice.upper()
            else:
                return "SKIPPED"
        except (EOFError, KeyboardInterrupt):
            return "SKIPPED"

    def run(self):
        """Starts real-time monitoring and event collection."""
        print("==================================================", flush=True)
        print("        INFINITY SNAP - Microphone Analyzer       ", flush=True)
        print("==================================================", flush=True)
        print("Audio Measurement & Diagnostic Tool:")
        print(f"  - Peak Threshold      : {self.threshold:.2f} (0.0 to 1.0)")
        print(f"  - Cooldown            : {self.cooldown:.2f} seconds")
        print(f"  - CSV Output File     : {self.output_file}")
        if self.session_label:
            print(f"  - Session Auto-Label  : {self.session_label}")
        elif self.interactive:
            print("  - Mode                : Interactive (prompt after each transient)")
        else:
            print("  - Mode                : Monitor & Auto-Log (label: UNCLASSIFIED)")

        try:
            device_info = sd.query_devices(device=self.device, kind="input")
            print(f"  - Selected Device     : {device_info['name']}", flush=True)
        except Exception as err:
            print(f"\n[ERROR] Device lookup error: {err}", flush=True)
            print_troubleshooting_tips()
            sys.exit(1)

        print("--------------------------------------------------", flush=True)
        print("Starting live monitor. Press Ctrl+C at any time to exit.\n", flush=True)

        last_display_time = 0.0
        display_interval = 0.12  # Refresh live terminal monitor ~8 times per second

        try:
            with sd.InputStream(
                device=self.device,
                channels=1,
                samplerate=DEFAULT_SAMPLE_RATE,
                blocksize=DEFAULT_BLOCK_SIZE,
                dtype="float32",
            ) as stream:
                while self.running:
                    # Read incoming audio chunk
                    audio_data, overflowed = stream.read(DEFAULT_BLOCK_SIZE)
                    current_time = time.time()

                    # Compute fundamental metrics
                    peak = float(np.max(np.abs(audio_data)))
                    rms = float(np.sqrt(np.mean(audio_data ** 2)))
                    dbfs = calculate_dbfs(rms)
                    crest_factor = float(peak / (rms + 1e-6))

                    # Update background noise floor when signal is quiet
                    if peak < self.threshold:
                        self.noise_floor_rms = (
                            (1.0 - self.alpha_noise) * self.noise_floor_rms
                            + self.alpha_noise * rms
                        )

                    peak_to_noise = float(peak / (self.noise_floor_rms + 1e-6))
                    is_transient = peak >= self.threshold

                    # Check for transient event trigger
                    if is_transient and (current_time - self.last_transient_time) >= self.cooldown:
                        self.last_transient_time = current_time
                        event = {
                            "timestamp": datetime.datetime.now().isoformat(timespec="milliseconds"),
                            "peak": peak,
                            "rms": rms,
                            "dbfs": dbfs,
                            "noise_floor": self.noise_floor_rms,
                            "crest_factor": crest_factor,
                            "peak_to_noise_ratio": peak_to_noise,
                            "label": self.session_label or "UNCLASSIFIED",
                        }

                        if self.interactive:
                            # Clear current live meter line
                            sys.stdout.write("\r" + " " * 78 + "\r")
                            sys.stdout.flush()
                            label = self.prompt_user_for_label(event)
                            if label != "SKIPPED":
                                event["label"] = label
                                self.log_event_to_csv(event)
                                print(f"    -> Saved as [{label}] to {self.output_file}\n", flush=True)
                            else:
                                print("    -> Event skipped (not saved).\n", flush=True)
                        else:
                            self.log_event_to_csv(event)
                            # Flash transient notice in terminal
                            indicator = f"[!] TRANSIENT (Peak: {peak:.2f}, RMS: {rms:.3f}, Crest: {crest_factor:.1f})"
                            sys.stdout.write(f"\n{indicator} -> Logged as [{event['label']}]\n")
                            sys.stdout.flush()

                    # Update live terminal line periodically (smooth display without flicker)
                    if (current_time - last_display_time) >= display_interval:
                        last_display_time = current_time
                        # Mini visual volume bar (20 chars)
                        bar_len = min(20, int(peak * 20))
                        meter_bar = "#" * bar_len + "-" * (20 - bar_len)
                        status_flag = "SPIKE" if is_transient else "NORM "

                        line = (
                            f"\r[{meter_bar}] Peak:{peak:.2f} | RMS:{rms:.3f} | "
                            f"{dbfs:6.1f}dBFS | Noise:{self.noise_floor_rms:.3f} | "
                            f"Crest:{crest_factor:4.1f} | {status_flag}"
                        )
                        sys.stdout.write(line)
                        sys.stdout.flush()

        except KeyboardInterrupt:
            print("\n\nStopping Microphone Analyzer. Closing audio stream...", flush=True)
        except sd.PortAudioError as err:
            print(f"\n[AUDIO ERROR] Audio stream encountered an error: {err}", flush=True)
            print_troubleshooting_tips()
            sys.exit(1)
        except Exception as err:
            print(f"\n[UNEXPECTED ERROR] {err}", flush=True)
            sys.exit(1)
        finally:
            self.print_summary()

    def print_summary(self):
        """Displays a diagnostic summary of the session."""
        print("\n==================================================", flush=True)
        print("              DIAGNOSTIC SESSION SUMMARY          ", flush=True)
        print("==================================================", flush=True)
        print(f"Total events recorded in this session: {len(self.recorded_events)}")
        if self.recorded_events:
            print(f"Log saved to: {os.path.abspath(self.output_file)}\n")
            print("Summary by label:")
            labels = set(e["label"] for e in self.recorded_events)
            for lbl in sorted(labels):
                matching = [e for e in self.recorded_events if e["label"] == lbl]
                avg_peak = np.mean([e["peak"] for e in matching])
                avg_rms = np.mean([e["rms"] for e in matching])
                avg_crest = np.mean([e["crest_factor"] for e in matching])
                avg_dbfs = np.mean([e["dbfs"] for e in matching])
                print(f"  - [{lbl}] (Count: {len(matching)}):")
                print(f"      Avg Peak        : {avg_peak:.3f}")
                print(f"      Avg RMS         : {avg_rms:.3f}")
                print(f"      Avg Crest Factor: {avg_crest:.2f} (Peak / RMS)")
                print(f"      Avg dBFS        : {avg_dbfs:.1f} dBFS")
        else:
            print("No transient events were logged to CSV.")
        print("==================================================\n", flush=True)


def parse_arguments():
    """Parses command-line arguments for the diagnostic tool."""
    parser = argparse.ArgumentParser(
        description="Infinity Snap - Phase 1.5: Live Microphone Diagnostic Analyzer"
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        default=DEFAULT_TRANSIENT_THRESHOLD,
        help=f"Transient trigger threshold between 0.0 and 1.0 (default: {DEFAULT_TRANSIENT_THRESHOLD})",
    )
    parser.add_argument(
        "-c",
        "--cooldown",
        type=float,
        default=DEFAULT_COOLDOWN,
        help=f"Cooldown time in seconds between transient captures (default: {DEFAULT_COOLDOWN}s)",
    )
    parser.add_argument(
        "-d",
        "--device",
        type=str,
        default=None,
        help="Input device index (e.g., 1) or name substring (default: system default)",
    )
    parser.add_argument(
        "-l",
        "--list-devices",
        action="store_true",
        help="List all detected audio input devices and exit",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=DEFAULT_CSV_FILE,
        help=f"CSV file path to record measurements (default: {DEFAULT_CSV_FILE})",
    )
    parser.add_argument(
        "-s",
        "--session",
        type=str,
        choices=["SNAP", "CLAP", "NOISE"],
        default=None,
        help="Automatically label all captured transients with this category (e.g., SNAP, CLAP, NOISE)",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Prompt for classification label ([s] SNAP, [c] CLAP, [n] NOISE) after each transient",
    )
    return parser.parse_args()


def resolve_device(device_arg):
    """Resolves device argument to integer index if provided."""
    if device_arg is None:
        return None
    try:
        return int(device_arg)
    except ValueError:
        return device_arg


def main():
    args = parse_arguments()

    if args.list_devices:
        list_audio_devices()
        return

    device = resolve_device(args.device)

    # Determine session labeling mode
    session_label = args.session
    interactive = args.interactive

    # If neither flag is passed, offer an intuitive quick-menu at startup
    if not session_label and not interactive:
        print("\nChoose an analysis mode:")
        print("  [1] Interactive (Prompt [s] SNAP / [c] CLAP / [n] NOISE after each sound)")
        print("  [2] Continuous SNAP test (auto-label all triggers as SNAP)")
        print("  [3] Continuous CLAP test (auto-label all triggers as CLAP)")
        print("  [4] Continuous NOISE test (auto-label all triggers as NOISE)")
        print("  [5] Live Monitor Only (no CSV logging)")
        print("Select [1-5] (default is 1): ", end="", flush=True)

        try:
            choice = input().strip()
            if choice == "2":
                session_label = "SNAP"
            elif choice == "3":
                session_label = "CLAP"
            elif choice == "4":
                session_label = "NOISE"
            elif choice == "5":
                session_label = None
                interactive = False
                # For monitor-only, point to null or skip writing
            else:
                interactive = True
        except (EOFError, KeyboardInterrupt):
            interactive = True

    session = DiagnosticSession(
        threshold=args.threshold,
        cooldown=args.cooldown,
        device=device,
        output_file=args.output,
        session_label=session_label,
        interactive=interactive,
    )
    session.run()


if __name__ == "__main__":
    main()
