"""Abstract base class for deterministic game tasks.

Standardizes:
- Full task lifecycle (setup, run, teardown, execute)
- Context holding (capturer, interaction, scene, watchdogs, config)
- Structured logging and diagnostic problem reporting integration
- 720p normalized capture pipeline
- Responsive look_again polling and OCR with adaptive reread
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, TypeVar

import numpy as np

from core.capture import normalize_to_720p
from core.vision.ocr_reread import ocr_with_reread

T = TypeVar("T")


class BaseGameTask(ABC):
    """Abstract base class for automated game tasks with standardized lifecycle."""

    def __init__(self, ctx: Any = None, name: Optional[str] = None) -> None:
        self.ctx = ctx
        self.name = name or self.__class__.__name__
        self.logger = getattr(ctx, "logger", None) or logging.getLogger(f"task.{self.name}")
        self.is_running: bool = False
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.duration: float = 0.0
        self._cooldown_cache: dict[str, float] = {}

    def setup(self) -> None:
        """Lifecycle hook: pre-task initialization, watchdog reset, and state check.

        Subclasses may override to prepare state before run().
        """
        if self.ctx and hasattr(self.ctx, "frozen_watch"):
            try:
                self.ctx.frozen_watch.reset()
            except Exception as exc:
                self.logger.warning(f"[{self.name}] Failed to reset frozen_watch: {exc}")

    @abstractmethod
    def run(self) -> Any:
        """Lifecycle hook: main task routine to be implemented by concrete tasks."""
        pass

    def teardown(self, exc: Optional[Exception] = None) -> None:
        """Lifecycle hook: post-task cleanup executed whether task succeeds or fails.

        Subclasses may override to reset UI state or clean up resources.
        """
        pass

    def execute(self) -> Any:
        """Standard execution harness coordinating setup, run, teardown and diagnostics."""
        self.start_time = time.monotonic()
        self.is_running = True
        self.log_info(f"任务 [{self.name}] 开始执行...")

        try:
            self.setup()
            result = self.run()
            self.teardown(None)
            self.duration = time.monotonic() - self.start_time
            self.log_info(f"任务 [{self.name}] 顺利完成，耗时 {self.duration:.2f}s")
            return result
        except Exception as exc:
            self.duration = time.monotonic() - self.start_time
            self.log_error(f"任务 [{self.name}] 异常中断 (运行 {self.duration:.2f}s): {exc}")

            # Export diagnostic report if ProblemReport is configured in ctx
            if self.ctx and hasattr(self.ctx, "problem_report"):
                try:
                    report_dir = getattr(self.ctx, "report_dir", "reports")
                    last_frame = None
                    if hasattr(self.ctx, "capture") and self.ctx.capture is not None:
                        last_frame = self.ctx.capture.get_latest_frame(normalize_720p=False)
                    self.ctx.problem_report.export_report(
                        output_dir=report_dir,
                        task_name=self.name,
                        error_msg=str(exc),
                        final_frame=last_frame,
                    )
                except Exception as rpt_err:
                    self.logger.warning(f"[{self.name}] 诊断日志导出失败: {rpt_err}")

            self.teardown(exc)
            raise
        finally:
            self.end_time = time.monotonic()
            self.is_running = False

    def __call__(self) -> Any:
        """Allow task instances to be called directly."""
        return self.execute()

    # --- Logging & Diagnostic Helpers ---

    def log_info(self, msg: str) -> None:
        self.logger.info(f"[{self.name}] {msg}")

    def log_warning(self, msg: str) -> None:
        self.logger.warning(f"[{self.name}] {msg}")

    def log_error(self, msg: str) -> None:
        self.logger.error(f"[{self.name}] {msg}")

    def record_step(self, step_name: str) -> None:
        """Record step transition in problem report if available."""
        self.log_info(f"--> {step_name}")
        if self.ctx and hasattr(self.ctx, "problem_report"):
            try:
                self.ctx.problem_report.record_step(f"{self.name}::{step_name}")
            except Exception:
                pass

    # --- Execution & Vision Helpers ---

    def sleep(self, seconds: float) -> None:
        """Task-aware sleep."""
        time.sleep(max(0.0, float(seconds)))

    def capture_720p(self) -> np.ndarray:
        """Capture current game frame and normalize to standard 1280x720 baseline."""
        if self.ctx and hasattr(self.ctx, "capture") and self.ctx.capture is not None:
            frame = self.ctx.capture.get_latest_frame(normalize_720p=True)
            if frame is not None:
                # Update problem report retrospective frame buffer
                if hasattr(self.ctx, "problem_report") and self.ctx.problem_report is not None:
                    try:
                        self.ctx.problem_report.sample_frame(frame)
                    except Exception:
                        pass
                return frame

        # Default fallback frame if capture is not bound
        return np.zeros((720, 1280, 3), dtype=np.uint8)

    def normalize_to_720p(self, frame: np.ndarray) -> np.ndarray:
        """Normalize arbitrary 16:9 frame to 1280x720."""
        return normalize_to_720p(frame)

    def look_again(
        self,
        predicate: Callable[[], T],
        label: str = "",
        grace: float = 5.0,
        poll_interval: float = 0.25,
    ) -> Optional[T]:
        """Poll ``predicate`` until it returns a truthy value, up to ``grace`` seconds.

        Returns immediately once found to avoid unnecessary lag.
        """
        result = predicate()
        if result:
            return result

        waited = 0.0
        while not result and waited < grace:
            step = min(poll_interval, grace - waited)
            self.sleep(step)
            waited += step
            result = predicate()
            if result:
                return result

        return result

    def ocr(
        self,
        frame: Optional[np.ndarray] = None,
        name: str = "",
        reread: bool = True,
        **kwargs: Any,
    ) -> list:
        """Run OCR on target frame with automatic bordered and multi-scale reread if empty.

        Uses ``ctx.ocr_engine`` or ``ctx.vision.ocr`` if available.
        """
        target_frame = frame if frame is not None else self.capture_720p()

        ocr_engine = None
        if self.ctx is not None:
            if hasattr(self.ctx, "ocr_engine") and hasattr(self.ctx.ocr_engine, "ocr"):
                ocr_engine = self.ctx.ocr_engine.ocr
            elif hasattr(self.ctx, "vision") and hasattr(self.ctx.vision, "ocr"):
                ocr_engine = self.ctx.vision.ocr

        if ocr_engine is None:
            self.log_warning("OCR engine not configured in context; returning empty result")
            return []

        return ocr_with_reread(
            ocr_func=ocr_engine,
            frame=target_frame,
            name=name,
            cooldown_cache=self._cooldown_cache,
            reread=reread,
            **kwargs,
        )
