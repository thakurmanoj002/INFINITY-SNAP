"""
Infinity Snap — Spatial Vision & Hand Tracking Engine (Apple Vision Pro Mode)
=============================================================================
Real-time 21-landmark 3D hand skeleton tracking and spatial gesture recognition
powered by Google MediaPipe Vision Tasks and OpenCV.

Recognized Gestures:
  - CLOSED_FIST   -> Triggers Panic Stealth Boss Mode (Minimizes windows & mutes audio)
  - OPEN_PALM     -> Toggles Microphone Mute / Surveillance Arm
  - PINCH         -> Spatial Air Pinch (Index + Thumb tap)
  - SNAP_POSTURE  -> Spatial Finger Snap posture (for Audio+Vision Multimodal Fusion)
  - VICTORY       -> Peace / Victory macro gesture
"""

import math
from pathlib import Path
import sys
import threading
import time
from typing import Callable, List, Optional, Tuple
import urllib.request

import cv2
import numpy as np

# Suppress TensorFlow Lite / MediaPipe verbose warnings
import os
os.environ["GLOG_minloglevel"] = "2"

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
MODEL_PATH = MODEL_DIR / "gesture_recognizer.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task"

# MediaPipe landmark indices
LANDMARK_WRIST = 0
LANDMARK_THUMB_TIP = 4
LANDMARK_INDEX_TIP = 8
LANDMARK_MIDDLE_TIP = 12
LANDMARK_RING_TIP = 16
LANDMARK_PINKY_TIP = 20

# Skeleton joint connections for drawing
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),           # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),           # Index
    (0, 9), (9, 10), (10, 11), (11, 12),      # Middle
    (0, 13), (13, 14), (14, 15), (15, 16),    # Ring
    (0, 17), (17, 18), (18, 19), (19, 20),    # Pinky
    (5, 9), (9, 13), (13, 17),                # Palm knuckle bridge
]


def ensure_model_exists() -> Path:
    """Ensures Google MediaPipe gesture recognizer task model is present on disk."""
    if not MODEL_PATH.exists():
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, str(MODEL_PATH))
    return MODEL_PATH


