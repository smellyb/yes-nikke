"""Constants and ROI definitions for NIKKE Growth & Rewards modules under 1280x720 baseline.

Covers:
1. Inquiry and Gift (咨询与送礼)
2. Daily Rewards & PASS (每日任务与战令PASS)
3. Tribe Tower / Unlimited Tower & Corporate Towers (无限之塔与企业塔)
"""

from __future__ import annotations

from typing import Tuple

# Re-export base constants for seamless imports
from games.nikke.constants import *

# ==============================================================================
# 1. Inquiry and Gift (咨询与送礼) ROIs & Text
# ==============================================================================
# Entry & Navigation
ROI_INQUIRY_ENTRY_BTN: Tuple[int, int, int, int] = (720, 665, 80, 50)      # Lobby bottom "妮姬" tab
ROI_NIKKE_LIST_INQUIRY_BTN: Tuple[int, int, int, int] = (434, 114, 278, 68) # "咨询" button in Nikke list screen
ROI_INQUIRY_TITLE: Tuple[int, int, int, int] = (556, 52, 168, 39)          # Title "咨询" in Inquiry main screen
ROI_INQUIRY_REMAINING_COUNT: Tuple[int, int, int, int] = (620, 50, 140, 45) # Remaining inquiry count display

# Top 3 Favorite Nikkes in Inquiry Screen (1280x720)
ROI_INQUIRY_NIKKE_1: Tuple[int, int, int, int] = (119, 217, 271, 51)       # Top 1 Nikke slot
ROI_INQUIRY_NIKKE_2: Tuple[int, int, int, int] = (506, 217, 278, 51)       # Top 2 Nikke slot
ROI_INQUIRY_NIKKE_3: Tuple[int, int, int, int] = (875, 220, 293, 49)       # Top 3 Nikke slot

# Inquiry Dialog & Action
ROI_INQUIRY_BASE_BTN: Tuple[int, int, int, int] = (637, 564, 173, 65)      # Normal "咨询" button on Nikke detail
ROI_INQUIRY_QUICK_BTN: Tuple[int, int, int, int] = (636, 518, 173, 51)     # "快速咨询" button on Nikke detail
ROI_INQUIRY_START_PROMPT: Tuple[int, int, int, int] = (465, 189, 359, 228)  # "是否对...进行咨询" modal
ROI_INQUIRY_CONFIRM_BTN: Tuple[int, int, int, int] = (650, 433, 151, 38)   # "确认" dialog button
ROI_INQUIRY_AFFINITY_UP: Tuple[int, int, int, int] = (520, 280, 240, 80)    # "好感度提升" notification
ROI_INQUIRY_RANK_UP: Tuple[int, int, int, int] = (520, 280, 240, 80)        # "追加能力值" rank-up notification
ROI_INQUIRY_CHAT_SKIP: Tuple[int, int, int, int] = (619, 529, 50, 40)       # Dialogue advance/skip button

# Gift Modal & Action
ROI_INQUIRY_GIFT_BTN: Tuple[int, int, int, int] = (1000, 540, 100, 80)     # "送礼" button on Nikke detail
ROI_INQUIRY_GIFT_TITLE: Tuple[int, int, int, int] = (575, 82, 141, 40)      # "送礼" modal title
ROI_INQUIRY_MAX_AFFINITY: Tuple[int, int, int, int] = (510, 306, 235, 95)   # "最高等级" / "彼此的唯一" check
ROI_INQUIRY_BASIC_GIFT_SLOT: Tuple[int, int, int, int] = (489, 349, 43, 45) # Basic gift item icon slot
ROI_INQUIRY_SEND_GIFT_BTN: Tuple[int, int, int, int] = (880, 560, 120, 50)  # "送礼" submit button
ROI_INQUIRY_CLAIM_SEND_GIFT: Tuple[int, int, int, int] = (560, 480, 160, 60) # Gift sent confirmation button
ROI_INQUIRY_GIFT_CLOSE: Tuple[int, int, int, int] = (20, 20, 80, 60)        # Back button out of gift modal

# Batch Inquiry (一键/批量咨询)
ROI_INQUIRY_BATCH_BTN: Tuple[int, int, int, int] = (1176, 650, 100, 57)    # "批量咨询" button
ROI_INQUIRY_BATCH_CONFIRM_BTN: Tuple[int, int, int, int] = (726, 601, 114, 55) # Secondary "批量咨询" / "确认" button
ROI_INQUIRY_NO_TIMES_MODAL: Tuple[int, int, int, int] = (547, 343, 209, 37) # "剩余咨询次数不足" modal
ROI_INQUIRY_NO_TIMES_CLOSE: Tuple[int, int, int, int] = (725, 654, 127, 58) # Close button on no-times modal
ROI_INQUIRY_STEP_NEXT: Tuple[int, int, int, int] = (640, 650, 180, 50)     # "点击进行下一步" confirmation

