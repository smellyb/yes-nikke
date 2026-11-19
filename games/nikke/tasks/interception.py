"""Production Interception (拦截战 / 异常拦截) task implementation.

Features:
1. Monday skip policy (skip_monday) to preserve attempts for bonus events.
2. Mode & Boss selection (Anomaly 异常拦截 vs Basic 特级拦截, default Kraken 克拉肯 with 5-boss switcher).
3. Resilient battle & sweep execution:
   - Attempts Quick Battle (快速战斗) first.
   - If daily 1st-play prerequisite required, enters combat with AUTO mode enabled.
   - Waits for battle settlement and dismisses victory/defeat popups.
   - Follows with 2 Quick Battle sweeps to consume all daily attempts.
4. Deterministic exit to Lobby Home.
"""

from __future__ import annotations

import datetime
import logging
import time
from enum import Enum, auto
from typing import Any, List, Optional, Tuple

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
    ROI_ARK_INTERCEPTION,
    ROI_INTERCEPTION_TITLE,
    ROI_INTERCEPTION_ATTEMPTS,
    ROI_INTERCEPTION_MODE_ANOMALY,
    ROI_INTERCEPTION_MODE_BASIC,
    ROI_INTERCEPTION_BOSS_SWITCH_BTN,
    ROI_INTERCEPTION_BOSS_KRAKEN,
    ROI_INTERCEPTION_BOSS_TARGET_BTN,
    ROI_INTERCEPTION_QUICK_BATTLE_BTN,
    ROI_INTERCEPTION_ENTER_BATTLE_BTN,
    ROI_INTERCEPTION_CANNOT_QUICK,
    ROI_INTERCEPTION_EXCEEDED,
    ROI_INTERCEPTION_BATTLE_AUTO,
    ROI_INTERCEPTION_SETTLEMENT,
    TEXT_ARK_TITLE,
    TEXT_INTERCEPTION_TITLE,
    TEXT_INTERCEPTION_ATTEMPTS,
    TEXT_INTERCEPTION_ANOMALY,
    TEXT_INTERCEPTION_BASIC,
    TEXT_INTERCEPTION_KRAKEN,
    TEXT_INTERCEPTION_QUICK_BATTLE,
    TEXT_INTERCEPTION_ENTER_BATTLE,
    TEXT_INTERCEPTION_CANNOT_QUICK,
    TEXT_INTERCEPTION_EXCEEDED,
    TEXT_BATTLE_AUTO,
    TEXT_BATTLE_SETTLEMENT,
)
import games.nikke.scene_combat  # Ensure monkey-patched scene methods are loaded

logger = logging.getLogger("yes_nikke.task.interception")

# Canonical Anomaly Boss Registry
ANOMALY_BOSSES = ("克拉肯", "镜体", "收割者", "极皇", "茵迪维利亚")


class InterceptionState(Enum):
    CHECK_WEEKDAY = auto()
    ENTER_ARK = auto()
    ENTER_INTERCEPTION = auto()
    SELECT_MODE_AND_BOSS = auto()
    CHECK_AND_EXECUTE = auto()
    RUN_AUTO_COMBAT = auto()
    SWEEP_REMAINING = auto()
    DISMISS_REWARDS = auto()
    EXIT_TO_HOME = auto()
    COMPLETED = auto()