class VisionEngine:
    """
    Captures live webcam stream, executes 3D hand landmark tracking at 30+ FPS,
    classifies spatial air gestures, and provides multimodal snap verification.
    """

    def __init__(
        self,
        camera_index: int = 0,
        enable_preview: bool = False,
        on_gesture_callback: Optional[Callable[[str, float], None]] = None,
    ):
        self.camera_index = camera_index
        self.enable_preview = enable_preview
        self.on_gesture_callback = on_gesture_callback

        # Thread synchronization & state
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        # Telemetry
        self.is_camera_active = False
        self.current_gesture = "NONE"
        self.gesture_confidence = 0.0
        self.hand_count = 0
        self.live_fps = 0.0
        self.last_snap_posture_time = 0.0

        # Debounce tracking
        self._last_triggered_gesture = "NONE"
        self._gesture_hold_start = 0.0
        self._last_trigger_time = 0.0

        # MediaPipe recognizer instance
        self._recognizer = None

    def start(self):
        """Initializes model and begins optical tracking in a background daemon thread."""
        ensure_model_exists()
        self._init_mediapipe()

        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._camera_loop,
            name="InfinitySnap-VisionEngine",
            daemon=True,
        )
        self._worker_thread.start()

    def _init_mediapipe(self):
        """Initializes Google MediaPipe Vision Tasks GestureRecognizer."""
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        base_options = python.BaseOptions(model_asset_path=str(MODEL_PATH))
        options = vision.GestureRecognizerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_hands=2,
            min_hand_detection_confidence=0.55,
            min_hand_presence_confidence=0.55,
            min_tracking_confidence=0.55,
        )
        self._recognizer = vision.GestureRecognizer.create_from_options(options)

    def stop(self):
        """Stops the optical capture loop and releases the camera device."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.5)

    def get_telemetry(self) -> Tuple[bool, str, float, int, float]:
        """Returns thread-safe (is_camera_active, current_gesture, confidence, hand_count, live_fps)."""
        with self._lock:
            return (
                self.is_camera_active,
                self.current_gesture,
                self.gesture_confidence,
                self.hand_count,
                self.live_fps,
            )

    def is_snap_posture_recent(self, window_seconds: float = 1.0) -> bool:
        """Returns True if a spatial snap posture (thumb + middle pinch) was observed within window."""
        with self._lock:
            return (time.time() - self.last_snap_posture_time) <= window_seconds

    def _camera_loop(self):
        """Continuous background frame acquisition and neural landmark inference."""
        import mediapipe as mp

        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
        if not cap.isOpened():
            # Fallback to standard capture API if CAP_DSHOW fails
            cap = cv2.VideoCapture(self.camera_index)

        if not cap.isOpened():
            with self._lock:
                self.is_camera_active = False
            return

        with self._lock:
            self.is_camera_active = True

        fps_counter = 0
        fps_timer = time.time()
        fps_val = 0.0

        try:
            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue

                # Flip for mirror effect and convert BGR -> RGB
                frame = cv2.flip(frame, 1)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, _ = frame.shape

                # Perform neural gesture recognition
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                recognition_result = self._recognizer.recognize(mp_image)

                detected_gesture = "NONE"
                detected_conf = 0.0
                detected_hands = 0
                hand_landmarks_list = []

                if recognition_result and recognition_result.hand_landmarks:
                    detected_hands = len(recognition_result.hand_landmarks)
                    hand_landmarks_list = recognition_result.hand_landmarks

                    # Analyze primary hand (first hand)
                    primary_landmarks = hand_landmarks_list[0]

                    # 1. Check custom Vision Pro pinch & snap distances
                    thumb_tip = primary_landmarks[LANDMARK_THUMB_TIP]
                    index_tip = primary_landmarks[LANDMARK_INDEX_TIP]
                    middle_tip = primary_landmarks[LANDMARK_MIDDLE_TIP]

                    dist_thumb_index = math.dist(
                        (thumb_tip.x, thumb_tip.y), (index_tip.x, index_tip.y)
                    )
                    dist_thumb_middle = math.dist(
                        (thumb_tip.x, thumb_tip.y), (middle_tip.x, middle_tip.y)
                    )

                    now = time.time()

                    # Check spatial snap posture (Thumb + Middle finger compressed)
                    if dist_thumb_middle < 0.055:
                        with self._lock:
                            self.last_snap_posture_time = now

                    # 2. Check MediaPipe built-in classified gestures
                    if recognition_result.gestures and recognition_result.gestures[0]:
                        top_gesture = recognition_result.gestures[0][0]
                        g_name = top_gesture.category_name
                        g_score = top_gesture.score

                        if g_name in {"Closed_Fist", "Open_Palm", "Victory", "Pointing_Up"}:
                            detected_gesture = g_name.upper()
                            detected_conf = float(g_score)

                    # Custom spatial gestures override if active
                    if dist_thumb_index < 0.045 and detected_gesture != "CLOSED_FIST":
                        detected_gesture = "PINCH"
                        detected_conf = max(detected_conf, 0.90)
                    elif dist_thumb_middle < 0.045 and detected_gesture != "CLOSED_FIST":
                        detected_gesture = "SNAP_POSTURE"
                        detected_conf = max(detected_conf, 0.88)

                # FPS calculation
                fps_counter += 1
                if (time.time() - fps_timer) >= 1.0:
                    fps_val = fps_counter / (time.time() - fps_timer)
                    fps_counter = 0
                    fps_timer = time.time()

                # Update telemetry
                with self._lock:
                    self.current_gesture = detected_gesture
                    self.gesture_confidence = detected_conf
                    self.hand_count = detected_hands
                    self.live_fps = fps_val

                # Gesture event dispatch with debounce
                self._handle_gesture_dispatch(detected_gesture, detected_conf)

                # Render optional Cyberpunk HUD camera preview window
                if self.enable_preview:
                    self._render_preview(frame, hand_landmarks_list, detected_gesture, fps_val)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

        finally:
            cap.release()
            if self.enable_preview:
                cv2.destroyAllWindows()
            with self._lock:
                self.is_camera_active = False

    def _handle_gesture_dispatch(self, gesture: str, confidence: float):
        """Debounces and fires action callbacks for actionable air gestures."""
        now = time.time()
        # Only actionable gestures: CLOSED_FIST, OPEN_PALM, PINCH, VICTORY
        if gesture not in {"CLOSED_FIST", "OPEN_PALM", "PINCH", "VICTORY"} or confidence < 0.70:
            self._gesture_hold_start = 0.0
            return

        if gesture != self._last_triggered_gesture:
            if self._gesture_hold_start == 0.0:
                self._gesture_hold_start = now
            elif (now - self._gesture_hold_start) >= 0.25:  # Hold for 250ms
                if (now - self._last_trigger_time) >= 1.5:  # 1.5s cooldown
                    self._last_triggered_gesture = gesture
                    self._last_trigger_time = now
                    if self.on_gesture_callback:
                        threading.Thread(
                            target=self.on_gesture_callback,
                            args=(gesture, confidence),
                            daemon=True,
                        ).start()
        else:
            self._gesture_hold_start = 0.0

    def _render_preview(self, frame, landmarks_list, gesture: str, fps: float):
        """Draws Cyberpunk skeleton overlay and HUD telemetry onto the preview frame."""
        h, w, _ = frame.shape

        # Draw hand skeletons
        for landmarks in landmarks_list:
            # Draw joint connections
            for p1_idx, p2_idx in HAND_CONNECTIONS:
                p1 = (int(landmarks[p1_idx].x * w), int(landmarks[p1_idx].y * h))
                p2 = (int(landmarks[p2_idx].x * w), int(landmarks[p2_idx].y * h))
                cv2.line(frame, p1, p2, (255, 0, 127), 2)  # Neon Magenta lines

            # Draw joint points
            for lm in landmarks:
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(frame, (cx, cy), 5, (0, 240, 255), -1)  # Neon Cyan joints
                cv2.circle(frame, (cx, cy), 7, (0, 255, 102), 1)   # Green border

        # Cyberpunk HUD Header Banner
        cv2.rectangle(frame, (0, 0), (w, 55), (15, 15, 25), -1)
        cv2.line(frame, (0, 55), (w, 55), (0, 240, 255), 2)

        cv2.putText(
            frame,
            "INFINITY SNAP // OPTICAL HUD [APPLE VISION PRO MODE]",
            (15, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 240, 255),
            1,
            cv2.LINE_AA,
        )

        gesture_color = (0, 255, 102) if gesture != "NONE" else (140, 140, 160)
        cv2.putText(
            frame,
            f"GESTURE: {gesture}  |  FPS: {fps:4.1f}",
            (15, 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            gesture_color,
            1,
            cv2.LINE_AA,
        )

        cv2.imshow("⚡ INFINITY SNAP // OPTICAL TRACKING HUD ⚡", frame)
