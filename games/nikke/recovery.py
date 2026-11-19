"""Deterministic recovery system for NIKKE: Multi-step return to lobby and modal sweeper.

Follows the YES-BD2 recovery protocol:
1. Sweep active modals (pass popups, level-up notices, settlement cards).
2. Click top-left back navigation.
3. Fallback to AttachThreadInput-protected tap_escape.
4. Verify lobby return by identifying bottom navigation menu.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from games.nikke.constants import (
    ROI_TOP_LEFT_BACK,
    ROI_HOME_BOTTOM_LOBBY,
    ROI_SAFE_CLICK_BLANK,
    ROI_MODAL_CONFIRM,
    ROI_PASS_POPUP_CLOSE,
)
from games.nikke.interaction import NikkeInteraction
from games.nikke.scene import NikkeScene

logger = logging.getLogger("yes_nikke.recovery")


class NikkeRecovery:
    """Recovery controller ensuring deterministic return to the main game lobby."""

    def __init__(self, ctx: Any = None) -> None:
        self.ctx = ctx
        self._interaction: Optional[NikkeInteraction] = getattr(ctx, "interaction", None)
        self._scene: Optional[NikkeScene] = getattr(ctx, "scene", None)

    @property
    def interact(self) -> NikkeInteraction:
        if self._interaction is None and self.ctx and hasattr(self.ctx, "interaction"):
            self._interaction = self.ctx.interaction
        if self._interaction is None:
            self._interaction = NikkeInteraction()
        return self._interaction

    @property
    def scene(self) -> NikkeScene:
        if self._scene is None and self.ctx and hasattr(self.ctx, "scene"):
            self._scene = self.ctx.scene
        if self._scene is None:
            self._scene = NikkeScene(self.ctx)
        return self._scene

    def sweep_modals(self, max_passes: int = 5) -> int:
        """Dismiss cascaded popups, settlement screens, notices, and PASS promotion modals.

        Returns the number of modal dismissal actions performed.
        """
        dismissed_count = 0

        for pass_idx in range(max_passes):
            # Check if any modal or reward overlay is active
            has_modal = self.scene.has_modal_active()
            has_reward = self.scene.has_reward_claim_modal()

            if not has_modal and not has_reward:
                logger.debug(f"[Recovery] No active modals detected at pass {pass_idx + 1}")
                break

            logger.info(f"[Recovery] Modal detected at pass {pass_idx + 1}, dismissing...")

            # Priority 1: Check pass promotion close button
            if self.scene.check_text_in_roi(("购买PASS", "全新角色"), (400, 20, 500, 300)):
                self.interact.click_rect(ROI_PASS_POPUP_CLOSE)
                dismissed_count += 1
                time.sleep(0.5)
                continue

            # Priority 2: Check confirmation dialogs ("确认", "确定")
            if self.scene.check_text_in_roi(("确认", "确定"), ROI_MODAL_CONFIRM):
                self.interact.click_rect(ROI_MODAL_CONFIRM)
                dismissed_count += 1
                time.sleep(0.5)
                continue

            # Priority 3: Blind click safe lower-center blank area for "点击任意区域关闭"
            self.interact.click_rect(ROI_SAFE_CLICK_BLANK)
            dismissed_count += 1
            time.sleep(0.5)

        return dismissed_count

    def recover_to_home(self, max_attempts: int = 5) -> bool:
        """Deterministically exit any nested game subview or error state back to Home Lobby.

        Execution chain:
        1. Fast-path check: already in Home?
        2. Sweep active modals.
        3. Click top-left back button.
        4. If still blocked, send hardware tap_escape.
        5. Verify presence of lobby bottom navigation.
        """
        logger.info("[Recovery] Starting deterministic recovery to Home Lobby...")

        if self.scene.is_in_home():
            logger.info("[Recovery] Already at Home Lobby.")
            return True

        for attempt in range(1, max_attempts + 1):
            logger.info(f"[Recovery] Recovery cycle {attempt}/{max_attempts}...")

            # 1. Sweep any active modals first
            self.sweep_modals(max_passes=3)
            if self.scene.is_in_home():
                logger.info("[Recovery] Reached Home Lobby after sweeping modals.")
                return True

            # 2. Try clicking top-left back button
            logger.info("[Recovery] Attempting top-left back button click...")
            self.interact.click_rect(ROI_TOP_LEFT_BACK)
            time.sleep(0.6)

            # Check if an exit confirmation popup appeared
            if self.scene.check_text_in_roi(("确认", "确定", "离开"), ROI_MODAL_CONFIRM):
                logger.info("[Recovery] Confirming exit popup...")
                self.interact.click_rect(ROI_MODAL_CONFIRM)
                time.sleep(0.6)

            if self.scene.is_in_home():
                logger.info("[Recovery] Reached Home Lobby after back click.")
                return True

            # 3. Fallback: Dispatch hardware ESC scancode
            logger.info("[Recovery] Back click did not reach Home; dispatching tap_escape...")
            self.interact.tap_escape()
            time.sleep(0.8)

            # 4. Sweep any new popups triggered by ESC
            self.sweep_modals(max_passes=2)

            if self.scene.is_in_home():
                logger.info("[Recovery] Reached Home Lobby after tap_escape.")
                return True

            # 5. Try clicking the bottom lobby tab
            logger.info("[Recovery] Trying bottom Lobby tab click...")
            self.interact.click_rect(ROI_HOME_BOTTOM_LOBBY)
            time.sleep(0.6)

            if self.scene.is_in_home():
                logger.info("[Recovery] Reached Home Lobby after bottom tab click.")
                return True

        final_state = self.scene.is_in_home()
        if final_state:
            logger.info("[Recovery] Deterministic recovery succeeded!")
        else:
            logger.error("[Recovery] Deterministic recovery failed to return to Home Lobby.")
        return final_state
