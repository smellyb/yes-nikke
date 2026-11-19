"""Production Daily Batch Runner and Context Orchestrator for NIKKE.

Features:
1. Priority Serial Scheduling:
   OutpostDefenseTask -> ClaimMailTask -> FriendPointsTask -> DispatchBoardTask -> DailyShopTask.
2. Unified Context Management:
   Centrally holds and injects FrozenWatch, ProblemReport, NikkeRecovery, NikkeScene,
   and NikkeInteraction across all daily tasks.
3. Fault Tolerance & Recovery Isolation:
   Isolates subtask exceptions, automatically captures diagnostic state into ProblemReport,
   triggers deterministic recovery back to Home Lobby (recover_to_home), marks the task FAILED,
   and safely proceeds with subsequent tasks without interrupting the batch workflow.
4. Structured Diagnostic Reporting:
   Produces comprehensive machine-readable and ASCII tabular reports summarizing task status,
   execution latency, and failure diagnostics.
5. Offline Mock Compatibility:
   Provides built-in simulated mock execution for headless CI and dry-run verification.
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

import numpy as np

from core.base_task import BaseGameTask
from core.capture import WindowCapture, find_nikke_window
from core.ops.frozen_watch import FrozenWatch
from core.ops.problem_report import ProblemReport
from games.nikke.interaction import NikkeInteraction
from games.nikke.recovery import NikkeRecovery
from games.nikke.scene import NikkeScene

logger = logging.getLogger("yes_nikke.batch_runner")

__all__ = [
    "DEFAULT_TASK_SEQUENCE",
    "DEFAULT_DAILY_PIPELINE",
    "NikkeDailyBatchRunner",
    "MockNikkeGameContext",
    "NikkeContext",
    "BatchReport",
    "TaskResult",
    "TaskStatus",
    "TASK_DESCRIPTIONS",
    "TASK_MODULE_REGISTRY",
]



class TaskStatus(str, Enum):
    """Execution status of an individual game task."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class TaskResult:
    """Detailed outcome of a single task execution."""
    task_name: str
    status: TaskStatus
    duration: float
    error_msg: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_name": self.task_name,
            "status": self.status.value if isinstance(self.status, TaskStatus) else str(self.status),
            "duration": round(self.duration, 3),
            "error_msg": self.error_msg,
            "details": self.details,
        }


@dataclass
class BatchReport:
    """Aggregated execution report for a daily batch run."""
    total_tasks: int
    success_count: int
    failed_count: int
    skipped_count: int
    total_duration: float
    results: List[TaskResult] = field(default_factory=list)

    @property
    def is_all_successful(self) -> bool:
        """True if at least one task ran and zero tasks failed."""
        return self.failed_count == 0 and self.success_count > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tasks": self.total_tasks,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "total_duration": round(self.total_duration, 3),
            "is_all_successful": self.is_all_successful,
            "results": [r.to_dict() for r in self.results],
        }

    def format_table(self) -> str:
        """Generate a clean ASCII tabular summary of the batch execution."""
        lines = [
            "=" * 78,
            "                NIKKE DAILY BATCH RUNNER EXECUTION REPORT",
            "=" * 78,
            f"Total: {self.total_tasks} | Success: {self.success_count} | Failed: {self.failed_count} | Skipped: {self.skipped_count} | Duration: {self.total_duration:.2f}s",
            "-" * 78,
            f"{'No.':<4} | {'Task Name':<22} | {'Status':<9} | {'Duration':<8} | {'Error / Reason':<25}",
            "-" * 78,
        ]

        for idx, res in enumerate(self.results, 1):
            status_str = res.status.value if isinstance(res.status, TaskStatus) else str(res.status)
            dur_str = f"{res.duration:.2f}s"
            err_str = res.error_msg if res.error_msg else "-"
            if len(err_str) > 25:
                err_str = err_str[:22] + "..."
            lines.append(
                f"{idx:<4} | {res.task_name:<22} | {status_str:<9} | {dur_str:<8} | {err_str:<25}"
            )

        lines.append("=" * 78)
        return "\n".join(lines)

    def print_summary(self) -> None:
        """Print the tabular report to standard output."""
        print(self.format_table())


# Preset Priority Task Pipeline for Daily Automation (11 Core Tasks)
DEFAULT_TASK_SEQUENCE: List[str] = [
    "OutpostDefenseTask",
    "ClaimMailTask",
    "FriendPointsTask",
    "DispatchBoardTask",
    "DailyShopTask",
    "SimRoomTask",
    "InterceptionTask",
    "ArenaTask",
    "InquiryAndGiftTask",
    "DailyRewardsTask",
    "ClimbTowerTask",
]
DEFAULT_DAILY_PIPELINE: List[str] = DEFAULT_TASK_SEQUENCE

TASK_DESCRIPTIONS: Dict[str, str] = {
    "OutpostDefenseTask": "前哨基地防御奖励领取与一举歼灭",
    "ClaimMailTask": "信箱邮件一键领取与奖励弹窗清扫",
    "FriendPointsTask": "好友友情点数一键赠送与收取",
    "DispatchBoardTask": "悬赏派遣看板一键领取与重新派遣",
    "DailyShopTask": "普通与付费商店每日免费商品全量遍历与领取",
    "SimRoomTask": "模拟室 5-C 扇区快速模拟与技能手册产出结算",
    "InterceptionTask": "拦截战与异常拦截首战自动战斗与快速战斗扫荡",
    "ArenaTask": "竞技场新人竞技场免费挑战与特殊竞技场点数收获",
    "InquiryAndGiftTask": "妮姬前排收藏单体咨询送礼与剩余全量一键批量咨询",
    "DailyRewardsTask": "每日任务与每周任务一键全部领取及战令PASS奖励清扫",
    "ClimbTowerTask": "方舟无限之塔日常挑战与今日开放企业塔自动遍历",
}