class InterceptionTask(NikkeTask):
    """【拦截战与异常拦截自动化】命令式任务实现.

    全链路流转：
    周一跳过判定 -> 大厅方舟入口 -> 拦截战 -> 模式与 Boss 选择（默认克拉肯）
    -> 首战自动战斗（如需） -> 剩余快速战斗扫荡 -> 确定性返回大厅。
    """

    def __init__(
        self,
        ctx: Any = None,
        boss_name: str = "克拉肯",
        mode: str = "anomaly",
        skip_monday: bool = False,
        max_attempts: int = 3,
    ) -> None:
        super().__init__(ctx, name="Interception")
        self.boss_name: str = boss_name
        self.mode: str = mode  # "anomaly" (异常) | "basic" (特级/普通)
        self.skip_monday: bool = skip_monday
        self.max_attempts: int = max_attempts
        self.attempts_executed: int = 0
        self.skipped_due_to_monday: bool = False
        self.combat_executed: bool = False
        self.current_state: InterceptionState = InterceptionState.CHECK_WEEKDAY

    def run(self) -> bool:
        """Execute Interception state machine."""
        logger.info(
            f">>> 启动任务：拦截战 (模式={self.mode}, 目标Boss={self.boss_name}, skip_monday={self.skip_monday})"
        )
        self.current_state = InterceptionState.CHECK_WEEKDAY
        self.attempts_executed = 0
        self.skipped_due_to_monday = False
        self.combat_executed = False

        if self.frozen_watch and hasattr(self.frozen_watch, "reset"):
            self.frozen_watch.reset()

        while self.current_state != InterceptionState.COMPLETED:
            try:
                self.ping_watchdog(detected_text=f"inter_state_{self.current_state.name}")

                if self.current_state == InterceptionState.CHECK_WEEKDAY:
                    self.current_state = self._step_check_weekday()
                elif self.current_state == InterceptionState.ENTER_ARK:
                    self.current_state = self._step_enter_ark()
                elif self.current_state == InterceptionState.ENTER_INTERCEPTION:
                    self.current_state = self._step_enter_interception()
                elif self.current_state == InterceptionState.SELECT_MODE_AND_BOSS:
                    self.current_state = self._step_select_mode_and_boss()
                elif self.current_state == InterceptionState.CHECK_AND_EXECUTE:
                    self.current_state = self._step_check_and_execute()
                elif self.current_state == InterceptionState.RUN_AUTO_COMBAT:
                    self.current_state = self._step_run_auto_combat()
                elif self.current_state == InterceptionState.SWEEP_REMAINING:
                    self.current_state = self._step_sweep_remaining()
                elif self.current_state == InterceptionState.DISMISS_REWARDS:
                    self.current_state = self._step_dismiss_rewards()
                elif self.current_state == InterceptionState.EXIT_TO_HOME:
                    self.current_state = self._step_exit_to_home()
                else:
                    raise RuntimeError(f"未处理的拦截战异常状态: {self.current_state}")

            except FrozenScreen as exc:
                logger.error(f"拦截战触发卡死告警: {exc}，执行大厅确定性恢复")
                self.recovery.recover_to_home()
                return False

        logger.info(
            f"<<< 任务完成：拦截战执行完毕 (总计执行 {self.attempts_executed} 次，周一跳过={self.skipped_due_to_monday})"
        )
        return True

    def _step_check_weekday(self) -> InterceptionState:
        """检查周一跳过策略 (skip_monday)."""
        logger.info("[InterState] 检查拦截战日期调度策略...")
        is_monday = datetime.date.today().weekday() == 0

        # Context mock override support
        if self.ctx and hasattr(self.ctx, "mock_weekday"):
            is_monday = self.ctx.mock_weekday == 0

        if self.skip_monday and is_monday:
            logger.info("今天是周一且配置了 skip_monday=True，安全跳过今日拦截战任务")
            self.skipped_due_to_monday = True
            return InterceptionState.COMPLETED

        return InterceptionState.ENTER_ARK

    def _step_enter_ark(self) -> InterceptionState:
        """从大厅进入方舟 Hub."""
        logger.info("[InterState] 进入方舟 Hub...")

        if self.scene.is_in_interception():
            logger.info("检测到已位于拦截战面板，直接进行模式与 Boss 选择")
            return InterceptionState.SELECT_MODE_AND_BOSS

        if self.scene.is_in_ark():
            logger.info("已位于方舟 Hub，直接进入拦截战")
            return InterceptionState.ENTER_INTERCEPTION

        confirmed = self.interact.press_and_confirm(
            label="大厅点击方舟入口",
            press_action=lambda: self.interact.click_rect(ROI_HOME_ARK_BTN),
            confirmed_check=lambda: self.scene.is_in_ark() or self.scene.is_in_interception(),
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
                confirmed_check=lambda: self.scene.is_in_ark() or self.scene.is_in_interception(),
                still_before_check=lambda: self.scene.is_in_home(),
                timeout=4.0,
                retry_after=1.5,
                retries=2,
            )

        if not confirmed and not self.scene.is_in_ark() and not self.scene.is_in_interception():
            raise FrozenScreen("未能成功进入方舟 Hub")

        return InterceptionState.ENTER_INTERCEPTION

    def _step_enter_interception(self) -> InterceptionState:
        """在方舟 Hub 中点击拦截战入口."""
        logger.info("[InterState] 进入拦截战入口...")

        if self.scene.is_in_interception():
            return InterceptionState.SELECT_MODE_AND_BOSS

        confirmed = self.interact.press_and_confirm(
            label="方舟点击拦截战入口",
            press_action=lambda: self.interact.click_rect(ROI_ARK_INTERCEPTION),
            confirmed_check=lambda: self.scene.is_in_interception(),
            still_before_check=lambda: self.scene.is_in_ark(),
            timeout=5.0,
            retry_after=1.5,
            retries=2,
        )

        if not confirmed and not self.scene.is_in_interception():
            raise FrozenScreen("未能进入拦截战面板（入口无响应或未识别到拦截战）")

        return InterceptionState.SELECT_MODE_AND_BOSS

    def _step_select_mode_and_boss(self) -> InterceptionState:
        """选择拦截战模式（异常拦截/特拦）与目标 Boss."""
        logger.info(f"[InterState] 配置拦截模式={self.mode}, Boss={self.boss_name}...")
        time.sleep(0.5)

        # 检查是否已无可用次数 ("已超出进入次数")
        if self.ocr_text_exists(TEXT_INTERCEPTION_EXCEEDED, ROI_INTERCEPTION_EXCEEDED):
            logger.info("检测到拦截战剩余次数为 0 (已超出进入次数)，准备退出")
            return InterceptionState.EXIT_TO_HOME

        # 1. 切换模式
        if self.mode.lower() == "basic" or "特级" in self.mode:
            logger.info("切换至特级/普通拦截模式")
            self.interact.click_rect(ROI_INTERCEPTION_MODE_BASIC)
        else:
            logger.info("切换至异常拦截模式")
            self.interact.click_rect(ROI_INTERCEPTION_MODE_ANOMALY)
        time.sleep(0.6)

        # 2. 目标 Boss 选择（默认克拉肯）
        if self.boss_name == "克拉肯" or self.boss_name.lower() == "kraken":
            logger.info("目标 Boss 为默认【克拉肯】，直接定位目标")
            self.interact.click_rect(ROI_INTERCEPTION_BOSS_TARGET_BTN)
        else:
            # 尝试通过切换按钮循环定位指定 Boss
            logger.info(f"目标 Boss 为【{self.boss_name}】，尝试切换定位")
            max_switches = 5
            found = False
            for _ in range(max_switches):
                if self.ocr_text_exists(self.boss_name, (400, 400, 480, 200)):
                    found = True
                    break
                self.interact.click_rect(ROI_INTERCEPTION_BOSS_SWITCH_BTN)
                time.sleep(0.5)
            self.interact.click_rect(ROI_INTERCEPTION_BOSS_TARGET_BTN)

        time.sleep(0.5)
        return InterceptionState.CHECK_AND_EXECUTE

    def _step_check_and_execute(self) -> InterceptionState:
        """尝试快速战斗；若提示需要先游玩 1 次，则转入实战战斗."""
        logger.info("[InterState] 尝试执行快速战斗...")

        # 检查次数是否已超出
        if self.ocr_text_exists(TEXT_INTERCEPTION_EXCEEDED, ROI_INTERCEPTION_EXCEEDED):
            logger.info("拦截战已超出进入次数，结束挑战")
            return InterceptionState.EXIT_TO_HOME

        # 点击快速战斗
        self.interact.click_rect(ROI_INTERCEPTION_QUICK_BATTLE_BTN)
        time.sleep(0.8)

        # 检查是否提示 "每日至少游玩1次后" / 无法快速战斗
        if self.ocr_text_exists(TEXT_INTERCEPTION_CANNOT_QUICK, ROI_INTERCEPTION_CANNOT_QUICK):
            logger.info("检测到尚未完成今日首次实战（每日至少游玩1次），启动自动战斗...")
            return InterceptionState.RUN_AUTO_COMBAT

        # 检查是否成功触发掉落弹窗（直接快速战斗成功）
        if self.scene.has_reward_claim_modal():
            logger.info("首发快速战斗扫荡成功！")
            self.attempts_executed += 1
            self.interact.click_rect(ROI_SAFE_CLICK_BLANK)
            time.sleep(0.5)
            return InterceptionState.SWEEP_REMAINING

        # 检查是否进入战斗或出现进入战斗按钮
        if self.ocr_text_exists(TEXT_INTERCEPTION_ENTER_BATTLE, ROI_INTERCEPTION_ENTER_BATTLE_BTN):
            return InterceptionState.RUN_AUTO_COMBAT

        return InterceptionState.SWEEP_REMAINING

    def _step_run_auto_combat(self) -> InterceptionState:
        """执行 1 次实战自动战斗，等待战斗结算完成."""
        logger.info("[InterState] 点击‘进入战斗’开始 1 次自动战斗挑战...")

        self.interact.click_rect(ROI_INTERCEPTION_ENTER_BATTLE_BTN)
        time.sleep(1.0)

        # 确认进入战斗画面并开启 AUTO
        logger.info("等待加载进入战斗画面...")
        battle_started = False
        for _ in range(15):
            if self.ocr_text_exists(TEXT_BATTLE_AUTO, ROI_INTERCEPTION_BATTLE_AUTO) or (
                self.ctx and getattr(self.ctx, "mock_in_battle", False)
            ):
                battle_started = True
                break
            time.sleep(0.5)

        if battle_started:
            logger.info("成功进入战斗画面，确认 AUTO 自动射击/爆裂开启")
            self.interact.click_rect(ROI_INTERCEPTION_BATTLE_AUTO)

        # 等待战斗结算 ("点击任意处" / "胜利" / "失败")
        logger.info("等待战斗结算完成...")
        max_combat_wait = 60  # 最长等待 60s
        start_wait = time.time()
        while time.time() - start_wait < max_combat_wait:
            self.ping_watchdog(detected_text="waiting_interception_combat_settle")

            # Mock 场景直接结算
            if self.ctx and getattr(self.ctx, "mock_combat_settled", True):
                break

            if self.ocr_text_exists(TEXT_BATTLE_SETTLEMENT, ROI_INTERCEPTION_SETTLEMENT) or (
                self.scene.has_reward_claim_modal()
            ):
                break
            time.sleep(1.0)

        logger.info("战斗结束，点击结算画面返回拦截战面板...")
        self.interact.click_rect(ROI_SAFE_CLICK_BLANK)
        time.sleep(0.8)
        self.attempts_executed += 1
        self.combat_executed = True

        return InterceptionState.SWEEP_REMAINING

    def _step_sweep_remaining(self) -> InterceptionState:
        """执行剩余快速战斗扫荡（直至消耗完全部 3 次挑战机会）."""
        logger.info(f"[InterState] 执行剩余快速战斗扫荡 (已执行 {self.attempts_executed}/{self.max_attempts})...")

        while self.attempts_executed < self.max_attempts:
            # 检查次数是否已耗尽
            if self.ocr_text_exists(TEXT_INTERCEPTION_EXCEEDED, ROI_INTERCEPTION_EXCEEDED):
                logger.info("检测到已超出进入次数，快速战斗扫荡结束")
                break

            # 点击快速战斗
            logger.info(f"点击快速战斗扫荡第 {self.attempts_executed + 1} 次...")
            self.interact.click_rect(ROI_INTERCEPTION_QUICK_BATTLE_BTN)
            time.sleep(0.8)

            # 消除掉落结算弹窗
            if self.scene.has_reward_claim_modal() or (
                self.ctx and getattr(self.ctx, "mock_reward_modal", False)
            ):
                logger.info("快速战斗成功，领取掉落装备与产出")
                self.interact.click_rect(ROI_SAFE_CLICK_BLANK)
                time.sleep(0.5)

            self.attempts_executed += 1

        return InterceptionState.DISMISS_REWARDS

    def _step_dismiss_rewards(self) -> InterceptionState:
        """清理任何残留的结算弹窗."""
        logger.info("[InterState] 清理拦截战残留奖励弹窗...")
        for _ in range(3):
            if self.scene.has_reward_claim_modal() or self.scene.has_modal_active():
                self.interact.click_rect(ROI_SAFE_CLICK_BLANK)
                time.sleep(0.4)
            else:
                break

        return InterceptionState.EXIT_TO_HOME

    def _step_exit_to_home(self) -> InterceptionState:
        """确定性退出至大厅主界面."""
        logger.info("[InterState] 确定性退出至大厅主界面...")

        if self.scene.is_in_home():
            return InterceptionState.COMPLETED

        recovered = self.recovery.recover_to_home()
        if not recovered and not self.scene.is_in_home():
            raise FrozenScreen("未能确定性恢复至大厅主界面")

        return InterceptionState.COMPLETED
