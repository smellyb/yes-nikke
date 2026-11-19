"""Constants, ROIs, and Text definitions for Ark, SimRoom, Interception, and Arena.

Normalized to the canonical 1280x720 logical coordinate system.
"""

from __future__ import annotations

from typing import Tuple

# --- Canonical Baseline Resolution ---
BASE_WIDTH: int = 1280
BASE_HEIGHT: int = 720
BASE_RESOLUTION: Tuple[int, int] = (BASE_WIDTH, BASE_HEIGHT)

# =============================================================================
# 1. Ark (方舟) Entrance & Hub ROIs
# =============================================================================
ROI_HOME_ARK_BTN: Tuple[int, int, int, int] = (813, 403, 193, 151)       # Lobby Ark portal widget
ROI_HOME_ARK_BTN_ALT: Tuple[int, int, int, int] = (825, 423, 159, 103)   # Alternative bounding box
ROI_HOME_BOTTOM_ARK: Tuple[int, int, int, int] = (100, 665, 80, 50)       # Bottom navigation "方舟" tab
ROI_ARK_TITLE: Tuple[int, int, int, int] = (0, 8, 120, 50)                # Top-left Ark screen title
ROI_ARK_TITLE_ALT: Tuple[int, int, int, int] = (7, 15, 60, 35)            # Compact title ROI

# Ark Sub-entrance Buttons within Ark Hub
ROI_ARK_SIM_ROOM: Tuple[int, int, int, int] = (433, 268, 174, 209)        # Simulation Room entrance
ROI_ARK_SIM_ROOM_ALT: Tuple[int, int, int, int] = (440, 258, 151, 219)    # SimRoom template ROI
ROI_ARK_INTERCEPTION: Tuple[int, int, int, int] = (509, 445, 160, 254)    # Interception entrance
ROI_ARK_INTERCEPTION_ALT: Tuple[int, int, int, int] = (528, 589, 146, 83) # Interception text ROI
ROI_ARK_ARENA: Tuple[int, int, int, int] = (631, 325, 208, 274)           # Arena entrance
ROI_ARK_ARENA_ALT: Tuple[int, int, int, int] = (672, 480, 157, 97)        # Arena text ROI
ROI_ARK_TOWER: Tuple[int, int, int, int] = (185, 395, 170, 230)           # Tribe Tower entrance

# =============================================================================
# 2. Simulation Room (模拟室) ROIs
# =============================================================================
ROI_SIM_START_BTN: Tuple[int, int, int, int] = (561, 384, 159, 75)        # "开始模拟" button
ROI_SIM_5C_SECTOR: Tuple[int, int, int, int] = (678, 261, 181, 272)       # 5-C sector card / button
ROI_SIM_QUICK_BTN: Tuple[int, int, int, int] = (636, 574, 201, 117)       # "快速模拟" button
ROI_SIM_SKIP_BUFFS_BTN: Tuple[int, int, int, int] = (471, 573, 358, 136)  # "跳过增益效果选择" button
ROI_SIM_END_MODAL_TEXT: Tuple[int, int, int, int] = (465, 193, 352, 220)  # "模拟结束 / 重置" dialog text
ROI_SIM_END_CONFIRM_BTN: Tuple[int, int, int, int] = (644, 427, 162, 50)  # "确认" in sim end dialog
ROI_SIM_TOP_EXIT_BTN: Tuple[int, int, int, int] = (1117, 27, 159, 88)     # Top-right "模拟结束" exit button
ROI_SIM_COMPLETED_PROMPT: Tuple[int, int, int, int] = (528, 341, 249, 121)# "不再显示" / "今日已完成"
ROI_SIM_NOT_5C_PROMPT: Tuple[int, int, int, int] = (458, 280, 354, 149)   # "无法进行快速" / "仅限5-C"