# Task mapping for canonical names and aliases
TASK_MODULE_REGISTRY: Dict[str, Tuple[str, str]] = {
    "outpost": ("games.nikke.tasks.outpost_defense", "OutpostDefenseTask"),
    "outpost_defense": ("games.nikke.tasks.outpost_defense", "OutpostDefenseTask"),
    "outpostdefensetask": ("games.nikke.tasks.outpost_defense", "OutpostDefenseTask"),
    "mail": ("games.nikke.tasks.mail_and_friends", "ClaimMailTask"),
    "claim_mail": ("games.nikke.tasks.mail_and_friends", "ClaimMailTask"),
    "claimmailtask": ("games.nikke.tasks.mail_and_friends", "ClaimMailTask"),
    "friends": ("games.nikke.tasks.mail_and_friends", "FriendPointsTask"),
    "friend": ("games.nikke.tasks.mail_and_friends", "FriendPointsTask"),
    "friend_points": ("games.nikke.tasks.mail_and_friends", "FriendPointsTask"),
    "friendpointstask": ("games.nikke.tasks.mail_and_friends", "FriendPointsTask"),
    "dispatch": ("games.nikke.tasks.dispatch_board", "DispatchBoardTask"),
    "dispatch_board": ("games.nikke.tasks.dispatch_board", "DispatchBoardTask"),
    "dispatchboardtask": ("games.nikke.tasks.dispatch_board", "DispatchBoardTask"),
    "shop": ("games.nikke.tasks.daily_shop", "DailyShopTask"),
    "daily_shop": ("games.nikke.tasks.daily_shop", "DailyShopTask"),
    "dailyshoptask": ("games.nikke.tasks.daily_shop", "DailyShopTask"),
    "sim_room": ("games.nikke.tasks.sim_room", "SimRoomTask"),
    "simroom": ("games.nikke.tasks.sim_room", "SimRoomTask"),
    "simroomtask": ("games.nikke.tasks.sim_room", "SimRoomTask"),
    "sim": ("games.nikke.tasks.sim_room", "SimRoomTask"),
    "interception": ("games.nikke.tasks.interception", "InterceptionTask"),
    "interceptiontask": ("games.nikke.tasks.interception", "InterceptionTask"),
    "arena": ("games.nikke.tasks.arena", "ArenaTask"),
    "arenatask": ("games.nikke.tasks.arena", "ArenaTask"),
    "inquiry": ("games.nikke.tasks.inquiry_and_gift", "InquiryAndGiftTask"),
    "inquiry_and_gift": ("games.nikke.tasks.inquiry_and_gift", "InquiryAndGiftTask"),
    "inquiryandgift": ("games.nikke.tasks.inquiry_and_gift", "InquiryAndGiftTask"),
    "inquiryandgifttask": ("games.nikke.tasks.inquiry_and_gift", "InquiryAndGiftTask"),
    "gift": ("games.nikke.tasks.inquiry_and_gift", "InquiryAndGiftTask"),
    "daily_rewards": ("games.nikke.tasks.daily_rewards", "DailyRewardsTask"),
    "dailyrewards": ("games.nikke.tasks.daily_rewards", "DailyRewardsTask"),
    "dailyrewardstask": ("games.nikke.tasks.daily_rewards", "DailyRewardsTask"),
    "rewards": ("games.nikke.tasks.daily_rewards", "DailyRewardsTask"),
    "reward": ("games.nikke.tasks.daily_rewards", "DailyRewardsTask"),
    "pass": ("games.nikke.tasks.daily_rewards", "DailyRewardsTask"),
    "task": ("games.nikke.tasks.daily_rewards", "DailyRewardsTask"),
    "climb_tower": ("games.nikke.tasks.climb_tower", "ClimbTowerTask"),
    "climbtower": ("games.nikke.tasks.climb_tower", "ClimbTowerTask"),
    "climbtowertask": ("games.nikke.tasks.climb_tower", "ClimbTowerTask"),
    "tower": ("games.nikke.tasks.climb_tower", "ClimbTowerTask"),
}


class NikkeContext:
    """Unified operational context shared across all NIKKE tasks and recovery routines."""

    def __init__(
        self,
        hwnd: int = 0,
        capture: Optional[Any] = None,
        interaction: Optional[NikkeInteraction] = None,
        scene: Optional[NikkeScene] = None,
        recovery: Optional[NikkeRecovery] = None,
        frozen_watch: Optional[FrozenWatch] = None,
        problem_report: Optional[ProblemReport] = None,
        logger_inst: Optional[logging.Logger] = None,
        report_dir: str = "reports",
        mock: bool = False,
    ) -> None:
        self.mock = mock
        self.report_dir = report_dir
        self.logger = logger_inst or logging.getLogger("yes_nikke.context")

        if not self.mock and hwnd == 0:
            hwnd = find_nikke_window()
            if hwnd:
                self.logger.info(f"自动发现 NIKKE 游戏窗口 HWND: {hwnd} (0x{hwnd:X})")
            else:
                self.logger.warning("未检测到运行中的 NIKKE 客户端或模拟器窗口，请先启动游戏或指定 --hwnd")

        self.hwnd = hwnd
        self.frozen_watch = frozen_watch or FrozenWatch()
        self.problem_report = problem_report or ProblemReport()
        self.capture = capture or (WindowCapture(hwnd=self.hwnd) if (self.hwnd and not self.mock) else None)

        self.interaction = interaction or NikkeInteraction(
            hwnd=self.hwnd, watchdog=self.frozen_watch
        )
        self.scene = scene or NikkeScene(self)
        self.recovery = recovery or NikkeRecovery(self)