# Keywords for Inquiry
TEXT_INQUIRY_TITLE: Tuple[str, ...] = ("咨询", "妮姬咨询", "inquiry")
TEXT_INQUIRY_BATCH: Tuple[str, ...] = ("批量咨询", "一键咨询", "批量")
TEXT_INQUIRY_BASE: Tuple[str, ...] = ("咨询", "开始咨询")
TEXT_INQUIRY_QUICK: Tuple[str, ...] = ("快速咨询", "快速")
TEXT_INQUIRY_FINISHED: Tuple[str, ...] = ("已完成今日咨询", "已完成", "已用完", "休息")
TEXT_INQUIRY_NO_TIMES: Tuple[str, ...] = ("剩余咨询次数不足", "次数不足", "当前没有可咨询", "当前没有")
TEXT_INQUIRY_AFFINITY_UP: Tuple[str, ...] = ("好感度提升", "追加能力值", "好感度")
TEXT_INQUIRY_MAX_LEVEL: Tuple[str, ...] = ("最高等级", "彼此的唯一", "max")
TEXT_INQUIRY_GIFT: Tuple[str, ...] = ("送礼", "赠送礼物", "gift")
TEXT_INQUIRY_NEXT_STEP: Tuple[str, ...] = ("点击进行下一步", "点击进行", "进行下一步")


# ==============================================================================
# 2. Daily Rewards & PASS (每日任务与战令PASS) ROIs & Text
# ==============================================================================
# Task Entry & Title
ROI_TASK_ENTRY_BTN: Tuple[int, int, int, int] = (1192, 134, 85, 320)       # Lobby top-right Task entry button
ROI_TASK_ENTRY_ALT: Tuple[int, int, int, int] = (1165, 120, 112, 277)      # Fallback region for task button
ROI_TASK_TITLE: Tuple[int, int, int, int] = (550, 44, 162, 65)             # Task window title "任务"
ROI_TASK_DAILY_TAB: Tuple[int, int, int, int] = (250, 92, 200, 87)         # "每日任务" tab
ROI_TASK_WEEKLY_TAB: Tuple[int, int, int, int] = (457, 92, 190, 87)        # "每周任务" tab (safe bounds avoiding close button)
ROI_TASK_CLAIM_ALL_BTN: Tuple[int, int, int, int] = (660, 630, 200, 60)    # "全部领取" button
ROI_TASK_CLOSE_BTN: Tuple[int, int, int, int] = (710, 28, 180, 154)        # Close button in task panel

# PASS Promotion & Rewards
ROI_PASS_ENTRY_BTN: Tuple[int, int, int, int] = (1109, 78, 70, 87)         # Lobby right-top PASS event entrance
ROI_PASS_RED_POINT: Tuple[int, int, int, int] = (1145, 70, 133, 77)        # PASS red dot indicator
ROI_PASS_TAB_TASK: Tuple[int, int, int, int] = (459, 215, 180, 42)         # PASS sub-tab "任务"
ROI_PASS_TAB_REWARD: Tuple[int, int, int, int] = (640, 215, 180, 42)       # PASS sub-tab "奖励"
ROI_PASS_CLAIM_ALL_BTN: Tuple[int, int, int, int] = (472, 648, 345, 42)    # PASS "全部领取" button
ROI_PASS_EXIT_BTN: Tuple[int, int, int, int] = (20, 20, 80, 60)            # Exit back button on PASS window

# Keywords for Daily Rewards & PASS
TEXT_TASK_TITLE: Tuple[str, ...] = ("任务", "每日任务", "每周任务", "task")
TEXT_TASK_DAILY: Tuple[str, ...] = ("每日任务", "每日")
TEXT_TASK_WEEKLY: Tuple[str, ...] = ("每周任务", "每周")
TEXT_TASK_CLAIM_ALL: Tuple[str, ...] = ("全部领取", "一键领取", "领取")
TEXT_PASS_TASK: Tuple[str, ...] = ("任务", "pass任务")
TEXT_PASS_REWARD: Tuple[str, ...] = ("奖励", "pass奖励")


# ==============================================================================
# 3. Tribe Tower & Corporate Towers (无限之塔与企业塔) ROIs & Text
# ==============================================================================
# Ark Entrance & Tower Main Page
ROI_ARK_TITLE: Tuple[int, int, int, int] = (9, 6, 76, 44)                  # "方舟" title in Ark screen
ROI_TOWER_ENTRY_BTN: Tuple[int, int, int, int] = (705, 288, 127, 49)       # Ark "无限之塔" building entrance
ROI_TOWER_TITLE: Tuple[int, int, int, int] = (4, 11, 93, 37)               # "塔" title
ROI_TOWER_STATUS_HEADER: Tuple[int, int, int, int] = (455, 341, 371, 97)   # Tower list header ("开启" / "未开启")

