"""Win32 client area window capture with high-quality 720p normalization.

Features:
- Pure ctypes GDI & PrintWindow implementation (zero thread-bound MFC/win32ui dependencies).
- Supports hardware-accelerated / obscured window capture via PW_RENDERFULLCONTENT.
- Clean fallback to Win32 Client DC BitBlt when PrintWindow returns 0.
- Unified 1280x720 16:9 normalization using anti-aliased cv2.INTER_AREA downsampling.
- Mock frame injection support for offline testing and QA suites.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from ctypes import wintypes
from typing import Any, Optional, Tuple, Union

import cv2
import numpy as np

logger = logging.getLogger("yes_nikke.core.capture")

# Win32 Constants
PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0
BGRA_CHANNELS = 4

# Target Normalized Resolution
TARGET_WIDTH_720P = 1280
TARGET_HEIGHT_720P = 720


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


class _Win32GDI:
    """Thread-safe, direct ctypes Win32 GDI wrapper."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            self.available = False
            return

        self.available = True
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

        HANDLE = ctypes.c_void_p

        # user32 signatures
        self._set_signature(self.user32, "GetDC", HANDLE, [HANDLE])
        self._set_signature(self.user32, "GetWindowDC", HANDLE, [HANDLE])
        self._set_signature(self.user32, "ReleaseDC", ctypes.c_int, [HANDLE, HANDLE])
        self._set_signature(self.user32, "GetClientRect", wintypes.BOOL, [HANDLE, ctypes.POINTER(wintypes.RECT)])
        self._set_signature(self.user32, "GetWindowRect", wintypes.BOOL, [HANDLE, ctypes.POINTER(wintypes.RECT)])
        self._set_signature(self.user32, "ClientToScreen", wintypes.BOOL, [HANDLE, ctypes.POINTER(wintypes.POINT)])
        self._set_signature(self.user32, "PrintWindow", wintypes.BOOL, [HANDLE, HANDLE, wintypes.UINT])
        self._set_signature(self.user32, "IsWindow", wintypes.BOOL, [HANDLE])

        # gdi32 signatures
        self._set_signature(self.gdi32, "CreateCompatibleDC", HANDLE, [HANDLE])
        self._set_signature(self.gdi32, "CreateCompatibleBitmap", HANDLE, [HANDLE, ctypes.c_int, ctypes.c_int])
        self._set_signature(self.gdi32, "SelectObject", HANDLE, [HANDLE, HANDLE])
        self._set_signature(self.gdi32, "DeleteObject", wintypes.BOOL, [HANDLE])
        self._set_signature(self.gdi32, "DeleteDC", wintypes.BOOL, [HANDLE])
        self._set_signature(
            self.gdi32,
            "BitBlt",
            wintypes.BOOL,
            [
                HANDLE,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                HANDLE,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.DWORD,
            ],
        )
        self._set_signature(
            self.gdi32,
            "GetDIBits",
            ctypes.c_int,
            [
                HANDLE,
                HANDLE,
                wintypes.UINT,
                wintypes.UINT,
                ctypes.c_void_p,
                ctypes.POINTER(BITMAPINFO),
                wintypes.UINT,
            ],
        )

    def _set_signature(self, dll: ctypes.WinDLL, name: str, restype: Any, argtypes: list[Any]) -> None:
        func = getattr(dll, name, None)
        if func is not None:
            func.restype = restype
            func.argtypes = argtypes
            setattr(self, name, func)


_gdi_instance: Optional[_Win32GDI] = None


def get_gdi() -> _Win32GDI:
    global _gdi_instance
    if _gdi_instance is None:
        _gdi_instance = _Win32GDI()
    return _gdi_instance


def normalize_to_720p(
    frame: np.ndarray,
    target_width: int = TARGET_WIDTH_720P,
    target_height: int = TARGET_HEIGHT_720P,
) -> np.ndarray:
    """Standardize any frame to 1280x720 baseline.

    Uses cv2.INTER_AREA for high-quality anti-aliasing when downsampling,
    and cv2.INTER_CUBIC when upsampling.
    """
    if frame is None or frame.size == 0:
        raise ValueError("Invalid frame for normalization")

    height, width = frame.shape[:2]
    if width == target_width and height == target_height:
        return frame

    # Interpolation choice: INTER_AREA is optimal for shrinking (retains crisp lines/fonts)
    if width >= target_width and height >= target_height:
        interpolation = cv2.INTER_AREA
    else:
        interpolation = cv2.INTER_CUBIC

    # Direct 16:9 resize
    return cv2.resize(frame, (target_width, target_height), interpolation=interpolation)


