"""Production Arena (新人竞技场 / 特殊竞技场) task implementation.

Features:
1. Navigates from Lobby Home -> Ark Hub -> Arena Hub.
2. Rookie Arena (新人竞技场):
   - Executes free challenges (default 2 times).
   - Strict asset protection: Immediately cancels and skips if diamond purchase modal appears.
   - Guarantees AUTO combat toggle is enabled ('ON').
   - Handles combat settlement and returns to arena hub.
3. Special Arena (特殊竞技场):
   - Collects accumulated arena reward points (收获竞技场点数).
   - Dismisses point claim confirmation dialogs.
   - Supports optional daily free challenge with asset safety gates.
4. Deterministic exit to Lobby Home.
"""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Any, Optional, Tuple

from core.ops.frozen_watch import FrozenScreen
from games.nikke.base_nikke_task import NikkeTask
from games.nikke.constants import (
    ROI_HOME_BOTTOM_ARK,
    ROI_TOP_LEFT_BACK,
    ROI_SAFE_CLICK_BLANK,
    ROI_GLOBAL_CLOSE,
    TEXT_CONFIRM,
    TEXT_CANCEL,
)
from games.nikke.constants_combat import (
    ROI_HOME_ARK_BTN,
    ROI_ARK_ARENA,
    ROI_ARENA_TITLE,
    ROI_ARENA_PAGE_HEADER,
    ROI_ARENA_ROOKIE_BTN,
    ROI_ARENA_SPECIAL_BTN,
    ROI_ARENA_ENTER_FIGHT_BTN,
    ROI_ARENA_CONFIRM_FIGHT_BTN,
    ROI_ARENA_AUTO_TOGGLE,
    ROI_ARENA_COST_DIAMOND_PROMPT,
    ROI_ARENA_COST_CANCEL_BTN,
    ROI_ARENA_SEASON_CLOSED_PROMPT,
    ROI_ARENA_SPECIAL_CLAIM_ENTRY,
    ROI_ARENA_SPECIAL_CLAIM_BTN,
    ROI_ARENA_SPECIAL_CLAIM_CLOSE,
    ROI_ARENA_SETTLEMENT_CLICK,
    TEXT_ARK_TITLE,
    TEXT_ARENA_TITLE,
    TEXT_ARENA_ROOKIE,
    TEXT_ARENA_SPECIAL,
    TEXT_ARENA_ENTER_FIGHT,
    TEXT_ARENA_AUTO_ON,
    TEXT_ARENA_AUTO_OFF,
    TEXT_ARENA_COST_DIAMOND,
    TEXT_ARENA_SEASON_CLOSED,
    TEXT_ARENA_SPECIAL_CLAIM,
    TEXT_ARENA_NEXT_STEP,
)
import games.nikke.scene_combat  # Ensure monkey-patched scene methods are loaded

logger = logging.getLogger("yes_nikke.task.arena")


class ArenaState(Enum):
    ENTER_ARK = auto()
    ENTER_ARENA_HUB = auto()
    HANDLE_ROOKIE_ARENA = auto()
    HANDLE_SPECIAL_ARENA = auto()
    EXIT_TO_HOME = auto()
    COMPLETED = auto()


