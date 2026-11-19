"""Daily Rewards and Mission Pass task implementation for NIKKE.

Features:
1. Closed-loop navigation from Lobby top-right task icon into Task Panel.
2. One-click claim for Daily Tasks ("全部领取").
3. One-click claim for Weekly Tasks ("每周任务" -> "全部领取").
4. Mission PASS rewards integration:
   - Red dot & entrance detection from Lobby.
   - Task exp claim and tier rewards claim ("任务" & "奖励" tabs).
5. Comprehensive reward popup sweeping and deterministic return to Lobby.
"""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Any, Optional, Tuple

from core.ops.frozen_watch import FrozenScreen
from games.nikke.base_nikke_task import NikkeTask
import games.nikke.scene_growth  # Ensure scene discriminators are registered
from games.nikke.constants_growth import (
    ROI_TASK_ENTRY_BTN,
    ROI_TASK_ENTRY_ALT,
    ROI_TASK_TITLE,
    ROI_TASK_DAILY_TAB,
    ROI_TASK_WEEKLY_TAB,
    ROI_TASK_CLAIM_ALL_BTN,
    ROI_TASK_CLOSE_BTN,
    ROI_PASS_ENTRY_BTN,
    ROI_PASS_RED_POINT,
    ROI_PASS_TAB_TASK,
    ROI_PASS_TAB_REWARD,
    ROI_PASS_CLAIM_ALL_BTN,
    ROI_PASS_EXIT_BTN,
    ROI_TOP_LEFT_BACK,
    ROI_SAFE_CLICK_BLANK,
    TEXT_TASK_TITLE,
    TEXT_TASK_DAILY,
    TEXT_TASK_WEEKLY,
    TEXT_TASK_CLAIM_ALL,
    TEXT_PASS_TASK,
    TEXT_PASS_REWARD,
)

logger = logging.getLogger("yes_nikke.task.daily_rewards")


class DailyRewardsState(Enum):
    ENTER_TASK_PANEL = auto()
    CLAIM_DAILY_TASKS = auto()
    CLAIM_WEEKLY_TASKS = auto()
    EXIT_TASK_PANEL = auto()
    CHECK_AND_CLAIM_PASS = auto()
    SWEEP_AND_EXIT = auto()
    COMPLETED = auto()