class WindowCapture:
    """Win32 window client area frame grabber with 720p normalization."""

    def __init__(self, hwnd: Optional[int] = None) -> None:
        self.hwnd = hwnd or 0
        self._lock = threading.Lock()
        self._compatible_dc: Optional[int] = None
        self._bitmap: Optional[int] = None
        self._buffer_width = 0
        self._buffer_height = 0
        self._mock_frame: Optional[np.ndarray] = None

    def set_hwnd(self, hwnd: int) -> None:
        """Update target window handle and invalidate cached DC buffers."""
        with self._lock:
            if self.hwnd != hwnd:
                self._release_buffers()
                self.hwnd = hwnd

    def set_mock_frame(self, frame: Optional[np.ndarray]) -> None:
        """Set mock frame for headless testing and QA verification."""
        with self._lock:
            self._mock_frame = frame

    def _release_buffers(self) -> None:
        """Release allocated GDI memory DC and bitmap."""
        try:
            global _gdi_instance
            if _gdi_instance is None or not _gdi_instance.available:
                return

            if self._compatible_dc:
                _gdi_instance.DeleteDC(self._compatible_dc)
                self._compatible_dc = None
            if self._bitmap:
                _gdi_instance.DeleteObject(self._bitmap)
                self._bitmap = None
            self._buffer_width = 0
            self._buffer_height = 0
        except Exception:
            pass

    def clean_up(self) -> None:
        """Full cleanup of resources."""
        try:
            with self._lock:
                self._release_buffers()
                self.hwnd = 0
        except Exception:
            pass

    def __del__(self) -> None:
        try:
            self.clean_up()
        except Exception:
            pass

    def get_client_dimensions(self, hwnd: Optional[int] = None) -> Tuple[int, int]:
        """Query client area width and height."""
        target_hwnd = hwnd or self.hwnd
        if not target_hwnd:
            return (0, 0)

        gdi = get_gdi()
        if not gdi.available:
            return (0, 0)

        rect = wintypes.RECT()
        if gdi.GetClientRect(target_hwnd, ctypes.byref(rect)):
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            return (max(0, width), max(0, height))
        return (0, 0)

    def _ensure_buffers(self, source_dc: int, width: int, height: int) -> None:
        gdi = get_gdi()
        if (
            self._compatible_dc
            and self._bitmap
            and self._buffer_width == width
            and self._buffer_height == height
        ):
            return

        self._release_buffers()
        mem_dc = gdi.CreateCompatibleDC(source_dc)
        if not mem_dc:
            raise OSError("CreateCompatibleDC failed")
        bitmap = gdi.CreateCompatibleBitmap(source_dc, width, height)
        if not bitmap:
            gdi.DeleteDC(mem_dc)
            raise OSError("CreateCompatibleBitmap failed")

        self._compatible_dc = int(mem_dc)
        self._bitmap = int(bitmap)
        self._buffer_width = width
        self._buffer_height = height

    def capture_raw(
        self,
        hwnd: Optional[int] = None,
        render_full_content: bool = True,
    ) -> Optional[np.ndarray]:
        """Capture the raw native client area frame as a BGR numpy array."""
        with self._lock:
            if self._mock_frame is not None:
                return self._mock_frame.copy()

            target_hwnd = hwnd or self.hwnd
            if not target_hwnd:
                return None

            gdi = get_gdi()
            if not gdi.available:
                logger.error("Win32 GDI is not available on this platform")
                return None

            if not gdi.IsWindow(target_hwnd):
                logger.warning(f"Window handle {target_hwnd} is no longer valid")
                return None

            width, height = self.get_client_dimensions(target_hwnd)
            if width <= 0 or height <= 0:
                logger.warning(f"Window client area is empty or minimized ({width}x{height})")
                return None

            client_dc = gdi.GetDC(target_hwnd)
            if not client_dc:
                logger.error(f"GetDC failed for hwnd={target_hwnd}")
                return None

            try:
                self._ensure_buffers(client_dc, width, height)
                mem_dc = self._compatible_dc
                bitmap = self._bitmap

                # Select bitmap into memory DC
                old_bitmap = gdi.SelectObject(mem_dc, bitmap)
                if not old_bitmap:
                    raise OSError("SelectObject failed")

                captured_by_print = False
                if render_full_content:
                    # PW_RENDERFULLCONTENT captures hardware-accelerated DirectX/Unity frames
                    # Combining with PW_CLIENTONLY when supported
                    flags = PW_RENDERFULLCONTENT | PW_CLIENTONLY
                    pw_success = gdi.PrintWindow(target_hwnd, mem_dc, flags)
                    if pw_success:
                        captured_by_print = True
                    else:
                        # Fall back to PW_RENDERFULLCONTENT without PW_CLIENTONLY
                        pw_success = gdi.PrintWindow(target_hwnd, mem_dc, PW_RENDERFULLCONTENT)
                        if pw_success:
                            captured_by_print = True

                if not captured_by_print:
                    # BitBlt fallback directly from client DC
                    if not gdi.BitBlt(mem_dc, 0, 0, width, height, client_dc, 0, 0, SRCCOPY):
                        raise OSError(f"BitBlt failed ({ctypes.get_last_error()})")

                # Deselect bitmap prior to GetDIBits
                gdi.SelectObject(mem_dc, old_bitmap)

                # Read pixels via GetDIBits into top-down BGRA numpy array
                info = BITMAPINFO()
                info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                info.bmiHeader.biWidth = width
                info.bmiHeader.biHeight = -height  # negative = top-down DIB
                info.bmiHeader.biPlanes = 1
                info.bmiHeader.biBitCount = 32
                info.bmiHeader.biCompression = BI_RGB

                bgra_image = np.empty((height, width, BGRA_CHANNELS), dtype=np.uint8)
                lines = gdi.GetDIBits(
                    mem_dc,
                    bitmap,
                    0,
                    height,
                    bgra_image.ctypes.data,
                    ctypes.byref(info),
                    DIB_RGB_COLORS,
                )

                if lines != height:
                    raise OSError(f"GetDIBits read {lines}/{height} scanlines")

                # Convert BGRA to standard BGR
                return cv2.cvtColor(bgra_image, cv2.COLOR_BGRA2BGR)

            except Exception as exc:
                logger.error(f"Error capturing window {target_hwnd}: {exc}")
                self._release_buffers()
                return None
            finally:
                gdi.ReleaseDC(target_hwnd, client_dc)

    def capture_720p(
        self,
        hwnd: Optional[int] = None,
        render_full_content: bool = True,
    ) -> Optional[np.ndarray]:
        """Capture raw frame and normalize to 1280x720."""
        raw = self.capture_raw(hwnd=hwnd, render_full_content=render_full_content)
        if raw is None:
            return None
        return normalize_to_720p(raw)

    def get_latest_frame(self, normalize_720p: bool = True) -> Optional[np.ndarray]:
        """Unified capture API expected by BaseGameTask and NikkeTask."""
        if normalize_720p:
            return self.capture_720p()
        return self.capture_raw()


