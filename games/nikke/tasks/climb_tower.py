"""Climb Tower (Tribe Tower / Unlimited Tower & Corporate Towers) task for NIKKE.

Features:
1. Closed-loop navigation from Lobby into Ark (方舟) and Tribe Tower (无限之塔).
2. Unlimited Tower (无限之塔) daily challenge:
   - Inspects remaining attempts (剩余次数, e.g. 3/3 vs 0/3).
   - Enters battle, waits for auto-combat resolution, handles victory or defeat.
   - Automatically handles Phoebe's flash sale popups (菲比的特惠礼包).
3. Corporate Towers (企业塔) traversal:
   - Sequentially inspects today's open status for Elysion (极乐净土), Missilis (米西利斯),
     Tetra (泰特拉), and Pilgrim (朝圣者).
   - Enters open corporate towers, executes daily attempts, and clears settlements.
4. Deterministic return to Lobby verified by scene discriminator.
"""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from core.ops.frozen_watch import FrozenScreen
from games.nikke.base_nikke_task import NikkeTask
import games.nikke.scene_growth  # Ensure scene discriminators are registered
from games.nikke.constants_growth import (
    ROI_HOME_BOTTOM_ARK,
    ROI_ARK_TITLE,
    ROI_TOWER_ENTRY_BTN,
    ROI_TOWER_TITLE,
    ROI_TOWER_STATUS_HEADER,
    ROI_TOWER_UNLIMITED_BTN,
    ROI_TOWER_UNLIMITED_TAG,
    ROI_TOWER_FORMATION_TAG,
    ROI_TOWER_REMAIN_CHANCES,
    ROI_TOWER_CHANCE_COUNT,
    ROI_TOWER_ENTER_FIGHT_BTN,
    ROI_TOWER_FIGHT_END_TAP,
    ROI_TOWER_FIGHT_RESULT,
    ROI_TOWER_FAILED_BACK_BTN,
    ROI_TOWER_FLASH_SALE_AREA,
    ROI_TOWER_FLASH_SALE_CLOSE,
    ROI_TOWER_EXIT_PAGE_BTN,
    ROI_COP_TOWER_ELYSIO,
    ROI_COP_TOWER_MISSILIS,
    ROI_COP_TOWER_TETRA,
    ROI_COP_TOWER_PILGRIM,
    ROI_TOP_LEFT_BACK,
    ROI_SAFE_CLICK_BLANK,
    ROI_GLOBAL_CLOSE,
    TEXT_TOWER_TITLE,
    TEXT_TOWER_UNLIMITED,
    TEXT_TOWER_ENTER_FIGHT,
    TEXT_TOWER_REMAIN_CHANCES,
    TEXT_TOWER_CHANCE_ZERO,
    TEXT_TOWER_FIGHT_END,
    TEXT_TOWER_FAILED,
    TEXT_TOWER_FLASH_SALE,
    TEXT_COP_TOWER_OPEN,
    TEXT_COP_TOWER_CLOSED,
)

logger = logging.getLogger("yes_nikke.task.climb_tower")


class TowerState(Enum):
    ENTER_ARK = auto()
    ENTER_TOWER_MAIN = auto()
    CHALLENGE_UNLIMITED = auto()
    CHALLENGE_CORPORATE = auto()
    SWEEP_AND_EXIT = auto()
    COMPLETED = auto()