# =============================================================================
# 3. Interception (拦截战) ROIs
# =============================================================================
ROI_INTERCEPTION_TITLE: Tuple[int, int, int, int] = (0, 8, 120, 50)       # Top-left Interception title
ROI_INTERCEPTION_ATTEMPTS: Tuple[int, int, int, int] = (400, 100, 480, 80)# "剩余拦截次数" info area
ROI_INTERCEPTION_MODE_ANOMALY: Tuple[int, int, int, int] = (765, 628, 48, 51) # 异常拦截 mode tab
ROI_INTERCEPTION_MODE_BASIC: Tuple[int, int, int, int] = (684, 626, 53, 52)   # 特级/普通拦截 mode tab
ROI_INTERCEPTION_BOSS_SWITCH_BTN: Tuple[int, int, int, int] = (728, 259, 66, 69) # Boss switch arrow
ROI_INTERCEPTION_BOSS_KRAKEN: Tuple[int, int, int, int] = (562, 489, 155, 74) # Kraken boss label
ROI_INTERCEPTION_BOSS_TARGET_BTN: Tuple[int, int, int, int] = (575, 570, 128, 36) # Boss target select button
ROI_INTERCEPTION_QUICK_BATTLE_BTN: Tuple[int, int, int, int] = (642, 582, 193, 55) # "快速战斗" sweep button
ROI_INTERCEPTION_ENTER_BATTLE_BTN: Tuple[int, int, int, int] = (699, 555, 185, 132) # "进入战斗" combat button
ROI_INTERCEPTION_CANNOT_QUICK: Tuple[int, int, int, int] = (400, 250, 480, 200) # "每日至少游玩1次后" notice
ROI_INTERCEPTION_EXCEEDED: Tuple[int, int, int, int] = (400, 250, 480, 200)     # "已超出进入次数" notice
ROI_INTERCEPTION_BATTLE_AUTO: Tuple[int, int, int, int] = (3, 4, 96, 67)   # AUTO toggle in combat
ROI_INTERCEPTION_BATTLE_PAUSE: Tuple[int, int, int, int] = (556, 30, 163, 88) # Combat pause header
ROI_INTERCEPTION_SETTLEMENT: Tuple[int, int, int, int] = (400, 480, 480, 180) # Combat settlement "点击任意处"

# =============================================================================
# 4. Arena (竞技场) ROIs
# =============================================================================
ROI_ARENA_TITLE: Tuple[int, int, int, int] = (0, 8, 120, 50)               # "竞技场" title area
ROI_ARENA_PAGE_HEADER: Tuple[int, int, int, int] = (524, 158, 241, 101)   # "ARENA" header
ROI_ARENA_ROOKIE_BTN: Tuple[int, int, int, int] = (424, 323, 146, 109)    # "新人竞技场" entrance
ROI_ARENA_SPECIAL_BTN: Tuple[int, int, int, int] = (633, 328, 108, 96)     # "特殊竞技场" entrance
ROI_ARENA_ENTER_FIGHT_BTN: Tuple[int, int, int, int] = (699, 555, 185, 132)# "进入战斗" list button
ROI_ARENA_CONFIRM_FIGHT_BTN: Tuple[int, int, int, int] = (620, 534, 205, 117) # "进入战斗" squad confirm
ROI_ARENA_AUTO_TOGGLE: Tuple[int, int, int, int] = (464, 560, 162, 82)    # Auto combat ON/OFF toggle
ROI_ARENA_COST_DIAMOND_PROMPT: Tuple[int, int, int, int] = (472, 237, 340, 173) # "消耗资金" / "币不足"
ROI_ARENA_COST_CANCEL_BTN: Tuple[int, int, int, int] = (460, 393, 187, 103) # Cancel diamond cost button
ROI_ARENA_SEASON_CLOSED_PROMPT: Tuple[int, int, int, int] = (400, 250, 480, 200) # "赛季已结束" / "敬请期待"
ROI_ARENA_SPECIAL_CLAIM_ENTRY: Tuple[int, int, int, int] = (580, 74, 131, 63) # Special arena point box
ROI_ARENA_SPECIAL_CLAIM_BTN: Tuple[int, int, int, int] = (639, 603, 181, 101) # "领取" button
ROI_ARENA_SPECIAL_CLAIM_CLOSE: Tuple[int, int, int, int] = (921, 490, 209, 127) # Blank close area
ROI_ARENA_SETTLEMENT_CLICK: Tuple[int, int, int, int] = (600, 500, 200, 100) # "点击进行下一步"

