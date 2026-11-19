"""Multi-dimensional scene and modal discriminator for NIKKE.

Provides deterministic predicates for identifying game states:
- Lobby / Home screen (is_in_home)
- Outpost Defense panel (is_in_outpost)
- Active blocking modals / dialogs (has_modal_active)
- Reward settlement and claim popups (has_reward_claim_modal)
- Outpost wipeout confirmation dialog (has_sweep_modal)
- Loading and transition states (is_loading)
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, List, Optional, Tuple, Union
import numpy as np

from core.vision.ocr_reread import ocr_with_reread
from games.nikke.constants import (
    ROI_HOME_BOTTOM_MENU,
    ROI_HOME_BOTTOM_LOBBY,
    ROI_HOME_BOTTOM_OUTPOST,
    ROI_HOME_OUTPOST_BTN,
    ROI_OUTPOST_TITLE,
    ROI_CLAIM_BTN,
    ROI_SWEEP_BTN,
    ROI_SWEEP_CONFIRM_BTN,
    ROI_SWEEP_FREE_TAG,
    ROI_GLOBAL_CLOSE,
    ROI_REWARD_CLAIM_TEXT,
    ROI_MODAL_CENTER,
    ROI_PASS_POPUP_CLOSE,
    ROI_MAIL_TITLE,
    ROI_MAIL_CLAIM_ALL_BTN,
    ROI_FRIEND_TITLE,
    ROI_FRIEND_SEND_RECEIVE_BTN,
    ROI_DISPATCH_TITLE,
    ROI_DISPATCH_ALL_BTN,
    ROI_SHOP_SIDEBAR,
    ROI_PAYSHOP_TITLE,
    TEXT_OUTPOST_TITLE,
    TEXT_CLAIM_REWARD,
    TEXT_SWEEP,
    TEXT_SWEEP_CONFIRM,
    TEXT_REWARD_MODAL,
    TEXT_HOME_TABS,
    TEXT_MAIL_TITLE,
    TEXT_MAIL_CLAIM_ALL,
    TEXT_FRIEND_TITLE,
    TEXT_FRIEND_SEND,
    TEXT_DISPATCH_TITLE,
    TEXT_DISPATCH_ALL,
    TEXT_SHOP_NORMAL,
    TEXT_SHOP_ARENA,
    TEXT_SHOP_BODY,
    TEXT_SHOP_SCRAP,
    TEXT_SHOP_PAYSHOP,
    LOADING_KEYWORDS,
)

logger = logging.getLogger("yes_nikke.scene")

# Common Chinese character variant mapping for OCR tolerance
CHINESE_CHAR_MAP = {
    "舉": "举", "殲": "歼", "滅": "灭", "防": "防", "禦": "御", "領": "领", "取": "取",
    "獎": "奖", "勵": "励", "點": "点", "擊": "击", "繼": "继", "續": "续",
    "確": "确", "認": "认", "關": "关", "閉": "闭", "畫": "画", "面": "面",
    "購": "购", "買": "买", "隊": "队", "廳": "厅", "紹": "绍", "哨": "哨",
    "現": "现", "在": "在", "無": "无", "珠": "珠", "寶": "宝", "費": "费",
    "獲": "获", "單": "单", "戰": "战", "鬥": "斗", "開": "开", "結": "结",
}


def normalize_text(text: str) -> str:
    """Normalize text by removing whitespace, converting lowercase, and folding variants."""
    flat = "".join(str(text or "").split()).lower()
    for src, dst in CHINESE_CHAR_MAP.items():
        flat = flat.replace(src, dst)
    return flat


def fuzzy_contains(needle: str, haystack: str) -> bool:
    """Check if normalized needle is a substring of normalized haystack."""
    norm_needle = normalize_text(needle)
    norm_haystack = normalize_text(haystack)
    if not norm_needle or not norm_haystack:
        return False
    return norm_needle in norm_haystack


class NikkeScene:
    """Scene discriminator providing high-confidence state identification for NIKKE."""

    def __init__(self, ctx: Any = None) -> None:
        self.ctx = ctx

    def _get_frame(self, frame: Optional[np.ndarray] = None) -> np.ndarray:
        """Obtain a 720p normalized frame from argument or context capture."""
        if frame is not None:
            return frame
        if self.ctx and hasattr(self.ctx, "capture") and self.ctx.capture is not None:
            ret = self.ctx.capture.get_latest_frame(normalize_720p=True)
            if ret is not None:
                return ret
        if self.ctx and hasattr(self.ctx, "latest_frame") and self.ctx.latest_frame is not None:
            return self.ctx.latest_frame
        # Return fallback blank canvas if nothing captured
        return np.zeros((720, 1280, 3), dtype=np.uint8)

    def _run_ocr(
        self,
        frame: np.ndarray,
        roi: Optional[Tuple[int, int, int, int]] = None,
        min_confidence: float = 0.70,
    ) -> List[str]:
        """Crop ROI and execute OCR engine with automatic reread."""
        if roi:
            rx, ry, rw, rh = roi
            h, w = frame.shape[:2]
            rx = max(0, min(rx, w - 1))
            ry = max(0, min(ry, h - 1))
            rw = max(1, min(rw, w - rx))
            rh = max(1, min(rh, h - ry))
            crop = frame[ry : ry + rh, rx : rx + rw]
        else:
            crop = frame

        ocr_engine = None
        if self.ctx is not None:
            if hasattr(self.ctx, "ocr_engine") and hasattr(self.ctx.ocr_engine, "ocr"):
                ocr_engine = self.ctx.ocr_engine.ocr
            elif hasattr(self.ctx, "vision") and hasattr(self.ctx.vision, "ocr"):
                ocr_engine = self.ctx.vision.ocr
            elif hasattr(self.ctx, "ocr_func") and callable(self.ctx.ocr_func):
                ocr_engine = self.ctx.ocr_func

        if ocr_engine is None:
            return []

        try:
            boxes = ocr_with_reread(ocr_func=ocr_engine, frame=crop, reread=True)
            return [b.text for b in boxes if b.confidence >= min_confidence]
        except Exception as exc:
            logger.debug(f"OCR run encountered error: {exc}")
            return []

    def check_text_in_roi(
        self,
        keywords: Union[str, Iterable[str]],
        roi: Tuple[int, int, int, int],
        frame: Optional[np.ndarray] = None,
        min_confidence: float = 0.70,
    ) -> bool:
        """Check if any keyword is present within the specified ROI."""
        curr_frame = self._get_frame(frame)
        detected_texts = self._run_ocr(curr_frame, roi=roi, min_confidence=min_confidence)
        if isinstance(keywords, str):
            keywords = [keywords]

        for text in detected_texts:
            for kw in keywords:
                if fuzzy_contains(kw, text):
                    return True
        return False

    def is_in_home(self, frame: Optional[np.ndarray] = None) -> bool:
        """Determine whether the current screen is the game Lobby / Home.

        Criteria:
        1. Context hook overrides (e.g. mock flag).
        2. Presence of lobby bottom navigation menu texts ("大厅", "前哨基地", "编队", "妮姬", "商城").
        3. Match on lobby bottom buttons or template icons.
        """
        if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
            return self.ctx.mock_scene_state == "home"

        curr_frame = self._get_frame(frame)

        # Fast OCR check on bottom menu
        for kw in ("大厅", "前哨基地", "编队", "妮姬", "商城"):
            if self.check_text_in_roi(kw, ROI_HOME_BOTTOM_MENU, frame=curr_frame):
                return True

        # Check template match for lobby home buttons if available
        if self.ctx and hasattr(self.ctx, "vision") and hasattr(self.ctx.vision, "match_template"):
            try:
                for tmpl_name in ("homebutton1.png", "homebutton2.png"):
                    if self.ctx.vision.match_template(curr_frame, tmpl_name):
                        return True
            except Exception:
                pass

        return False

    def is_in_outpost(self, frame: Optional[np.ndarray] = None) -> bool:
        """Determine whether the current screen is the Outpost Defense panel.

        Criteria:
        1. Context hook overrides.
        2. Presence of Outpost Title ("防御前哨基地", "前哨基地防御", "防御前哨").
        3. Presence of Defense action buttons ("获得奖励", "一举歼灭").
        """
        if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
            return self.ctx.mock_scene_state == "outpost"

        curr_frame = self._get_frame(frame)

        # Check Title Area
        if self.check_text_in_roi(TEXT_OUTPOST_TITLE, ROI_OUTPOST_TITLE, frame=curr_frame):
            return True

        # Check buttons in outpost defense panel
        has_claim = self.check_text_in_roi(TEXT_CLAIM_REWARD, ROI_CLAIM_BTN, frame=curr_frame)
        has_sweep = self.check_text_in_roi(TEXT_SWEEP, ROI_SWEEP_BTN, frame=curr_frame)
        if has_claim or has_sweep:
            return True

        return False

    def is_in_mail(self, frame: Optional[np.ndarray] = None) -> bool:
        """Determine whether current screen is the Mailbox dialog/window."""
        if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
            return self.ctx.mock_scene_state == "mail"

        curr_frame = self._get_frame(frame)
        if self.check_text_in_roi(TEXT_MAIL_TITLE, ROI_MAIL_TITLE, frame=curr_frame):
            return True
        if self.check_text_in_roi(TEXT_MAIL_CLAIM_ALL, ROI_MAIL_CLAIM_ALL_BTN, frame=curr_frame):
            return True
        return False

    def is_in_friends(self, frame: Optional[np.ndarray] = None) -> bool:
        """Determine whether current screen is the Friends dialog/window."""
        if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
            return self.ctx.mock_scene_state == "friends"

        curr_frame = self._get_frame(frame)
        if self.check_text_in_roi(TEXT_FRIEND_TITLE, ROI_FRIEND_TITLE, frame=curr_frame):
            return True
        if self.check_text_in_roi(TEXT_FRIEND_SEND, ROI_FRIEND_SEND_RECEIVE_BTN, frame=curr_frame):
            return True
        return False

    def is_in_dispatch(self, frame: Optional[np.ndarray] = None) -> bool:
        """Determine whether current screen is the Dispatch Bulletin Board."""
        if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
            return self.ctx.mock_scene_state == "dispatch"

        curr_frame = self._get_frame(frame)
        if self.check_text_in_roi(TEXT_DISPATCH_TITLE, ROI_DISPATCH_TITLE, frame=curr_frame):
            return True
        if self.check_text_in_roi(TEXT_DISPATCH_ALL, ROI_DISPATCH_ALL_BTN, frame=curr_frame):
            return True
        return False

    def is_in_shop(self, frame: Optional[np.ndarray] = None) -> bool:
        """Determine whether current screen is within the Game Shop (normal/arena/body/scrap)."""
        if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
            return self.ctx.mock_scene_state in ("shop", "normal_shop", "arena_shop", "body_shop", "scrap_shop")

        curr_frame = self._get_frame(frame)
        for kw in (TEXT_SHOP_NORMAL + TEXT_SHOP_ARENA + TEXT_SHOP_BODY + TEXT_SHOP_SCRAP):
            if self.check_text_in_roi(kw, ROI_SHOP_SIDEBAR, frame=curr_frame):
                return True
        return False

    def is_in_payshop(self, frame: Optional[np.ndarray] = None) -> bool:
        """Determine whether current screen is the Paid Shop (Cash Shop)."""
        if self.ctx and getattr(self.ctx, "mock_scene_state", None) is not None:
            return self.ctx.mock_scene_state == "payshop"

        curr_frame = self._get_frame(frame)
        if self.check_text_in_roi(TEXT_SHOP_PAYSHOP, ROI_PAYSHOP_TITLE, frame=curr_frame):
            return True
        return False

    def has_modal_active(self, frame: Optional[np.ndarray] = None) -> bool:
        """Detect any active blocking dialog, notice popup, or overlay on screen."""
        if self.ctx and getattr(self.ctx, "mock_modal_active", None) is not None:
            return bool(self.ctx.mock_modal_active)

        curr_frame = self._get_frame(frame)

        # Global close prompts
        if self.check_text_in_roi(
            ("点击任意区域关闭", "点击关闭画面", "点击任意处", "点击继续", "跳过", "关闭"),
            ROI_GLOBAL_CLOSE,
            frame=curr_frame,
        ):
            return True

        # Center modal buttons (Confirm / Cancel / OK)
        if self.check_text_in_roi(
            ("确认", "取消", "购买PASS", "今日不再显示", "立刻前往"),
            ROI_MODAL_CENTER,
            frame=curr_frame,
        ):
            return True

        return False

    def has_reward_claim_modal(self, frame: Optional[np.ndarray] = None) -> bool:
        """Detect whether a reward settlement or item drop modal is currently displayed."""
        if self.ctx and getattr(self.ctx, "mock_reward_modal", None) is not None:
            return bool(self.ctx.mock_reward_modal)

        curr_frame = self._get_frame(frame)

        # Reward settlement prompts
        if self.check_text_in_roi(TEXT_REWARD_MODAL, ROI_REWARD_CLAIM_TEXT, frame=curr_frame):
            return True

        if self.check_text_in_roi(
            ("点击任意区域关闭", "点击关闭画面", "点击继续", "领取奖励"),
            ROI_GLOBAL_CLOSE,
            frame=curr_frame,
        ):
            return True

        return False

    def has_sweep_modal(self, frame: Optional[np.ndarray] = None) -> bool:
        """Detect whether the Outpost Wipeout confirmation popup is visible."""
        if self.ctx and getattr(self.ctx, "mock_sweep_modal", None) is not None:
            return bool(self.ctx.mock_sweep_modal)

        curr_frame = self._get_frame(frame)

        # Sweep confirm button
        if self.check_text_in_roi(TEXT_SWEEP_CONFIRM, ROI_SWEEP_CONFIRM_BTN, frame=curr_frame):
            return True

        # Gem secondary confirmation
        if self.check_text_in_roi(
            ("是否消耗珠宝", "今日不再显示", "优先扣除免费珠宝", "免费珠宝不足"),
            ROI_MODAL_CENTER,
            frame=curr_frame,
        ):
            return True

        return False

    def is_loading(self, frame: Optional[np.ndarray] = None) -> bool:
        """Detect whether the game is currently in a loading or dark transition state."""
        if self.ctx and hasattr(self.ctx, "frozen_watch"):
            return getattr(self.ctx.frozen_watch, "is_loading", False)

        curr_frame = self._get_frame(frame)
        return self.check_text_in_roi(LOADING_KEYWORDS, (0, 0, 1280, 720), frame=curr_frame)


# =============================================================================
# Unified Scene Discriminator Registration & Module Exports
# =============================================================================
try:
    from games.nikke.scene_combat import (  # noqa: F401
        is_in_ark,
        is_in_sim_room,
        is_in_interception,
        is_in_arena,
    )
except ImportError:
    pass

try:
    from games.nikke.scene_growth import (  # noqa: F401
        is_in_inquiry,
        is_in_task_panel,
        is_in_tower,
    )
except ImportError:
    pass

__all__ = [
    "NikkeScene",
    "normalize_text",
    "fuzzy_contains",
    "is_in_ark",
    "is_in_sim_room",
    "is_in_interception",
    "is_in_arena",
    "is_in_inquiry",
    "is_in_task_panel",
    "is_in_tower",
]