class MockNikkeGameContext:
    """Deterministic simulated NIKKE game environment for offline testing and verification."""

    def __init__(
        self,
        initial_screen: str = "home",
        has_accumulated_reward: bool = True,
        free_sweep_available: bool = True,
        hwnd: int = 0,
        report_dir: str = "reports",
    ) -> None:
        self.screen_state: str = initial_screen  # "home" | "outpost" | "mail" | "friends" | "dispatch" | "shop" | "payshop"
        self.reward_modal: bool = False
        self.sweep_modal: bool = False
        self.modal_active: bool = False
        self.has_accumulated_reward: bool = has_accumulated_reward
        self.free_sweep_available: bool = free_sweep_available
        self.mail_has_unread: bool = True
        self.friends_need_action: bool = True
        self.dispatch_has_completed: bool = True
        self.dispatch_has_pending: bool = True
        self.shop_free_claimed: bool = False
        self.clicks: List[Tuple[int, int, str]] = []
        self.report_dir = report_dir
        self.logger = logging.getLogger("yes_nikke.mock")

        self.frozen_watch = FrozenWatch()
        self.problem_report = ProblemReport()

        self.interaction = NikkeInteraction(hwnd=hwnd, watchdog=self.frozen_watch)
        self.interaction.post_click = self._dispatch_click
        self.interaction.tap_escape = self._dispatch_escape

        self.scene = NikkeScene(self)
        self.recovery = NikkeRecovery(self)
        self.mock = True

    @property
    def mock_scene_state(self) -> str:
        return self.screen_state

    @property
    def mock_modal_active(self) -> bool:
        return self.modal_active or self.reward_modal or self.sweep_modal

    @property
    def mock_reward_modal(self) -> bool:
        return self.reward_modal

    @property
    def mock_sweep_modal(self) -> bool:
        return self.sweep_modal

    def _dispatch_escape(self) -> None:
        self.clicks.append((0, 0, "escape"))
        self.reward_modal = False
        self.sweep_modal = False
        self.modal_active = False

    def _dispatch_click(self, x: int, y: int, hold_ms: int = 50) -> None:
        """Route click coordinate to simulate state transitions."""
        # 0. Safe blank dismissal click
        if (self.reward_modal or self.modal_active) and y >= 600:
            self.reward_modal = False
            self.modal_active = False
            self.clicks.append((x, y, "dismiss_modal"))
            return

        # 1. Top-left back button
        if 10 <= x <= 110 and 10 <= y <= 90:
            if self.screen_state in ("outpost", "mail", "friends", "shop", "payshop", "dispatch", "ark", "sim_room", "interception", "arena", "arena_rookie", "arena_special"):
                self.screen_state = "home"
                self.clicks.append((x, y, "back_home"))
                return

        # 2. In Home Lobby
        if self.screen_state == "home":
            # Outpost button: (1120, 600, 120, 90)
            if 1100 <= x <= 1260 and 580 <= y <= 710:
                self.screen_state = "outpost"
                self.clicks.append((x, y, "enter_outpost"))
                return
            # Mail entry: (1206, 4, 45, 44)
            elif 1190 <= x <= 1270 and 0 <= y <= 70:
                self.screen_state = "mail"
                self.clicks.append((x, y, "enter_mail"))
                return
            # Friend entry: ROI_FRIEND_ENTRY_BTN (1175, 144, 105, 310)
            elif 1160 <= x <= 1280 and 130 <= y <= 460:
                self.screen_state = "friends"
                self.clicks.append((x, y, "enter_friends"))
                return
            # Shop entry: ROI_HOME_BOTTOM_SHOP (960, 665, 80, 50)
            elif 940 <= x <= 1060 and 650 <= y <= 720:
                self.screen_state = "shop"
                self.clicks.append((x, y, "enter_shop"))
                return
            # Ark entry: (813, 403, 193, 151) or bottom tab (100, 665, 80, 50)
            elif (780 <= x <= 1020 and 390 <= y <= 560) or (80 <= x <= 200 and 650 <= y <= 720):
                self.screen_state = "ark"
                self.clicks.append((x, y, "enter_ark"))
                return
            # Nikke bottom tab: ROI_HOME_BOTTOM_NIKKE (720, 665, 80, 50)
            elif 700 <= x <= 820 and 640 <= y <= 720:
                self.screen_state = "inquiry"
                self.clicks.append((x, y, "enter_inquiry"))
                return
            # PASS icon: ROI_PASS_ENTRY_BTN (1109, 78, 70, 87)
            elif 1080 <= x <= 1180 and 60 <= y <= 165:
                self.screen_state = "pass_modal"
                self.clicks.append((x, y, "enter_pass_modal"))
                return
            # Task icon: ROI_TASK_ENTRY_BTN (1192, 134, 85, 320)
            elif 1180 <= x <= 1280 and 120 <= y <= 450:
                self.screen_state = "task_panel"
                self.clicks.append((x, y, "enter_task_panel"))
                return

        # 3. In Outpost Defense Panel
        elif self.screen_state == "outpost":
            if self.sweep_modal:
                if 440 <= x <= 600 and 500 <= y <= 580:
                    self.sweep_modal = False
                    self.clicks.append((x, y, "cancel_sweep"))
                    return
                elif 650 <= x <= 830 and 500 <= y <= 580:
                    self.sweep_modal = False
                    self.reward_modal = True
                    self.free_sweep_available = False
                    self.clicks.append((x, y, "confirm_sweep"))
                    return
            else:
                # Claim accumulated reward: (440, 520, 160, 60)
                if self.has_accumulated_reward and 430 <= x <= 610 and 510 <= y <= 570:
                    self.reward_modal = True
                    self.has_accumulated_reward = False
                    self.clicks.append((x, y, "claim_reward"))
                    return
                # Open sweep modal: (680, 520, 160, 60)
                elif 670 <= x <= 850 and 510 <= y <= 590:
                    self.sweep_modal = True
                    self.clicks.append((x, y, "open_sweep"))
                    return
                # Dispatch Board Entrance: ROI_DISPATCH_ENTRY_BTN (413, 565, 124, 70)
                elif 400 <= x <= 550 and 571 <= y <= 640:
                    self.screen_state = "dispatch"
                    self.clicks.append((x, y, "enter_dispatch"))
                    return

        # 4. In Mail Screen
        elif self.screen_state == "mail":
            # Close mail: ROI_MAIL_CLOSE_BTN (709, 28, 179, 154)
            if 700 <= x <= 890 and 20 <= y <= 190:
                self.screen_state = "home"
                self.clicks.append((x, y, "close_mail"))
                return
            # Claim all button: ROI_MAIL_CLAIM_ALL_BTN (593, 541, 252, 135)
            elif 580 <= x <= 860 and 530 <= y <= 680:
                self.reward_modal = True
                self.mail_has_unread = False
                self.clicks.append((x, y, "mail_claim_all"))
                return

        # 5. In Friends Screen
        elif self.screen_state == "friends":
            # Close friends: ROI_FRIEND_CLOSE_BTN (710, 28, 180, 154)
            if 700 <= x <= 900 and 20 <= y <= 190:
                self.screen_state = "home"
                self.clicks.append((x, y, "close_friends"))
                return
            # Send / Receive: ROI_FRIEND_SEND_RECEIVE_BTN (667, 565, 155, 80)
            elif 650 <= x <= 830 and 550 <= y <= 660:
                self.modal_active = True
                self.clicks.append((x, y, "friends_send_receive"))
                return
            # Confirm modal: ROI_FRIEND_CONFIRM_BTN (566, 430, 150, 45)
            elif 550 <= x <= 730 and 420 <= y <= 490:
                self.modal_active = False
                self.friends_need_action = False
                self.clicks.append((x, y, "friends_confirm"))
                return

        # 6. In Dispatch Board Screen
        elif self.screen_state == "dispatch":
            # Exit dispatch: ROI_DISPATCH_EXIT_BTN (20, 20, 80, 60)
            if 10 <= x <= 110 and 10 <= y <= 90:
                self.screen_state = "home"
                self.clicks.append((x, y, "dispatch_exit"))
                return
            # Claim all dispatches: ROI_DISPATCH_CLAIM_ALL_BTN (702, 570, 120, 65)
            elif 690 <= x <= 830 and 560 <= y <= 645:
                self.reward_modal = True
                self.dispatch_has_completed = False
                self.clicks.append((x, y, "dispatch_claim_all"))
                return
            # Dispatch all pending: ROI_DISPATCH_ALL_BTN (582, 575, 120, 65)
            elif 570 <= x <= 710 and 565 <= y <= 650:
                self.modal_active = True
                self.clicks.append((x, y, "dispatch_all"))
                return
            # Confirm dispatch: ROI_DISPATCH_CONFIRM_BTN (640, 510, 180, 60)
            elif 630 <= x <= 830 and 500 <= y <= 580:
                self.modal_active = False
                self.dispatch_has_pending = False
                self.clicks.append((x, y, "dispatch_confirm"))
                return

        # 7. In Daily Shop Screen
        elif self.screen_state in ("shop", "payshop"):
            # Normal free item: ROI_SHOP_NORMAL_FREE_ITEM (72, 348, 120, 180)
            if 60 <= x <= 200 and 340 <= y <= 540:
                self.reward_modal = True
                self.shop_free_claimed = True
                self.clicks.append((x, y, "shop_buy_free"))
                return
            # Shop buy confirm: ROI_SHOP_BUY_CONFIRM_BTN (560, 480, 160, 60)
            elif 550 <= x <= 730 and 470 <= y <= 550:
                self.reward_modal = False
                self.clicks.append((x, y, "shop_buy_confirm"))
                return
            # Shop tabs
            elif 0 <= x <= 70 and 240 <= y <= 590:
                self.clicks.append((x, y, "switch_shop_tab"))
                return

        # 8. In Ark Hub
        elif self.screen_state == "ark":
            # Ark Hub
            # Unlimited Tower building: (705, 288, 127, 49)
            if 680 <= x <= 850 and 260 <= y <= 350:
                self.screen_state = "tower_main"
                self.clicks.append((x, y, "enter_tower_main"))
                return
            # SimRoom entry: (433, 268, 174, 209)
            elif 400 <= x <= 620 and 240 <= y <= 480:
                self.screen_state = "sim_room"
                self.clicks.append((x, y, "enter_sim_room"))
                return
            # Interception entry: (509, 445, 160, 254)
            elif 480 <= x <= 680 and 440 <= y <= 700:
                self.screen_state = "interception"
                self.clicks.append((x, y, "enter_interception"))
                return
            # Arena entry: (631, 325, 208, 274)
            elif 620 <= x <= 850 and 310 <= y <= 600:
                self.screen_state = "arena"
                self.clicks.append((x, y, "enter_arena"))
                return

        # 9. In SimRoom Screen
        elif self.screen_state == "sim_room":
            # Start Sim: (561, 384, 159, 75)
            if 540 <= x <= 730 and 370 <= y <= 470:
                self.clicks.append((x, y, "start_sim"))
                return
            # 5-C Sector: (678, 261, 181, 272)
            elif 650 <= x <= 870 and 240 <= y <= 540:
                self.clicks.append((x, y, "select_5c"))
                return
            # Quick Sim: (636, 574, 201, 117)
            elif 620 <= x <= 850 and 560 <= y <= 700:
                self.reward_modal = True
                self.clicks.append((x, y, "quick_sim"))
                return
            # End Sim confirm: (644, 427, 162, 50)
            elif 630 <= x <= 820 and 410 <= y <= 490:
                self.reward_modal = True
                self.clicks.append((x, y, "sim_end_confirm"))
                return

        # 10. In Interception Screen
        elif self.screen_state == "interception":
            # Mode / Boss target: (575, 570, 128, 36)
            if 550 <= x <= 720 and 550 <= y <= 620:
                self.clicks.append((x, y, "interception_target"))
                return
            # Quick Battle: (642, 582, 193, 55)
            elif 630 <= x <= 850 and 570 <= y <= 650:
                self.reward_modal = True
                self.clicks.append((x, y, "interception_quick_battle"))
                return
            # Enter Battle: (699, 555, 185, 132)
            elif 680 <= x <= 900 and 540 <= y <= 700:
                self.reward_modal = True
                self.clicks.append((x, y, "interception_enter_battle"))
                return

        # 11. In Arena Screen
        elif self.screen_state in ("arena", "arena_rookie", "arena_special"):
            # Rookie entrance: (424, 323, 146, 109)
            if self.screen_state == "arena" and 410 <= x <= 580 and 310 <= y <= 440:
                self.screen_state = "arena_rookie"
                self.clicks.append((x, y, "enter_rookie_arena"))
                return
            # Special entrance: (633, 328, 108, 96)
            elif self.screen_state == "arena" and 620 <= x <= 750 and 310 <= y <= 440:
                self.screen_state = "arena_special"
                self.clicks.append((x, y, "enter_special_arena"))
                return
            # In rookie/special back to arena
            elif 10 <= x <= 110 and 10 <= y <= 90:
                self.screen_state = "arena"
                self.clicks.append((x, y, "arena_sub_back"))
                return
            # Enter fight / Confirm fight
            elif 600 <= x <= 900 and 520 <= y <= 700:
                self.reward_modal = True
                self.clicks.append((x, y, "arena_fight"))
                return
            # Special point claim: (580, 74, 131, 63)
            elif 560 <= x <= 720 and 60 <= y <= 150:
                self.reward_modal = True
                self.clicks.append((x, y, "special_claim_points"))
                return

        # 12. In Inquiry Screens
        elif self.screen_state == "inquiry":
            # Batch inquiry: (1176, 650, 100, 57)
            if 1150 <= x <= 1280 and 630 <= y <= 720:
                self.reward_modal = True
                self.clicks.append((x, y, "inquiry_batch"))
                return
            # Nikke slots: (119, 217, 271, 51)
            elif 100 <= x <= 1180 and 200 <= y <= 280:
                self.screen_state = "nikke_detail"
                self.clicks.append((x, y, "enter_nikke_detail"))
                return
            # Back
            elif x <= 100 and y <= 100:
                self.screen_state = "home"
                self.clicks.append((x, y, "exit_to_home"))
                return

        elif self.screen_state == "nikke_detail":
            # Quick / Base inquiry: (636, 518, 173, 51)
            if 600 <= x <= 820 and 500 <= y <= 620:
                self.reward_modal = True
                self.clicks.append((x, y, "nikke_inquire"))
                return
            # Gift: (1000, 540, 100, 80)
            elif 950 <= x <= 1120 and 500 <= y <= 630:
                self.screen_state = "gift_modal"
                self.clicks.append((x, y, "enter_gift_modal"))
                return
            # Back
            elif x <= 100 and y <= 100:
                self.screen_state = "inquiry"
                self.clicks.append((x, y, "back_to_inquiry"))
                return

        elif self.screen_state == "gift_modal":
            # Send gift: (880, 560, 120, 50)
            if 850 <= x <= 1020 and 530 <= y <= 630:
                self.reward_modal = True
                self.clicks.append((x, y, "send_gift"))
                return
            # Back
            elif x <= 100 and y <= 100:
                self.screen_state = "nikke_detail"
                self.clicks.append((x, y, "back_from_gift"))
                return

        # 13. In Task Panel
        elif self.screen_state == "task_panel":
            # Switch to weekly tab: (457, 92, 190, 87)
            if 450 <= x <= 650 and 80 <= y <= 180:
                self.clicks.append((x, y, "switch_weekly_tab"))
                return
            # Claim all: (660, 630, 200, 60)
            elif 650 <= x <= 880 and 600 <= y <= 700:
                self.reward_modal = True
                self.clicks.append((x, y, "task_claim_all"))
                return
            # Close task panel: (710, 28, 180, 154) or Back
            elif (700 <= x <= 950 and 20 <= y <= 180) or (x <= 100 and y <= 100):
                self.screen_state = "home"
                self.clicks.append((x, y, "close_task_panel"))
                return

        # 14. In PASS Modal
        elif self.screen_state == "pass_modal":
            # Claim all: (472, 648, 345, 42)
            if 450 <= x <= 850 and 600 <= y <= 700:
                self.reward_modal = True
                self.clicks.append((x, y, "pass_claim_all"))
                return
            # Exit pass: (20, 20, 80, 60)
            elif x <= 100 and y <= 100:
                self.screen_state = "home"
                self.clicks.append((x, y, "exit_pass"))
                return

        # 15. In Tower Screens
        elif self.screen_state == "tower_main":
            # Unlimited tower / corporate tower cards
            if (580 <= x <= 700 and 240 <= y <= 360) or (400 <= x <= 850 and 400 <= y <= 650):
                self.screen_state = "tower_detail"
                self.clicks.append((x, y, "enter_tower_detail"))
                return
            # Back to home
            elif x <= 100 and y <= 100:
                self.screen_state = "home"
                self.clicks.append((x, y, "exit_tower_to_home"))
                return

        elif self.screen_state == "tower_detail":
            # Enter fight: (661, 632, 193, 74)
            if 640 <= x <= 880 and 600 <= y <= 710:
                self.reward_modal = True
                self.clicks.append((x, y, "tower_enter_fight"))
                return
            # Exit tower detail: (42, 674, 40, 30) or back
            elif x <= 100 or (30 <= x <= 80 and 660 <= y <= 710):
                self.screen_state = "tower_main"
                self.clicks.append((x, y, "exit_tower_detail"))
                return

        self.clicks.append((x, y, f"click_{self.screen_state}"))


