"""Inquiry and Gift task implementation for NIKKE.

Features:
1. Closed-loop navigation into the Inquiry (咨询) system from Lobby or Nikke screen.
2. Configurable manual interaction for the top N (default 3) favorite Nikkes:
   - Dialogue inquiry (supporting Quick Inquiry / Fast Chat if available).
   - Gift sending with max-level safety check to avoid wasting gift items.
3. Automatic batch inquiry (一键批量咨询) for remaining daily chances.
4. Comprehensive settlement clearance (Affinity rank-up, rewards, item popups).
5. Deterministic return to Lobby verified by scene discriminator.
"""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Any, List, Optional, Tuple

from core.ops.frozen_watch import FrozenScreen
from games.nikke.base_nikke_task import NikkeTask
import games.nikke.scene_growth  # Ensure scene discriminators are registered
from games.nikke.constants_growth import (
    ROI_HOME_BOTTOM_NIKKE,
    ROI_NIKKE_LIST_INQUIRY_BTN,
    ROI_INQUIRY_TITLE,
    ROI_INQUIRY_NIKKE_1,
    ROI_INQUIRY_NIKKE_2,
    ROI_INQUIRY_NIKKE_3,
    ROI_INQUIRY_BASE_BTN,
    ROI_INQUIRY_QUICK_BTN,
    ROI_INQUIRY_START_PROMPT,
    ROI_INQUIRY_CONFIRM_BTN,
    ROI_INQUIRY_CHAT_SKIP,
    ROI_INQUIRY_GIFT_BTN,
    ROI_INQUIRY_MAX_AFFINITY,
    ROI_INQUIRY_BASIC_GIFT_SLOT,
    ROI_INQUIRY_SEND_GIFT_BTN,
    ROI_INQUIRY_CLAIM_SEND_GIFT,
    ROI_INQUIRY_BATCH_BTN,
    ROI_INQUIRY_BATCH_CONFIRM_BTN,
    ROI_INQUIRY_NO_TIMES_MODAL,
    ROI_INQUIRY_NO_TIMES_CLOSE,
    ROI_INQUIRY_STEP_NEXT,
    ROI_TOP_LEFT_BACK,
    ROI_SAFE_CLICK_BLANK,
    TEXT_INQUIRY_TITLE,
    TEXT_INQUIRY_BATCH,
    TEXT_INQUIRY_BASE,
    TEXT_INQUIRY_QUICK,
    TEXT_INQUIRY_FINISHED,
    TEXT_INQUIRY_NO_TIMES,
    TEXT_INQUIRY_MAX_LEVEL,
    TEXT_INQUIRY_NEXT_STEP,
    TEXT_CONFIRM,
)

logger = logging.getLogger("yes_nikke.task.inquiry_and_gift")


class InquiryState(Enum):
    ENTER_INQUIRY = auto()
    MANUAL_INQUIRY = auto()
    BATCH_INQUIRY = auto()
    SWEEP_MODALS = auto()
    EXIT_TO_HOME = auto()
    COMPLETED = auto()