def find_nikke_window() -> int:
    """Auto-detect NIKKE official PC client or Android emulator window handle."""
    try:
        import win32gui
    except ImportError:
        return 0

    # 1. Exact match for Official PC Client
    hwnd = win32gui.FindWindow("UnityWndClass", "NIKKE")
    if hwnd and win32gui.IsWindow(hwnd):
        return hwnd

    hwnd = win32gui.FindWindow(None, "NIKKE")
    if hwnd and win32gui.IsWindow(hwnd):
        return hwnd

    # 2. Enumerate windows matching keywords
    matched_hwnds: list[tuple[int, str, str]] = []

    def _enum_cb(hwnd_item: int, _lparam: Any) -> bool:
        if win32gui.IsWindowVisible(hwnd_item):
            title = win32gui.GetWindowText(hwnd_item)
            cls_name = win32gui.GetClassName(hwnd_item)
            if not title:
                return True
            title_lower = title.lower()
            if "nikke" in title_lower or "胜利女神" in title_lower:
                matched_hwnds.append((hwnd_item, title, cls_name))
            elif any(emu in title_lower for emu in ("mumu", "leidian", "ldplayer", "nox", "夜神")):
                matched_hwnds.append((hwnd_item, title, cls_name))
        return True

    try:
        win32gui.EnumWindows(_enum_cb, None)
    except Exception:
        pass

    if matched_hwnds:
        # Prefer UnityWndClass / NIKKE title
        for h, t, c in matched_hwnds:
            if "nikke" in t.lower() or c == "UnityWndClass":
                return h
        return matched_hwnds[0][0]

    return 0

