"""Production-grade Outpost Defense and Wipeout task implementation for NIKKE.

Features:
1. Closed-loop confirmation (press_and_confirm): Claim and wipeout strictly wait for state transitions.
2. Asset protection: Diamond wipes strictly governed by configured thresholds with retries=0.
3. Adaptive popup absorption: Gracefully dismisses cascading PASS promotion, level-up, and drop modals.
4. Deterministic exit: Guarantees return to Lobby verified against bottom navigation tabs.
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
    ROI_TITLE,
    ROI_OUTPOST_TITLE,
    ROI_CLAIM_BTN,
    ROI_SWEEP_BTN,
    ROI_SWEEP_CONFIRM_BTN,
    ROI_SWEEP_CANCEL_BTN,
    ROI_SWEEP_FREE_TAG,
    ROI_SWEEP_GEM_CONFIRM_BTN,
    ROI_GLOBAL_CLOSE,
    ROI_TOP_LEFT_BACK,
    ROI_SAFE_CLICK_BLANK,
    ROI_OUTPOST_NO_REWARD,
    TEXT_OUTPOST_TITLE,
    TEXT_CLAIM_REWARD,
    TEXT_SWEEP,
    TEXT_SWEEP_CONFIRM,
    TEXT_CANCEL,
)

logger = logging.getLogger("yes_nikke.task.outpost")


class OutpostState(Enum):
    ENTER_OUTPOST = auto()
    CHECK_DEFENSE_PANEL = auto()
    CLAIM_OUTPOST_REWARD = auto()
    HANDLE_SWEEP_MODAL = auto()
    EXECUTE_SWEEP = auto()
    DISMISS_REWARD_POPUP = auto()
    EXIT_TO_HOME = auto()
    COMPLETED = auto()


class OutpostDefenseTask(NikkeTask):
    """【前哨防御与一举歼灭】纯 Python 命令式状态机实现.

    针对性特性：
    1. 闭环确认：领取与歼灭点击严格等待奖励弹窗回馈；
    2. 资产安全：钻石歼灭次数由配置严格门限控制，retries=0；
    3. 动态容错：自动吸收 PASS 升级、等级提升等突发遮罩；
    4. 纯净退出：退出时校验大厅图标，不达目标绝不标记 Success。
    """

    # 1280x720 逻辑坐标常量
    ROI_HOME_OUTPOST_BTN: Tuple[int, int, int, int] = ROI_HOME_OUTPOST_BTN
    ROI_TITLE: Tuple[int, int, int, int] = ROI_TITLE
    ROI_CLAIM_BTN: Tuple[int, int, int, int] = ROI_CLAIM_BTN
    ROI_SWEEP_BTN: Tuple[int, int, int, int] = ROI_SWEEP_BTN
    ROI_SWEEP_CONFIRM_BTN: Tuple[int, int, int, int] = ROI_SWEEP_CONFIRM_BTN
    ROI_SWEEP_CANCEL_BTN: Tuple[int, int, int, int] = ROI_SWEEP_CANCEL_BTN
    ROI_SWEEP_FREE_TAG: Tuple[int, int, int, int] = ROI_SWEEP_FREE_TAG
    ROI_GLOBAL_CLOSE: Tuple[int, int, int, int] = ROI_GLOBAL_CLOSE

    def __init__(self, ctx: Any = None, max_diamond_sweeps: int = 0) -> None:
        super().__init__(ctx, name="OutpostDefense")
        self.max_diamond_sweeps: int = max_diamond_sweeps
        self.current_diamond_sweeps: int = 0
        self.free_sweep_done: bool = False
        self.current_state: OutpostState = OutpostState.ENTER_OUTPOST

    def run(self) -> bool:
        """Execute Outpost Defense state machine."""
        logger.info(">>> 启动任务：前哨防御与一举歼灭")
        self.current_state = OutpostState.ENTER_OUTPOST
        self.current_diamond_sweeps = 0
        self.free_sweep_done = False

        if self.frozen_watch and hasattr(self.frozen_watch, "reset"):
            self.frozen_watch.reset()

        while self.current_state != OutpostState.COMPLETED:
            try:
                # 喂狗：记录当前步骤有效推进
                self.ping_watchdog(detected_text=f"state_{self.current_state.name}")

                if self.current_state == OutpostState.ENTER_OUTPOST:
                    self.current_state = self._step_enter_outpost()
                elif self.current_state == OutpostState.CHECK_DEFENSE_PANEL:
                    self.current_state = self._step_check_defense_panel()
                elif self.current_state == OutpostState.CLAIM_OUTPOST_REWARD:
                    self.current_state = self._step_claim_reward()
                elif self.current_state == OutpostState.HANDLE_SWEEP_MODAL:
                    self.current_state = self._step_handle_sweep()
                elif self.current_state == OutpostState.EXIT_TO_HOME:
                    self.current_state = self._step_exit_to_home()
                else:
                    raise RuntimeError(f"未处理的异常状态: {self.current_state}")

            except FrozenScreen as exc:
                logger.error(f"前哨防御触发卡死看门狗告警: {exc}，启动确定性恢复大厅")
                self.recovery.recover_to_home()
                return False

        logger.info("<<< 任务完成：前哨防御与一举歼灭成功执行完毕")
        return True

    def _step_enter_outpost(self) -> OutpostState:
        """从大厅点击前哨基地，闭环确认标题出现."""
        logger.info("[State] 进入前哨基地...")

        # If already inside outpost defense panel, proceed directly
        if self.scene.is_in_outpost() or self.ocr_text_exists(TEXT_OUTPOST_TITLE, self.ROI_TITLE):
            logger.info("已位于前哨防御面板，跳过大厅点击入口")
            return OutpostState.CHECK_DEFENSE_PANEL

        # 闭环确认：点击前哨基地后，必须在 4s 内观察到标题 "防御前哨基地" 或进入前哨界面
        confirmed = self.interact.press_and_confirm(
            label="大厅点击前哨基地",
            press_action=lambda: self.interact.click_rect(self.ROI_HOME_OUTPOST_BTN),
            confirmed_check=lambda: self.scene.is_in_outpost() or self.ocr_text_exists(TEXT_OUTPOST_TITLE, self.ROI_TITLE),
            still_before_check=lambda: self.scene.is_in_home(),
            timeout=4.0,
            retry_after=1.5,
            retries=2,
        )

        if not confirmed:
            raise FrozenScreen("未能成功进入前哨基地面板（点击无响应或标题未识别）")

        return OutpostState.CHECK_DEFENSE_PANEL

    def _step_check_defense_panel(self) -> OutpostState:
        """检查面板状态，决定先领奖还是一举歼灭."""
        time.sleep(0.5)  # 缓冲 UI 淡入动画
        logger.info("[State] 检查前哨基地防御面板奖励状态...")

        # 检查是否有累积奖励可领（文字 OCR "获得奖励" / 模板存在）
        has_reward = self.ocr_text_exists(TEXT_CLAIM_REWARD, self.ROI_CLAIM_BTN)

        # 辅助检查：如果显式检测到“无可获得”，则确认无奖励
        has_no_reward = self.ocr_text_exists("无可获得", ROI_OUTPOST_NO_REWARD)

        if has_reward and not has_no_reward:
            logger.info("检测到可领取累积挂机奖励，转入领奖步骤")
            return OutpostState.CLAIM_OUTPOST_REWARD
        else:
            logger.info("当前无累积防御奖励或已领取完毕，转入一举歼灭判定")
            return OutpostState.HANDLE_SWEEP_MODAL

    def _step_claim_reward(self) -> OutpostState:
        """点击领取挂机累积奖励，并闭环清除奖励飞入弹窗."""
        logger.info("[State] 正在领取前哨基地累积挂机奖励...")

        # 闭环确认：点击“获得奖励”后，必须出现结算道具光晕或“点击任意区域关闭”
        claimed = self.interact.press_and_confirm(
            label="点击获得奖励",
            press_action=lambda: self.interact.click_rect(self.ROI_CLAIM_BTN),
            confirmed_check=lambda: self.scene.has_reward_claim_modal(),
            still_before_check=lambda: self.ocr_text_exists(TEXT_CLAIM_REWARD, self.ROI_CLAIM_BTN),
            timeout=3.0,
            retries=1,
        )

        if claimed:
            logger.info("检测到奖励到账弹窗，执行点击空白处关闭...")
            self._dismiss_reward_modals()
        else:
            logger.warning("领取奖励未触发弹窗，可能已在网络端同步或无奖励")

        return OutpostState.HANDLE_SWEEP_MODAL

    def _step_handle_sweep(self) -> OutpostState:
        """处理一举歼灭逻辑（免费 + 阈值内钻石）."""
        logger.info("[State] 打开一举歼灭窗口...")

        # 闭环打开歼灭窗口
        opened = self.interact.press_and_confirm(
            label="点击一举歼灭入口",
            press_action=lambda: self.interact.click_rect(self.ROI_SWEEP_BTN),
            confirmed_check=lambda: self.scene.has_sweep_modal() or self.ocr_text_exists(TEXT_SWEEP_CONFIRM, self.ROI_SWEEP_CONFIRM_BTN),
            timeout=3.0,
            retries=1,
        )

        if not opened:
            logger.warning("无法打开一举歼灭确认框（可能已达当日全部上限或不在前哨），准备退出")
            return OutpostState.EXIT_TO_HOME

        # 判定是否免费：检查有无消耗钻石模板或文字
        is_free = False
        if not self.free_sweep_done:
            has_diamond_icon = bool(
                self.find_template_multidim("outpostdefense/spendzuan.png", self.ROI_SWEEP_FREE_TAG)
                or self.find_template_multidim("spendzuan.png", self.ROI_SWEEP_FREE_TAG)
            )
            has_free_text = self.ocr_text_exists(("免费", "0"), self.ROI_SWEEP_FREE_TAG)
            if has_free_text or (not has_diamond_icon):
                is_free = True

        if is_free:
            logger.info("检测到当前为【免费】一举歼灭，立即执行")
            self._execute_single_sweep(is_diamond=False)
            self.free_sweep_done = True
            # 免费歼灭完成后，返回继续评估是否需要进行钻石歼灭
            return OutpostState.HANDLE_SWEEP_MODAL

        # 钻石歼灭门限判定
        if self.current_diamond_sweeps < self.max_diamond_sweeps:
            logger.info(
                f"执行【钻石】一举歼灭 (当前第 {self.current_diamond_sweeps + 1} 次, 上限 {self.max_diamond_sweeps} 次)"
            )
            self._execute_single_sweep(is_diamond=True)
            self.current_diamond_sweeps += 1
            return OutpostState.HANDLE_SWEEP_MODAL
        else:
            logger.info(f"已达到钻石一举歼灭上限 ({self.max_diamond_sweeps})，关闭歼灭窗口")
            # 点击取消退出弹窗
            self.interact.click_rect(self.ROI_SWEEP_CANCEL_BTN)
            time.sleep(0.6)
            return OutpostState.EXIT_TO_HOME

    def _execute_single_sweep(self, is_diamond: bool) -> None:
        """执行单次歼灭确认并消化结算动画."""
        # 钻石消费操作绝对安全：强制 retries=0！
        retries_allowed = 0 if is_diamond else 1

        confirmed = self.interact.press_and_confirm(
            label="点击进行歼灭确认",
            press_action=lambda: self.interact.click_rect(self.ROI_SWEEP_CONFIRM_BTN),
            confirmed_check=lambda: self.scene.has_reward_claim_modal() or self.scene.check_text_in_roi(("是否消耗珠宝", "今日不再显示"), (400, 200, 480, 320)),
            timeout=4.0,
            retries=retries_allowed,
        )

        # 处理钻石二次确认弹窗（“是否消耗珠宝”）
        if self.scene.check_text_in_roi(("是否消耗珠宝", "优先扣除免费珠宝"), (400, 200, 480, 320)):
            logger.info("检测到钻石二次扣费确认弹窗，点击确认...")
            self.interact.click_rect(ROI_SWEEP_GEM_CONFIRM_BTN)
            time.sleep(0.6)

        if confirmed:
            logger.info("一举歼灭成功触发，消化结算展示...")
            self._dismiss_reward_modals()
        else:
            logger.error("一举歼灭执行失败（未检测到结算反馈）")

    def _dismiss_reward_modals(self) -> None:
        """鲁棒清除所有级联结算弹窗（防偶发 PASS 升级弹窗）."""
        self.recovery.sweep_modals(max_passes=5)

    def _step_exit_to_home(self) -> OutpostState:
        """确定性退出前哨基地，验证大厅归位."""
        logger.info("[State] 退出前哨基地，返回大厅...")

        # 优先点击左上角返回按钮
        self.interact.press_and_confirm(
            label="点击返回大厅",
            press_action=lambda: self.interact.click_rect(ROI_TOP_LEFT_BACK),
            confirmed_check=lambda: self.scene.is_in_home(),
            still_before_check=lambda: self.ocr_text_exists(TEXT_OUTPOST_TITLE, self.ROI_TITLE),
            timeout=3.0,
            retries=2,
        )

        if not self.scene.is_in_home():
            # 兜底：如果常规返回未抵达大厅，调用确定性恢复机制
            logger.warning("常规返回未抵达大厅，启动 recover_to_home 兜底")
            self.recovery.recover_to_home(max_attempts=3)

        if self.scene.is_in_home():
            logger.info("已成功返回游戏大厅")
            return OutpostState.COMPLETED
        else:
            raise FrozenScreen("未能确定性返回游戏大厅")
