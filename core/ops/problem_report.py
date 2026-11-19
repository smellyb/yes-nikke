"""Diagnostic reporter with 10-second retrospective thumbnails and in-memory log ring.

When an unexpected exception, FrozenScreen, or assertion failure occurs,
ProblemReport generates a sanitized diagnostic archive containing:
1. The exact failure reason and stack trace;
2. Recent 15 step transitions;
3. 5 retrospective thumbnails taken every 2.0s prior to failure;
4. The high-resolution failure frame.
"""

from __future__ import annotations

import collections
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Deque, Optional, Tuple, Any
import cv2
import numpy as np

logger = logging.getLogger("yes_nikke.ops.problem_report")


@dataclass(frozen=True)
class FrameSample:
    timestamp: float
    thumbnail: np.ndarray  # 480x270 thumbnail


class LogRingHandler(logging.Handler):
    """Ring buffer holding the most recent 600 log lines."""

    def __init__(self, capacity: int = 600):
        super().__init__()
        self.buffer: Deque[str] = collections.deque(maxlen=capacity)
        self.lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with self.lock:
                self.buffer.append(msg)
        except Exception:
            self.handleError(record)

    def get_lines(self) -> list[str]:
        with self.lock:
            return list(self.buffer)


class ProblemReport:
    """Manages failure frame buffers and generates diagnostic reports."""

    def __init__(self, log_capacity: int = 600, max_retrospective_frames: int = 5):
        self.log_handler = LogRingHandler(capacity=log_capacity)
        self.log_handler.setFormatter(
            logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
        )
        self.frame_buffer: Deque[FrameSample] = collections.deque(maxlen=max_retrospective_frames)
        self.step_history: Deque[str] = collections.deque(maxlen=20)
        self.lock = threading.Lock()
        self.last_sample_time = 0.0

    def record_step(self, step_name: str) -> None:
        """Record step transition."""
        with self.lock:
            timestamp = time.strftime("%H:%M:%S")
            self.step_history.append(f"[{timestamp}] {step_name}")

    def sample_frame(self, full_frame: np.ndarray, min_interval_sec: float = 2.0) -> None:
        """Sample a thumbnail every min_interval_sec for retrospective debugging."""
        now = time.monotonic()
        if now - self.last_sample_time < min_interval_sec:
            return

        with self.lock:
            self.last_sample_time = now
            # Resize to 480x270 thumbnail
            thumb = cv2.resize(full_frame, (480, 270), interpolation=cv2.INTER_AREA)
            self.frame_buffer.append(FrameSample(timestamp=time.time(), thumbnail=thumb.copy()))

    def export_report(
        self,
        output_dir: str,
        task_name: str,
        error_msg: str,
        final_frame: Optional[np.ndarray] = None,
    ) -> str:
        """Export full diagnostic bundle to output_dir."""
        os.makedirs(output_dir, exist_ok=True)
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        report_dir = os.path.join(output_dir, f"report_{task_name}_{timestamp_str}")
        os.makedirs(report_dir, exist_ok=True)

        # 1. Write text summary & log
        summary_path = os.path.join(report_dir, "summary.txt")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(f"Task: {task_name}\n")
            f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Error: {error_msg}\n\n")
            f.write("=== Recent Step History ===\n")
            with self.lock:
                for step in self.step_history:
                    f.write(f"{step}\n")
            f.write("\n=== Recent Logs ===\n")
            for line in self.log_handler.get_lines():
                f.write(f"{line}\n")

        # 2. Save final frame
        if final_frame is not None:
            cv2.imwrite(os.path.join(report_dir, "final_frame.png"), final_frame)

        # 3. Save retrospective thumbnails
        with self.lock:
            for idx, sample in enumerate(self.frame_buffer):
                fn = f"retro_{idx + 1:02d}_{int(sample.timestamp)}.png"
                cv2.imwrite(os.path.join(report_dir, fn), sample.thumbnail)

        logger.info(f"已生成故障诊断报告: {report_dir}")
        return report_dir