# Unlimited Tower (无限之塔)
ROI_TOWER_UNLIMITED_BTN: Tuple[int, int, int, int] = (604, 263, 71, 76)    # Infinite Tower central entry
ROI_TOWER_UNLIMITED_TAG: Tuple[int, int, int, int] = (534, 572, 209, 95)   # "无限之塔" card text area
ROI_TOWER_REMAIN_CHANCES: Tuple[int, int, int, int] = (483, 488, 319, 211) # "剩余次数" area in tower page
ROI_TOWER_CHANCE_COUNT: Tuple[int, int, int, int] = (506, 525, 295, 160)   # Specific chance counter (e.g. 3/3, 0/3)
ROI_TOWER_ENTER_FIGHT_BTN: Tuple[int, int, int, int] = (661, 632, 193, 74) # "进入战斗" button
ROI_TOWER_FORMATION_TAG: Tuple[int, int, int, int] = (698, 309, 125, 33)   # "通关阵容" tag confirming tower page

# Corporate Towers (4 大企业塔)
ROI_COP_TOWER_ELYSIO: Tuple[int, int, int, int] = (745, 441, 76, 176)      # Elysion (极乐净土) tower entrance
ROI_COP_TOWER_MISSILIS: Tuple[int, int, int, int] = (653, 460, 68, 142)    # Missilis (米西利斯) tower entrance
ROI_COP_TOWER_TETRA: Tuple[int, int, int, int] = (558, 445, 73, 157)       # Tetra (泰特拉) tower entrance
ROI_COP_TOWER_PILGRIM: Tuple[int, int, int, int] = (463, 420, 70, 195)     # Pilgrim (朝圣者) tower entrance

# Combat Execution & Settlement
ROI_TOWER_FIGHT_END_TAP: Tuple[int, int, int, int] = (540, 600, 200, 60)   # "点击任意处" victory tap area
ROI_TOWER_FIGHT_RESULT: Tuple[int, int, int, int] = (461, 198, 358, 122)   # "战斗胜利" / "战败" / "逾时" / "FAILED"
ROI_TOWER_FAILED_BACK_BTN: Tuple[int, int, int, int] = (8, 605, 159, 109)  # "ESC" / "返回" on combat defeat
ROI_TOWER_CONTINUE_BTN: Tuple[int, int, int, int] = (918, 107, 100, 50)    # "继续游戏" button
ROI_TOWER_FLASH_SALE_AREA: Tuple[int, int, int, int] = (328, 22, 584, 682) # Flash sale popup
ROI_TOWER_FLASH_SALE_CLOSE: Tuple[int, int, int, int] = (1065, 80, 60, 60) # Flash sale close button
ROI_TOWER_EXIT_PAGE_BTN: Tuple[int, int, int, int] = (42, 674, 40, 30)     # Bottom-left exit tower back button

# Keywords for Tower
TEXT_TOWER_TITLE: Tuple[str, ...] = ("塔", "无限之塔", "企业塔", "tower")
TEXT_TOWER_UNLIMITED: Tuple[str, ...] = ("无限之塔", "无限", "unlimited")
TEXT_TOWER_ENTER_FIGHT: Tuple[str, ...] = ("进入战斗", "战斗", "挑战")
TEXT_TOWER_REMAIN_CHANCES: Tuple[str, ...] = ("剩余次数", "剩余")
TEXT_TOWER_CHANCE_ZERO: Tuple[str, ...] = ("0/3", "0次", "已用完", "剩余0次", "剩余次数0")
TEXT_TOWER_FIGHT_END: Tuple[str, ...] = ("点击任意处", "点击继续", "点击任意区域关闭", "获得奖励")
TEXT_TOWER_FAILED: Tuple[str, ...] = ("战败", "逾时", "FAILED", "OPERATIONFAILED", "失败")
TEXT_TOWER_FLASH_SALE: Tuple[str, ...] = ("同时出现的礼包", "SALE", "选择一个购买", "特惠礼包", "菲比")
TEXT_COP_TOWER_OPEN: Tuple[str, ...] = ("开启", "开放")
TEXT_COP_TOWER_CLOSED: Tuple[str, ...] = ("未开启", "未开放", "后开启")
TEXT_COP_TOWER_NAMES: Tuple[str, ...] = ("极乐净土", "米西利斯", "泰特拉", "朝圣者")
