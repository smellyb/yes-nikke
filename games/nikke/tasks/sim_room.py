"""Simulation Room (模拟室) daily quick simulation task implementation.

Features:
1. Navigates from Lobby Home -> Ark Hub -> Simulation Room.
2. Selects Difficulty 5-C and executes Quick Simulation (快速模拟).
3. Bypasses buff selection modal and confirms simulation finalization.
4. Sweeps skill manual rewards and drop modals.
5. Deterministically recovers back to Lobby Home.
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
)
from games.nikke.constants_combat import (
    ROI_HOME_ARK_BTN,
    ROI_ARK_SIM_ROOM,
    ROI_SIM_START_BTN,
    ROI_SIM_5C_SECTOR,
    ROI_SIM_QUICK_BTN,
    ROI_SIM_SKIP_BUFFS_BTN,
    ROI_SIM_END_MODAL_TEXT,
    ROI_SIM_END_CONFIRM_BTN,
    ROI_SIM_TOP_EXIT_BTN,
    ROI_SIM_COMPLETED_PROMPT,
    ROI_SIM_NOT_5C_PROMPT,
    TEXT_ARK_TITLE,
    TEXT_SIM_TITLE,
    TEXT_SIM_START,
    TEXT_SIM_5C,
    TEXT_SIM_QUICK,
    TEXT_SIM_SKIP_BUFFS,
    TEXT_SIM_END_MODAL,
    TEXT_SIM_COMPLETED,
    TEXT_SIM_NOT_5C,
)
import games.nikke.scene_combat  # Ensure monkey-patched scene methods are loaded

logger = logging.getLogger("yes_nikke.task.sim_room")


class SimRoomState(Enum):
    ENTER_ARK = auto()
    ENTER_SIM_ROOM = auto()
    CHECK_SIM_ROOM_STATUS = auto()
    SELECT_5C = auto()
    EXECUTE_QUICK_SIM = auto()
    DISMISS_REWARDS = auto()
    EXIT_TO_HOME = auto()
    COMPLETED = auto()


class SimRoomTask(NikkeTask):
    """【模拟室 5-C 快速模拟】自动化任务.

    全链路流转：
    大厅方舟入口 -> 模拟室 -> 选择 5-C -> 快速模拟确认 -> 领取技能手册与产出 -> 消除结算弹窗 -> 确定性返回大厅。
    """

    def __init__(self, ctx: Any = None, difficulty: str = "5C") -> None:
        super().__init__(ctx, name="SimRoom")
        self.difficulty: str = difficulty
        self.current_state: SimRoomState = SimRoomState.ENTER_ARK
        self.already_completed: bool = False
        self.quick_sim_succeeded: bool = False

    def run(self) -> bool:
        """Execute SimRoom automation state machine."""
        logger.info(">>> 启动任务：模拟室 5-C 快速模拟")
        self.current_state = SimRoomState.ENTER_ARK
        self.already_completed = False
        self.quick_sim_succeeded = False

        if self.frozen_watch and hasattr(self.frozen_watch, "reset"):
            self.frozen_watch.reset()

        while self.current_state != SimRoomState.COMPLETED:
            try:
                self.ping_watchdog(detected_text=f"sim_state_{self.current_state.name}")

                if self.current_state == SimRoomState.ENTER_ARK:
                    self.current_state = self._step_enter_ark()
                elif self.current_state == SimRoomState.ENTER_SIM_ROOM:
                    self.current_state = self._step_enter_sim_room()
                elif self.current_state == SimRoomState.CHECK_SIM_ROOM_STATUS:
                    self.current_state = self._step_check_status()
                elif self.current_state == SimRoomState.SELECT_5C:
                    self.current_state = self._step_select_5c()
                elif self.current_state == SimRoomState.EXECUTE_QUICK_SIM:
                    self.current_state = self._step_execute_quick_sim()
                elif self.current_state == SimRoomState.DISMISS_REWARDS:
                    self.current_state = self._step_dismiss_rewards()
                elif self.current_state == SimRoomState.EXIT_TO_HOME:
                    self.current_state = self._step_exit_to_home()
                else:
                    raise RuntimeError(f"未处理的模拟室异常状态: {self.current_state}")

            except FrozenScreen as exc:
                logger.error(f"模拟室执行触发卡死告警: {exc}，执行大厅确定性恢复")
                self.recovery.recover_to_home()
                return False

        logger.info("<<< 任务完成：模拟室 5-C 快速模拟执行完毕")
        return True

    def _step_enter_ark(self) -> SimRoomState:
        """从大厅进入方舟 Hub."""
        logger.info("[SimRoomState] 进入方舟 Hub...")

        # If already in SimRoom, skip directly to status check
        if self.scene.is_in_sim_room():
            logger.info("检测到已位于模拟室内，直接进入状态检查")
            return SimRoomState.CHECK_SIM_ROOM_STATUS

        # If already in Ark, skip Ark click
        if self.scene.is_in_ark():
            logger.info("已位于方舟 Hub，直接进入模拟室")
            return SimRoomState.ENTER_SIM_ROOM

        confirmed = self.interact.press_and_confirm(
            label="大厅点击方舟入口",
            press_action=lambda: self.interact.click_rect(ROI_HOME_ARK_BTN),
            confirmed_check=lambda: self.scene.is_in_ark() or self.scene.is_in_sim_room(),
            still_before_check=lambda: self.scene.is_in_home(),
            timeout=5.0,
            retry_after=1.5,
            retries=2,
        )

        if not confirmed:
            # Try bottom navigation Ark tab fallback
            logger.info("尝试通过底部导航栏方舟 Tab 备选路径进入")
            confirmed = self.interact.press_and_confirm(
                label="底部导航栏点击方舟",
                press_action=lambda: self.interact.click_rect(ROI_HOME_BOTTOM_ARK),
                confirmed_check=lambda: self.scene.is_in_ark() or self.scene.is_in_sim_room(),
                still_before_check=lambda: self.scene.is_in_home(),
                timeout=4.0,
                retry_after=1.5,
                retries=2,
            )

        if not confirmed and not self.scene.is_in_ark() and not self.scene.is_in_sim_room():
            raise FrozenScreen("未能成功进入方舟 Hub（点击无响应或未识别到方舟界面）")

        return SimRoomState.ENTER_SIM_ROOM

    def _step_enter_sim_room(self) -> SimRoomState:
        """在方舟 Hub 中点击模拟室入口."""
        logger.info("[SimRoomState] 进入模拟室入口...")

        if self.scene.is_in_sim_room():
            return SimRoomState.CHECK_SIM_ROOM_STATUS

        confirmed = self.interact.press_and_confirm(
            label="方舟点击模拟室入口",
            press_action=lambda: self.interact.click_rect(ROI_ARK_SIM_ROOM),
            confirmed_check=lambda: self.scene.is_in_sim_room(),
            still_before_check=lambda: self.scene.is_in_ark(),
            timeout=5.0,
            retry_after=1.5,
            retries=2,
        )

        if not confirmed and not self.scene.is_in_sim_room():
            raise FrozenScreen("未能成功进入模拟室（模拟室入口点击无响应）")

        return SimRoomState.CHECK_SIM_ROOM_STATUS

    def _step_check_status(self) -> SimRoomState:
        """检查模拟室今日完成状态或是否需要点击‘开始模拟’."""
        logger.info("[SimRoomState] 检查模拟室今日完成状态...")
        time.sleep(0.5)

        # 检查是否今日已完成 ("不再显示" / "今日已完成")
        if self.ocr_text_exists(TEXT_SIM_COMPLETED, ROI_SIM_COMPLETED_PROMPT):
            logger.info("检测到今日模拟室奖励已全部结清（今日已完成），直接退出")
            self.already_completed = True
            return SimRoomState.EXIT_TO_HOME

        # 检查是否在模拟室首页并显示 "开始模拟"
        if self.ocr_text_exists(TEXT_SIM_START, ROI_SIM_START_BTN):
            logger.info("点击‘开始模拟’进入扇区难度选择...")
            self.interact.click_rect(ROI_SIM_START_BTN)
            time.sleep(0.8)

        return SimRoomState.SELECT_5C

    def _step_select_5c(self) -> SimRoomState:
        """选择 5-C 难度扇区."""
        logger.info("[SimRoomState] 选择 5-C 难度扇区...")

        # 尝试通过模板匹配或固定 ROI 选中 5-C
        tmpl_pos = self.find_template_multidim("simroom/simroom-5C.png", roi_720p=(600, 200, 300, 400))
        target_roi = tmpl_pos if tmpl_pos is not None else ROI_SIM_5C_SECTOR

        self.interact.click_rect(target_roi)
        time.sleep(0.6)

        # 验证快速模拟按钮是否出现
        has_quick = self.ocr_text_exists(TEXT_SIM_QUICK, ROI_SIM_QUICK_BTN)
        if not has_quick:
            logger.info("快速模拟按钮未立即呈现，二次点击 5-C 扇区")
            self.interact.click_rect(target_roi)
            time.sleep(0.5)

        return SimRoomState.EXECUTE_QUICK_SIM

    def _step_execute_quick_sim(self) -> SimRoomState:
        """点击快速模拟并处理弹窗结算闭环."""
        logger.info("[SimRoomState] 执行快速模拟...")

        confirmed = self.interact.press_and_confirm(
            label="点击快速模拟",
            press_action=lambda: self.interact.click_rect(ROI_SIM_QUICK_BTN),
            confirmed_check=lambda: (
                self.ocr_text_exists(TEXT_SIM_SKIP_BUFFS, ROI_SIM_SKIP_BUFFS_BTN)
                or self.ocr_text_exists(TEXT_SIM_END_MODAL, ROI_SIM_END_MODAL_TEXT)
                or self.scene.has_reward_claim_modal()
                or self.ocr_text_exists(TEXT_SIM_NOT_5C, ROI_SIM_NOT_5C_PROMPT)
                or self.ocr_text_exists(TEXT_SIM_COMPLETED, ROI_SIM_COMPLETED_PROMPT)
            ),
            still_before_check=lambda: self.ocr_text_exists(TEXT_SIM_QUICK, ROI_SIM_QUICK_BTN),
            timeout=5.0,
            retry_after=1.5,
            retries=2,
        )

        # 检查是否无法快速模拟（非5-C）
        if self.ocr_text_exists(TEXT_SIM_NOT_5C, ROI_SIM_NOT_5C_PROMPT):
            logger.warning("提示仅限 5-C 可以快速模拟，重新选择 5-C 扇区")
            self.interact.click_rect(ROI_SIM_5C_SECTOR)
            time.sleep(0.5)
            self.interact.click_rect(ROI_SIM_QUICK_BTN)

        # 处理跳过增益效果选择
        if self.ocr_text_exists(TEXT_SIM_SKIP_BUFFS, ROI_SIM_SKIP_BUFFS_BTN):
            logger.info("出现增益选择，点击‘跳过增益效果选择’")
            self.interact.click_rect(ROI_SIM_SKIP_BUFFS_BTN)
            time.sleep(0.6)

        # 处理模拟结束/重置确认弹窗
        if self.ocr_text_exists(TEXT_SIM_END_MODAL, ROI_SIM_END_MODAL_TEXT) or self.ocr_text_exists(
            TEXT_CONFIRM, ROI_SIM_END_CONFIRM_BTN
        ):
            logger.info("确认模拟结束，提交技能手册产出结算")
            self.interact.click_rect(ROI_SIM_END_CONFIRM_BTN)
            time.sleep(0.8)

        self.quick_sim_succeeded = True
        return SimRoomState.DISMISS_REWARDS

    def _step_dismiss_rewards(self) -> SimRoomState:
        """消除技能手册与掉落道具结算弹窗."""
        logger.info("[SimRoomState] 清理产出结算弹窗...")
        max_dismiss_clicks = 5

        for _ in range(max_dismiss_clicks):
            if self.scene.has_reward_claim_modal() or self.scene.has_modal_active():
                self.interact.click_rect(ROI_SAFE_CLICK_BLANK)
                time.sleep(0.4)
            else:
                break

        # 点击右上角模拟结束 / 退出图标
        if self.ocr_text_exists(("模拟结束", "结束"), ROI_SIM_TOP_EXIT_BTN):
            self.interact.click_rect(ROI_SIM_TOP_EXIT_BTN)
            time.sleep(0.5)
            if self.ocr_text_exists(TEXT_CONFIRM, ROI_SIM_END_CONFIRM_BTN):
                self.interact.click_rect(ROI_SIM_END_CONFIRM_BTN)
                time.sleep(0.5)

        return SimRoomState.EXIT_TO_HOME

    def _step_exit_to_home(self) -> SimRoomState:
        """确定性退出至大厅主界面."""
        logger.info("[SimRoomState] 确定性退出至大厅主界面...")

        if self.scene.is_in_home():
            logger.info("已成功确认处于大厅，模拟室任务顺利闭环")
            return SimRoomState.COMPLETED

        # 尝试通过大厅兜底恢复
        recovered = self.recovery.recover_to_home()
        if not recovered and not self.scene.is_in_home():
            raise FrozenScreen("未能确定性恢复至大厅主界面")

        return SimRoomState.COMPLETED
