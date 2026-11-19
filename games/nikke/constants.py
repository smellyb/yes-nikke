"""Constants and ROI definitions for NIKKE automation under 1280x720 baseline.

Every coordinate, bounding box, and region-of-interest (ROI) in this module is
strictly normalized to the 1280x720 logical coordinate system.
"""

from __future__ import annotations

from typing import Tuple

# --- Canonical Resolution ---
BASE_WIDTH: int = 1280
BASE_HEIGHT: int = 720
BASE_RESOLUTION: Tuple[int, int] = (BASE_WIDTH, BASE_HEIGHT)

# --- Lobby (Home) ROIs: (x, y, w, h) ---
ROI_HOME_OUTPOST_BTN: Tuple[int, int, int, int] = (1120, 600, 120, 90)  # Lobby bottom-right Outpost button
ROI_HOME_BOTTOM_MENU: Tuple[int, int, int, int] = (0, 640, 1280, 80)     # Bottom navigation bar
ROI_HOME_BOTTOM_LOBBY: Tuple[int, int, int, int] = (600, 665, 80, 50)    # "大厅" tab
ROI_HOME_BOTTOM_OUTPOST: Tuple[int, int, int, int] = (1120, 600, 120, 90) # Outpost base button
ROI_HOME_BOTTOM_ARK: Tuple[int, int, int, int] = (100, 665, 80, 50)      # "方舟" tab
ROI_HOME_BOTTOM_NIKKE: Tuple[int, int, int, int] = (720, 665, 80, 50)    # "妮姬" tab
ROI_HOME_BOTTOM_SQUAD: Tuple[int, int, int, int] = (840, 665, 80, 50)    # "编队" tab
ROI_HOME_BOTTOM_SHOP: Tuple[int, int, int, int] = (960, 665, 80, 50)     # "商城" tab
ROI_HOME_OUTPOST_SUBVIEW: Tuple[int, int, int, int] = (260, 565, 170, 95) # In-map outpost defense icon

# --- Navigation & Recovery ROIs ---
ROI_TOP_LEFT_BACK: Tuple[int, int, int, int] = (20, 20, 80, 60)         # Top-left back arrow / icon
ROI_TOP_LEFT_HOME: Tuple[int, int, int, int] = (0, 640, 155, 75)        # Home icon on some subpages
ROI_SAFE_CLICK_BLANK: Tuple[int, int, int, int] = (640, 660, 1, 1)      # Safe lower-center blank click point

# --- Outpost Defense Panel ROIs ---
ROI_TITLE: Tuple[int, int, int, int] = (410, 40, 280, 80)               # "防御前哨基地" Title area
ROI_OUTPOST_TITLE: Tuple[int, int, int, int] = (410, 40, 280, 80)       # Alias for title area
ROI_CLAIM_BTN: Tuple[int, int, int, int] = (440, 520, 160, 60)           # "获得奖励" (Claim defense rewards)
ROI_SWEEP_BTN: Tuple[int, int, int, int] = (680, 520, 160, 60)           # "一举歼灭" (Wipeout entrance)
ROI_OUTPOST_LEVEL_INFO: Tuple[int, int, int, int] = (400, 120, 300, 60) # Level and accumulation rate
ROI_OUTPOST_NO_REWARD: Tuple[int, int, int, int] = (484, 413, 327, 166)  # "目前没有获得" / "无可获得" area

# --- Outpost Wipeout (Sweep) Modal ROIs ---
ROI_SWEEP_CONFIRM_BTN: Tuple[int, int, int, int] = (660, 510, 160, 60)   # "进行歼灭" (Confirm sweep)
ROI_SWEEP_CANCEL_BTN: Tuple[int, int, int, int] = (450, 510, 140, 60)    # "取消" (Cancel sweep dialog)
ROI_SWEEP_FREE_TAG: Tuple[int, int, int, int] = (610, 535, 180, 30)      # Free indicator or diamond icon
ROI_SWEEP_COST_INFO: Tuple[int, int, int, int] = (580, 520, 220, 50)     # Sweep cost area (free vs diamond)
ROI_SWEEP_GEM_CONFIRM_BTN: Tuple[int, int, int, int] = (639, 425, 178, 51) # Second gem spending confirmation
ROI_SWEEP_GEM_NO_PROMPT_TODAY: Tuple[int, int, int, int] = (514, 244, 255, 161) # "今日不再显示" checkbox

# --- Mail ROIs ---
ROI_MAIL_ENTRY_BTN: Tuple[int, int, int, int] = (1206, 4, 45, 44)         # Lobby top-right mail button
ROI_MAIL_TITLE: Tuple[int, int, int, int] = (565, 55, 165, 95)             # Mail window title area
ROI_MAIL_CLAIM_ALL_BTN: Tuple[int, int, int, int] = (593, 541, 252, 135)   # "全部领取" button
ROI_MAIL_CLOSE_BTN: Tuple[int, int, int, int] = (709, 28, 179, 154)        # Close button in mail window
ROI_MAIL_EMPTY_PROMPT: Tuple[int, int, int, int] = (500, 300, 280, 120)    # Empty mail prompt area