class InquiryAndGiftTask(NikkeTask):
    """【妮姬咨询与送礼】命令式状态机任务实现."""

    def __init__(
        self,
        ctx: Any = None,
        manual_top_nikkes: bool = True,
        enable_gift: bool = True,
        max_manual_count: int = 3,
        enable_batch_inquiry: bool = True,
    ) -> None:
        super().__init__(ctx, name="InquiryAndGift")
        self.manual_top_nikkes: bool = manual_top_nikkes
        self.enable_gift: bool = enable_gift
        self.max_manual_count: int = max(0, min(max_manual_count, 3))
        self.enable_batch_inquiry: bool = enable_batch_inquiry

        self.current_state: InquiryState = InquiryState.ENTER_INQUIRY
        self.manual_inquiries_done: int = 0
        self.gifts_sent: int = 0
        self.batch_inquiry_done: bool = False

    def run(self) -> bool:
        """Execute Inquiry and Gift state machine."""
        logger.info(">>> 启动任务：妮姬咨询与送礼")
        self.current_state = InquiryState.ENTER_INQUIRY
        self.manual_inquiries_done = 0
        self.gifts_sent = 0
        self.batch_inquiry_done = False

        if self.frozen_watch and hasattr(self.frozen_watch, "reset"):
            self.frozen_watch.reset()

        while self.current_state != InquiryState.COMPLETED:
            try:
                self.ping_watchdog(detected_text=f"state_{self.current_state.name}")

                if self.current_state == InquiryState.ENTER_INQUIRY:
                    self.current_state = self._step_enter_inquiry()
                elif self.current_state == InquiryState.MANUAL_INQUIRY:
                    self.current_state = self._step_manual_inquiry()
                elif self.current_state == InquiryState.BATCH_INQUIRY:
                    self.current_state = self._step_batch_inquiry()
                elif self.current_state == InquiryState.SWEEP_MODALS:
                    self.current_state = self._step_sweep_modals()
                elif self.current_state == InquiryState.EXIT_TO_HOME:
                    self.current_state = self._step_exit_to_home()
                else:
                    raise RuntimeError(f"未处理的异常状态: {self.current_state}")

            except FrozenScreen as exc:
                logger.error(f"咨询与送礼触发卡死看门狗告警: {exc}，启动确定性恢复大厅")
                self.recovery.recover_to_home()
                return False

        logger.info(
            f"<<< 任务完成：咨询与送礼执行完毕 (手动咨询: {self.manual_inquiries_done}, "
            f"送礼: {self.gifts_sent}, 批量咨询: {self.batch_inquiry_done})"
        )
        return True

    def _step_enter_inquiry(self) -> InquiryState:
        """进入咨询界面."""
        logger.info("[State] 进入咨询主界面...")

        # 检查是否已在咨询界面
        if self.scene.is_in_inquiry() or self.ocr_text_exists(TEXT_INQUIRY_TITLE, ROI_INQUIRY_TITLE):
            logger.info("已处于咨询界面，跳过导航")
            return InquiryState.MANUAL_INQUIRY if self.manual_top_nikkes else InquiryState.BATCH_INQUIRY

        # 步骤 1：从大厅点击底部 "妮姬"
        logger.info("从大厅点击底部'妮姬'栏位...")
        into_nikke = self.interact.press_and_confirm(
            label="点击底部妮姬入口",
            press_action=lambda: self.interact.click_rect(ROI_HOME_BOTTOM_NIKKE),
            confirmed_check=lambda: self.scene.is_in_inquiry()
            or self.ocr_text_exists("咨询", ROI_NIKKE_LIST_INQUIRY_BTN)
            or self.ocr_text_exists(TEXT_INQUIRY_TITLE, ROI_INQUIRY_TITLE),
            still_before_check=lambda: self.scene.is_in_home(),
            timeout=5.0,
            retries=2,
        )

        if not into_nikke and not self.scene.is_in_inquiry():
            raise FrozenScreen("未能成功进入妮姬列表界面")

        # 步骤 2：若在妮姬列表界面，点击上方/子菜单的 "咨询" 按钮
        if not self.scene.is_in_inquiry() and not self.ocr_text_exists(TEXT_INQUIRY_TITLE, ROI_INQUIRY_TITLE):
            logger.info("点击妮姬界面内的'咨询'入口...")
            into_inquiry = self.interact.press_and_confirm(
                label="点击咨询子入口",
                press_action=lambda: self.interact.click_rect(ROI_NIKKE_LIST_INQUIRY_BTN),
                confirmed_check=lambda: self.scene.is_in_inquiry()
                or self.ocr_text_exists(TEXT_INQUIRY_TITLE, ROI_INQUIRY_TITLE)
                or self.ocr_text_exists(TEXT_INQUIRY_BATCH, ROI_INQUIRY_BATCH_BTN),
                timeout=5.0,
                retries=2,
            )
            if not into_inquiry and not self.scene.is_in_inquiry():
                raise FrozenScreen("未能成功进入咨询主界面")

        logger.info("已成功就绪在咨询主界面")
        return InquiryState.MANUAL_INQUIRY if self.manual_top_nikkes else InquiryState.BATCH_INQUIRY

    def _step_manual_inquiry(self) -> InquiryState:
        """处理前 N 个收藏妮姬的手动单体咨询与送礼."""
        logger.info(f"[State] 准备处理前 {self.max_manual_count} 个收藏妮姬手动单体互动...")
        nikke_slots: List[Tuple[int, int, int, int]] = [
            ROI_INQUIRY_NIKKE_1,
            ROI_INQUIRY_NIKKE_2,
            ROI_INQUIRY_NIKKE_3,
        ]

        for idx in range(self.max_manual_count):
            slot_roi = nikke_slots[idx]
            logger.info(f"--- 处理第 {idx + 1}/{self.max_manual_count} 位妮姬 (ROI={slot_roi}) ---")

            # 1. 点击进入该妮姬详情
            entered_detail = self.interact.press_and_confirm(
                label=f"进入第 {idx + 1} 位妮姬详情",
                press_action=lambda roi=slot_roi: self.interact.click_rect(roi),
                confirmed_check=lambda: self.ocr_text_exists(TEXT_INQUIRY_QUICK, ROI_INQUIRY_QUICK_BTN)
                or self.ocr_text_exists(TEXT_INQUIRY_BASE, ROI_INQUIRY_BASE_BTN)
                or self.ocr_text_exists(TEXT_INQUIRY_FINISHED, (400, 400, 480, 200)),
                still_before_check=lambda: self.scene.is_in_inquiry(),
                timeout=4.0,
                retries=2,
            )

            if not entered_detail:
                logger.warning(f"无法进入第 {idx + 1} 位妮姬详情，可能已达到列表末尾或无收藏妮姬")
                continue

            time.sleep(0.5)

            # 2. 检查是否可咨询（快速咨询或普通咨询）
            can_quick = self.ocr_text_exists(TEXT_INQUIRY_QUICK, ROI_INQUIRY_QUICK_BTN)
            can_base = self.ocr_text_exists(TEXT_INQUIRY_BASE, ROI_INQUIRY_BASE_BTN)
            is_finished = self.ocr_text_exists(TEXT_INQUIRY_FINISHED, (400, 400, 480, 200))

            if (can_quick or can_base) and not is_finished:
                logger.info(f"第 {idx + 1} 位妮姬可咨询 (快速={can_quick}, 普通={can_base})")
                btn_to_click = ROI_INQUIRY_QUICK_BTN if can_quick else ROI_INQUIRY_BASE_BTN
                self.interact.click_rect(btn_to_click)
                time.sleep(0.8)

                # 检查确认弹窗 ("是否对...进行咨询" 或 "确认")
                if self.ocr_text_exists(TEXT_CONFIRM, ROI_INQUIRY_CONFIRM_BTN) or self.ocr_text_exists(
                    ("是否对", "进行咨询"), ROI_INQUIRY_START_PROMPT
                ):
                    logger.info("点击咨询二次确认...")
                    self.interact.click_rect(ROI_INQUIRY_CONFIRM_BTN)
                    time.sleep(1.0)

                # 对话跳过与好感度弹窗消除
                for _ in range(3):
                    if self.ocr_text_exists(("自动", "记录", "点击"), (0, 400, 1280, 320)):
                        self.interact.click_rect(ROI_INQUIRY_CHAT_SKIP)
                        time.sleep(0.5)
                    self.recovery.sweep_modals(max_passes=2)

                self.manual_inquiries_done += 1
            else:
                logger.info(f"第 {idx + 1} 位妮姬今日咨询次数已耗尽或已完成")

            # 3. 送礼处理（如果开启了送礼功能）
            if self.enable_gift:
                self._handle_gift_sending(idx + 1)

            # 4. 返回咨询主列表
            self._exit_nikke_detail()

        logger.info(f"前 {self.max_manual_count} 位妮姬手动处理完毕，转入批量咨询步骤")
        return InquiryState.BATCH_INQUIRY

    def _handle_gift_sending(self, nikke_num: int) -> None:
        """处理单体妮姬的送礼逻辑."""
        logger.info(f"检查第 {nikke_num} 位妮姬送礼...")
        # 点击送礼入口
        self.interact.click_rect(ROI_INQUIRY_GIFT_BTN)
        time.sleep(0.8)

        # 检查是否已达最高好感度
        if self.ocr_text_exists(TEXT_INQUIRY_MAX_LEVEL, ROI_INQUIRY_MAX_AFFINITY):
            logger.info(f"第 {nikke_num} 位妮姬好感度已达最高等级，跳过送礼以节约道具")
            self.interact.click_rect(ROI_TOP_LEFT_BACK)
            time.sleep(0.5)
            return

        # 选择基础礼物道具槽位并赠送
        logger.info(f"第 {nikke_num} 位妮姬选择基础礼物赠送...")
        self.interact.click_rect(ROI_INQUIRY_BASIC_GIFT_SLOT)
        time.sleep(0.4)
        self.interact.click_rect(ROI_INQUIRY_SEND_GIFT_BTN)
        time.sleep(0.6)

        # 确认送礼
        if self.ocr_text_exists(TEXT_CONFIRM, ROI_INQUIRY_CLAIM_SEND_GIFT):
            self.interact.click_rect(ROI_INQUIRY_CLAIM_SEND_GIFT)
            time.sleep(0.8)
            self.gifts_sent += 1
            logger.info(f"第 {nikke_num} 位妮姬送礼成功")

        # 消除好感度与属性提升弹窗
        self.recovery.sweep_modals(max_passes=3)

        # 退出送礼界面
        self.interact.click_rect(ROI_TOP_LEFT_BACK)
        time.sleep(0.5)

    def _exit_nikke_detail(self) -> None:
        """从妮姬详情返回咨询列表主界面."""
        logger.debug("从妮姬详情返回咨询列表...")
        self.interact.press_and_confirm(
            label="返回咨询列表",
            press_action=lambda: self.interact.click_rect(ROI_TOP_LEFT_BACK),
            confirmed_check=lambda: self.scene.is_in_inquiry()
            or self.ocr_text_exists(TEXT_INQUIRY_TITLE, ROI_INQUIRY_TITLE)
            or self.ocr_text_exists(TEXT_INQUIRY_BATCH, ROI_INQUIRY_BATCH_BTN),
            timeout=3.5,
            retries=2,
        )

    def _step_batch_inquiry(self) -> InquiryState:
        """执行批量咨询剩余妮姬."""
        if not self.enable_batch_inquiry:
            logger.info("配置未启用批量咨询，直接转入清扫状态")
            return InquiryState.SWEEP_MODALS

        logger.info("[State] 执行一键批量咨询...")

        # 检查批量咨询按钮
        has_batch_btn = self.ocr_text_exists(TEXT_INQUIRY_BATCH, ROI_INQUIRY_BATCH_BTN)
        if not has_batch_btn and not self.scene.is_in_inquiry():
            logger.info("未检测到批量咨询按钮，可能位于非主界面或已处理")
            return InquiryState.SWEEP_MODALS

        # 点击批量咨询按钮
        logger.info("点击'批量咨询'按钮...")
        self.interact.click_rect(ROI_INQUIRY_BATCH_BTN)
        time.sleep(1.0)

        # 检查是否弹出"剩余咨询次数不足"
        if self.ocr_text_exists(TEXT_INQUIRY_NO_TIMES, ROI_INQUIRY_NO_TIMES_MODAL):
            logger.info("检测到今日剩余咨询次数不足，关闭弹窗并结束批量咨询")
            self.interact.click_rect(ROI_INQUIRY_NO_TIMES_CLOSE)
            time.sleep(0.5)
            return InquiryState.SWEEP_MODALS

        # 检查批量确认按钮并点击
        if self.ocr_text_exists(TEXT_INQUIRY_BATCH, ROI_INQUIRY_BATCH_CONFIRM_BTN) or self.ocr_text_exists(
            TEXT_CONFIRM, ROI_INQUIRY_CONFIRM_BTN
        ):
            logger.info("确认执行批量咨询...")
            self.interact.click_rect(ROI_INQUIRY_BATCH_CONFIRM_BTN)
            time.sleep(1.5)
            self.batch_inquiry_done = True

            # 点击下一步/消除结算动画
            if self.ocr_text_exists(TEXT_INQUIRY_NEXT_STEP, ROI_INQUIRY_STEP_NEXT):
                self.interact.click_rect(ROI_INQUIRY_STEP_NEXT)
                time.sleep(0.8)

        return InquiryState.SWEEP_MODALS

    def _step_sweep_modals(self) -> InquiryState:
        """清扫好感度、奖励与任何未关闭的弹窗."""
        logger.info("[State] 清扫弹窗与好感度奖励...")
        self.recovery.sweep_modals(max_passes=5)
        return InquiryState.EXIT_TO_HOME

    def _step_exit_to_home(self) -> InquiryState:
        """确定性退出咨询与妮姬界面，返回游戏大厅."""
        logger.info("[State] 退出咨询系统，确定性返回游戏大厅...")
        # 优先使用 recovery.recover_to_home 确保彻底脱离深层菜单
        success = self.recovery.recover_to_home(max_attempts=6)
        if not success and not self.scene.is_in_home():
            raise FrozenScreen("未能从咨询界面确定性恢复至大厅")

        logger.info("已安全返回大厅")
        return InquiryState.COMPLETED