def bind_mock_vision_for_task(task: Any, game: MockNikkeGameContext) -> None:
    """Attach mock vision and OCR hooks to simulate successful completion in mock mode."""
    def mock_ocr(keyword, roi, min_confidence=0.70, frame=None):
        kw_tuple = (keyword,) if isinstance(keyword, str) else tuple(keyword)

        # Titles and screen identification
        if any(k in kw_tuple for k in ("防御前哨基地", "前哨基地防御", "防御前哨", "前哨基地")):
            return game.screen_state == "outpost"
        if any(k in kw_tuple for k in ("邮箱", "邮件", "mail")):
            return game.screen_state == "mail"
        if any(k in kw_tuple for k in ("好友", "friend")):
            return game.screen_state == "friends"
        if any(k in kw_tuple for k in ("派遣公告栏", "派遣公告", "公告栏", "派遣")):
            return game.screen_state == "dispatch"
        if any(k in kw_tuple for k in ("普通", "普通商店", "basic", "商城")):
            return game.screen_state in ("shop", "normal_shop")
        if any(k in kw_tuple for k in ("付费商店", "付费", "cash")):
            return game.screen_state in ("shop", "payshop")
        if any(k in kw_tuple for k in ("方舟", "ark")):
            return game.screen_state == "ark"
        if any(k in kw_tuple for k in ("模拟室", "simulation", "5-c", "5c")):
            return game.screen_state == "sim_room"
        if any(k in kw_tuple for k in ("拦截战", "interception", "克拉肯", "kraken")):
            return game.screen_state == "interception"
        if any(k in kw_tuple for k in ("竞技场", "arena")):
            return game.screen_state in ("arena", "arena_rookie", "arena_special")
        if any(k in kw_tuple for k in ("新人竞技场", "新人")):
            return game.screen_state == "arena" or game.screen_state == "arena_rookie"
        if any(k in kw_tuple for k in ("特殊竞技场", "特殊")):
            return game.screen_state == "arena" or game.screen_state == "arena_special"

        # Outpost defense buttons
        if "获得奖励" in kw_tuple:
            return game.screen_state == "outpost" and game.has_accumulated_reward
        if "无可获得" in kw_tuple:
            return game.screen_state == "outpost" and not game.has_accumulated_reward
        if any(k in kw_tuple for k in ("免费", "0")):
            if game.sweep_modal:
                return game.free_sweep_available
            return True
        if "进行歼灭" in kw_tuple:
            return game.sweep_modal

        # Mail buttons
        if any(k in kw_tuple for k in ("全部领取", "一键领取", "领取")):
            return True
        if any(k in kw_tuple for k in ("没有邮件", "无可领取", "暂无")):
            return False

        # Friends buttons
        if any(k in kw_tuple for k in ("赠送", "全部赠送", "赠送点数", "收取并赠送")):
            return True
        if any(k in kw_tuple for k in ("无法获得", "已完成", "今日上限")):
            return False

        # Dispatch buttons
        if any(k in kw_tuple for k in ("全部派遣", "重新派遣")):
            return True
        if any(k in kw_tuple for k in ("没有可进行", "无可派遣", "无派遣任务")):
            return False

        # Shop buttons
        if any(k in kw_tuple for k in ("购买", "免费礼包", "每日免费", "免费刷新", "重置")):
            return True
        if any(k in kw_tuple for k in ("售罄", "soldout", "已售罄", "已领")):
            return False

        # Combat & Ark buttons
        if any(k in kw_tuple for k in ("开始模拟", "快速模拟", "快速战斗", "进入战斗", "收获", "领取")):
            return True
        if any(k in kw_tuple for k in ("消耗资金", "币不足", "消耗珠宝", "已超出进入次数", "无法进行快速", "每日至少游玩1次后")):
            return False

        # Phase 3 Growth, Rewards & Tower keywords
        if any(k in kw_tuple for k in ("咨询", "inquiry")):
            return game.screen_state in ("inquiry", "nikke_detail")
        if any(k in kw_tuple for k in ("快速咨询", "批量咨询", "批量", "每周任务", "每周")):
            return True
        if any(k in kw_tuple for k in ("任务", "task")):
            return game.screen_state == "task_panel"
        if any(k in kw_tuple for k in ("奖励", "pass奖励")):
            return game.screen_state == "pass_modal"
        if any(k in kw_tuple for k in ("塔", "tower")):
            return game.screen_state in ("tower_main", "tower_detail")
        if any(k in kw_tuple for k in ("无限之塔", "无限")):
            return game.screen_state in ("ark", "tower_main", "tower_detail")
        if any(k in kw_tuple for k in ("通关阵容", "进入战斗", "剩余次数")):
            return game.screen_state == "tower_detail"
        if any(k in kw_tuple for k in ("0/3", "0次", "已用完", "剩余0次", "剩余咨询次数不足", "次数不足", "未开启", "未开放")):
            return False
        if any(k in kw_tuple for k in ("点击任意处", "点击继续", "点击进行下一步")):
            return game.reward_modal

        # Confirm & OK
        if any(k in kw_tuple for k in ("确认", "确定", "离开")):
            return True

        return False

    def mock_template(name, roi=None, **kwargs):
        if "spendzuan" in name:
            return (620, 540, 20, 20) if not game.free_sweep_available else None
        return None

    task.ocr_text_exists = mock_ocr
    task.find_template_multidim = mock_template


