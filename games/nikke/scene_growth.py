"""Scene discriminators for NIKKE Growth, Rewards & Tower modules.

Extends NikkeScene with:
- is_in_inquiry: Detects Inquiry (咨询) main screen / Nikke list
- is_in_task_panel: Detects Daily/Weekly Tasks panel (任务面板)
- is_in_tower: Detects Tribe Tower / Unlimited Tower screen (爬塔界面)
"""

from __future__ import annotations

import logging
from typing import Optional
import numpy as np

from games.nikke.scene import NikkeScene
from games.nikke.constants_growth import (
    ROI_INQUIRY_TITLE,
    ROI_INQUIRY_BATCH_BTN,
    ROI_TASK_TITLE,
    ROI_TASK_WEEKLY_TAB,
    ROI_TASK_DAILY_TAB,
    ROI_TASK_CLAIM_ALL_BTN,
    ROI_TOWER_TITLE,
    ROI_TOWER_UNLIMITED_TAG,
    ROI_TOWER_FORMATION_TAG,
    ROI_TOWER_ENTER_FIGHT_BTN,
    TEXT_INQUIRY_TITLE,
    TEXT_INQUIRY_BATCH,
    TEXT_TASK_TITLE,
    TEXT_TASK_WEEKLY,
    TEXT_TASK_DAILY,
    TEXT_TASK_CLAIM_ALL,
    TEXT_TOWER_TITLE,
    TEXT_TOWER_UNLIMITED,
    TEXT_TOWER_ENTER_FIGHT,
)

logger = logging.getLogger("yes_nikke.scene.growth")


def is_in_inquiry(self: NikkeScene, frame: Optional[np.ndarray] = None) -> bool:
    """Determine whether the current screen is the Inquiry (咨询) panel or Nikke list."""
    if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
        return self.ctx.mock_scene_state in ("inquiry", "nikke_list", "inquiry_gift")

    curr_frame = self._get_frame(frame)

    # 1. Check title area for "咨询"
    if self.check_text_in_roi(TEXT_INQUIRY_TITLE, ROI_INQUIRY_TITLE, frame=curr_frame):
        return True

    # 2. Check batch inquiry button "批量咨询"
    if self.check_text_in_roi(TEXT_INQUIRY_BATCH, ROI_INQUIRY_BATCH_BTN, frame=curr_frame):
        return True

    return False


def is_in_task_panel(self: NikkeScene, frame: Optional[np.ndarray] = None) -> bool:
    """Determine whether the current screen is the Task dialog (任务界面)."""
    if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
        return self.ctx.mock_scene_state in ("task", "task_panel", "daily_rewards")

    curr_frame = self._get_frame(frame)

    # 1. Check title area for "任务"
    if self.check_text_in_roi(TEXT_TASK_TITLE, ROI_TASK_TITLE, frame=curr_frame):
        return True

    # 2. Check weekly / daily task tabs
    if self.check_text_in_roi(TEXT_TASK_WEEKLY, ROI_TASK_WEEKLY_TAB, frame=curr_frame):
        return True
    if self.check_text_in_roi(TEXT_TASK_DAILY, ROI_TASK_DAILY_TAB, frame=curr_frame):
        return True

    # 3. Check claim all button
    if self.check_text_in_roi(TEXT_TASK_CLAIM_ALL, ROI_TASK_CLAIM_ALL_BTN, frame=curr_frame):
        return True

    return False


def is_in_tower(self: NikkeScene, frame: Optional[np.ndarray] = None) -> bool:
    """Determine whether the current screen is within Tribe Tower / Unlimited Tower."""
    if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
        return self.ctx.mock_scene_state in ("tower", "climb_tower", "unlimited_tower", "cop_tower")

    curr_frame = self._get_frame(frame)

    # 1. Check title area for "塔"
    if self.check_text_in_roi(TEXT_TOWER_TITLE, ROI_TOWER_TITLE, frame=curr_frame):
        return True

    # 2. Check unlimited tower entry or formation tags
    if self.check_text_in_roi(TEXT_TOWER_UNLIMITED, ROI_TOWER_UNLIMITED_TAG, frame=curr_frame):
        return True
    if self.check_text_in_roi("通关阵容", ROI_TOWER_FORMATION_TAG, frame=curr_frame):
        return True

    # 3. Check enter fight button
    if self.check_text_in_roi(TEXT_TOWER_ENTER_FIGHT, ROI_TOWER_ENTER_FIGHT_BTN, frame=curr_frame):
        return True

    return False


# Dynamically attach to NikkeScene class for backward and cross-module compatibility
setattr(NikkeScene, "is_in_inquiry", is_in_inquiry)
setattr(NikkeScene, "is_in_task_panel", is_in_task_panel)
setattr(NikkeScene, "is_in_tower", is_in_tower)
