"""Base task class for NIKKE automation workflows.

Inherits from BaseGameTask, providing:
- 1280x720 normalized frame capture pipeline.
- Four-dimensional template verification (Pixel, ZNCC, Gradient ZNCC, Canny Edge F1).
- Adaptive white-border reread text detection with fuzzy variant tolerance.
- Watchdog feeding and state synchronization.
"""

from __future__ import annotations

import logging
import os
from abc import ABC
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

import cv2
import numpy as np

from core.base_task import BaseGameTask
from core.vision.image_utils import (
    green_mask_from_template,
    template_match_response,
    independent_match_candidates,
    TemplateCandidate,
)
from games.nikke.interaction import NikkeInteraction
from games.nikke.recovery import NikkeRecovery
from games.nikke.scene import NikkeScene, normalize_text, fuzzy_contains

logger = logging.getLogger("yes_nikke.task.base")

# Base directory for template assets
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "assets" / "templates"


class NikkeTask(BaseGameTask, ABC):
    """Abstract base class for all NIKKE domain-specific tasks."""

    def __init__(self, ctx: Any = None, name: Optional[str] = None) -> None:
        super().__init__(ctx, name=name)
        self.interact: NikkeInteraction = getattr(ctx, "interaction", None) or NikkeInteraction(
            watchdog=getattr(ctx, "frozen_watch", None)
        )
        self.scene: NikkeScene = getattr(ctx, "scene", None) or NikkeScene(ctx)
        self.recovery: NikkeRecovery = getattr(ctx, "recovery", None) or NikkeRecovery(ctx)
        self.frozen_watch = getattr(ctx, "frozen_watch", None)
        self._template_cache: dict[str, Tuple[np.ndarray, Optional[np.ndarray]]] = {}

    def setup(self) -> None:
        """Initialize task watchdog and interaction context."""
        super().setup()
        if self.frozen_watch and hasattr(self.frozen_watch, "reset"):
            try:
                self.frozen_watch.reset()
            except Exception:
                pass

    def ping_watchdog(self, detected_text: str = "") -> None:
        """Feed watchdog with latest normalized frame and recognized screen text."""
        if self.frozen_watch and hasattr(self.frozen_watch, "update_frame"):
            try:
                frame = self.capture_720p()
                self.frozen_watch.update_frame(frame, detected_text=detected_text)
            except Exception as exc:
                # Re-raise FrozenScreen if watchdog fired
                if exc.__class__.__name__ == "FrozenScreen":
                    raise
                logger.debug(f"Watchdog ping error: {exc}")

    def load_template(self, template_name: str) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """Load template and its mask, supporting asset manager caching and disk loading."""
        if template_name in self._template_cache:
            return self._template_cache[template_name]

        # 1. Try ctx.asset_manager if present
        if self.ctx and hasattr(self.ctx, "asset_manager") and hasattr(self.ctx.asset_manager, "get_template"):
            try:
                tmpl, mask = self.ctx.asset_manager.get_template(template_name)
                self._template_cache[template_name] = (tmpl, mask)
                return tmpl, mask
            except Exception:
                pass

        # 2. Try loading from assets/templates/
        file_path = TEMPLATES_DIR / template_name
        if not file_path.exists():
            # Try appending .png if not present
            file_path = TEMPLATES_DIR / f"{template_name}.png"

        if file_path.exists():
            raw = cv2.imdecode(np.fromfile(str(file_path), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            if raw is not None:
                mask = None
                if raw.shape[-1] == 4:
                    mask = green_mask_from_template(raw)
                    tmpl = raw[:, :, :3]
                else:
                    tmpl = raw
                    mask = green_mask_from_template(tmpl)
                self._template_cache[template_name] = (tmpl, mask)
                return tmpl, mask

        # Fallback dummy template for offline / unit tests without assets on disk
        dummy = np.full((32, 32, 3), 128, dtype=np.uint8)
        return dummy, None

    def find_template_multidim(
        self,
        template_name: str,
        roi_720p: Optional[Tuple[int, int, int, int]] = None,
        min_zncc: float = 0.65,
        min_edge_f1: float = 0.50,
        frame: Optional[np.ndarray] = None,
    ) -> Optional[Tuple[int, int, int, int]]:
        """Four-dimensional template match with structural evidence gates.

        Returns (x, y, w, h) in 1280x720 baseline coordinates if matched, else None.
        """
        search_frame = frame if frame is not None else self.capture_720p()
        tmpl, mask = self.load_template(template_name)
        if tmpl is None or tmpl.size == 0:
            return None

        th, tw = tmpl.shape[:2]
        offset_x, offset_y = 0, 0
        search_region = search_frame

        if roi_720p:
            rx, ry, rw, rh = roi_720p
            h, w = search_frame.shape[:2]
            rx = max(0, min(rx, w - 1))
            ry = max(0, min(ry, h - 1))
            rw = max(1, min(rw, w - rx))
            rh = max(1, min(rh, h - ry))
            search_region = search_frame[ry : ry + rh, rx : rx + rw]
            offset_x, offset_y = rx, ry

        sh, sw = search_region.shape[:2]
        if sh < th or sw < tw:
            return None

        # Calculate normalized response map
        try:
            response = template_match_response(search_region, tmpl, mask=mask)
            candidates: Tuple[TemplateCandidate, ...] = independent_match_candidates(
                response=response,
                search=search_region,
                template=tmpl,
                mask=mask,
                template_threshold=0.55,
                max_matches=5,
            )

            for cand in candidates:
                if cand.zncc_score >= min_zncc and cand.edge_score >= min_edge_f1:
                    gx = cand.location[0] + offset_x
                    gy = cand.location[1] + offset_y
                    logger.debug(
                        f"[MultiDim] Hit '{template_name}' at ({gx}, {gy}, {tw}, {th}) "
                        f"ZNCC={cand.zncc_score:.3f}, EdgeF1={cand.edge_score:.3f}"
                    )
                    return (gx, gy, tw, th)

        except Exception as exc:
            logger.debug(f"[MultiDim] Error during template match '{template_name}': {exc}")

        return None

    def ocr_text_exists(
        self,
        keyword: Union[str, List[str], Tuple[str, ...]],
        roi_720p: Tuple[int, int, int, int],
        min_confidence: float = 0.70,
        frame: Optional[np.ndarray] = None,
    ) -> bool:
        """Check whether target keyword exists in ROI, using adaptive reread and fuzzy matching."""
        target_frame = frame if frame is not None else self.capture_720p()
        exists = self.scene.check_text_in_roi(
            keywords=keyword,
            roi=roi_720p,
            frame=target_frame,
            min_confidence=min_confidence,
        )
        # Notify watchdog with keyword context if true
        if exists:
            kw_str = keyword if isinstance(keyword, str) else "|".join(keyword)
            self.ping_watchdog(detected_text=kw_str)
        return exists

    def find_ocr_text_pos(
        self,
        keyword: Union[str, List[str], Tuple[str, ...]],
        roi_720p: Tuple[int, int, int, int],
        min_confidence: float = 0.70,
        frame: Optional[np.ndarray] = None,
    ) -> Optional[Tuple[int, int, int, int]]:
        """Locate bounding box of text matching keyword inside target ROI."""
        target_frame = frame if frame is not None else self.capture_720p()
        rx, ry, rw, rh = roi_720p
        h, w = target_frame.shape[:2]
        rx = max(0, min(rx, w - 1))
        ry = max(0, min(ry, h - 1))
        rw = max(1, min(rw, w - rx))
        rh = max(1, min(rh, h - ry))
        crop = target_frame[ry : ry + rh, rx : rx + rw]

        ocr_engine = None
        if self.ctx is not None:
            if hasattr(self.ctx, "ocr_engine") and hasattr(self.ctx.ocr_engine, "ocr"):
                ocr_engine = self.ctx.ocr_engine.ocr
            elif hasattr(self.ctx, "vision") and hasattr(self.ctx.vision, "ocr"):
                ocr_engine = self.ctx.vision.ocr
            elif hasattr(self.ctx, "ocr_func") and callable(self.ctx.ocr_func):
                ocr_engine = self.ctx.ocr_func

        if ocr_engine is None:
            return None

        keywords = [keyword] if isinstance(keyword, str) else list(keyword)
        boxes = self.ocr(frame=crop, name=f"find_pos_{keywords[0]}", reread=True)

        for b in boxes:
            if b.confidence < min_confidence:
                continue
            for kw in keywords:
                if fuzzy_contains(kw, b.text):
                    bx, by, bw, bh = b.box
                    return (rx + bx, ry + by, bw, bh)

        return None

    def click_ocr_text(
        self,
        keyword: Union[str, List[str], Tuple[str, ...]],
        roi_720p: Tuple[int, int, int, int],
        min_confidence: float = 0.70,
    ) -> bool:
        """Find text in ROI and perform a jittered click on its bounding box."""
        pos = self.find_ocr_text_pos(keyword, roi_720p, min_confidence=min_confidence)
        if pos is not None:
            self.interact.click_rect(pos)
            return True
        return False