class NikkeDailyBatchRunner:
    """Master batch scheduler and execution engine for NIKKE daily automation tasks.

    Responsibilities:
    - Coordinates ordered execution of daily tasks according to priority.
    - Manages shared lifecycle context (FrozenWatch, ProblemReport, Interaction, Scene, Recovery).
    - Guarantees fault recovery isolation: failures never halt the batch; recovery to Home is invoked.
    - Exports comprehensive execution reports.
    """

    def __init__(
        self,
        ctx: Optional[Any] = None,
        pipeline: Optional[List[Union[str, Type[BaseGameTask], BaseGameTask]]] = None,
        report_dir: str = "reports",
        mock: bool = False,
        hwnd: int = 0,
    ) -> None:
        self.mock = mock
        self.report_dir = report_dir
        self.logger = logging.getLogger("yes_nikke.batch_runner")

        # Context initialization & unification
        if ctx is not None:
            self.ctx = ctx
            self._ensure_context_attributes(self.ctx)
        elif self.mock:
            self.ctx = MockNikkeGameContext(hwnd=hwnd, report_dir=report_dir)
        else:
            self.ctx = NikkeContext(hwnd=hwnd, report_dir=report_dir, mock=False)

        # Direct property bindings for high-efficiency reference
        self.frozen_watch: FrozenWatch = getattr(self.ctx, "frozen_watch", None)
        self.problem_report: ProblemReport = getattr(self.ctx, "problem_report", None)
        self.interaction: NikkeInteraction = getattr(self.ctx, "interaction", None)
        self.scene: NikkeScene = getattr(self.ctx, "scene", None)
        self.recovery: NikkeRecovery = getattr(self.ctx, "recovery", None)

        # Pipeline configuration
        self.pipeline: List[Union[str, Type[BaseGameTask], BaseGameTask]] = (
            list(pipeline) if pipeline is not None else list(DEFAULT_TASK_SEQUENCE)
        )

    def _ensure_context_attributes(self, ctx: Any) -> None:
        """Guarantee that a provided context object possesses all essential operational services."""
        if not hasattr(ctx, "frozen_watch") or ctx.frozen_watch is None:
            ctx.frozen_watch = FrozenWatch()
        if not hasattr(ctx, "problem_report") or ctx.problem_report is None:
            ctx.problem_report = ProblemReport()
        if not hasattr(ctx, "interaction") or ctx.interaction is None:
            ctx.interaction = NikkeInteraction(
                hwnd=getattr(ctx, "hwnd", 0), watchdog=ctx.frozen_watch
            )
        if not hasattr(ctx, "scene") or ctx.scene is None:
            ctx.scene = NikkeScene(ctx)
        if not hasattr(ctx, "recovery") or ctx.recovery is None:
            ctx.recovery = NikkeRecovery(ctx)
        if not hasattr(ctx, "report_dir"):
            ctx.report_dir = self.report_dir

    def set_pipeline(self, pipeline: List[Union[str, Type[BaseGameTask], BaseGameTask]]) -> None:
        """Override the task pipeline."""
        self.pipeline = list(pipeline)

    def add_task(self, task_spec: Union[str, Type[BaseGameTask], BaseGameTask]) -> None:
        """Append a task to the pipeline."""
        self.pipeline.append(task_spec)

    def resolve_task_class(self, task_identifier: Union[str, Type[BaseGameTask]]) -> Type[BaseGameTask]:
        """Resolve a task identifier (class name or alias) into an instantiable task class."""
        if isinstance(task_identifier, type) and issubclass(task_identifier, BaseGameTask):
            return task_identifier

        if not isinstance(task_identifier, str):
            raise TypeError(f"Invalid task identifier type: {type(task_identifier).__name__}")

        raw_name = task_identifier.strip()
        norm_key = raw_name.lower().replace("_", "").replace("-", "")

        # 1. Match known task registry
        if norm_key in TASK_MODULE_REGISTRY:
            mod_path, cls_name = TASK_MODULE_REGISTRY[norm_key]
            try:
                mod = importlib.import_module(mod_path)
                return getattr(mod, cls_name)
            except (ImportError, AttributeError) as exc:
                self.logger.debug(f"Direct import from {mod_path} failed: {exc}")

        # 2. Try importing directly from games.nikke.tasks
        try:
            tasks_pkg = importlib.import_module("games.nikke.tasks")
            if hasattr(tasks_pkg, raw_name):
                return getattr(tasks_pkg, raw_name)
            for attr in dir(tasks_pkg):
                if attr.lower() == norm_key:
                    cand = getattr(tasks_pkg, attr)
                    if isinstance(cand, type) and issubclass(cand, BaseGameTask):
                        return cand
        except Exception:
            pass

        # 3. Try scanning individual modules in games.nikke.tasks
        candidate_modules = [
            "games.nikke.tasks.outpost_defense",
            "games.nikke.tasks.mail_and_friends",
            "games.nikke.tasks.dispatch_board",
            "games.nikke.tasks.daily_shop",
            "games.nikke.tasks.sim_room",
            "games.nikke.tasks.interception",
            "games.nikke.tasks.arena",
            "games.nikke.tasks.inquiry_and_gift",
            "games.nikke.tasks.daily_rewards",
            "games.nikke.tasks.climb_tower",
        ]
        for c_mod in candidate_modules:
            try:
                mod = importlib.import_module(c_mod)
                for attr_name in dir(mod):
                    if attr_name.lower() == norm_key or attr_name == raw_name:
                        cand = getattr(mod, attr_name)
                        if isinstance(cand, type) and issubclass(cand, BaseGameTask):
                            return cand
            except Exception:
                continue

        # 4. If in Mock mode, generate a dynamic mock task fallback for testing
        if self.mock:
            self.logger.warning(
                f"[BatchRunner] Task class '{raw_name}' not yet available on disk; creating mock task."
            )
            return self._create_mock_fallback_task(raw_name)

        raise ImportError(f"Could not resolve task class for identifier: '{raw_name}'")

    def _create_mock_fallback_task(self, name: str) -> Type[BaseGameTask]:
        """Synthesize an ephemeral mock task class for offline regression verification."""
        class EphemeralMockTask(BaseGameTask):
            def __init__(self, ctx: Any = None) -> None:
                super().__init__(ctx, name=name)

            def run(self) -> bool:
                self.log_info(f"[MockTask] Simulated execution of {self.name} completed successfully.")
                if self.ctx and hasattr(self.ctx, "screen_state"):
                    self.ctx.screen_state = "home"
                return True

        EphemeralMockTask.__name__ = name
        return EphemeralMockTask

    def dry_run(self) -> List[Tuple[str, str]]:
        """Inspect and return the planned pipeline without executing any tasks.

        Returns:
            List of (task_name, description) tuples.
        """
        result = []
        for task_spec in self.pipeline:
            if isinstance(task_spec, str):
                name = task_spec
            elif isinstance(task_spec, type):
                name = task_spec.__name__
            elif isinstance(task_spec, BaseGameTask):
                name = task_spec.name
            else:
                name = str(task_spec)

            desc = TASK_DESCRIPTIONS.get(name, "日常自动化任务")
            result.append((name, desc))
        return result

    def run_task(
        self,
        task_spec: Union[str, Type[BaseGameTask], BaseGameTask],
    ) -> TaskResult:
        """Execute a single task with full lifecycle isolation, watchdog feeding, and recovery."""
        # Resolve task instance
        task_obj: BaseGameTask
        if isinstance(task_spec, BaseGameTask):
            task_obj = task_spec
            if getattr(task_obj, "ctx", None) is None:
                task_obj.ctx = self.ctx
        elif isinstance(task_spec, type) and issubclass(task_spec, BaseGameTask):
            task_obj = task_spec(self.ctx)
        else:
            task_cls = self.resolve_task_class(task_spec)
            task_obj = task_cls(self.ctx)

        task_name = task_obj.name
        self.logger.info(f"=== [BatchRunner] Starting Task: {task_name} ===")

        # Attach mock vision if running under mock context
        if self.mock and isinstance(self.ctx, MockNikkeGameContext):
            bind_mock_vision_for_task(task_obj, self.ctx)

        # Reset watchdog before task execution
        if self.frozen_watch and hasattr(self.frozen_watch, "reset"):
            try:
                self.frozen_watch.reset()
            except Exception as exc:
                self.logger.debug(f"Failed to reset frozen_watch: {exc}")

        t0 = time.monotonic()
        task_failed = False
        error_msg = None

        try:
            # Execute task lifecycle via execute()
            res = task_obj.execute()
            if res is False:
                task_failed = True
                error_msg = f"Task [{task_name}] returned False indicating unfulfilled goal"
        except Exception as exc:
            task_failed = True
            error_msg = f"{type(exc).__name__}: {str(exc)}"
            self.logger.error(f"[BatchRunner] Task [{task_name}] threw exception: {error_msg}")

        duration = time.monotonic() - t0

        if task_failed:
            self.logger.warning(
                f"[BatchRunner] Task [{task_name}] FAILED after {duration:.2f}s: {error_msg}"
            )

            # 1. Record diagnostics into ProblemReport
            if self.problem_report and hasattr(self.problem_report, "export_report"):
                try:
                    last_frame = None
                    if hasattr(self.ctx, "capture") and self.ctx.capture is not None:
                        last_frame = self.ctx.capture.get_latest_frame(normalize_720p=False)
                    elif hasattr(self.ctx, "latest_frame"):
                        last_frame = self.ctx.latest_frame

                    self.problem_report.export_report(
                        output_dir=self.report_dir,
                        task_name=task_name,
                        error_msg=error_msg or "Unknown error",
                        final_frame=last_frame,
                    )
                except Exception as rpt_err:
                    self.logger.warning(f"[BatchRunner] Problem report export failed: {rpt_err}")

            # 2. Recovery Isolation: Deterministically return to Home Lobby
            recovery_target = getattr(self, "recovery", None) or getattr(self.ctx, "recovery", None)
            if recovery_target and hasattr(recovery_target, "recover_to_home"):
                try:
                    self.logger.info(
                        f"[BatchRunner] Initiating recovery isolation (recover_to_home) after [{task_name}]..."
                    )
                    rec_ok = recovery_target.recover_to_home()
                    if rec_ok:
                        self.logger.info(f"[BatchRunner] Isolation recovery to Home Lobby succeeded.")
                    else:
                        self.logger.warning(f"[BatchRunner] recover_to_home did not verify Home Lobby.")
                except Exception as rec_err:
                    self.logger.error(f"[BatchRunner] Error during recover_to_home: {rec_err}")

            return TaskResult(
                task_name=task_name,
                status=TaskStatus.FAILED,
                duration=duration,
                error_msg=error_msg,
            )

        self.logger.info(f"[BatchRunner] Task [{task_name}] SUCCEEDED in {duration:.2f}s")

        # Verify home lobby state before next task
        scene_target = getattr(self, "scene", None) or getattr(self.ctx, "scene", None)
        recovery_target = getattr(self, "recovery", None) or getattr(self.ctx, "recovery", None)
        if scene_target and hasattr(scene_target, "is_in_home"):
            try:
                if not scene_target.is_in_home() and recovery_target:
                    recovery_target.recover_to_home()
            except Exception:
                pass

        return TaskResult(
            task_name=task_name,
            status=TaskStatus.SUCCESS,
            duration=duration,
            error_msg=None,
        )

    def run_all(self) -> BatchReport:
        """Execute all configured daily tasks serially in priority order with recovery isolation."""
        self.logger.info(
            f"========================================================================\n"
            f"          NIKKE DAILY BATCH RUNNER STARTED (Total {len(self.pipeline)} tasks)\n"
            f"========================================================================"
        )
        batch_start = time.monotonic()
        results: List[TaskResult] = []

        total = len(self.pipeline)
        for idx, task_spec in enumerate(self.pipeline, 1):
            name_label = getattr(task_spec, "__name__", getattr(task_spec, "name", str(task_spec)))
            self.logger.info(f"--- Processing Batch Step [{idx}/{total}]: {name_label} ---")

            try:
                result = self.run_task(task_spec)
            except Exception as outer_exc:
                err_text = f"RunnerException: {outer_exc}"
                self.logger.error(f"[BatchRunner] Failed to run step {name_label}: {err_text}")
                result = TaskResult(
                    task_name=str(name_label),
                    status=TaskStatus.FAILED,
                    duration=0.0,
                    error_msg=err_text,
                )
                if self.recovery and hasattr(self.recovery, "recover_to_home"):
                    try:
                        self.recovery.recover_to_home()
                    except Exception:
                        pass

            results.append(result)

        total_duration = time.monotonic() - batch_start
        success_count = sum(1 for r in results if r.status == TaskStatus.SUCCESS)
        failed_count = sum(1 for r in results if r.status == TaskStatus.FAILED)
        skipped_count = sum(1 for r in results if r.status == TaskStatus.SKIPPED)

        report = BatchReport(
            total_tasks=total,
            success_count=success_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            total_duration=total_duration,
            results=results,
        )

        self.logger.info(
            f"Batch run complete: {success_count}/{total} succeeded, {failed_count} failed in {total_duration:.2f}s"
        )
        return report
