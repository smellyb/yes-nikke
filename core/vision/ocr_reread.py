"""Read a small text box again, bordered and enlarged, when it read nothing.

Extracted from YES-BD2 ``src/utils/ocr_reread.py``:
Small boxes (a title, a value, one button's label) are where OCR reads are commonly lost:
1. the box as given (unchanged: a box that reads keeps its result);
2. read nothing: the same box with a plain median border around it, because the
   text finder misses text that touches the image edge;
3. still nothing: enlarged 2x, then 3x, each with the median border.

Only small boxes (<= 1400x360) qualify. Bounding boxes detected on padded / scaled
images are inversely mapped back to the original box dimensions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import monotonic
from typing import Callable, Iterable, List, Optional, Tuple, Any, Sequence, Union

import cv2
import numpy as np

logger = logging.getLogger("yes_nikke.vision.ocr_reread")

# Boxes this size or smaller get the extra reads
REREAD_MAX_HEIGHT = 360
REREAD_MAX_WIDTH = 1400
# Enlargements after the bordered read at original size
REREAD_SCALES = (1.0, 2.0, 3.0)
# Border around the box: half its height, at least this many pixels
REREAD_MIN_BORDER = 12
# An enlarged image stays within this size cap
REREAD_MAX_SIDE = 2400
REREAD_COOLDOWN_SECONDS = 1.0

# Minimum confidence thresholds
REREAD_MIN_CONFIDENCE = 0.8
REREAD_LONE_DIGIT_CONFIDENCE = 0.9


@dataclass(frozen=True)
class RereadImage:
    image: np.ndarray
    scale: float
    border: int


def qualifies(image: Any) -> bool:
    """Check if a crop qualifies for reread (must be a small text box)."""
    shape = getattr(image, "shape", None)
    if shape is None or len(shape) < 2:
        return False
    height, width = int(shape[0]), int(shape[1])
    return 0 < height <= REREAD_MAX_HEIGHT and 0 < width <= REREAD_MAX_WIDTH


def _border_colour(image: np.ndarray) -> Union[int, list[int]]:
    """The box's own median colour, so the border adds no artificial edge of its own."""
    if image.ndim == 2:
        return int(np.median(image))
    channels = image.shape[2]
    return [int(val) for val in np.median(image.reshape(-1, channels), axis=0)]