class DailyRewardsTask(NikkeTask):
    """【每日任务与战令PASS领取】命令式状态机任务实现."""

    def __init__(
        self,
        ctx: Any = None,
        claim_weekly: bool = True,
        check_pass: bool = True,
    ) -> None:
        super().__init__(ctx, name="DailyRewards")
        self.claim_weekly: bool = claim_weekly
        self.check_pass: bool = check_pass

        self.current_state: DailyRewardsState = DailyRewardsState.ENTER_TASK_PANEL
        self.daily_claimed: bool = False
        self.weekly_claimed: bool = False
        self.pass_claimed: bool = False

    def run(self) -> bool:
        """Execute Daily Rewards & PASS claim state machine."""
        logger.info(">>> 启动任务：每日任务与战令PASS奖励领取")
        self.current_state = DailyRewardsState.ENTER_TASK_PANEL
        self.daily_claimed = False
        self.weekly_claimed = False
        self.pass_claimed = False

        if self.frozen_watch and hasattr(self.frozen_watch, "reset"):
            self.frozen_watch.reset()

        while self.current_state != DailyRewardsState.COMPLETED:
            try:
                self.ping_watchdog(detected_text=f"state_{self.current_state.name}")

                if self.current_state == DailyRewardsState.ENTER_TASK_PANEL:
                    self.current_state = self._step_enter_task_panel()
                elif self.current_state == DailyRewardsState.CLAIM_DAILY_TASKS:
                    self.current_state = self._step_claim_daily_tasks()
                elif self.current_state == DailyRewardsState.CLAIM_WEEKLY_TASKS:
                    self.current_state = self._step_claim_weekly_tasks()
                elif self.current_state == DailyRewardsState.EXIT_TASK_PANEL:
                    self.current_state = self._step_exit_task_panel()
                elif self.current_state == DailyRewardsState.CHECK_AND_CLAIM_PASS:
                    self.current_state = self._step_check_and_claim_pass()
                elif self.current_state == DailyRewardsState.SWEEP_AND_EXIT:
                    self.current_state = self._step_sweep_and_exit()
                else:
                    raise RuntimeError(f"未处理的异常状态: {self.current_state}")

            except FrozenScreen as exc:
                logger.error(f"每日任务领取触发卡死看门狗告警: {exc}，启动确定性恢复大厅")
                self.recovery.recover_to_home()
                return False

        logger.info(
            f"<<< 任务完成：每日任务与PASS领取执行完毕 (每日: {self.daily_claimed}, "
            f"每周: {self.weekly_claimed}, PASS: {self.pass_claimed})"
        )
        return True

    def _step_enter_task_panel(self) -> DailyRewardsState:
        """从大厅点击右上角任务图标进入任务面板."""
        logger.info("[State] 进入任务面板...")

        # 检查是否已在任务面板中
        if self.scene.is_in_task_panel() or self.ocr_text_exists(TEXT_TASK_TITLE, ROI_TASK_TITLE):
            logger.info("已位于任务面板界面，跳过入口点击")
            return DailyRewardsState.CLAIM_DAILY_TASKS

        # 优先点击主 ROI，若无响应尝试备选 ROI
        confirmed = self.interact.press_and_confirm(
            label="点击大厅右上角任务图标",
            press_action=lambda: self.interact.click_rect(ROI_TASK_ENTRY_BTN),
            confirmed_check=lambda: self.scene.is_in_task_panel()
            or self.ocr_text_exists(TEXT_TASK_TITLE, ROI_TASK_TITLE)
            or self.ocr_text_exists(TEXT_TASK_CLAIM_ALL, ROI_TASK_CLAIM_ALL_BTN),
            still_before_check=lambda: self.scene.is_in_home(),
            timeout=4.0,
            retries=2,
        )

        if not confirmed and not self.scene.is_in_task_panel():
            logger.info("尝试备用任务图标区域点击...")
            confirmed = self.interact.press_and_confirm(
                label="点击备用任务图标区域",
                press_action=lambda: self.interact.click_rect(ROI_TASK_ENTRY_ALT),
                confirmed_check=lambda: self.scene.is_in_task_panel()
                or self.ocr_text_exists(TEXT_TASK_TITLE, ROI_TASK_TITLE),
                timeout=4.0,
                retries=1,
            )

        if not confirmed and not self.scene.is_in_task_panel():
            raise FrozenScreen("未能成功进入任务面板界面")

        logger.info("成功就绪在任务面板")
        return DailyRewardsState.CLAIM_DAILY_TASKS

    def _step_claim_daily_tasks(self) -> DailyRewardsState:
        """领取每日任务奖励."""
        logger.info("[State] 检查并领取每日任务...")
        time.sleep(0.5)

        # 检查是否有全部领取按钮
        has_claim_btn = self.ocr_text_exists(TEXT_TASK_CLAIM_ALL, ROI_TASK_CLAIM_ALL_BTN)
        if has_claim_btn:
            logger.info("检测到可领取每日任务，执行全部领取...")
            claimed = self.interact.press_and_confirm(
                label="点击每日任务全部领取",
                press_action=lambda: self.interact.click_rect(ROI_TASK_CLAIM_ALL_BTN),
                confirmed_check=lambda: self.scene.has_reward_claim_modal()
                or not self.ocr_text_exists(TEXT_TASK_CLAIM_ALL, ROI_TASK_CLAIM_ALL_BTN),
                timeout=3.5,
                retries=2,
            )
            if claimed:
                self.daily_claimed = True
                logger.info("每日任务领取成功，清扫结算弹窗...")
                self.recovery.sweep_modals(max_passes=4)
        else:
            logger.info("每日任务当前无可领取项或已全部领取")

        if self.claim_weekly:
            return DailyRewardsState.CLAIM_WEEKLY_TASKS
        return DailyRewardsState.EXIT_TASK_PANEL

    def _step_claim_weekly_tasks(self) -> DailyRewardsState:
        """切换到每周任务标签页并领取奖励."""
        logger.info("[State] 切换至每周任务标签页...")

        # 点击每周任务标签
        self.interact.click_rect(ROI_TASK_WEEKLY_TAB)
        time.sleep(0.8)

        # 检查是否有每周任务全部领取按钮
        has_claim_btn = self.ocr_text_exists(TEXT_TASK_CLAIM_ALL, ROI_TASK_CLAIM_ALL_BTN)
        if has_claim_btn:
            logger.info("检测到可领取每周任务，执行全部领取...")
            claimed = self.interact.press_and_confirm(
                label="点击每周任务全部领取",
                press_action=lambda: self.interact.click_rect(ROI_TASK_CLAIM_ALL_BTN),
                confirmed_check=lambda: self.scene.has_reward_claim_modal()
                or not self.ocr_text_exists(TEXT_TASK_CLAIM_ALL, ROI_TASK_CLAIM_ALL_BTN),
                timeout=3.5,
                retries=2,
            )
            if claimed:
                self.weekly_claimed = True
                logger.info("每周任务领取成功，清扫结算弹窗...")
                self.recovery.sweep_modals(max_passes=4)
        else:
            logger.info("每周任务当前无可领取项或已全部领取")

        return DailyRewardsState.EXIT_TASK_PANEL

    def _step_exit_task_panel(self) -> DailyRewardsState:
        """关闭任务面板并返回游戏大厅."""
        logger.info("[State] 退出任务面板返回大厅...")

        # 优先点击右上角关闭叉号或返回键
        self.interact.press_and_confirm(
            label="点击关闭任务面板",
            press_action=lambda: self.interact.click_rect(ROI_TASK_CLOSE_BTN),
            confirmed_check=lambda: self.scene.is_in_home(),
            still_before_check=lambda: self.scene.is_in_task_panel(),
            timeout=3.5,
            retries=2,
        )

        if not self.scene.is_in_home():
            self.interact.click_rect(ROI_TOP_LEFT_BACK)
            time.sleep(1.0)

        return DailyRewardsState.CHECK_AND_CLAIM_PASS if self.check_pass else DailyRewardsState.SWEEP_AND_EXIT

    def _step_check_and_claim_pass(self) -> DailyRewardsState:
        """检查大厅是否存在 PASS 入口并领取 PASS 任务及奖励."""
        logger.info("[State] 检查大厅 PASS 战令入口...")

        if not self.scene.is_in_home():
            logger.debug("当前不在大厅，尝试对齐大厅场景...")
            self.recovery.recover_to_home(max_attempts=3)

        # 检查 PASS 入口
        has_pass_entry = self.ocr_text_exists(("pass", "战令", "通行证"), ROI_PASS_ENTRY_BTN)
        has_red_point = self.find_template_multidim("redpoint", roi_720p=ROI_PASS_RED_POINT) is not None

        # 无论是否有红点，尝试点击一次 PASS 入口进行检查
        logger.info("点击进入 PASS 界面...")
        entered_pass = self.interact.press_and_confirm(
            label="点击大厅 PASS 入口",
            press_action=lambda: self.interact.click_rect(ROI_PASS_ENTRY_BTN),
            confirmed_check=lambda: self.ocr_text_exists(TEXT_PASS_TASK, ROI_PASS_TAB_TASK)
            or self.ocr_text_exists(TEXT_PASS_REWARD, ROI_PASS_TAB_REWARD)
            or self.ocr_text_exists(TEXT_TASK_CLAIM_ALL, ROI_PASS_CLAIM_ALL_BTN),
            still_before_check=lambda: self.scene.is_in_home(),
            timeout=4.0,
            retries=2,
        )

        if not entered_pass:
            logger.info("未能进入 PASS 界面（可能无正在进行的 PASS 活动），跳过 PASS 领取")
            return DailyRewardsState.SWEEP_AND_EXIT

        time.sleep(0.8)

        # 1. 领取 PASS 任务积分
        logger.info("检查 PASS 任务积分领取...")
        self.interact.click_rect(ROI_PASS_TAB_TASK)
        time.sleep(0.6)
        if self.ocr_text_exists(TEXT_TASK_CLAIM_ALL, ROI_PASS_CLAIM_ALL_BTN):
            logger.info("点击全部领取 PASS 任务积分...")
            self.interact.click_rect(ROI_PASS_CLAIM_ALL_BTN)
            time.sleep(1.0)
            self.recovery.sweep_modals(max_passes=3)
            self.pass_claimed = True

        # 2. 领取 PASS 等级奖励
        logger.info("检查 PASS 等级阶梯奖励领取...")
        self.interact.click_rect(ROI_PASS_TAB_REWARD)
        time.sleep(0.6)
        if self.ocr_text_exists(TEXT_TASK_CLAIM_ALL, ROI_PASS_CLAIM_ALL_BTN):
            logger.info("点击全部领取 PASS 阶梯奖励...")
            self.interact.click_rect(ROI_PASS_CLAIM_ALL_BTN)
            time.sleep(1.0)
            self.recovery.sweep_modals(max_passes=4)
            self.pass_claimed = True

        # 3. 退出 PASS 界面
        logger.info("退出 PASS 界面...")
        self.interact.press_and_confirm(
            label="点击退出 PASS 界面",
            press_action=lambda: self.interact.click_rect(ROI_PASS_EXIT_BTN),
            confirmed_check=lambda: self.scene.is_in_home(),
            timeout=3.5,
            retries=2,
        )

        return DailyRewardsState.SWEEP_AND_EXIT

    def _step_sweep_and_exit(self) -> DailyRewardsState:
        """清扫残余弹窗并确定性恢复至大厅."""
        logger.info("[State] 清扫结算弹窗并确定性返回大厅...")
        self.recovery.sweep_modals(max_passes=5)

        success = self.recovery.recover_to_home(max_attempts=5)
        if not success and not self.scene.is_in_home():
            raise FrozenScreen("未能确定性恢复至游戏大厅")

        logger.info("已安全就绪在大厅")
        return DailyRewardsState.COMPLETED
