"""
Infinity Snap — Spatial Air Desktop Controller (Apple Vision Pro Mode)
======================================================================
Autonomous spatial hand tracking engine that translates webcam hand movements
directly into Windows desktop interactions:
  - AIR CURSOR   : Index finger smoothly controls Windows mouse pointer with EMA jitter filtering.
  - PINCH CLICK  : Thumb + Index tap performs Left Click; holding performs Drag & Drop.
  - RIGHT CLICK  : Thumb + Middle finger tap opens context menus.
  - TWO-FINGER   : Index + Middle finger glide performs buttery smooth document / web scrolling.
  - FIST FREEZE  : Clenched fist temporarily freezes cursor so you can rest your hand.
"""

from ctypes import wintypes
import ctypes
import math
from pathlib import Path
import sys
import threading
import time
from typing import Optional, Tuple
import urllib.request

import cv2
import numpy as np

# Win32 Mouse Constants
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800

user32 = ctypes.windll.user32

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
MODEL_PATH = MODEL_DIR / "gesture_recognizer.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task"

# Landmark indices
THUMB_TIP = 4
INDEX_TIP = 8
INDEX_PIP = 6
MIDDLE_TIP = 12
MIDDLE_PIP = 10
RING_TIP = 16
PINKY_TIP = 20
WRIST = 0

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),           # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),           # Index
    (0, 9), (9, 10), (10, 11), (11, 12),      # Middle
    (0, 13), (13, 14), (14, 15), (15, 16),    # Ring
    (0, 17), (17, 18), (18, 19), (19, 20),    # Pinky
    (5, 9), (9, 13), (13, 17),                # Knuckles
]


def ensure_model_file() -> Path:
    """Ensures Google MediaPipe model task file exists on disk."""
    if not MODEL_PATH.exists():
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, str(MODEL_PATH))
    return MODEL_PATH