def reread_images(
    image: np.ndarray,
    scales: Sequence[float] = REREAD_SCALES,
) -> Iterable[RereadImage]:
    """Generate bordered, enlarged versions of ``image`` to try, in order."""
    for scale in scales:
        height, width = image.shape[:2]
        if max(height, width) * scale > REREAD_MAX_SIDE:
            break
        target = image
        if scale != 1.0:
            target = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        border = max(REREAD_MIN_BORDER, target.shape[0] // 2)
        bordered = cv2.copyMakeBorder(
            target,
            border,
            border,
            border,
            border,
            cv2.BORDER_CONSTANT,
            value=_border_colour(target),
        )
        yield RereadImage(bordered, float(scale), border)


def _confidence(box: Any) -> float:
    """Extract and normalize confidence score in [0.0, 1.0]."""
    value = getattr(box, "confidence", None)
    if value is None:
        value = getattr(box, "score", None)
    if value is None and isinstance(box, dict):
        value = box.get("confidence", box.get("score", 1.0))
    if value is None:
        value = 1.0
    val_float = float(value)
    return val_float / 100.0 if val_float > 1.0 else val_float


def _box_text(box: Any) -> str:
    """Extract string text from a box item."""
    if hasattr(box, "name"):
        return str(getattr(box, "name") or "")
    if hasattr(box, "text"):
        return str(getattr(box, "text") or "")
    if isinstance(box, dict):
        return str(box.get("name", box.get("text", "")))
    return str(box)


def trusted(boxes: Iterable[Any]) -> list:
    """Filter reread boxes to retain high-confidence characters and filter stray marks."""
    kept = []
    for box in boxes:
        text = "".join(_box_text(box).split())
        confidence = _confidence(box)
        if not text or confidence < REREAD_MIN_CONFIDENCE:
            continue
        # Lone non-digit character rejected; lone digit requires higher threshold
        if len(text) == 1 and not (text.isdigit() and confidence >= REREAD_LONE_DIGIT_CONFIDENCE):
            continue
        kept.append(box)
    return kept


def _text(boxes: Iterable[Any]) -> str:
    """Concatenate text from all boxes."""
    return "".join("".join(_box_text(box).split()) for box in boxes)


def keeps_first_read(first: Iterable[Any], found: Iterable[Any]) -> bool:
    """False when ``found`` lost digits or text that the first read had."""
    words = _text(box for box in first if len(_text([box])) > 1)
    text = _text(found)
    digits = sum(ch.isdigit() for ch in words)
    return len(text) >= len(words) and sum(ch.isdigit() for ch in text) >= digits


def map_back(boxes: Iterable[Any], reread: RereadImage, width: int, height: int) -> list:
    """Inverse-map boxes found on a bordered/scaled reread image back onto the original box."""
    mapped = []
    for box in boxes:
        # Support object with .x, .y, .width, .height or dict
        is_obj = hasattr(box, "x") and hasattr(box, "y")
        bx = float(getattr(box, "x") if is_obj else box["x"])
        by = float(getattr(box, "y") if is_obj else box["y"])
        bw = float(getattr(box, "width") if is_obj else box["width"])
        bh = float(getattr(box, "height") if is_obj else box["height"])

        x = (bx - reread.border) / reread.scale
        y = (by - reread.border) / reread.scale
        right = x + bw / reread.scale
        bottom = y + bh / reread.scale

        x = max(0.0, x)
        y = max(0.0, y)
        right = min(float(width), right)
        bottom = min(float(height), bottom)

        new_x = int(round(x))
        new_y = int(round(y))
        new_w = max(1, int(round(right - x)))
        new_h = max(1, int(round(bottom - y)))

        if is_obj:
            box.x = new_x
            box.y = new_y
            box.width = new_w
            box.height = new_h
            mapped.append(box)
        else:
            mapped_box = dict(box)
            mapped_box["x"] = new_x
            mapped_box["y"] = new_y
            mapped_box["width"] = new_w
            mapped_box["height"] = new_h
            mapped.append(mapped_box)

    return mapped


def ocr_with_reread(
    ocr_func: Callable[..., list],
    frame: np.ndarray,
    name: str = "",
    cooldown_cache: Optional[dict[str, float]] = None,
    reread: bool = True,
    **kwargs: Any,
) -> list:
    """Run OCR on ``frame`` with automatic bordered and multi-scale reread if empty.

    Args:
        ocr_func: Callable accepting frame (and optionally kwargs) returning OCR box objects.
        frame: Target image crop.
        name: Name identifier for logging and cooldown management.
        cooldown_cache: Optional dict tracking last empty read timestamps.
        reread: Whether to enable adaptive reread (disable if already enlarged).
        **kwargs: Additional parameters forwarded to ocr_func.

    Returns:
        List of OCR box objects mapped to original frame coordinates.
    """
    first_boxes = ocr_func(frame=frame, **kwargs)
    if not reread or not qualifies(frame):
        return first_boxes

    # If first read produced trusted results, return directly
    if trusted(first_boxes):
        if cooldown_cache is not None and name in cooldown_cache:
            cooldown_cache.pop(name, None)
        return first_boxes

    # Cooldown check to prevent repeated reread attempts on genuinely empty areas
    now = monotonic()
    if cooldown_cache is not None:
        last_empty = cooldown_cache.get(name, -1e9)
        if now - last_empty < REREAD_COOLDOWN_SECONDS:
            return first_boxes

    orig_h, orig_w = frame.shape[:2]
    shorter_fallback = None

    for attempt in reread_images(frame):
        sub_kwargs = dict(kwargs)
        sub_kwargs["frame"] = attempt.image
        # If target_height is specified in kwargs, set to 0 for enlarged reads
        if "target_height" in sub_kwargs:
            sub_kwargs["target_height"] = 0

        attempt_boxes = ocr_func(**sub_kwargs)
        found = trusted(attempt_boxes)

        if found:
            if not keeps_first_read(first_boxes, found):
                # Sure read but lost some characters: keep as last resort
                if shorter_fallback is None:
                    shorter_fallback = (found, attempt)
            else:
                if cooldown_cache is not None:
                    cooldown_cache.pop(name, None)
                logger.info(
                    f"OCR '{name}': empty on initial read; successfully read after "
                    f"border padding & {attempt.scale:g}x scaling"
                )
                return map_back(found, attempt, orig_w, orig_h)

    if shorter_fallback is not None:
        if cooldown_cache is not None:
            cooldown_cache.pop(name, None)
        found, attempt = shorter_fallback
        logger.info(
            f"OCR '{name}': read with border & {attempt.scale:g}x scaling (shorter than initial)"
        )
        return map_back(found, attempt, orig_w, orig_h)

    if cooldown_cache is not None and name:
        cooldown_cache[name] = now

    return first_boxes
