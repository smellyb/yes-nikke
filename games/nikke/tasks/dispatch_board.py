"""Dispatch Board task implementation for NIKKE.

Features:
1. Closed-loop confirmation (press_and_confirm) for all state transitions.
2. Claim all completed dispatch missions and sweep reward popups.
3. One-click batch dispatch for all pending unassigned missions.
4. Graceful handling if no dispatches are completable or pendable.
5. Deterministic return to Lobby from nested Outpost subviews.
"""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Any, Optional, Tuple

from core.ops.frozen_watch import FrozenScreen
from games.nikke.base_nikke_task import NikkeTask
from games.nikke.constants import (
    ROI_HOME_OUTPOST_BTN,
    ROI_DISPATCH_ENTRY_BTN,
    ROI_DISPATCH_TITLE,
    ROI_DISPATCH_CLAIM_ALL_BTN,
    ROI_DISPATCH_ALL_BTN,
    ROI_DISPATCH_CONFIRM_BTN,
    ROI_DISPATCH_EXIT_BTN,
    ROI_TOP_LEFT_BACK,
    ROI_SAFE_CLICK_BLANK,
    TEXT_DISPATCH_TITLE,
    TEXT_DISPATCH_CLAIM_ALL,
    TEXT_DISPATCH_ALL,
    TEXT_DISPATCH_EMPTY,
    TEXT_OUTPOST_TITLE,
    TEXT_CONFIRM,
)

logger = logging.getLogger("yes_nikke.task.dispatch_board")


class DispatchState(Enum):
    ENTER_DISPATCH = auto()
    CHECK_DISPATCH_STATUS = auto()
    CLAIM_ALL_COMPLETED = auto()
    DISPATCH_ALL_PENDING = auto()
    EXIT_TO_HOME = auto()
    COMPLETED = auto()


