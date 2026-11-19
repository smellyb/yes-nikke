"""Claim Mail and Friend Points task implementations for NIKKE.

Features:
1. Closed-loop confirmation (press_and_confirm) for all state transitions.
2. Graceful skip if no unread mail or friend points are claimable.
3. Adaptive popup clearance for reward settlements and notifications.
4. Deterministic return to Lobby verified by scene discriminator.
"""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Any, Optional, Tuple

from core.ops.frozen_watch import FrozenScreen
from games.nikke.base_nikke_task import NikkeTask
from games.nikke.constants import (
    ROI_MAIL_ENTRY_BTN,
    ROI_MAIL_TITLE,
    ROI_MAIL_CLAIM_ALL_BTN,
    ROI_MAIL_CLOSE_BTN,
    ROI_MAIL_EMPTY_PROMPT,
    ROI_FRIEND_ENTRY_BTN,
    ROI_FRIEND_TITLE,
    ROI_FRIEND_SEND_RECEIVE_BTN,
    ROI_FRIEND_CONFIRM_BTN,
    ROI_FRIEND_CLOSE_BTN,
    ROI_TOP_LEFT_BACK,
    ROI_SAFE_CLICK_BLANK,
    TEXT_MAIL_TITLE,
    TEXT_MAIL_CLAIM_ALL,
    TEXT_MAIL_EMPTY,
    TEXT_FRIEND_TITLE,
    TEXT_FRIEND_SEND,
    TEXT_FRIEND_FINISHED,
    TEXT_CONFIRM,
)

logger = logging.getLogger("yes_nikke.task.mail_and_friends")


class MailState(Enum):
    ENTER_MAIL = auto()
    CHECK_MAIL = auto()
    CLAIM_ALL = auto()
    EXIT_TO_HOME = auto()
    COMPLETED = auto()


class FriendState(Enum):
    ENTER_FRIENDS = auto()
    CHECK_FRIENDS = auto()
    SEND_RECEIVE_POINTS = auto()
    EXIT_TO_HOME = auto()
    COMPLETED = auto()


