"""Scene discriminators for Ark, SimRoom, Interception, and Arena.

Provides deterministic predicates for identifying game states:
- Ark Hub (is_in_ark)
- Simulation Room (is_in_sim_room)
- Interception (is_in_interception)
- Arena (is_in_arena)
"""

from __future__ import annotations

import logging
from typing import Optional
import numpy as np

from games.nikke.scene import NikkeScene
from games.nikke.constants_combat import (
    ROI_ARK_TITLE,
    ROI_ARK_TITLE_ALT,
    ROI_ARK_SIM_ROOM,
    ROI_ARK_INTERCEPTION,
    ROI_ARK_ARENA,
    ROI_SIM_START_BTN,
    ROI_SIM_5C_SECTOR,
    ROI_SIM_QUICK_BTN,
    ROI_INTERCEPTION_TITLE,
    ROI_INTERCEPTION_ATTEMPTS,
    ROI_INTERCEPTION_QUICK_BATTLE_BTN,
    ROI_ARENA_TITLE,
    ROI_ARENA_PAGE_HEADER,
    ROI_ARENA_ROOKIE_BTN,
    ROI_ARENA_SPECIAL_BTN,
    TEXT_ARK_TITLE,
    TEXT_ARK_SUB_SIM,
    TEXT_ARK_SUB_INTERCEPTION,
    TEXT_ARK_SUB_ARENA,
    TEXT_SIM_TITLE,
    TEXT_SIM_START,
    TEXT_SIM_5C,
    TEXT_INTERCEPTION_TITLE,
    TEXT_INTERCEPTION_ATTEMPTS,
    TEXT_INTERCEPTION_QUICK_BATTLE,
    TEXT_ARENA_TITLE,
    TEXT_ARENA_ROOKIE,
    TEXT_ARENA_SPECIAL,
)

logger = logging.getLogger("yes_nikke.scene_combat")


def is_in_ark(self: NikkeScene, frame: Optional[np.ndarray] = None) -> bool:
    """Determine whether current screen is the Ark Hub.

    Criteria:
    1. Context hook overrides (e.g. mock_scene_state == 'ark').
    2. Header title matches '方舟' / 'ARK'.
    3. Ark sub-entrances present (SimRoom / Interception / Arena).
    """
    if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
        return self.ctx.mock_scene_state == "ark"

    curr_frame = self._get_frame(frame)

    if self.check_text_in_roi(TEXT_ARK_TITLE, ROI_ARK_TITLE, frame=curr_frame):
        return True
    if self.check_text_in_roi(TEXT_ARK_TITLE, ROI_ARK_TITLE_ALT, frame=curr_frame):
        return True

    # Check for presence of Ark sub-entrance buttons
    has_sim = self.check_text_in_roi(TEXT_ARK_SUB_SIM, ROI_ARK_SIM_ROOM, frame=curr_frame)
    has_inter = self.check_text_in_roi(TEXT_ARK_SUB_INTERCEPTION, ROI_ARK_INTERCEPTION, frame=curr_frame)
    has_arena = self.check_text_in_roi(TEXT_ARK_SUB_ARENA, ROI_ARK_ARENA, frame=curr_frame)
    if (has_sim and has_inter) or (has_sim and has_arena) or (has_inter and has_arena):
        return True

    return False


def is_in_sim_room(self: NikkeScene, frame: Optional[np.ndarray] = None) -> bool:
    """Determine whether current screen is within Simulation Room.

    Criteria:
    1. Context hook overrides (mock_scene_state == 'sim_room').
    2. Header matches '模拟室'.
    3. Presence of '开始模拟' or '5-C' or '快速模拟'.
    """
    if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
        return self.ctx.mock_scene_state == "sim_room"

    curr_frame = self._get_frame(frame)

    if self.check_text_in_roi(TEXT_SIM_TITLE, (0, 0, 300, 100), frame=curr_frame):
        return True
    if self.check_text_in_roi(TEXT_SIM_START, ROI_SIM_START_BTN, frame=curr_frame):
        return True
    if self.check_text_in_roi(TEXT_SIM_5C, ROI_SIM_5C_SECTOR, frame=curr_frame):
        return True
    if self.check_text_in_roi(TEXT_SIM_QUICK, ROI_SIM_QUICK_BTN, frame=curr_frame):
        return True

    return False


def is_in_interception(self: NikkeScene, frame: Optional[np.ndarray] = None) -> bool:
    """Determine whether current screen is within Interception.

    Criteria:
    1. Context hook overrides (mock_scene_state == 'interception').
    2. Header matches '拦截战'.
    3. Presence of '剩余拦截次数' or '快速战斗'.
    """
    if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
        return self.ctx.mock_scene_state == "interception"

    curr_frame = self._get_frame(frame)

    if self.check_text_in_roi(TEXT_INTERCEPTION_TITLE, ROI_INTERCEPTION_TITLE, frame=curr_frame):
        return True
    if self.check_text_in_roi(TEXT_INTERCEPTION_ATTEMPTS, ROI_INTERCEPTION_ATTEMPTS, frame=curr_frame):
        return True
    if self.check_text_in_roi(TEXT_INTERCEPTION_QUICK_BATTLE, ROI_INTERCEPTION_QUICK_BATTLE_BTN, frame=curr_frame):
        return True

    return False


def is_in_arena(self: NikkeScene, frame: Optional[np.ndarray] = None) -> bool:
    """Determine whether current screen is within Arena Hub or its sub-modes.

    Criteria:
    1. Context hook overrides (mock_scene_state in ('arena', 'arena_rookie', 'arena_special')).
    2. Header matches '竞技场' or 'ARENA'.
    3. Sub-modes '新人竞技场' or '特殊竞技场' visible.
    """
    if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
        return self.ctx.mock_scene_state in ("arena", "arena_rookie", "arena_special")

    curr_frame = self._get_frame(frame)

    if self.check_text_in_roi(TEXT_ARENA_TITLE, ROI_ARENA_TITLE, frame=curr_frame):
        return True
    if self.check_text_in_roi(TEXT_ARENA_TITLE, ROI_ARENA_PAGE_HEADER, frame=curr_frame):
        return True
    if self.check_text_in_roi(TEXT_ARENA_ROOKIE, ROI_ARENA_ROOKIE_BTN, frame=curr_frame):
        return True
    if self.check_text_in_roi(TEXT_ARENA_SPECIAL, ROI_ARENA_SPECIAL_BTN, frame=curr_frame):
        return True

    return False


# Monkey-patch predicates onto NikkeScene class for transparent access via self.scene
NikkeScene.is_in_ark = is_in_ark
NikkeScene.is_in_sim_room = is_in_sim_room
NikkeScene.is_in_interception = is_in_interception
NikkeScene.is_in_arena = is_in_arena
