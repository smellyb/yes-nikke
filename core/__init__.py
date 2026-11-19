"""Core infrastructure package for YES-NIKKE."""

from core.base_task import BaseGameTask
from core.capture import WindowCapture, normalize_to_720p

__all__ = [
    "BaseGameTask",
    "WindowCapture",
    "normalize_to_720p",
]