# =============================================================================
# 5. Semantic Texts and OCR Keywords
# =============================================================================
# Ark
TEXT_ARK_TITLE: Tuple[str, ...] = ("方舟", "ARK")
TEXT_ARK_SUB_SIM: Tuple[str, ...] = ("模拟室", "SIMULATION")
TEXT_ARK_SUB_INTERCEPTION: Tuple[str, ...] = ("拦截战", "INTERCEPTION")
TEXT_ARK_SUB_ARENA: Tuple[str, ...] = ("竞技场", "ARENA")

# SimRoom
TEXT_SIM_TITLE: Tuple[str, ...] = ("模拟室", "SIMULATION ROOM", "SIMULATION")
TEXT_SIM_START: Tuple[str, ...] = ("开始模拟", "开始")
TEXT_SIM_5C: Tuple[str, ...] = ("5-C", "5C", "难度5", "5-c")
TEXT_SIM_QUICK: Tuple[str, ...] = ("快速模拟", "快速")
TEXT_SIM_SKIP_BUFFS: Tuple[str, ...] = ("跳过增益效果选择", "跳过增益", "效果选择")
TEXT_SIM_END_MODAL: Tuple[str, ...] = ("模拟结束", "重置", "无法保存")
TEXT_SIM_COMPLETED: Tuple[str, ...] = ("不再显示", "已完成", "今日已完成")
TEXT_SIM_NOT_5C: Tuple[str, ...] = ("无法进行快速", "仅限5-C可以", "仅限5-C")

# Interception
TEXT_INTERCEPTION_TITLE: Tuple[str, ...] = ("拦截战", "INTERCEPTION")
TEXT_INTERCEPTION_ATTEMPTS: Tuple[str, ...] = ("剩余拦截次数", "剩余拦截", "拦截次数")
TEXT_INTERCEPTION_ANOMALY: Tuple[str, ...] = ("异常", "异常拦截")
TEXT_INTERCEPTION_BASIC: Tuple[str, ...] = ("特级", "特殊", "普通")
TEXT_INTERCEPTION_KRAKEN: Tuple[str, ...] = ("克拉肯", "kraken")
TEXT_INTERCEPTION_QUICK_BATTLE: Tuple[str, ...] = ("快速战斗", "快速")
TEXT_INTERCEPTION_ENTER_BATTLE: Tuple[str, ...] = ("进入战斗", "战斗")
TEXT_INTERCEPTION_CANNOT_QUICK: Tuple[str, ...] = ("每日至少游玩1次后", "每日至少", "游玩1次后", "至少游玩")
TEXT_INTERCEPTION_EXCEEDED: Tuple[str, ...] = ("已超出进入次数", "已超出", "剩余次数不足", "次数不足")
TEXT_BATTLE_AUTO: Tuple[str, ...] = ("AUTO", "auto")
TEXT_BATTLE_SETTLEMENT: Tuple[str, ...] = ("点击任意处", "点击继续", "胜利", "失败", "点击屏幕")

# Arena
TEXT_ARENA_TITLE: Tuple[str, ...] = ("竞技场", "ARENA")
TEXT_ARENA_ROOKIE: Tuple[str, ...] = ("新人竞技场", "新人")
TEXT_ARENA_SPECIAL: Tuple[str, ...] = ("特殊竞技场", "特殊")
TEXT_ARENA_ENTER_FIGHT: Tuple[str, ...] = ("进入战斗", "战斗")
TEXT_ARENA_AUTO_ON: Tuple[str, ...] = ("ON", "on")
TEXT_ARENA_AUTO_OFF: Tuple[str, ...] = ("OFF", "off")
TEXT_ARENA_COST_DIAMOND: Tuple[str, ...] = ("消耗资金", "币不足", "消耗珠宝", "购买入场券", "购买次数")
TEXT_ARENA_SEASON_CLOSED: Tuple[str, ...] = ("赛季已结束", "敬请期待", "下个赛季")
TEXT_ARENA_SPECIAL_CLAIM: Tuple[str, ...] = ("领取", "收获", "获得")
TEXT_ARENA_NEXT_STEP: Tuple[str, ...] = ("点击进行下一步", "点击进行", "点击任意处", "点击继续")
