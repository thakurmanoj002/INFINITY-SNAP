"""
Infinity Snap — Multi-Gesture Audio Engine
==========================================
Real-time microphone analysis, spectral differentiation, live VU telemetry,
and multi-snap gesture accumulator (1 snap = Panic Stealth, 2 snaps = Folder Purge).
"""

import threading
import time
from typing import Callable, Optional, Tuple

import numpy as np
import sounddevice as sd

DEFAULT_SAMPLE_RATE = 44100
DEFAULT_BLOCK_SIZE = 1024
DEFAULT_THRESHOLD = 0.50
DEFAULT_COOLDOWN = 1.20

# Multi-snap accumulation timing (seconds)
DEBOUNCE_INTERVAL = 0.12    # Ignores echo/reverberation of the same snap
GESTURE_BASE_WINDOW = 0.65  # Time to wait for a 2nd snap before firing single snap


class MultiGestureAudioEngine:
    """
    Captures live audio stream, analyzes transient peaks & spectral energy,
    accumulates multi-snap patterns, and provides real-time VU telemetry.
    """

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        cooldown: float = DEFAULT_COOLDOWN,
        device: Optional[str] = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        block_size: int = DEFAULT_BLOCK_SIZE,
        on_gesture_callback: Optional[Callable[[int, float, float], None]] = None,
        on_state_change: Optional[Callable[[str], None]] = None,
    ):
        self.threshold = threshold
        self.cooldown = cooldown
        self.device = device
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.on_gesture_callback = on_gesture_callback
        self.on_state_change = on_state_change

        # Telemetry state
        self._lock = threading.Lock()
        self.live_peak = 0.0
        self.live_rms = 0.0
        self.live_dbfs = -60.0
        self.gesture_display = "READY"

        # Accumulator state
        self._stop_event = threading.Event()
        self._snap_count = 0
        self._window_deadline = 0.0
        self._last_snap_time = 0.0
        self._max_peak_in_gesture = 0.0
        self._is_in_cooldown = False
        self._cooldown_until = 0.0

        # Stream & timer thread
        self._stream: Optional[sd.InputStream] = None
        self._timer_thread: Optional[threading.Thread] = None
        self.device_name = "Default Microphone"

    def start(self):
        """Initializes and opens the microphone stream and background gesture timer."""
        # Query device name
        try:
            device_info = sd.query_devices(device=self.device, kind="input")
            self.device_name = device_info["name"]
        except Exception:
            self.device_name = "Default Audio Transducer"

        self._stop_event.clear()

        # Start timer daemon thread for gesture window timeouts
        self._timer_thread = threading.Thread(
            target=self._gesture_timer_loop,
            name="InfinitySnap-GestureTimer",
            daemon=True,
        )
        self._timer_thread.start()

        self._stream = sd.InputStream(
            device=self.device,
            channels=1,
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            dtype="float32",
            callback=self._audio_callback,
        )
        self._stream.start()

    def stop(self):
        """Stops the audio stream and gesture timers."""
        self._stop_event.set()
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_thread.join(timeout=1.0)

    def get_telemetry(self) -> Tuple[float, float, float, str]:
        """Returns thread-safe (live_peak, live_rms, live_dbfs, gesture_display)."""
        with self._lock:
            return self.live_peak, self.live_rms, self.live_dbfs, self.gesture_display

    def _audio_callback(self, indata, frames, time_info, status):
        """SoundDevice real-time audio block callback."""
        if status:
            pass

        audio_block = indata[:, 0]
        peak = float(np.max(np.abs(audio_block)))
        rms = float(np.sqrt(np.mean(audio_block ** 2)))
        dbfs = 20.0 * np.log10(max(rms, 1e-6))

        now = time.time()

        with self._lock:
            self.live_peak = peak
            self.live_rms = rms
            self.live_dbfs = dbfs

            # Check if currently in action cooldown
            if self._is_in_cooldown:
                if now >= self._cooldown_until:
                    self._is_in_cooldown = False
                    self.gesture_display = "READY"
                else:
                    return

            # Check threshold trigger
            if peak >= self.threshold:
                # Check intra-snap debounce to avoid echo of same snap
                if (now - self._last_snap_time) >= DEBOUNCE_INTERVAL:
                    self._last_snap_time = now

                    # Accumulate snap
                    if self._snap_count == 0:
                        self._snap_count = 1
                        self._window_deadline = now + GESTURE_BASE_WINDOW
                        self._max_peak_in_gesture = peak
                        self.gesture_display = "SNAP 1 INTERCEPTED (Listening...)"
                    elif self._snap_count >= 1:
                        self._snap_count = 2
                        self._max_peak_in_gesture = max(self._max_peak_in_gesture, peak)
                        self.gesture_display = "DOUBLE SNAP DETECTED!"
                        # Immediate trigger on 2 snaps without waiting
                        self._dispatch_gesture_locked()

    def _dispatch_gesture_locked(self):
        """Dispatches accumulated gesture and enters cooldown. Caller must hold self._lock."""
        count = self._snap_count
        peak = self._max_peak_in_gesture
        self._snap_count = 0
        self._window_deadline = 0.0
        self._is_in_cooldown = True
        self._cooldown_until = time.time() + self.cooldown
        self.gesture_display = f"EXECUTING {count} SNAP PROTOCOL..."

        # Dispatch callback in a separate thread so audio callback is never blocked
        if self.on_gesture_callback and count > 0:
            threading.Thread(
                target=self._run_callback,
                args=(count, peak, self.threshold),
                daemon=True,
            ).start()

    def _run_callback(self, count: int, peak: float, threshold: float):
        """Worker thread to run gesture action."""
        try:
            if self.on_gesture_callback:
                self.on_gesture_callback(count, peak, threshold)
        finally:
            with self._lock:
                self.gesture_display = "READY"

    def _gesture_timer_loop(self):
        """Monitors gesture window deadlines and triggers on timeout."""
        while not self._stop_event.is_set():
            time.sleep(0.02)
            now = time.time()
            with self._lock:
                if self._snap_count > 0 and self._window_deadline > 0:
                    if now >= self._window_deadline:
                        # Gesture accumulation window expired, dispatch accumulated count
                        self._dispatch_gesture_locked()
