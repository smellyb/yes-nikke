"""NIKKE interaction engine: Win32 message dispatch, closed-loop confirmation, jitter injection, and hardware ESC.

Follows YES-BD2 deterministic interaction standards:
- Background clicks via Win32 PostMessage (WM_LBUTTONDOWN/UP).
- Jitter injection within safe inner-padded bounding boxes (d = min(w, h) * 0.15).
- Closed-loop press_and_confirm with state divergence abort and currency protection.
- AttachThreadInput protected foreground hardware scancode ESC (VK_ESCAPE 0x01).
"""

from __future__ import annotations

import logging
import random
import sys
import time
from typing import Any, Callable, Optional, Tuple, Union

from core.ops.press_confirm import PressOutcome, press_and_confirm as core_press_and_confirm

logger = logging.getLogger("yes_nikke.interaction")

# Win32 Constants
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001
VK_ESCAPE = 0x1B
KEYEVENTF_KEYUP = 0x0002
SCANCODE_ESCAPE = 0x01

# Optional Win32 dependencies with graceful fallback for CI / mock testing
try:
    import win32api
    import win32con
    import win32gui
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


def _makelong(low: int, high: int) -> int:
    """Pack two 16-bit integers into a 32-bit LPARAM."""
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


class NikkeInteraction:
    """NIKKE interaction controller handling background clicks, confirmation loops, and keyboard escape."""

    def __init__(
        self,
        hwnd: int = 0,
        get_scale: Optional[Callable[[], Union[float, Tuple[float, float]]]] = None,
        watchdog: Optional[Any] = None,
    ) -> None:
        self.hwnd = hwnd
        self._get_scale = get_scale or (lambda: 1.0)
        self.watchdog = watchdog
        self.last_clicked_pos: Optional[Tuple[int, int]] = None
        self.total_clicks: int = 0

    def get_scale_factors(self) -> Tuple[float, float]:
        """Retrieve current scaling factors from 1280x720 logical coordinates to physical window."""
        try:
            scale_val = self._get_scale()
            if isinstance(scale_val, (tuple, list)):
                return float(scale_val[0]), float(scale_val[1])
            elif float(scale_val) != 1.0:
                return float(scale_val), float(scale_val)

            if self.hwnd and HAS_WIN32:
                rect = win32gui.GetClientRect(self.hwnd)
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                if w > 0 and h > 0:
                    return w / 1280.0, h / 720.0
            return 1.0, 1.0
        except Exception:
            return 1.0, 1.0

    def to_client_pos(self, x_720p: int, y_720p: int) -> Tuple[int, int]:
        """Map 1280x720 logical coordinates to client window pixel positions."""
        sx, sy = self.get_scale_factors()
        return round(x_720p * sx), round(y_720p * sy)

    def post_click(self, client_x: int, client_y: int, hold_ms: int = 50) -> None:
        """Dispatch precise background mouse click via Win32 PostMessage."""
        self.total_clicks += 1
        if self.watchdog and hasattr(self.watchdog, "notify_press"):
            try:
                self.watchdog.notify_press()
            except Exception:
                pass

        if not HAS_WIN32 or not self.hwnd:
            logger.debug(f"[MockClick] PostMessage click to ({client_x}, {client_y}) [hwnd={self.hwnd}]")
            time.sleep(max(0.001, hold_ms / 1000.0))
            return

        try:
            lparam = _makelong(client_x, client_y)
            win32gui.PostMessage(self.hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
            time.sleep(max(0.001, hold_ms / 1000.0))
            win32gui.PostMessage(self.hwnd, WM_LBUTTONUP, 0, lparam)
            logger.debug(f"PostMessage WM_LBUTTONDOWN/UP to hwnd={self.hwnd} at ({client_x}, {client_y})")
        except Exception as exc:
            logger.warning(f"Failed to post Win32 click to hwnd {self.hwnd}: {exc}")

    def click_rect(
        self,
        rect_720p: Tuple[int, int, int, int],
        inner_padding: float = 0.2,
        hold_ms: int = 50,
    ) -> Tuple[int, int]:
        """Click within logical bounding box with randomized micro-jitter inside safe margins.

        Jitter formula:
        pad_w = rw * inner_padding
        pad_h = rh * inner_padding
        target_x ~ U(rx + pad_w, rx + rw - pad_w)
        target_y ~ U(ry + pad_h, ry + rh - pad_h)
        """
        rx, ry, rw, rh = rect_720p
        inner_padding = max(0.0, min(0.45, float(inner_padding)))

        pad_w = rw * inner_padding
        pad_h = rh * inner_padding
        avail_w = max(1.0, rw - 2 * pad_w)
        avail_h = max(1.0, rh - 2 * pad_h)

        target_x_720 = rx + pad_w + random.random() * avail_w
        target_y_720 = ry + pad_h + random.random() * avail_h

        cx, cy = self.to_client_pos(int(target_x_720), int(target_y_720))
        self.post_click(cx, cy, hold_ms=hold_ms)
        self.last_clicked_pos = (int(target_x_720), int(target_y_720))
        return int(target_x_720), int(target_y_720)

    def press_and_confirm(
        self,
        label: str,
        press_action: Callable[[], Any],
        confirmed_check: Callable[[], Any],
        still_before_check: Optional[Callable[[], Any]] = None,
        timeout: float = 3.0,
        retry_after: float = 1.5,
        retries: int = 1,
        poll_interval: float = 0.25,
        log: Optional[Callable[[str], Any]] = None,
    ) -> bool:
        """Closed-loop confirmation protocol ensuring deterministic screen state transitions.

        Prevents blind re-clicks when the screen has moved on or when performing currency-spending actions.
        """
        log_fn = log or logger.info
        outcome: PressOutcome = core_press_and_confirm(
            label=label,
            press=press_action,
            confirmed=confirmed_check,
            still_before=still_before_check,
            timeout=timeout,
            retry_after=retry_after,
            retries=retries,
            poll=poll_interval,
            log=log_fn,
        )
        return bool(outcome.confirmed)

    def tap_escape(self) -> bool:
        """Trigger foreground hardware scan code ESC (0x01) with AttachThreadInput protection.

        Restores the previous foreground window immediately after sending the keystroke.
        """
        logger.info("Executing tap_escape with hardware scancode (0x01)...")

        if not HAS_WIN32 or sys.platform != "win32" or not self.hwnd:
            logger.debug(f"[MockEscape] Hardware scan code ESC dispatched [hwnd={self.hwnd}]")
            time.sleep(0.08)
            return True

        fore_hwnd = win32gui.GetForegroundWindow()
        cur_thread = win32api.GetCurrentThreadId()
        fore_thread, _ = win32process.GetWindowThreadProcessId(fore_hwnd)
        attached = False

        try:
            if fore_thread != cur_thread and fore_thread != 0:
                win32process.AttachThreadInput(cur_thread, fore_thread, True)
                attached = True

            win32gui.SetForegroundWindow(self.hwnd)
            time.sleep(0.03)

            # Send hardware scancode 0x01 for VK_ESCAPE
            win32api.keybd_event(VK_ESCAPE, SCANCODE_ESCAPE, 0, 0)
            time.sleep(0.04)
            win32api.keybd_event(VK_ESCAPE, SCANCODE_ESCAPE, KEYEVENTF_KEYUP, 0)
            time.sleep(0.03)
            return True

        except Exception as exc:
            logger.warning(f"Error during tap_escape AttachThreadInput/keybd_event: {exc}")
            return False

        finally:
            if fore_hwnd and fore_hwnd != self.hwnd:
                try:
                    win32gui.SetForegroundWindow(fore_hwnd)
                except Exception:
                    pass
            if attached:
                try:
                    win32process.AttachThreadInput(cur_thread, fore_thread, False)
                except Exception:
                    pass