class DispatchBoardTask(NikkeTask):
    """【派遣公告栏】命令式状态机任务实现.

    流程：
    进入派遣面板 -> 检查状态 -> 点击一键领取所有完成任务 -> 点击一键派遣所有未出任务 -> 确定性返回大厅。
    """

    ROI_DISPATCH_ENTRY_BTN: Tuple[int, int, int, int] = ROI_DISPATCH_ENTRY_BTN
    ROI_DISPATCH_TITLE: Tuple[int, int, int, int] = ROI_DISPATCH_TITLE
    ROI_DISPATCH_CLAIM_ALL_BTN: Tuple[int, int, int, int] = ROI_DISPATCH_CLAIM_ALL_BTN
    ROI_DISPATCH_ALL_BTN: Tuple[int, int, int, int] = ROI_DISPATCH_ALL_BTN
    ROI_DISPATCH_CONFIRM_BTN: Tuple[int, int, int, int] = ROI_DISPATCH_CONFIRM_BTN
    ROI_DISPATCH_EXIT_BTN: Tuple[int, int, int, int] = ROI_DISPATCH_EXIT_BTN

    def __init__(self, ctx: Any = None) -> None:
        super().__init__(ctx, name="DispatchBoard")
        self.current_state: DispatchState = DispatchState.ENTER_DISPATCH
        self.dispatches_claimed: bool = False
        self.dispatches_sent: bool = False

    def run(self) -> bool:
        """Execute Dispatch Board task state machine."""
        logger.info(">>> 启动任务：派遣公告栏一键收发")
        self.current_state = DispatchState.ENTER_DISPATCH
        self.dispatches_claimed = False
        self.dispatches_sent = False

        if self.frozen_watch and hasattr(self.frozen_watch, "reset"):
            self.frozen_watch.reset()

        while self.current_state != DispatchState.COMPLETED:
            try:
                self.ping_watchdog(detected_text=f"state_{self.current_state.name}")

                if self.current_state == DispatchState.ENTER_DISPATCH:
                    self.current_state = self._step_enter_dispatch()
                elif self.current_state == DispatchState.CHECK_DISPATCH_STATUS:
                    self.current_state = self._step_check_dispatch_status()
                elif self.current_state == DispatchState.CLAIM_ALL_COMPLETED:
                    self.current_state = self._step_claim_all_completed()
                elif self.current_state == DispatchState.DISPATCH_ALL_PENDING:
                    self.current_state = self._step_dispatch_all_pending()
                elif self.current_state == DispatchState.EXIT_TO_HOME:
                    self.current_state = self._step_exit_to_home()
                else:
                    raise RuntimeError(f"未处理的异常状态: {self.current_state}")

            except FrozenScreen as exc:
                logger.error(f"派遣公告栏触发卡死看门狗告警: {exc}，启动确定性恢复大厅")
                self.recovery.recover_to_home()
                return False

        logger.info("<<< 任务完成：派遣公告栏任务执行完毕")
        return True

    def _step_enter_dispatch(self) -> DispatchState:
        """从大厅或前哨进入派遣公告栏面板."""
        logger.info("[State] 进入派遣公告栏...")

        # 检查是否已在派遣面板中
        if self.scene.is_in_dispatch() or self.ocr_text_exists(TEXT_DISPATCH_TITLE, self.ROI_DISPATCH_TITLE):
            logger.info("已位于派遣公告栏，直接进入状态检查")
            return DispatchState.CHECK_DISPATCH_STATUS

        # 如果在大厅，先进入前哨基地
        if self.scene.is_in_home():
            logger.info("当前位于大厅，点击前哨基地入口...")
            confirmed_outpost = self.interact.press_and_confirm(
                label="大厅点击前哨基地",
                press_action=lambda: self.interact.click_rect(ROI_HOME_OUTPOST_BTN),
                confirmed_check=lambda: self.scene.is_in_outpost()
                or self.scene.is_in_dispatch()
                or self.ocr_text_exists(TEXT_OUTPOST_TITLE, (400, 40, 300, 80))
                or self.ocr_text_exists(TEXT_DISPATCH_TITLE, self.ROI_DISPATCH_TITLE),
                still_before_check=lambda: self.scene.is_in_home(),
                timeout=4.0,
                retries=2,
            )
            if not confirmed_outpost:
                raise FrozenScreen("未能进入前哨基地场景")

        # 检查是否直接到了派遣面板
        if self.scene.is_in_dispatch() or self.ocr_text_exists(TEXT_DISPATCH_TITLE, self.ROI_DISPATCH_TITLE):
            return DispatchState.CHECK_DISPATCH_STATUS

        # 在前哨界面中点击派遣公告栏建筑
        logger.info("在前哨基地点击派遣公告栏建筑...")
        confirmed_dispatch = self.interact.press_and_confirm(
            label="点击派遣公告栏建筑",
            press_action=lambda: self.interact.click_rect(self.ROI_DISPATCH_ENTRY_BTN),
            confirmed_check=lambda: self.scene.is_in_dispatch()
            or self.ocr_text_exists(TEXT_DISPATCH_TITLE, self.ROI_DISPATCH_TITLE),
            timeout=4.0,
            retries=2,
        )

        if not confirmed_dispatch:
            raise FrozenScreen("未能成功进入派遣公告栏面板")

        return DispatchState.CHECK_DISPATCH_STATUS

    def _step_check_dispatch_status(self) -> DispatchState:
        """检查派遣面板，决定是否领奖或派遣."""
        time.sleep(0.5)
        logger.info("[State] 检查派遣任务完成状态...")

        has_claim_btn = self.ocr_text_exists(TEXT_DISPATCH_CLAIM_ALL, self.ROI_DISPATCH_CLAIM_ALL_BTN)

        if has_claim_btn:
            logger.info("检测到已完成派遣任务，转入一键领取步骤")
            return DispatchState.CLAIM_ALL_COMPLETED
        else:
            logger.info("当前无已完成派遣任务，转入一键派遣步骤")
            return DispatchState.DISPATCH_ALL_PENDING

    def _step_claim_all_completed(self) -> DispatchState:
        """点击全部领取已完成派遣奖励，并清扫弹窗."""
        logger.info("[State] 点击全部领取派遣奖励...")

        claimed = self.interact.press_and_confirm(
            label="点击全部领取派遣奖励",
            press_action=lambda: self.interact.click_rect(self.ROI_DISPATCH_CLAIM_ALL_BTN),
            confirmed_check=lambda: self.scene.has_reward_claim_modal()
            or not self.ocr_text_exists(TEXT_DISPATCH_CLAIM_ALL, self.ROI_DISPATCH_CLAIM_ALL_BTN),
            still_before_check=lambda: self.ocr_text_exists(TEXT_DISPATCH_CLAIM_ALL, self.ROI_DISPATCH_CLAIM_ALL_BTN),
            timeout=3.5,
            retries=1,
        )

        if claimed:
            logger.info("派遣奖励领取成功，清扫弹窗...")
            self.dispatches_claimed = True
            self.recovery.sweep_modals(max_passes=5)
        else:
            logger.warning("未能确认派遣奖励领取反馈")

        return DispatchState.DISPATCH_ALL_PENDING

    def _step_dispatch_all_pending(self) -> DispatchState:
        """点击一键派遣所有未出任务."""
        time.sleep(0.5)
        logger.info("[State] 检查是否有待派遣任务...")

        has_empty_notice = self.ocr_text_exists(TEXT_DISPATCH_EMPTY, (400, 200, 480, 320))
        has_dispatch_btn = self.ocr_text_exists(TEXT_DISPATCH_ALL, self.ROI_DISPATCH_ALL_BTN)

        if has_empty_notice or not has_dispatch_btn:
            logger.info("当前没有可进行的派遣任务或已全部派遣完毕，准备退出")
            return DispatchState.EXIT_TO_HOME

        logger.info("点击全部派遣按钮...")
        confirmed = self.interact.press_and_confirm(
            label="点击全部派遣",
            press_action=lambda: self.interact.click_rect(self.ROI_DISPATCH_ALL_BTN),
            confirmed_check=lambda: not self.ocr_text_exists(TEXT_DISPATCH_ALL, self.ROI_DISPATCH_ALL_BTN)
            or bool(self.find_template_multidim("dispatchboard/dispatch.png", self.ROI_DISPATCH_CONFIRM_BTN))
            or self.ocr_text_exists(("派遣", "确认"), self.ROI_DISPATCH_CONFIRM_BTN),
            still_before_check=lambda: self.ocr_text_exists(TEXT_DISPATCH_ALL, self.ROI_DISPATCH_ALL_BTN),
            timeout=3.5,
            retries=1,
        )

        # 处理二次确认点击（例如弹出确认派遣窗口）
        if self.ocr_text_exists(("派遣", "确认"), self.ROI_DISPATCH_CONFIRM_BTN) or bool(
            self.find_template_multidim("dispatchboard/dispatch.png", self.ROI_DISPATCH_CONFIRM_BTN)
        ):
            logger.info("检测到二次派遣确认按钮，点击确认...")
            self.interact.click_rect(self.ROI_DISPATCH_CONFIRM_BTN)
            time.sleep(0.5)

        if confirmed:
            logger.info("全部派遣操作执行完成")
            self.dispatches_sent = True
            self.recovery.sweep_modals(max_passes=3)
        else:
            logger.warning("未能确认全部派遣操作反馈")

        return DispatchState.EXIT_TO_HOME

    def _step_exit_to_home(self) -> DispatchState:
        """从派遣面板及前哨基地确定性返回游戏大厅."""
        logger.info("[State] 退出派遣公告栏，返回大厅...")

        # 步骤 1：退出派遣公告栏
        self.interact.press_and_confirm(
            label="退出派遣公告栏",
            press_action=lambda: self.interact.click_rect(self.ROI_DISPATCH_EXIT_BTN),
            confirmed_check=lambda: not self.scene.is_in_dispatch(),
            timeout=3.0,
            retries=2,
        )

        # 步骤 2：如果还在前哨基地或非大厅界面，退出至大厅
        if not self.scene.is_in_home():
            self.interact.press_and_confirm(
                label="从前哨基地返回大厅",
                press_action=lambda: self.interact.click_rect(ROI_TOP_LEFT_BACK),
                confirmed_check=lambda: self.scene.is_in_home(),
                timeout=3.0,
                retries=2,
            )

        if not self.scene.is_in_home():
            logger.warning("常规返回未抵达大厅，启动 recover_to_home 兜底")
            self.recovery.recover_to_home(max_attempts=3)

        if self.scene.is_in_home():
            logger.info("已成功返回游戏大厅")
            return DispatchState.COMPLETED
        else:
            raise FrozenScreen("未能确定性返回游戏大厅")