class ClimbTowerTask(NikkeTask):
    """【无限塔与企业塔日常挑战】命令式状态机任务实现."""

    def __init__(
        self,
        ctx: Any = None,
        challenge_unlimited: bool = True,
        challenge_corporate: bool = True,
        max_combat_wait_seconds: float = 180.0,
    ) -> None:
        super().__init__(ctx, name="ClimbTower")
        self.challenge_unlimited: bool = challenge_unlimited
        self.challenge_corporate: bool = challenge_corporate
        self.max_combat_wait_seconds: float = max_combat_wait_seconds

        self.current_state: TowerState = TowerState.ENTER_ARK
        self.unlimited_battles_done: int = 0
        self.corporate_battles_done: int = 0

    def run(self) -> bool:
        """Execute Climb Tower state machine."""
        logger.info(">>> 启动任务：方舟无限之塔与企业塔日常爬塔")
        self.current_state = TowerState.ENTER_ARK
        self.unlimited_battles_done = 0
        self.corporate_battles_done = 0

        if self.frozen_watch and hasattr(self.frozen_watch, "reset"):
            self.frozen_watch.reset()

        while self.current_state != TowerState.COMPLETED:
            try:
                self.ping_watchdog(detected_text=f"state_{self.current_state.name}")

                if self.current_state == TowerState.ENTER_ARK:
                    self.current_state = self._step_enter_ark()
                elif self.current_state == TowerState.ENTER_TOWER_MAIN:
                    self.current_state = self._step_enter_tower_main()
                elif self.current_state == TowerState.CHALLENGE_UNLIMITED:
                    self.current_state = self._step_challenge_unlimited()
                elif self.current_state == TowerState.CHALLENGE_CORPORATE:
                    self.current_state = self._step_challenge_corporate()
                elif self.current_state == TowerState.SWEEP_AND_EXIT:
                    self.current_state = self._step_sweep_and_exit()
                else:
                    raise RuntimeError(f"未处理的异常状态: {self.current_state}")

            except FrozenScreen as exc:
                logger.error(f"爬塔任务触发卡死看门狗告警: {exc}，启动确定性恢复大厅")
                self.recovery.recover_to_home()
                return False

        logger.info(
            f"<<< 任务完成：爬塔执行完毕 (无限塔场次: {self.unlimited_battles_done}, "
            f"企业塔场次: {self.corporate_battles_done})"
        )
        return True

    def _step_enter_ark(self) -> TowerState:
        """从大厅进入方舟界面."""
        logger.info("[State] 进入方舟界面...")

        # 检查是否已在爬塔或方舟界面
        if self.scene.is_in_tower():
            logger.info("已位于爬塔界面，跳过方舟导航")
            return TowerState.CHALLENGE_UNLIMITED if self.challenge_unlimited else TowerState.CHALLENGE_CORPORATE

        if self.ocr_text_exists("方舟", ROI_ARK_TITLE):
            logger.info("已位于方舟界面，直接进入爬塔")
            return TowerState.ENTER_TOWER_MAIN

        # 从大厅点击底部导航栏 "方舟"
        confirmed = self.interact.press_and_confirm(
            label="点击底部方舟入口",
            press_action=lambda: self.interact.click_rect(ROI_HOME_BOTTOM_ARK),
            confirmed_check=lambda: self.ocr_text_exists("方舟", ROI_ARK_TITLE)
            or self.scene.is_in_tower()
            or self.ocr_text_exists("无限之塔", ROI_TOWER_ENTRY_BTN),
            still_before_check=lambda: self.scene.is_in_home(),
            timeout=5.0,
            retries=2,
        )

        if not confirmed and not self.scene.is_in_tower():
            raise FrozenScreen("未能成功进入方舟界面")

        logger.info("成功就绪在方舟界面")
        return TowerState.ENTER_TOWER_MAIN

    def _step_enter_tower_main(self) -> TowerState:
        """从方舟界面点击进入无限之塔建筑."""
        logger.info("[State] 进入无限之塔建筑...")

        if self.scene.is_in_tower() or self.ocr_text_exists(TEXT_TOWER_TITLE, ROI_TOWER_TITLE):
            logger.info("已处于无限之塔主界面")
            return TowerState.CHALLENGE_UNLIMITED if self.challenge_unlimited else TowerState.CHALLENGE_CORPORATE

        confirmed = self.interact.press_and_confirm(
            label="点击方舟无限之塔建筑",
            press_action=lambda: self.interact.click_rect(ROI_TOWER_ENTRY_BTN),
            confirmed_check=lambda: self.scene.is_in_tower()
            or self.ocr_text_exists(TEXT_TOWER_TITLE, ROI_TOWER_TITLE)
            or self.ocr_text_exists(TEXT_TOWER_UNLIMITED, ROI_TOWER_UNLIMITED_TAG),
            timeout=5.0,
            retries=2,
        )

        if not confirmed and not self.scene.is_in_tower():
            raise FrozenScreen("未能成功进入无限之塔主界面")

        logger.info("成功就绪在无限之塔选择界面")
        return TowerState.CHALLENGE_UNLIMITED if self.challenge_unlimited else TowerState.CHALLENGE_CORPORATE

    def _step_challenge_unlimited(self) -> TowerState:
        """检测无限塔今日挑战次数并执行日常战斗."""
        if not self.challenge_unlimited:
            logger.info("配置未启用无限塔挑战，转入企业塔步骤")
            return TowerState.CHALLENGE_CORPORATE

        logger.info("[State] 进入中央无限之塔...")

        # 点击中央无限塔入口
        entered = self.interact.press_and_confirm(
            label="点击中央无限塔入口",
            press_action=lambda: self.interact.click_rect(ROI_TOWER_UNLIMITED_BTN),
            confirmed_check=lambda: self.ocr_text_exists("通关阵容", ROI_TOWER_FORMATION_TAG)
            or self.ocr_text_exists(TEXT_TOWER_ENTER_FIGHT, ROI_TOWER_ENTER_FIGHT_BTN)
            or self.ocr_text_exists(TEXT_TOWER_REMAIN_CHANCES, ROI_TOWER_REMAIN_CHANCES),
            timeout=4.0,
            retries=2,
        )

        if not entered:
            logger.warning("未能进入无限之塔详情页，尝试直接检查企业塔")
            return TowerState.CHALLENGE_CORPORATE

        time.sleep(0.5)

        # 检查剩余次数
        has_zero_chance = self.ocr_text_exists(TEXT_TOWER_CHANCE_ZERO, ROI_TOWER_CHANCE_COUNT) or self.ocr_text_exists(
            TEXT_TOWER_CHANCE_ZERO, ROI_TOWER_REMAIN_CHANCES
        )

        if has_zero_chance:
            logger.info("无限之塔今日可用挑战次数为 0，退出并准备进入企业塔")
            self._exit_tower_page()
            return TowerState.CHALLENGE_CORPORATE

        # 检查并点击 "进入战斗"
        if self.ocr_text_exists(TEXT_TOWER_ENTER_FIGHT, ROI_TOWER_ENTER_FIGHT_BTN):
            logger.info("检测到无限塔可挑战，点击'进入战斗'...")
            self.interact.click_rect(ROI_TOWER_ENTER_FIGHT_BTN)
            time.sleep(1.5)

            # 等待战斗与结算
            success = self._wait_combat_and_settle()
            if success:
                self.unlimited_battles_done += 1
                logger.info(f"无限塔战斗执行完毕 (成功累加 1 次)")

        # 退出无限塔详情页，返回塔列表界面
        self._exit_tower_page()
        return TowerState.CHALLENGE_CORPORATE

    def _step_challenge_corporate(self) -> TowerState:
        """自动遍历今日开放的企业塔（极乐净土、米西利斯、泰特拉、朝圣者）进行日常挑战."""
        if not self.challenge_corporate:
            logger.info("配置未启用企业塔挑战，直接转入清扫状态")
            return TowerState.SWEEP_AND_EXIT

        logger.info("[State] 开始遍历 4 大企业塔...")

        corporate_towers: List[Dict[str, Any]] = [
            {"name": "极乐净土 (Elysion)", "roi": ROI_COP_TOWER_ELYSIO},
            {"name": "米西利斯 (Missilis)", "roi": ROI_COP_TOWER_MISSILIS},
            {"name": "泰特拉 (Tetra)", "roi": ROI_COP_TOWER_TETRA},
            {"name": "朝圣者 (Pilgrim)", "roi": ROI_COP_TOWER_PILGRIM},
        ]

        for tower in corporate_towers:
            t_name = tower["name"]
            t_roi = tower["roi"]
            logger.info(f"--- 检查企业塔：{t_name} (ROI={t_roi}) ---")

            # 检查该企业塔是否开放（若识别到"未开启"或无"开启"，则安全跳过）
            is_closed = self.ocr_text_exists(TEXT_COP_TOWER_CLOSED, t_roi)
            if is_closed:
                logger.info(f"企业塔 {t_name} 今日未开启，安全跳过")
                continue

            # 点击进入该企业塔
            logger.info(f"尝试进入企业塔：{t_name}...")
            entered = self.interact.press_and_confirm(
                label=f"进入企业塔 {t_name}",
                press_action=lambda roi=t_roi: self.interact.click_rect(roi),
                confirmed_check=lambda: self.ocr_text_exists("通关阵容", ROI_TOWER_FORMATION_TAG)
                or self.ocr_text_exists(TEXT_TOWER_ENTER_FIGHT, ROI_TOWER_ENTER_FIGHT_BTN)
                or self.ocr_text_exists(TEXT_TOWER_REMAIN_CHANCES, ROI_TOWER_REMAIN_CHANCES),
                timeout=3.5,
                retries=2,
            )

            if not entered:
                logger.info(f"企业塔 {t_name} 点击无响应或未开放，跳过")
                continue

            time.sleep(0.5)

            # 检查剩余次数
            has_zero = self.ocr_text_exists(TEXT_TOWER_CHANCE_ZERO, ROI_TOWER_CHANCE_COUNT) or self.ocr_text_exists(
                TEXT_TOWER_CHANCE_ZERO, ROI_TOWER_REMAIN_CHANCES
            )

            if has_zero:
                logger.info(f"企业塔 {t_name} 今日挑战次数已耗尽 (0/3)")
            else:
                if self.ocr_text_exists(TEXT_TOWER_ENTER_FIGHT, ROI_TOWER_ENTER_FIGHT_BTN):
                    logger.info(f"企业塔 {t_name} 触发'进入战斗'...")
                    self.interact.click_rect(ROI_TOWER_ENTER_FIGHT_BTN)
                    time.sleep(1.5)

                    success = self._wait_combat_and_settle()
                    if success:
                        self.corporate_battles_done += 1
                        logger.info(f"企业塔 {t_name} 战斗完成")

            # 退出该企业塔详情页，返回塔选择界面
            self._exit_tower_page()

        logger.info("4 大企业塔遍历检查与挑战完成")
        return TowerState.SWEEP_AND_EXIT

    def _wait_combat_and_settle(self) -> bool:
        """等待战斗完成、处理胜负结算及菲比限时特惠礼包弹窗."""
        logger.info("等待战斗加载与自动结算...")
        start_time = time.time()

        # Mock 环境支持快速短路返回
        if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
            time.sleep(0.2)
            self.recovery.sweep_modals(max_passes=2)
            return True

        while time.time() - start_time < self.max_combat_wait_seconds:
            self.ping_watchdog(detected_text="tower_combat_waiting")
            time.sleep(2.0)

            # 1. 检查战斗胜利结算 ("点击任意处" / "获得奖励" / 奖励弹窗)
            if self.ocr_text_exists(TEXT_TOWER_FIGHT_END, ROI_TOWER_FIGHT_END_TAP) or self.scene.has_reward_claim_modal():
                logger.info("检测到战斗胜利结算，点击任意区域继续...")
                self.interact.click_rect(ROI_TOWER_FIGHT_END_TAP)
                time.sleep(1.0)
                self.recovery.sweep_modals(max_passes=3)
                self._handle_flash_sale()
                return True

            # 2. 检查战斗失败 / 逾时结算 ("战败" / "逾时" / "FAILED")
            if self.ocr_text_exists(TEXT_TOWER_FAILED, ROI_TOWER_FIGHT_RESULT):
                logger.info("检测到爬塔战败或超时结算，点击返回退出战斗...")
                self.interact.click_rect(ROI_TOWER_FAILED_BACK_BTN)
                time.sleep(1.5)
                self.recovery.sweep_modals(max_passes=2)
                return False

            # 3. 检查限时礼包弹窗 (菲比特惠等)
            if self.ocr_text_exists(TEXT_TOWER_FLASH_SALE, ROI_TOWER_FLASH_SALE_AREA):
                self._handle_flash_sale()
                return True

        logger.warning(f"战斗等待超时 ({self.max_combat_wait_seconds}s)，执行防御性弹窗清扫")
        self.recovery.sweep_modals(max_passes=3)
        return False

    def _handle_flash_sale(self) -> None:
        """检查并关闭菲比限时特惠礼包弹窗."""
        if self.ocr_text_exists(TEXT_TOWER_FLASH_SALE, ROI_TOWER_FLASH_SALE_AREA):
            logger.info("检测到限时礼包弹窗，点击关闭...")
            self.interact.click_rect(ROI_TOWER_FLASH_SALE_CLOSE)
            time.sleep(0.5)
            self.interact.click_rect(ROI_GLOBAL_CLOSE)
            time.sleep(0.5)

    def _exit_tower_page(self) -> None:
        """从塔详情页返回无限之塔主列表."""
        logger.debug("从塔详情页返回主列表...")
        self.interact.press_and_confirm(
            label="退出塔详情页",
            press_action=lambda: self.interact.click_rect(ROI_TOWER_EXIT_PAGE_BTN),
            confirmed_check=lambda: self.scene.is_in_tower()
            or self.ocr_text_exists(TEXT_TOWER_TITLE, ROI_TOWER_TITLE)
            or self.ocr_text_exists(TEXT_TOWER_UNLIMITED, ROI_TOWER_UNLIMITED_TAG),
            timeout=3.5,
            retries=2,
        )

    def _step_sweep_and_exit(self) -> TowerState:
        """清扫残余弹窗并确定性返回大厅."""
        logger.info("[State] 清扫结算弹窗，确定性返回游戏大厅...")
        self.recovery.sweep_modals(max_passes=5)

        success = self.recovery.recover_to_home(max_attempts=6)
        if not success and not self.scene.is_in_home():
            raise FrozenScreen("未能从爬塔/方舟界面确定性恢复至游戏大厅")

        logger.info("已安全就绪在大厅")
        return TowerState.COMPLETED