class AirDesktopController:
    """
    Translates optical 3D hand tracking into native Windows mouse control,
    spatial pinch gestures, and scrolling.
    """

    def __init__(
        self,
        camera_index: int = 0,
        enable_preview: bool = True,
        smoothing: float = 0.40,
        scroll_speed: float = 24.0,
    ):
        self.camera_index = camera_index
        self.enable_preview = enable_preview
        self.smoothing = smoothing
        self.scroll_speed = scroll_speed

        # Query primary screen dimensions
        self.screen_w = user32.GetSystemMetrics(0)
        self.screen_h = user32.GetSystemMetrics(1)

        # Active interaction boundary margins in camera view (normalized 0.0 to 1.0)
        self.margin_x = 0.18
        self.margin_y = 0.20

        # Cursor smoothing state
        self.prev_x = self.screen_w / 2
        self.prev_y = self.screen_h / 2

        # Gesture & button state
        self.is_pinching = False
        self.pinch_start_time = 0.0
        self.last_right_click_time = 0.0
        self.prev_scroll_y = 0.0

        # Thread state
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.current_mode = "STANDBY"
        self.live_fps = 0.0

        # Recognizer instance
        self._recognizer = None

    def start(self):
        """Initializes neural model and begins air desktop interaction thread."""
        ensure_model_file()
        self._init_recognizer()

        self._running = True
        self._thread = threading.Thread(
            target=self._interaction_loop,
            name="InfinitySnap-AirDesktopThread",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        """Halts optical tracking and releases mouse buttons if held."""
        self._running = False
        if self.is_pinching:
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.is_pinching = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

    def _init_recognizer(self):
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        base_options = python.BaseOptions(model_asset_path=str(MODEL_PATH))
        options = vision.GestureRecognizerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_hands=1,
            min_hand_detection_confidence=0.55,
            min_hand_presence_confidence=0.55,
            min_tracking_confidence=0.55,
        )
        self._recognizer = vision.GestureRecognizer.create_from_options(options)

    def _interaction_loop(self):
        import mediapipe as mp

        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.camera_index)

        if not cap.isOpened():
            return

        fps_count = 0
        fps_timer = time.time()
        fps_val = 0.0

        try:
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue

                # Mirror frame for natural 1:1 human interaction
                frame = cv2.flip(frame, 1)
                h, w, _ = frame.shape
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # MediaPipe inference
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                result = self._recognizer.recognize(mp_img)

                mode_str = "STANDBY"
                active_landmarks = None

                if result and result.hand_landmarks:
                    landmarks = result.hand_landmarks[0]
                    active_landmarks = landmarks

                    # Extract primary fingertips & knuckles
                    thumb = landmarks[THUMB_TIP]
                    index = landmarks[INDEX_TIP]
                    index_pip = landmarks[INDEX_PIP]
                    middle = landmarks[MIDDLE_TIP]
                    middle_pip = landmarks[MIDDLE_PIP]
                    ring = landmarks[RING_TIP]
                    pinky = landmarks[PINKY_TIP]

                    # Distances
                    dist_pinch = math.dist((thumb.x, thumb.y), (index.x, index.y))
                    dist_right_pinch = math.dist((thumb.x, thumb.y), (middle.x, middle.y))

                    # Finger extension states
                    is_index_extended = index.y < index_pip.y
                    is_middle_extended = middle.y < middle_pip.y
                    is_ring_curled = ring.y > landmarks[14].y
                    is_pinky_curled = pinky.y > landmarks[18].y
                    is_fist = (
                        index.y > index_pip.y and
                        middle.y > middle_pip.y and
                        ring.y > landmarks[14].y and
                        pinky.y > landmarks[18].y
                    )

                    now = time.time()

                    # 1. FIST FREEZE: Hand is resting or clutching
                    if is_fist:
                        mode_str = "FREEZE (Resting)"
                        if self.is_pinching:
                            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                            self.is_pinching = False

                    # 2. TWO-FINGER SCROLL: Index & Middle both extended, Ring & Pinky curled
                    elif is_index_extended and is_middle_extended and is_ring_curled and is_pinky_curled and dist_pinch > 0.07:
                        mode_str = "TWO-FINGER SCROLL"
                        if self.is_pinching:
                            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                            self.is_pinching = False

                        curr_y = (index.y + middle.y) / 2.0
                        if self.prev_scroll_y > 0:
                            diff_y = self.prev_scroll_y - curr_y
                            if abs(diff_y) > 0.003:
                                wheel_delta = int(diff_y * self.scroll_speed * 120)
                                user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, wheel_delta, 0)
                        self.prev_scroll_y = curr_y

                    # 3. RIGHT CLICK PINCH: Thumb touches Middle finger tip
                    elif dist_right_pinch < 0.040 and (now - self.last_right_click_time) >= 0.70:
                        mode_str = "RIGHT CLICK"
                        self.last_right_click_time = now
                        if self.is_pinching:
                            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                            self.is_pinching = False
                        user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                        user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

                    # 4. AIR CURSOR & PINCH CLICK/DRAG
                    else:
                        self.prev_scroll_y = 0.0

                        # Map normalized coordinates within comfortable interaction margins
                        norm_x = (index.x - self.margin_x) / (1.0 - 2 * self.margin_x)
                        norm_y = (index.y - self.margin_y) / (1.0 - 2 * self.margin_y)

                        norm_x = max(0.0, min(1.0, norm_x))
                        norm_y = max(0.0, min(1.0, norm_y))

                        target_screen_x = norm_x * self.screen_w
                        target_screen_y = norm_y * self.screen_h

                        # Exponential Moving Average smoothing filter
                        smooth_x = self.prev_x + self.smoothing * (target_screen_x - self.prev_x)
                        smooth_y = self.prev_y + self.smoothing * (target_screen_y - self.prev_y)

                        self.prev_x = smooth_x
                        self.prev_y = smooth_y

                        # Move Windows Cursor
                        user32.SetCursorPos(int(smooth_x), int(smooth_y))

                        # Check Pinch Click (Left Click / Drag)
                        if dist_pinch < 0.040:
                            if not self.is_pinching:
                                self.is_pinching = True
                                self.pinch_start_time = now
                                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                mode_str = "PINCH CLICK"
                            else:
                                mode_str = "PINCH DRAGGING"
                        else:
                            if self.is_pinching:
                                self.is_pinching = False
                                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                            mode_str = "AIR CURSOR ACTIVE"

                else:
                    self.prev_scroll_y = 0.0
                    if self.is_pinching:
                        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        self.is_pinching = False

                # FPS calculation
                fps_count += 1
                if (time.time() - fps_timer) >= 1.0:
                    fps_val = fps_count / (time.time() - fps_timer)
                    fps_count = 0
                    fps_timer = time.time()

                with self._lock:
                    self.current_mode = mode_str
                    self.live_fps = fps_val

                # Render preview window if enabled
                if self.enable_preview:
                    self._draw_hud(frame, active_landmarks, mode_str, fps_val)
                    key = cv2.waitKey(1) & 0xFF
                    if key in {ord('q'), 27}:  # 'q' or ESC
                        break

        finally:
            cap.release()
            if self.is_pinching:
                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            if self.enable_preview:
                cv2.destroyAllWindows()
            self._running = False

    def _draw_hud(self, frame, landmarks, mode: str, fps: float):
        """Renders live Cyberpunk spatial interaction HUD window."""
        h, w, _ = frame.shape

        # Draw Active Interaction Zone Boundary Box
        bx1 = int(self.margin_x * w)
        by1 = int(self.margin_y * h)
        bx2 = int((1.0 - self.margin_x) * w)
        by2 = int((1.0 - self.margin_y) * h)
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), (0, 240, 255), 1)

        # Draw hand skeleton if present
        if landmarks:
            for p1_idx, p2_idx in HAND_CONNECTIONS:
                p1 = (int(landmarks[p1_idx].x * w), int(landmarks[p1_idx].y * h))
                p2 = (int(landmarks[p2_idx].x * w), int(landmarks[p2_idx].y * h))
                cv2.line(frame, p1, p2, (255, 0, 127), 2)

            for lm in landmarks:
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(frame, (cx, cy), 4, (0, 240, 255), -1)

            # Highlight cursor pointer fingertip (Index tip)
            idx_pt = (int(landmarks[INDEX_TIP].x * w), int(landmarks[INDEX_TIP].y * h))
            cv2.circle(frame, idx_pt, 9, (0, 255, 102), 2)
            cv2.circle(frame, idx_pt, 4, (0, 255, 102), -1)

        # Top HUD Banner
        cv2.rectangle(frame, (0, 0), (w, 55), (15, 15, 25), -1)
        cv2.line(frame, (0, 55), (w, 55), (0, 240, 255), 2)

        cv2.putText(
            frame,
            "INFINITY SNAP // SPATIAL AIR DESKTOP CONTROLLER",
            (15, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 240, 255),
            1,
            cv2.LINE_AA,
        )

        status_color = (0, 255, 102) if "ACTIVE" in mode or "PINCH" in mode else (255, 230, 0)
        cv2.putText(
            frame,
            f"MODE: {mode}  |  FPS: {fps:4.1f}  |  SCREEN: {self.screen_w}x{self.screen_h}",
            (15, 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            status_color,
            1,
            cv2.LINE_AA,
        )

        # Bottom Instructions
        cv2.putText(
            frame,
            "[Index: Move Cursor]  [Pinch: Left Click / Drag]  [Middle Pinch: Right Click]  [Two Fingers: Scroll]  [Fist: Rest]",
            (15, h - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (180, 180, 200),
            1,
            cv2.LINE_AA,
        )

        cv2.imshow("⚡ INFINITY SNAP // AIR DESKTOP CONTROLLER ⚡", frame)