# --- Friends ROIs ---
ROI_FRIEND_ENTRY_BTN: Tuple[int, int, int, int] = (1175, 144, 105, 310)    # Lobby right sidebar friend button
ROI_FRIEND_TITLE: Tuple[int, int, int, int] = (557, 65, 185, 55)           # Friend window title area
ROI_FRIEND_SEND_RECEIVE_BTN: Tuple[int, int, int, int] = (667, 565, 155, 80) # "赠送" / "全部赠送" button
ROI_FRIEND_CONFIRM_BTN: Tuple[int, int, int, int] = (566, 430, 150, 45)    # Friend swap confirmation dialog button
ROI_FRIEND_CLOSE_BTN: Tuple[int, int, int, int] = (710, 28, 180, 154)      # Close button in friend window

# --- Dispatch Board ROIs ---
ROI_DISPATCH_ENTRY_BTN: Tuple[int, int, int, int] = (413, 565, 124, 70)    # Outpost dispatch board building / entrance
ROI_DISPATCH_TITLE: Tuple[int, int, int, int] = (482, 85, 120, 50)         # "派遣公告栏" title area
ROI_DISPATCH_CLAIM_ALL_BTN: Tuple[int, int, int, int] = (702, 570, 120, 65) # "全部领取" completed dispatches button
ROI_DISPATCH_ALL_BTN: Tuple[int, int, int, int] = (582, 575, 120, 65)      # "全部派遣" pending dispatches button
ROI_DISPATCH_CONFIRM_BTN: Tuple[int, int, int, int] = (640, 510, 180, 60)  # Secondary confirmation button
ROI_DISPATCH_EXIT_BTN: Tuple[int, int, int, int] = (20, 20, 80, 60)        # Dispatch exit / back button

# --- Shop ROIs ---
ROI_SHOP_ENTRY_BTN: Tuple[int, int, int, int] = (960, 665, 80, 50)         # Lobby bottom menu "商城"
ROI_SHOP_SIDEBAR: Tuple[int, int, int, int] = (0, 250, 60, 380)            # Shop left tab sidebar
ROI_SHOP_TAB_NORMAL: Tuple[int, int, int, int] = (0, 254, 58, 80)          # Normal / Basic shop tab
ROI_SHOP_TAB_ARENA: Tuple[int, int, int, int] = (0, 334, 58, 80)           # Arena shop tab
ROI_SHOP_TAB_BODY: Tuple[int, int, int, int] = (0, 414, 58, 80)            # Body tag shop tab
ROI_SHOP_TAB_SCRAP: Tuple[int, int, int, int] = (0, 494, 58, 80)           # Scrap shop tab
ROI_SHOP_TAB_PAYSHOP: Tuple[int, int, int, int] = (274, 387, 182, 109)     # Paid shop entry button
ROI_SHOP_NORMAL_FREE_ITEM: Tuple[int, int, int, int] = (72, 348, 120, 180) # Normal shop 0-gem free item slot
ROI_SHOP_NORMAL_FREE_REFRESH_BTN: Tuple[int, int, int, int] = (490, 615, 180, 65) # Free shop refresh button
ROI_SHOP_BUY_CONFIRM_BTN: Tuple[int, int, int, int] = (560, 480, 160, 60)  # Buy confirm button in shop modal
ROI_PAYSHOP_TITLE: Tuple[int, int, int, int] = (0, 11, 100, 40)            # Paid shop title area
ROI_PAYSHOP_BASIC_PACK_TAB: Tuple[int, int, int, int] = (2, 114, 354, 80)  # Basic pack tab in paid shop
ROI_PAYSHOP_DAILY_TAB: Tuple[int, int, int, int] = (1, 179, 538, 59)       # Daily tab in paid shop
ROI_PAYSHOP_DAILY_FREE_ITEM: Tuple[int, int, int, int] = (9, 242, 130, 240) # Daily free gift package item
ROI_PAYSHOP_CLAIM_CONFIRM_BTN: Tuple[int, int, int, int] = (560, 480, 160, 60) # Daily free claim confirm button

# --- Modals, Popups & Dialogs ROIs ---
ROI_GLOBAL_CLOSE: Tuple[int, int, int, int] = (540, 640, 200, 60)        # "点击任意区域关闭"
ROI_MODAL_CENTER: Tuple[int, int, int, int] = (400, 200, 480, 320)       # Center dialog body
ROI_MODAL_CONFIRM: Tuple[int, int, int, int] = (560, 480, 160, 60)       # Generic dialog confirm button
ROI_MODAL_CANCEL: Tuple[int, int, int, int] = (400, 480, 160, 60)        # Generic dialog cancel button
ROI_REWARD_CLAIM_TEXT: Tuple[int, int, int, int] = (430, 200, 420, 440)  # Reward popup text / click area
ROI_PASS_POPUP_CLOSE: Tuple[int, int, int, int] = (1134, 538, 30, 60)    # Pass promotion popup close button

