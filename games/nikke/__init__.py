"""NIKKE vertical adaptation layer for YES-NIKKE."""

from games.nikke.constants import (
    BASE_WIDTH,
    BASE_HEIGHT,
    BASE_RESOLUTION,
    ROI_HOME_OUTPOST_BTN,
    ROI_TITLE,
    ROI_CLAIM_BTN,
    ROI_SWEEP_BTN,
    ROI_SWEEP_CONFIRM_BTN,
    ROI_SWEEP_FREE_TAG,
    ROI_GLOBAL_CLOSE,
)
from games.nikke.interaction import NikkeInteraction
from games.nikke.scene import NikkeScene
from games.nikke.recovery import NikkeRecovery
from games.nikke.base_nikke_task import NikkeTask
from games.nikke.tasks.outpost_defense import OutpostDefenseTask

__all__ = [
    "BASE_WIDTH",
    "BASE_HEIGHT",
    "BASE_RESOLUTION",
    "ROI_HOME_OUTPOST_BTN",
    "ROI_TITLE",
    "ROI_CLAIM_BTN",
    "ROI_SWEEP_BTN",
    "ROI_SWEEP_CONFIRM_BTN",
    "ROI_SWEEP_FREE_TAG",
    "ROI_GLOBAL_CLOSE",
    "NikkeInteraction",
    "NikkeScene",
    "NikkeRecovery",
    "NikkeTask",
    "OutpostDefenseTask",
]