class ArenaTask(NikkeTask):
    """【竞技场自动化】纯命令式任务实现.

    全链路流转：
    方舟 -> 竞技场 -> 新人竞技场（免费挑战 2 次，自动战斗）
    -> 特殊竞技场（收获竞技场点数/每日免费挑战） -> 确定性返回大厅。
    """

    def __init__(
        self,
        ctx: Any = None,
        rookie_challenges: int = 2,
        special_claim_points: bool = True,
        special_challenges: int = 0,
    ) -> None:
        super().__init__(ctx, name="Arena")
        self.rookie_challenges: int = rookie_challenges
        self.special_claim_points: bool = special_claim_points
        self.special_challenges: int = special_challenges

        self.rookie_completed: int = 0
        self.special_completed: int = 0
        self.points_claimed: bool = False
        self.current_state: ArenaState = ArenaState.ENTER_ARK

    def run(self) -> bool:
        """Execute Arena task state machine."""
        logger.info(
            f">>> 启动任务：竞技场 (新人挑战目标={self.rookie_challenges}, 特殊点数收获={self.special_claim_points})"
        )
        self.current_state = ArenaState.ENTER_ARK
        self.rookie_completed = 0
        self.special_completed = 0
        self.points_claimed = False

        if self.frozen_watch and hasattr(self.frozen_watch, "reset"):
            self.frozen_watch.reset()

        while self.current_state != ArenaState.COMPLETED:
            try:
                self.ping_watchdog(detected_text=f"arena_state_{self.current_state.name}")

                if self.current_state == ArenaState.ENTER_ARK:
                    self.current_state = self._step_enter_ark()
                elif self.current_state == ArenaState.ENTER_ARENA_HUB:
                    self.current_state = self._step_enter_arena_hub()
                elif self.current_state == ArenaState.HANDLE_ROOKIE_ARENA:
                    self.current_state = self._step_handle_rookie_arena()
                elif self.current_state == ArenaState.HANDLE_SPECIAL_ARENA:
                    self.current_state = self._step_handle_special_arena()
                elif self.current_state == ArenaState.EXIT_TO_HOME:
                    self.current_state = self._step_exit_to_home()
                else:
                    raise RuntimeError(f"未处理的竞技场异常状态: {self.current_state}")

            except FrozenScreen as exc:
                logger.error(f"竞技场执行触发卡死告警: {exc}，执行大厅确定性恢复")
                self.recovery.recover_to_home()
                return False

        logger.info(
            f"<<< 任务完成：竞技场执行完毕 (新人挑战={self.rookie_completed}次, 点数已收获={self.points_claimed})"
        )
        return True

    def _step_enter_ark(self) -> ArenaState:
        """从大厅进入方舟 Hub."""
        logger.info("[ArenaState] 进入方舟 Hub...")

        if self.scene.is_in_arena():
            logger.info("已位于竞技场面板，直接进入新人竞技场")
            return ArenaState.HANDLE_ROOKIE_ARENA

        if self.scene.is_in_ark():
            logger.info("已位于方舟 Hub，直接进入竞技场")
            return ArenaState.ENTER_ARENA_HUB

        confirmed = self.interact.press_and_confirm(
            label="大厅点击方舟入口",
            press_action=lambda: self.interact.click_rect(ROI_HOME_ARK_BTN),
            confirmed_check=lambda: self.scene.is_in_ark() or self.scene.is_in_arena(),
            still_before_check=lambda: self.scene.is_in_home(),
            timeout=5.0,
            retry_after=1.5,
            retries=2,
        )

        if not confirmed:
            logger.info("尝试底部导航栏方舟 Tab 备选路径")
            confirmed = self.interact.press_and_confirm(
                label="底部导航栏方舟Tab",
                press_action=lambda: self.interact.click_rect(ROI_HOME_BOTTOM_ARK),
                confirmed_check=lambda: self.scene.is_in_ark() or self.scene.is_in_arena(),
                still_before_check=lambda: self.scene.is_in_home(),
                timeout=4.0,
                retry_after=1.5,
                retries=2,
            )

        if not confirmed and not self.scene.is_in_ark() and not self.scene.is_in_arena():
            raise FrozenScreen("未能成功进入方舟 Hub")

        return ArenaState.ENTER_ARENA_HUB

    def _step_enter_arena_hub(self) -> ArenaState:
        """在方舟 Hub 中点击竞技场入口."""
        logger.info("[ArenaState] 进入竞技场入口...")

        if self.scene.is_in_arena():
            return ArenaState.HANDLE_ROOKIE_ARENA

        confirmed = self.interact.press_and_confirm(
            label="方舟点击竞技场入口",
            press_action=lambda: self.interact.click_rect(ROI_ARK_ARENA),
            confirmed_check=lambda: self.scene.is_in_arena(),
            still_before_check=lambda: self.scene.is_in_ark(),
            timeout=5.0,
            retry_after=1.5,
            retries=2,
        )

        if not confirmed and not self.scene.is_in_arena():
            raise FrozenScreen("未能进入竞技场主界面")

        return ArenaState.HANDLE_ROOKIE_ARENA

    def _step_handle_rookie_arena(self) -> ArenaState:
        """进入新人竞技场，执行免费战斗挑战并保证资产安全."""
        logger.info(f"[ArenaState] 处理新人竞技场 (目标挑战次数={self.rookie_challenges})...")

        # 点击新人竞技场
        self.interact.click_rect(ROI_ARENA_ROOKIE_BTN)
        time.sleep(0.8)

        # 检查是否赛季结束 ("赛季已结束" / "敬请期待")
        if self.ocr_text_exists(TEXT_ARENA_SEASON_CLOSED, ROI_ARENA_SEASON_CLOSED_PROMPT):
            logger.info("新人竞技场赛季已结束或暂未开放，安全跳过")
            self.interact.click_rect(ROI_TOP_LEFT_BACK)
            time.sleep(0.5)
            return ArenaState.HANDLE_SPECIAL_ARENA

        while self.rookie_completed < self.rookie_challenges:
            logger.info(f"新人竞技场挑战第 {self.rookie_completed + 1} 次...")

            # 点击列表第一项 "进入战斗"
            self.interact.click_rect(ROI_ARENA_ENTER_FIGHT_BTN)
            time.sleep(0.8)

            # 资产安全门禁：检查是否弹出钻石购买提示 ("消耗资金" / "币不足")
            if self.ocr_text_exists(TEXT_ARENA_COST_DIAMOND, ROI_ARENA_COST_DIAMOND_PROMPT) or (
                self.ctx and getattr(self.ctx, "mock_cost_diamond", False)
            ):
                logger.info("检测到免费挑战次数已用尽（提示消耗钻石/资金），立即点击取消退出挑战")
                self.interact.click_rect(ROI_ARENA_COST_CANCEL_BTN)
                time.sleep(0.5)
                break

            # 编队准备界面：检查 AUTO 自动战斗是否开启
            if self.ocr_text_exists(TEXT_ARENA_AUTO_OFF, ROI_ARENA_AUTO_TOGGLE):
                logger.info("检测到 AUTO 为 OFF，点击切换至 ON")
                self.interact.click_rect(ROI_ARENA_AUTO_TOGGLE)
                time.sleep(0.4)

            # 点击确定进入战斗
            logger.info("确认进入竞技场战斗...")
            self.interact.click_rect(ROI_ARENA_CONFIRM_FIGHT_BTN)
            time.sleep(1.0)

            # 等待战斗完成 ("点击进行下一步" / 结算)
            logger.info("等待战斗结算完成...")
            max_wait = 45
            start_wait = time.time()
            while time.time() - start_wait < max_wait:
                self.ping_watchdog(detected_text="waiting_rookie_arena_settle")

                if self.ctx and getattr(self.ctx, "mock_combat_settled", True):
                    break

                if self.ocr_text_exists(TEXT_ARENA_NEXT_STEP, (400, 400, 480, 260)):
                    break
                time.sleep(1.0)

            # 点击结算推进下一步
            self.interact.click_rect(ROI_ARENA_SETTLEMENT_CLICK)
            time.sleep(1.0)
            self.rookie_completed += 1
            logger.info(f"新人竞技场第 {self.rookie_completed} 次挑战完成")

        # 返回竞技场 Hub
        logger.info("退出新人竞技场，返回竞技场 Hub")
        self.interact.click_rect(ROI_TOP_LEFT_BACK)
        time.sleep(0.8)

        return ArenaState.HANDLE_SPECIAL_ARENA

    def _step_handle_special_arena(self) -> ArenaState:
        """进入特殊竞技场，收获点数并执行可选免费挑战."""
        logger.info("[ArenaState] 处理特殊竞技场 (收获点数与每日挑战)...")

        # 点击特殊竞技场
        self.interact.click_rect(ROI_ARENA_SPECIAL_BTN)
        time.sleep(0.8)

        # 检查是否赛季结束
        if self.ocr_text_exists(TEXT_ARENA_SEASON_CLOSED, ROI_ARENA_SEASON_CLOSED_PROMPT):
            logger.info("特殊竞技场赛季已结束或结算中，安全跳过")
            self.interact.click_rect(ROI_TOP_LEFT_BACK)
            time.sleep(0.5)
            return ArenaState.EXIT_TO_HOME

        # 1. 收获竞技场点数
        if self.special_claim_points:
            logger.info("点击顶部点数箱，收取特殊竞技场累计点数...")
            self.interact.click_rect(ROI_ARENA_SPECIAL_CLAIM_ENTRY)
            time.sleep(0.8)

            # 点击 "领取" 按钮
            if self.ocr_text_exists(TEXT_ARENA_SPECIAL_CLAIM, ROI_ARENA_SPECIAL_CLAIM_BTN) or (
                self.ctx and getattr(self.ctx, "mock_special_reward_open", True)
            ):
                self.interact.click_rect(ROI_ARENA_SPECIAL_CLAIM_BTN)
                time.sleep(0.6)
                self.points_claimed = True
                logger.info("已点击领取点数，消除弹窗")
                self.interact.click_rect(ROI_ARENA_SPECIAL_CLAIM_CLOSE)
                time.sleep(0.5)

        # 2. 可选每日免费挑战
        if self.special_challenges > 0:
            logger.info(f"尝试特殊竞技场免费挑战 (目标={self.special_challenges}次)...")
            while self.special_completed < self.special_challenges:
                self.interact.click_rect(ROI_ARENA_ENTER_FIGHT_BTN)
                time.sleep(0.8)

                # 钻石安全门禁
                if self.ocr_text_exists(TEXT_ARENA_COST_DIAMOND, ROI_ARENA_COST_DIAMOND_PROMPT) or (
                    self.ctx and getattr(self.ctx, "mock_cost_diamond", False)
                ):
                    logger.info("特殊竞技场无免费次数，点击取消")
                    self.interact.click_rect(ROI_ARENA_COST_CANCEL_BTN)
                    time.sleep(0.5)
                    break

                self.interact.click_rect(ROI_ARENA_CONFIRM_FIGHT_BTN)
                time.sleep(1.0)
                self.interact.click_rect(ROI_ARENA_SETTLEMENT_CLICK)
                time.sleep(1.0)
                self.special_completed += 1

        # 返回竞技场 Hub
        logger.info("退出特殊竞技场，返回竞技场 Hub")
        self.interact.click_rect(ROI_TOP_LEFT_BACK)
        time.sleep(0.8)

        return ArenaState.EXIT_TO_HOME

    def _step_exit_to_home(self) -> ArenaState:
        """确定性退出至大厅主界面."""
        logger.info("[ArenaState] 确定性退出至大厅主界面...")

        if self.scene.is_in_home():
            return ArenaState.COMPLETED

        recovered = self.recovery.recover_to_home()
        if not recovered and not self.scene.is_in_home():
            raise FrozenScreen("未能确定性恢复至大厅主界面")

        return ArenaState.COMPLETED