# --- Loading ROIs & Detection ---
ROI_LOADING_RING: Tuple[int, int, int, int] = (1177, 619, 90, 86)        # Loading ring in bottom right
LOADING_KEYWORDS: Tuple[str, ...] = (
    "nowloading",
    "loading",
    "加载",
    "载入",
    "读取中",
    "连接中",
    "连线中",
    "通信中",
    "请稍候",
)

# --- Standard Text Keywords & Semantic Variants ---
TEXT_OUTPOST_TITLE: Tuple[str, ...] = ("防御前哨基地", "前哨基地防御", "防御前哨", "前哨基地")
TEXT_CLAIM_REWARD: Tuple[str, ...] = ("获得奖励", "领取奖励", "可获得")
TEXT_SWEEP: Tuple[str, ...] = ("一举歼灭", "举歼灭", "歼灭")
TEXT_SWEEP_CONFIRM: Tuple[str, ...] = ("进行歼灭", "确认歼灭")
TEXT_CANCEL: Tuple[str, ...] = ("取消", "关闭")
TEXT_CONFIRM: Tuple[str, ...] = ("确认", "确定")
TEXT_NO_REWARD: Tuple[str, ...] = ("无可获得", "目前没有获得", "目前没有", "没有可领取的奖励")
TEXT_REWARD_MODAL: Tuple[str, ...] = (
    "点击领取奖励",
    "点击领取",
    "领取奖励",
    "点击继续",
    "立刻领取",
    "全部领取",
    "点击任意处",
    "点击关闭画面",
    "点击任意区域关闭",
)
TEXT_HOME_TABS: Tuple[str, ...] = ("大厅", "前哨基地", "编队", "妮姬", "商城", "方舟")

# --- Mail Keywords ---
TEXT_MAIL_TITLE: Tuple[str, ...] = ("邮箱", "邮件", "mail")
TEXT_MAIL_CLAIM_ALL: Tuple[str, ...] = ("全部领取", "一键领取", "领取")
TEXT_MAIL_EMPTY: Tuple[str, ...] = ("没有邮件", "无可领取", "暂无", "无可领取的邮件")

# --- Friends Keywords ---
TEXT_FRIEND_TITLE: Tuple[str, ...] = ("好友", "friend")
TEXT_FRIEND_SEND: Tuple[str, ...] = ("赠送", "全部赠送", "赠送点数", "收取并赠送")
TEXT_FRIEND_FINISHED: Tuple[str, ...] = ("无法获得", "已完成", "今日上限", "已达上限")

# --- Dispatch Keywords ---
TEXT_DISPATCH_TITLE: Tuple[str, ...] = ("派遣公告栏", "派遣公告", "公告栏", "派遣")
TEXT_DISPATCH_CLAIM_ALL: Tuple[str, ...] = ("全部领取", "领取")
TEXT_DISPATCH_ALL: Tuple[str, ...] = ("全部派遣", "派遣")
TEXT_DISPATCH_EMPTY: Tuple[str, ...] = ("没有可进行", "无可派遣", "无派遣任务")

# --- Shop Keywords ---
TEXT_SHOP_NORMAL: Tuple[str, ...] = ("普通", "普通商店", "basic")
TEXT_SHOP_ARENA: Tuple[str, ...] = ("竞技场", "竞技场商店", "arena")
TEXT_SHOP_BODY: Tuple[str, ...] = ("躯体标签", "躯体标签商店", "标签")
TEXT_SHOP_SCRAP: Tuple[str, ...] = ("废铁", "废铁商店", "scrap")
TEXT_SHOP_PAYSHOP: Tuple[str, ...] = ("付费商店", "付费", "cash")
TEXT_SHOP_FREE: Tuple[str, ...] = ("免费", "100%", "sale", "0")
TEXT_SHOP_SOLD_OUT: Tuple[str, ...] = ("售罄", "soldout", "已售罄", "已领")
TEXT_SHOP_DAILY_FREE_PACK: Tuple[str, ...] = ("免费礼包", "免费", "每日免费")
TEXT_SHOP_REFRESH: Tuple[str, ...] = ("免费刷新", "重置", "刷新")

# =============================================================================
# Unified Re-exports: Combat and Growth Module Constants
# =============================================================================
try:
    from games.nikke.constants_combat import *  # noqa: F401, F403
except ImportError:
    pass

try:
    from games.nikke.constants_growth import *  # noqa: F401, F403
except ImportError:
    pass

