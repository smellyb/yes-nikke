"""Tasks package for NIKKE automation."""

from games.nikke.tasks.outpost_defense import OutpostDefenseTask, OutpostState
from games.nikke.tasks.mail_and_friends import (
    ClaimMailTask,
    MailState,
    FriendPointsTask,
    FriendState,
)
from games.nikke.tasks.dispatch_board import DispatchBoardTask, DispatchState
from games.nikke.tasks.daily_shop import DailyShopTask, ShopState
from games.nikke.tasks.sim_room import SimRoomTask, SimRoomState
from games.nikke.tasks.interception import InterceptionTask, InterceptionState
from games.nikke.tasks.arena import ArenaTask, ArenaState
from games.nikke.tasks.inquiry_and_gift import InquiryAndGiftTask, InquiryState
from games.nikke.tasks.daily_rewards import DailyRewardsTask, DailyRewardsState
from games.nikke.tasks.climb_tower import ClimbTowerTask, TowerState

__all__ = [
    "OutpostDefenseTask",
    "OutpostState",
    "ClaimMailTask",
    "MailState",
    "FriendPointsTask",
    "FriendState",
    "DispatchBoardTask",
    "DispatchState",
    "DailyShopTask",
    "ShopState",
    "SimRoomTask",
    "SimRoomState",
    "InterceptionTask",
    "InterceptionState",
    "ArenaTask",
    "ArenaState",
    "InquiryAndGiftTask",
    "InquiryState",
    "DailyRewardsTask",
    "DailyRewardsState",
    "ClimbTowerTask",
    "TowerState",
]
