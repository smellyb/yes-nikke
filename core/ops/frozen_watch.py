"""Watchdog to catch stuck game screens while granting loading screens immunity.

A screen that stops changing while the automation presses nothing is stuck.
Live2D and particle animations mean real game screens constantly exhibit micro-changes,
so a screen that stays identical while waiting means nothing is coming.

Critical distinction:
- Normal screens stuck for > 10.0s or with >= 3 ineffective presses trigger FrozenScreen.
- Loading screens (dark screens, Loading words, spinning indicators) are granted up to
  45.0s of grace time (LOADING_MAX_SECONDS).
"""

from __future__ import annotations

import logging
from time import monotonic
from typing import Optional, Tuple
import cv2
import numpy as np

logger = logging.getLogger("yes_nikke.ops.frozen_watch")

STUCK_SECONDS = 10.0
LOADING_MAX_SECONDS = 45.0
THUMB_SIZE = (192, 108)  # 16:9 thumbnail for fast diff comparison
PIXEL_DIFF = 6
CHANGED_PIXELS = 4
INEFFECTIVE_PRESSES = 3

LOADING_WORDS = (
    "nowloading",
    "loading",
    "加载",
    "载入",
    "读取中",
    "连接中",
    "连线中",
    "通信中",
    "请稍候",
)


class FrozenScreen(RuntimeError):
    """Raised when the game screen freezes or presses have no effect."""
    pass


def extract_loading_word(text: str) -> str:
    """Return the matched loading keyword, or empty string."""
    flat = "".join(str(text or "").split()).lower()
    return next((word for word in LOADING_WORDS if word in flat), "")


def is_dark_frame(thumb: np.ndarray, max_mean_brightness: float = 15.0) -> bool:
    """Check if the thumbnail is an almost black transition/loading frame."""
    if thumb.ndim == 3:
        gray = cv2.cvtColor(thumb, cv2.COLOR_BGR2GRAY)
    else:
        gray = thumb
    return float(np.mean(gray)) <= max_mean_brightness


class FrozenWatch:
    """Watches screen transitions and flags frozen/stuck conditions."""

    def __init__(
        self,
        stuck_timeout: float = STUCK_SECONDS,
        loading_timeout: float = LOADING_MAX_SECONDS,
    ):
        self.stuck_timeout = stuck_timeout
        self.loading_timeout = loading_timeout
        self.last_thumb: Optional[np.ndarray] = None
        self.last_change_time = monotonic()
        self.last_press_time = monotonic()
        self.ineffective_press_count = 0
        self.is_loading = False

    def reset(self) -> None:
        """Reset state when switching tasks."""
        self.last_thumb = None
        self.last_change_time = monotonic()
        self.last_press_time = monotonic()
        self.ineffective_press_count = 0
        self.is_loading = False

    def notify_press(self) -> None:
        """Call whenever an action/press is initiated."""
        self.last_press_time = monotonic()

    def update_frame(
        self,
        full_frame: np.ndarray,
        detected_text: str = "",
    ) -> None:
        """Evaluate a new frame for movement or stuck conditions."""
        thumb = cv2.resize(full_frame, THUMB_SIZE, interpolation=cv2.INTER_AREA)
        now = monotonic()

        # Check for loading keywords or dark transition
        loading_keyword = extract_loading_word(detected_text)
        loading_dark = is_dark_frame(thumb)
        self.is_loading = bool(loading_keyword or loading_dark)

        if self.last_thumb is None:
            self.last_thumb = thumb
            self.last_change_time = now
            return

        # Calculate pixel diff
        diff = cv2.absdiff(self.last_thumb, thumb)
        if diff.ndim == 3:
            diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        changed_pixels = int(np.count_nonzero(diff > PIXEL_DIFF))

        if changed_pixels >= CHANGED_PIXELS:
            # Screen moved
            self.last_change_time = now
            self.last_thumb = thumb
            self.ineffective_press_count = 0
        else:
            # Screen has not moved
            still_duration = now - self.last_change_time
            allowed_timeout = self.loading_timeout if self.is_loading else self.stuck_timeout

            if still_duration > allowed_timeout:
                status_desc = "加载中画面超时" if self.is_loading else "游戏画面完全静止卡死"
                msg = f"{status_desc} ({still_duration:.1f}s > 门限 {allowed_timeout:.1f}s)"
                logger.error(msg)
                raise FrozenScreen(msg)