class ClaimMailTask(NikkeTask):
    """【邮件领取】命令式状态机任务实现.

    流程：
    大厅右上角邮件入口 -> 检查未读/领奖状态 -> 点击全部领取 -> 闭环确认奖励弹窗并清扫 -> 确定性返回大厅。
    """

    ROI_MAIL_ENTRY_BTN: Tuple[int, int, int, int] = ROI_MAIL_ENTRY_BTN
    ROI_MAIL_TITLE: Tuple[int, int, int, int] = ROI_MAIL_TITLE
    ROI_MAIL_CLAIM_ALL_BTN: Tuple[int, int, int, int] = ROI_MAIL_CLAIM_ALL_BTN
    ROI_MAIL_CLOSE_BTN: Tuple[int, int, int, int] = ROI_MAIL_CLOSE_BTN
    ROI_MAIL_EMPTY_PROMPT: Tuple[int, int, int, int] = ROI_MAIL_EMPTY_PROMPT

    def __init__(self, ctx: Any = None) -> None:
        super().__init__(ctx, name="ClaimMail")
        self.current_state: MailState = MailState.ENTER_MAIL
        self.mail_claimed: bool = False

    def run(self) -> bool:
        """Execute Mail claim task state machine."""
        logger.info(">>> 启动任务：邮件一键领取")
        self.current_state = MailState.ENTER_MAIL
        self.mail_claimed = False

        if self.frozen_watch and hasattr(self.frozen_watch, "reset"):
            self.frozen_watch.reset()

        while self.current_state != MailState.COMPLETED:
            try:
                self.ping_watchdog(detected_text=f"state_{self.current_state.name}")

                if self.current_state == MailState.ENTER_MAIL:
                    self.current_state = self._step_enter_mail()
                elif self.current_state == MailState.CHECK_MAIL:
                    self.current_state = self._step_check_mail()
                elif self.current_state == MailState.CLAIM_ALL:
                    self.current_state = self._step_claim_all()
                elif self.current_state == MailState.EXIT_TO_HOME:
                    self.current_state = self._step_exit_to_home()
                else:
                    raise RuntimeError(f"未处理的异常状态: {self.current_state}")

            except FrozenScreen as exc:
                logger.error(f"邮件领取触发卡死看门狗告警: {exc}，启动确定性恢复大厅")
                self.recovery.recover_to_home()
                return False

        logger.info("<<< 任务完成：邮件一键领取执行完毕")
        return True

    def _step_enter_mail(self) -> MailState:
        """从大厅点击右上角邮件入口，闭环确认进入邮箱."""
        logger.info("[State] 进入邮箱界面...")

        if self.scene.is_in_mail() or self.ocr_text_exists(TEXT_MAIL_TITLE, self.ROI_MAIL_TITLE):
            logger.info("已位于邮件界面，跳过大厅入口点击")
            return MailState.CHECK_MAIL

        confirmed = self.interact.press_and_confirm(
            label="大厅点击邮件入口",
            press_action=lambda: self.interact.click_rect(self.ROI_MAIL_ENTRY_BTN),
            confirmed_check=lambda: self.scene.is_in_mail() or self.ocr_text_exists(TEXT_MAIL_TITLE, self.ROI_MAIL_TITLE),
            still_before_check=lambda: self.scene.is_in_home(),
            timeout=4.0,
            retry_after=1.5,
            retries=2,
        )

        if not confirmed:
            raise FrozenScreen("未能成功进入邮件界面（点击无响应或标题未识别）")

        return MailState.CHECK_MAIL

    def _step_check_mail(self) -> MailState:
        """检查是否有可领取的邮件."""
        time.sleep(0.5)
        logger.info("[State] 检查邮箱邮件状态...")

        # 检查是否已有全部领取按钮
        has_claim_btn = self.ocr_text_exists(TEXT_MAIL_CLAIM_ALL, self.ROI_MAIL_CLAIM_ALL_BTN)
        has_empty_notice = self.ocr_text_exists(TEXT_MAIL_EMPTY, self.ROI_MAIL_EMPTY_PROMPT)

        if has_claim_btn and not has_empty_notice:
            logger.info("检测到可领取邮件，转入一键领取步骤")
            return MailState.CLAIM_ALL
        else:
            logger.info("当前无待领邮件或邮箱为空，准备退出")
            return MailState.EXIT_TO_HOME

    def _step_claim_all(self) -> MailState:
        """点击全部领取，并清扫所有结算与奖励弹窗."""
        logger.info("[State] 点击全部领取邮件...")

        claimed = self.interact.press_and_confirm(
            label="点击全部领取邮件",
            press_action=lambda: self.interact.click_rect(self.ROI_MAIL_CLAIM_ALL_BTN),
            confirmed_check=lambda: self.scene.has_reward_claim_modal()
            or not self.ocr_text_exists(TEXT_MAIL_CLAIM_ALL, self.ROI_MAIL_CLAIM_ALL_BTN),
            still_before_check=lambda: self.ocr_text_exists(TEXT_MAIL_CLAIM_ALL, self.ROI_MAIL_CLAIM_ALL_BTN),
            timeout=3.5,
            retries=1,
        )

        if claimed:
            logger.info("邮件领取成功触发，清扫奖励弹窗...")
            self.mail_claimed = True
            self.recovery.sweep_modals(max_passes=5)
        else:
            logger.warning("未能确认邮件领取反馈，可能无邮件或网络微卡")

        return MailState.EXIT_TO_HOME

    def _step_exit_to_home(self) -> MailState:
        """退出邮箱，确定性返回游戏大厅."""
        logger.info("[State] 退出邮箱，返回大厅...")

        # 优先点击关闭叉号或返回键
        self.interact.press_and_confirm(
            label="关闭邮箱返回大厅",
            press_action=lambda: self.interact.click_rect(self.ROI_MAIL_CLOSE_BTN),
            confirmed_check=lambda: self.scene.is_in_home(),
            still_before_check=lambda: self.scene.is_in_mail(),
            timeout=3.0,
            retries=2,
        )

        if not self.scene.is_in_home():
            logger.warning("点击关闭未直接返回大厅，启动 recover_to_home 兜底")
            self.recovery.recover_to_home(max_attempts=3)

        if self.scene.is_in_home():
            logger.info("已成功返回游戏大厅")
            return MailState.COMPLETED
        else:
            raise FrozenScreen("未能确定性返回游戏大厅")


