"""
Infinity Snap — Spatial Air Desktop Controller (Precision Engineered)
=====================================================================
Ultra-responsive, jitter-free spatial hand tracking engine translating optical
webcam hand movements directly into native Windows desktop interactions:

Key Improvements:
  1. Low-Latency Pipeline : 60 FPS capture with buffer size 1 and fast inference downscaling.
  2. Relative Pinch Physics: Dynamic hand-scale normalization prevents false clicks when pointing.
  3. Stable Adaptive Filter: Jitter deadband (<4px) eliminates micro-tremors; adaptive alpha eliminates lag.
  4. Directional Scrolling : Accumulator deadband prevents up/down confusion; smooth rate-limited scroll.
  5. Dual-Pinch Controls  :
       - Index + Thumb Pinch  -> Left Click / Hold to Drag & Drop.
       - Middle + Thumb Pinch -> Right Click (Context Menu).
       - Two-Finger Glide     -> Smooth directional scroll.
       - Clenched Fist        -> Rest / Freeze cursor.
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

# MediaPipe Hand Landmarks
WRIST = 0
THUMB_CMC = 1
THUMB_MCP = 2
THUMB_IP = 3
THUMB_TIP = 4

INDEX_MCP = 5
INDEX_PIP = 6
INDEX_DIP = 7
INDEX_TIP = 8

MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_DIP = 11
MIDDLE_TIP = 12

RING_MCP = 13
RING_PIP = 14
RING_DIP = 15
RING_TIP = 16

PINKY_MCP = 17
PINKY_PIP = 18
PINKY_DIP = 19
PINKY_TIP = 20

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),           # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),           # Index
    (0, 9), (9, 10), (10, 11), (11, 12),      # Middle
    (0, 13), (13, 14), (14, 15), (15, 16),    # Ring
    (0, 17), (17, 18), (18, 19), (19, 20),    # Pinky
    (5, 9), (9, 13), (13, 17),                # Knuckle bridge
]

# Pinch thresholds normalized to palm scale (wrist to middle knuckle)
PINCH_DOWN_THRESHOLD = 0.22   # Normalized distance to engage pinch
PINCH_UP_THRESHOLD = 0.32     # Normalized distance to release pinch (hysteresis)
RIGHT_PINCH_THRESHOLD = 0.22  # Middle finger pinch threshold

# Jitter & Motion Filter Constants
JITTER_DEADBAND_PIXELS = 3.5  # Ignore tremors smaller than this
MIN_SMOOTH_ALPHA = 0.18       # Strong smoothing when holding still
MAX_SMOOTH_ALPHA = 0.85       # Responsive tracking when moving fast
MAX_SPEED_PIXELS = 120.0      # Speed threshold for max alpha

# Scroll Constants
SCROLL_DEADBAND = 0.015       # Minimum accumulated movement before scrolling
SCROLL_STEP_TICKS = 120       # Windows standard scroll step
SCROLL_MIN_INTERVAL = 0.04    # 25 scrolls/sec max for buttery smooth flow


def ensure_model_file() -> Path:
    """Ensures Google MediaPipe model task file exists on disk."""
    if not MODEL_PATH.exists():
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, str(MODEL_PATH))
    return MODEL_PATH


class AirDesktopController:
    """
    Precision optical spatial desktop controller. Converts webcam hand tracking
    into high-accuracy, zero-latency Windows mouse input.
    """

    def __init__(
        self,
        camera_index: int = 0,
        enable_preview: bool = True,
        scroll_speed: float = 1.0,
    ):
        self.camera_index = camera_index
        self.enable_preview = enable_preview
        self.scroll_speed = scroll_speed

        # Screen dimensions
        self.screen_w = max(800, user32.GetSystemMetrics(0))
        self.screen_h = max(600, user32.GetSystemMetrics(1))

        # Comfortable interaction margin (normalized in camera frame)
        self.margin_x = 0.15
        self.margin_y = 0.16

        # Cursor position & smoothing state
        self.prev_x = float(self.screen_w // 2)
        self.prev_y = float(self.screen_h // 2)

        # Pinch & click state machine
        self.is_pinching = False
        self.last_right_click_time = 0.0

        # Scroll state machine
        self.scroll_accumulator = 0.0
        self.last_scroll_time = 0.0
        self.scroll_anchor_y = 0.0

        # Thread state
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.current_mode = "STANDBY"
        self.live_fps = 0.0

        # MediaPipe recognizer
        self._recognizer = None

    def start(self):
        """Initializes model and launches low-latency interaction loop."""
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
        """Stops the controller and cleanly releases any held mouse buttons."""
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

        # Open camera with DirectShow for zero buffer lag on Windows
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.camera_index)

        if not cap.isOpened():
            return

        # Configure camera for lowest possible latency
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 60)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        fps_count = 0
        fps_timer = time.time()
        fps_val = 0.0

        try:
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.005)
                    continue

                # Mirror frame horizontally for natural 1:1 human interaction
                frame = cv2.flip(frame, 1)
                h, w, _ = frame.shape

                # Resize to optimized resolution for lightning-fast neural inference
                small_frame = cv2.resize(frame, (480, 360), interpolation=cv2.INTER_LINEAR)
                rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

                # MediaPipe inference
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_small)
                result = self._recognizer.recognize(mp_img)

                mode_str = "STANDBY"
                active_landmarks = None

                if result and result.hand_landmarks:
                    landmarks = result.hand_landmarks[0]
                    active_landmarks = landmarks

                    # Key landmarks
                    wrist = landmarks[WRIST]
                    thumb = landmarks[THUMB_TIP]
                    index = landmarks[INDEX_TIP]
                    index_pip = landmarks[INDEX_PIP]
                    index_mcp = landmarks[INDEX_MCP]
                    middle = landmarks[MIDDLE_TIP]
                    middle_pip = landmarks[MIDDLE_PIP]
                    middle_mcp = landmarks[MIDDLE_MCP]
                    ring = landmarks[RING_TIP]
                    pinky = landmarks[PINKY_TIP]

                    # 1. Calculate dynamic palm scale (Wrist to Middle Knuckle MCP)
                    # This makes all distances scale-invariant regardless of how close/far the hand is!
                    palm_scale = math.dist((wrist.x, wrist.y), (middle_mcp.x, middle_mcp.y))
                    palm_scale = max(palm_scale, 0.08)  # Prevent division by zero

                    # 2. Scale-normalized pinch distances
                    norm_index_pinch = math.dist((thumb.x, thumb.y), (index.x, index.y)) / palm_scale
                    norm_middle_pinch = math.dist((thumb.x, thumb.y), (middle.x, middle.y)) / palm_scale

                    # 3. Finger extension states
                    is_index_extended = index.y < index_pip.y
                    is_middle_extended = middle.y < middle_pip.y
                    is_ring_curled = ring.y > landmarks[RING_PIP].y
                    is_pinky_curled = pinky.y > landmarks[PINKY_PIP].y
                    is_fist = (
                        index.y > index_mcp.y and
                        middle.y > middle_mcp.y and
                        ring.y > landmarks[RING_MCP].y and
                        pinky.y > landmarks[PINKY_MCP].y
                    )

                    now = time.time()

                    # -------------------------------------------------------------
                    # GESTURE 1: FIST FREEZE (Resting hand)
                    # -------------------------------------------------------------
                    if is_fist:
                        mode_str = "FREEZE (Resting)"
                        self._release_pinch_if_active()
                        self.scroll_anchor_y = 0.0

                    # -------------------------------------------------------------
                    # GESTURE 2: TWO-FINGER DIRECTIONAL SCROLL
                    # -------------------------------------------------------------
                    elif (
                        is_index_extended and
                        is_middle_extended and
                        is_ring_curled and
                        is_pinky_curled and
                        norm_index_pinch > 0.45
                    ):
                        mode_str = "SCROLLING"
                        self._release_pinch_if_active()

                        curr_y = (index.y + middle.y) / 2.0
                        if self.scroll_anchor_y == 0.0:
                            self.scroll_anchor_y = curr_y
                        else:
                            delta_y = self.scroll_anchor_y - curr_y
                            self.scroll_accumulator += delta_y
                            self.scroll_anchor_y = curr_y

                            # Rate limit and emit directional scroll ticks
                            if (now - self.last_scroll_time) >= SCROLL_MIN_INTERVAL:
                                if self.scroll_accumulator > SCROLL_DEADBAND:
                                    # Finger moved UP -> Page scrolls UP
                                    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, SCROLL_STEP_TICKS, 0)
                                    self.scroll_accumulator = max(0.0, self.scroll_accumulator - SCROLL_DEADBAND)
                                    self.last_scroll_time = now
                                elif self.scroll_accumulator < -SCROLL_DEADBAND:
                                    # Finger moved DOWN -> Page scrolls DOWN
                                    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, -SCROLL_STEP_TICKS, 0)
                                    self.scroll_accumulator = min(0.0, self.scroll_accumulator + SCROLL_DEADBAND)
                                    self.last_scroll_time = now

                    # -------------------------------------------------------------
                    # GESTURE 3: RIGHT CLICK (Middle Finger + Thumb Pinch)
                    # -------------------------------------------------------------
                    elif (
                        norm_middle_pinch < RIGHT_PINCH_THRESHOLD and
                        norm_index_pinch > 0.35 and
                        (now - self.last_right_click_time) >= 0.60
                    ):
                        mode_str = "RIGHT CLICK"
                        self._release_pinch_if_active()
                        self.scroll_anchor_y = 0.0
                        self.last_right_click_time = now
                        user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                        user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

                    # -------------------------------------------------------------
                    # GESTURE 4: AIR CURSOR & PINCH LEFT CLICK / DRAG
                    # -------------------------------------------------------------
                    else:
                        self.scroll_anchor_y = 0.0
                        self.scroll_accumulator = 0.0

                        # Map normalized coordinates to screen dimensions with interaction margins
                        norm_x = (index.x - self.margin_x) / (1.0 - 2 * self.margin_x)
                        norm_y = (index.y - self.margin_y) / (1.0 - 2 * self.margin_y)

                        norm_x = max(0.0, min(1.0, norm_x))
                        norm_y = max(0.0, min(1.0, norm_y))

                        target_screen_x = norm_x * self.screen_w
                        target_screen_y = norm_y * self.screen_h

                        # Motion vector
                        delta_dist = math.hypot(target_screen_x - self.prev_x, target_screen_y - self.prev_y)

                        # JITTER DEADBAND: If movement is tiny hand tremor, stay completely rock steady
                        if delta_dist > JITTER_DEADBAND_PIXELS:
                            # Dynamic Adaptive Smoothing:
                            # Slow movement = strong smoothing (high precision)
                            # Fast movement = responsive alpha (zero lag)
                            speed_ratio = min(1.0, delta_dist / MAX_SPEED_PIXELS)
                            adaptive_alpha = MIN_SMOOTH_ALPHA + speed_ratio * (MAX_SMOOTH_ALPHA - MIN_SMOOTH_ALPHA)

                            smooth_x = self.prev_x + adaptive_alpha * (target_screen_x - self.prev_x)
                            smooth_y = self.prev_y + adaptive_alpha * (target_screen_y - self.prev_y)

                            self.prev_x = smooth_x
                            self.prev_y = smooth_y

                            # Move Windows cursor
                            user32.SetCursorPos(int(smooth_x), int(smooth_y))

                        # PINCH LEFT CLICK STATE MACHINE (With Hysteresis)
                        # When pointing with index finger alone, norm_index_pinch is > 0.50 (Never clicks!)
                        if not self.is_pinching:
                            if norm_index_pinch < PINCH_DOWN_THRESHOLD:
                                self.is_pinching = True
                                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                mode_str = "PINCH CLICK"
                            else:
                                mode_str = "AIR CURSOR"
                        else:
                            # Currently pinching -> Hold to Drag
                            if norm_index_pinch > PINCH_UP_THRESHOLD:
                                self.is_pinching = False
                                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                mode_str = "AIR CURSOR"
                            else:
                                mode_str = "PINCH DRAGGING"

                else:
                    self.scroll_anchor_y = 0.0
                    self.scroll_accumulator = 0.0
                    self._release_pinch_if_active()

                # FPS calculation
                fps_count += 1
                if (time.time() - fps_timer) >= 1.0:
                    fps_val = fps_count / (time.time() - fps_timer)
                    fps_count = 0
                    fps_timer = time.time()

                with self._lock:
                    self.current_mode = mode_str
                    self.live_fps = fps_val

                # Render preview HUD window
                if self.enable_preview:
                    self._draw_hud(frame, active_landmarks, mode_str, fps_val)
                    key = cv2.waitKey(1) & 0xFF
                    if key in {ord('q'), 27}:
                        break

        finally:
            cap.release()
            self._release_pinch_if_active()
            if self.enable_preview:
                cv2.destroyAllWindows()
            self._running = False

    def _release_pinch_if_active(self):
        """Releases the left mouse button if currently in a pinch drag state."""
        if self.is_pinching:
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.is_pinching = False

    def _draw_hud(self, frame, landmarks, mode: str, fps: float):
        """Draws Cyberpunk spatial interaction overlay on the preview frame."""
        h, w, _ = frame.shape

        # Active Interaction Boundary
        bx1 = int(self.margin_x * w)
        by1 = int(self.margin_y * h)
        bx2 = int((1.0 - self.margin_x) * w)
        by2 = int((1.0 - self.margin_y) * h)
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), (0, 240, 255), 1)

        # Draw hand skeleton
        if landmarks:
            for p1_idx, p2_idx in HAND_CONNECTIONS:
                p1 = (int(landmarks[p1_idx].x * w), int(landmarks[p1_idx].y * h))
                p2 = (int(landmarks[p2_idx].x * w), int(landmarks[p2_idx].y * h))
                cv2.line(frame, p1, p2, (255, 0, 127), 2)

            for lm in landmarks:
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(frame, (cx, cy), 4, (0, 240, 255), -1)

            # Cursor pointer beacon on index tip
            idx_pt = (int(landmarks[INDEX_TIP].x * w), int(landmarks[INDEX_TIP].y * h))
            cv2.circle(frame, idx_pt, 10, (0, 255, 102), 2)
            cv2.circle(frame, idx_pt, 4, (0, 255, 102), -1)

            # Pinch indicator on thumb tip
            thumb_pt = (int(landmarks[THUMB_TIP].x * w), int(landmarks[THUMB_TIP].y * h))
            cv2.circle(frame, thumb_pt, 6, (255, 230, 0), -1)

        # Header banner
        cv2.rectangle(frame, (0, 0), (w, 55), (15, 15, 25), -1)
        cv2.line(frame, (0, 55), (w, 55), (0, 240, 255), 2)

        cv2.putText(
            frame,
            "INFINITY SNAP // SPATIAL AIR DESKTOP [PRECISION ENGINE]",
            (15, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 240, 255),
            1,
            cv2.LINE_AA,
        )

        status_color = (0, 255, 102) if "AIR" in mode or "PINCH" in mode else (255, 230, 0)
        cv2.putText(
            frame,
            f"MODE: {mode}  |  FPS: {fps:4.1f}  |  RES: {self.screen_w}x{self.screen_h}",
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
            "[Index: Move]  [Thumb+Index: Click/Drag]  [Thumb+Middle: Right Click]  [Two Fingers: Scroll]  [Fist: Freeze]",
            (15, h - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            (200, 200, 220),
            1,
            cv2.LINE_AA,
        )

        cv2.imshow("⚡ INFINITY SNAP // AIR DESKTOP CONTROLLER ⚡", frame)