class FriendPointsTask(NikkeTask):
    """【好友点数收发】命令式状态机任务实现.

    流程：
    大厅右上角好友入口 -> 检查好友列表状态 -> 点击赠送/收取全部 -> 闭环确认 -> 确定性返回大厅。
    """

    ROI_FRIEND_ENTRY_BTN: Tuple[int, int, int, int] = ROI_FRIEND_ENTRY_BTN
    ROI_FRIEND_TITLE: Tuple[int, int, int, int] = ROI_FRIEND_TITLE
    ROI_FRIEND_SEND_RECEIVE_BTN: Tuple[int, int, int, int] = ROI_FRIEND_SEND_RECEIVE_BTN
    ROI_FRIEND_CONFIRM_BTN: Tuple[int, int, int, int] = ROI_FRIEND_CONFIRM_BTN
    ROI_FRIEND_CLOSE_BTN: Tuple[int, int, int, int] = ROI_FRIEND_CLOSE_BTN

    def __init__(self, ctx: Any = None) -> None:
        super().__init__(ctx, name="FriendPoints")
        self.current_state: FriendState = FriendState.ENTER_FRIENDS
        self.points_sent: bool = False

    def run(self) -> bool:
        """Execute Friend Points task state machine."""
        logger.info(">>> 启动任务：好友点数收发")
        self.current_state = FriendState.ENTER_FRIENDS
        self.points_sent = False

        if self.frozen_watch and hasattr(self.frozen_watch, "reset"):
            self.frozen_watch.reset()

        while self.current_state != FriendState.COMPLETED:
            try:
                self.ping_watchdog(detected_text=f"state_{self.current_state.name}")

                if self.current_state == FriendState.ENTER_FRIENDS:
                    self.current_state = self._step_enter_friends()
                elif self.current_state == FriendState.CHECK_FRIENDS:
                    self.current_state = self._step_check_friends()
                elif self.current_state == FriendState.SEND_RECEIVE_POINTS:
                    self.current_state = self._step_send_receive_points()
                elif self.current_state == FriendState.EXIT_TO_HOME:
                    self.current_state = self._step_exit_to_home()
                else:
                    raise RuntimeError(f"未处理的异常状态: {self.current_state}")

            except FrozenScreen as exc:
                logger.error(f"好友点数收发触发卡死看门狗告警: {exc}，启动确定性恢复大厅")
                self.recovery.recover_to_home()
                return False

        logger.info("<<< 任务完成：好友点数收发执行完毕")
        return True

    def _step_enter_friends(self) -> FriendState:
        """从大厅点击右侧好友按钮，闭环确认进入好友界面."""
        logger.info("[State] 进入好友界面...")

        if self.scene.is_in_friends() or self.ocr_text_exists(TEXT_FRIEND_TITLE, self.ROI_FRIEND_TITLE):
            logger.info("已位于好友界面，跳过入口点击")
            return FriendState.CHECK_FRIENDS

        confirmed = self.interact.press_and_confirm(
            label="大厅点击好友入口",
            press_action=lambda: self.interact.click_rect(self.ROI_FRIEND_ENTRY_BTN),
            confirmed_check=lambda: self.scene.is_in_friends() or self.ocr_text_exists(TEXT_FRIEND_TITLE, self.ROI_FRIEND_TITLE),
            still_before_check=lambda: self.scene.is_in_home(),
            timeout=4.0,
            retry_after=1.5,
            retries=2,
        )

        if not confirmed:
            raise FrozenScreen("未能成功进入好友界面（点击无响应或标题未识别）")

        return FriendState.CHECK_FRIENDS

    def _step_check_friends(self) -> FriendState:
        """检查好友列表点数收发状态."""
        time.sleep(0.5)
        logger.info("[State] 检查好友点数收发状态...")

        # 检查是否已完成（“无法获得”、“已完成”、“今日上限”）
        is_finished = self.ocr_text_exists(TEXT_FRIEND_FINISHED, (400, 200, 480, 400))
        if is_finished:
            logger.info("好友点数今日已达到收发上限或已完成，准备退出")
            return FriendState.EXIT_TO_HOME

        # 检查赠送按钮
        has_send_btn = (
            self.ocr_text_exists(TEXT_FRIEND_SEND, self.ROI_FRIEND_SEND_RECEIVE_BTN)
            or bool(self.find_template_multidim("friendpoints/sendpoints.png", self.ROI_FRIEND_SEND_RECEIVE_BTN))
        )

        if has_send_btn:
            logger.info("检测到可收发好友点数，转入操作步骤")
            return FriendState.SEND_RECEIVE_POINTS
        else:
            logger.info("未检测到有效赠送按钮，准备退出")
            return FriendState.EXIT_TO_HOME

    def _step_send_receive_points(self) -> FriendState:
        """点击赠送/收取全部点数，并闭环确认弹窗."""
        logger.info("[State] 点击赠送/收取全部好友点数...")

        confirmed = self.interact.press_and_confirm(
            label="点击赠送好友点数",
            press_action=lambda: self.interact.click_rect(self.ROI_FRIEND_SEND_RECEIVE_BTN),
            confirmed_check=lambda: self.scene.has_modal_active()
            or self.scene.has_reward_claim_modal()
            or self.ocr_text_exists(TEXT_CONFIRM, self.ROI_FRIEND_CONFIRM_BTN)
            or self.ocr_text_exists(TEXT_FRIEND_FINISHED, (400, 200, 480, 400)),
            still_before_check=lambda: self.ocr_text_exists(TEXT_FRIEND_SEND, self.ROI_FRIEND_SEND_RECEIVE_BTN),
            timeout=3.5,
            retries=1,
        )

        # 处理弹出的二次确认对话框（如“获得友情点数”确认）
        if self.ocr_text_exists(TEXT_CONFIRM, self.ROI_FRIEND_CONFIRM_BTN):
            logger.info("检测到好友点数确认框，点击确认...")
            self.interact.click_rect(self.ROI_FRIEND_CONFIRM_BTN)
            time.sleep(0.5)

        if confirmed:
            logger.info("好友点数赠送成功，清扫弹窗...")
            self.points_sent = True
            self.recovery.sweep_modals(max_passes=5)
        else:
            logger.warning("未能确认好友点数赠送反馈，可能网络同步延迟")

        return FriendState.EXIT_TO_HOME

    def _step_exit_to_home(self) -> FriendState:
        """退出好友界面，确定性返回游戏大厅."""
        logger.info("[State] 退出好友界面，返回大厅...")

        self.interact.press_and_confirm(
            label="关闭好友界面返回大厅",
            press_action=lambda: self.interact.click_rect(self.ROI_FRIEND_CLOSE_BTN),
            confirmed_check=lambda: self.scene.is_in_home(),
            still_before_check=lambda: self.scene.is_in_friends(),
            timeout=3.0,
            retries=2,
        )

        if not self.scene.is_in_home():
            logger.warning("点击关闭未直接返回大厅，启动 recover_to_home 兜底")
            self.recovery.recover_to_home(max_attempts=3)

        if self.scene.is_in_home():
            logger.info("已成功返回游戏大厅")
            return FriendState.COMPLETED
        else:
            raise FrozenScreen("未能确定性返回游戏大厅")
