"""Deterministic vision and template matching primitives extracted from YES-BD2.

Includes:
- Green mask extraction (RGB green-screen and RGBA alpha filtering)
- Multi-dimensional verification:
  - Zero-mean Normalized Cross-Correlation (masked_zncc)
  - Sobel Gradient ZNCC (gradient_zncc)
  - Canny Edge F1-Score consistency (edge_consistency)
- Temporal stabilization:
  - 6-frame rolling consensus window (stabilize_template_match)
  - Drift gate (<= 12px) and consecutive trailing hit verification (>= 3 frames)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from statistics import fmean, median
from typing import Optional, Tuple, List, Union

import cv2
import numpy as np


# Standard reference dimensions
HD_720_WIDTH = 1280
HD_720_HEIGHT = 720
FHD_1080_WIDTH = 1920
FHD_1080_HEIGHT = 1080


def green_mask_from_template(
    template: np.ndarray,
    tolerance: int = 0,
) -> np.ndarray:
    """Build the project green-screen mask (plus transparent alpha) for a crop.

    Returns a uint8 mask where 255 represents valid template pixels, and 0
    represents ignored green-screen or transparent pixels.
    """
    if template.ndim < 3:
        return np.full(template.shape[:2], 255, dtype=np.uint8)

    color = template[:, :, :3]
    tolerance = max(0, int(tolerance))
    # OpenCv BGR order: B=channel 0, G=channel 1, R=channel 2
    green_pixels = (
        (color[:, :, 0] <= tolerance)
        & (color[:, :, 1] >= 255 - tolerance)
        & (color[:, :, 2] <= tolerance)
    )
    if template.shape[2] >= 4:
        # Alpha channel == 0 (fully transparent)
        green_pixels |= template[:, :, 3] == 0

    return np.where(green_pixels, 0, 255).astype(np.uint8)


@dataclass(frozen=True)
class PixelValidMatch:
    """Highest template-score candidate that also passes pixel validation."""

    score: float
    pixel_score: float
    location: tuple[int, int]
    zncc_score: float = -1.0


@dataclass(frozen=True)
class TemplateCandidate:
    """A response peak with all structural evidence retained."""

    score: float
    pixel_score: float
    zncc_score: float
    gradient_zncc_score: float
    edge_score: float
    location: tuple[int, int]


@dataclass(frozen=True)
class StableMatchObservation:
    """One valid template hit within a temporal stabilization window."""

    sample_index: int
    center: tuple[int, int]
    score: float
    pixel_score: float


@dataclass(frozen=True)
class StableMatchConsensus:
    """A spatially stable cluster selected from multiple captured frames."""

    center: tuple[int, int]
    hit_count: int
    sample_count: int
    average_score: float
    average_pixel_score: float
    center_spread: float


# Temporal stabilization defaults
STABLE_MATCH_SAMPLE_INTERVAL = 0.1
STABLE_MATCH_WINDOW_SAMPLES = 6
STABLE_MATCH_MAX_SAMPLES = 14
STABLE_MATCH_MINIMUM_HITS = 3
STABLE_MATCH_TRAILING_HITS = 3
STABLE_MATCH_CLUSTER_RADIUS_REFERENCE = 24.0
STABLE_MATCH_MAXIMUM_SPREAD_REFERENCE = 12.0
MASKED_MIN_CONTRAST_RATIO = 0.1


def to_gray(image: np.ndarray) -> np.ndarray:
    """Return a gray image from gray, BGR, or BGRA input."""
    if image.ndim == 2:
        return image
    if image.ndim != 3 or image.shape[2] not in {3, 4}:
        raise ValueError(f"Unsupported image shape for grayscale conversion: {image.shape}")
    conversion = cv2.COLOR_BGRA2GRAY if image.shape[2] == 4 else cv2.COLOR_BGR2GRAY
    return cv2.cvtColor(image, conversion)


def pixel_similarity(
    region: np.ndarray,
    template: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> float:
    """Return normalized absolute-difference similarity [0.0, 1.0], optionally under a mask."""
    if region.shape != template.shape:
        return -1.0
    difference = np.abs(region.astype(np.float32) - template.astype(np.float32))
    if mask is not None:
        active = mask > 0
        if not np.any(active):
            return -1.0
        difference = difference[active]
    return float(1.0 - np.mean(difference) / 255.0)


def masked_zncc(
    region: np.ndarray,
    template: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> float:
    """Return zero-mean normalized correlation (ZNCC) under an optional binary mask.

    Returns a score in [-1.0, 1.0]. Robust against ambient brightness offsets.
    """
    if region.shape != template.shape:
        return -1.0

    region_values = region.astype(np.float64, copy=False)
    template_values = template.astype(np.float64, copy=False)

    if mask is not None:
        if mask.shape != region.shape[:2] and mask.shape != region.shape:
            return -1.0
        active = mask > 0
        if np.count_nonzero(active) < 2:
            return -1.0
        # If image is multi-channel, broadcast active mask
        if region.ndim == 3 and active.ndim == 2:
            active = np.repeat(active[:, :, np.newaxis], region.shape[2], axis=2)
        region_values = region_values[active]
        template_values = template_values[active]
    else:
        region_values = region_values.reshape(-1)
        template_values = template_values.reshape(-1)
        if region_values.size < 2:
            return -1.0

    region_centered = region_values - np.mean(region_values)
    template_centered = template_values - np.mean(template_values)

    norm_region = np.linalg.norm(region_centered)
    norm_template = np.linalg.norm(template_centered)
    denominator = float(norm_region * norm_template)

    if not np.isfinite(denominator) or denominator <= np.finfo(np.float64).eps:
        return -1.0

    score = float(np.dot(region_centered, template_centered) / denominator)
    if not np.isfinite(score):
        return -1.0
    return float(np.clip(score, -1.0, 1.0))


def _gradient_magnitude(image: np.ndarray) -> np.ndarray:
    """Compute local gradient magnitude using 3x3 Sobel filters."""
    gray = to_gray(image).astype(np.float32, copy=False)
    gradient_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(gradient_x, gradient_y)


def gradient_zncc(
    region: np.ndarray,
    template: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> float:
    """Compare local edge strength via Sobel gradient magnitude while ignoring absolute brightness."""
    if region.shape != template.shape:
        return -1.0
    region_gradient = _gradient_magnitude(region)
    template_gradient = _gradient_magnitude(template)
    grad_mask = mask
    if mask is not None and mask.ndim == 3:
        grad_mask = to_gray(mask)
    return masked_zncc(region_gradient, template_gradient, grad_mask)


def edge_consistency(
    region: np.ndarray,
    template: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> float:
    """Return a tolerant F1 score [0.0, 1.0] for binary Canny edge maps.

    Allows 1-pixel anti-aliasing / displacement tolerance using 3x3 dilation.
    """
    if region.shape != template.shape:
        return -1.0

    region_gray = to_gray(region)
    template_gray = to_gray(template)

    region_edges = cv2.Canny(region_gray, 40, 120) > 0
    template_edges = cv2.Canny(template_gray, 40, 120) > 0

    if mask is not None:
        active = (mask > 0)
        if active.ndim == 3:
            active = active[:, :, 0]
        if active.shape != region_edges.shape:
            return -1.0
        region_edges &= active
        template_edges &= active

    template_count = int(np.count_nonzero(template_edges))
    region_count = int(np.count_nonzero(region_edges))
    if template_count == 0 or region_count == 0:
        return 0.0

    # 1px dilation tolerance prevents harsh penalization from subpixel rendering
    kernel = np.ones((3, 3), dtype=np.uint8)
    region_dilated = cv2.dilate(region_edges.astype(np.uint8), kernel) > 0
    template_dilated = cv2.dilate(template_edges.astype(np.uint8), kernel) > 0

    true_positive = min(
        int(np.count_nonzero(template_edges & region_dilated)),
        int(np.count_nonzero(region_edges & template_dilated)),
    )
    precision = true_positive / max(1, region_count)
    recall = true_positive / max(1, template_count)

    if precision + recall <= 0:
        return 0.0
    return float(2.0 * precision * recall / (precision + recall))


def template_candidate_evidence(
    region: np.ndarray,
    template: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> tuple[float, float, float, float]:
    """Return pixel similarity, raw ZNCC, gradient ZNCC, and edge consistency evidence."""
    return (
        pixel_similarity(region, template, mask),
        masked_zncc(region, template, mask),
        gradient_zncc(region, template, mask),
        edge_consistency(region, template, mask),
    )


def sanitize_template_response(response: np.ndarray) -> np.ndarray:
    """Reject non-finite and mathematically invalid normalized scores in place."""
    np.nan_to_num(response, copy=False, nan=-1.0, posinf=-1.0, neginf=-1.0)
    response[(response < -1.000001) | (response > 1.000001)] = -1.0
    return response


def template_match_response(
    search: np.ndarray,
    template: np.ndarray,
    mask: Optional[np.ndarray] = None,
    *,
    zero_mean: bool = False,
) -> np.ndarray:
    """Run normalized template matching and return sanitized response map."""
    if zero_mean or mask is None:
        method = cv2.TM_CCOEFF_NORMED
    else:
        method = cv2.TM_CCORR_NORMED
    response = cv2.matchTemplate(search, template, method, mask=mask)
    return sanitize_template_response(response)


def correlation_response(search: np.ndarray, template: np.ndarray) -> np.ndarray:
    """Plain TM_CCORR_NORMED without mask (no mean removal), sanitized."""
    response = cv2.matchTemplate(search, template, cv2.TM_CCORR_NORMED)
    return sanitize_template_response(response)


def masked_contrast_ratio(
    region: np.ndarray,
    template: np.ndarray,
    mask: Optional[np.ndarray],
) -> float:
    """Ratio of standard deviation of region over template inside mask."""
    if region.shape != template.shape:
        return 0.0
    if mask is not None:
        active = (mask > 0)
        if active.ndim == 2 and region.ndim == 3:
            active = np.repeat(active[:, :, np.newaxis], region.shape[2], axis=2)
    else:
        active = np.ones(region.shape, dtype=bool)

    if not np.any(active):
        return 0.0

    template_spread = float(template[active].astype(np.float32).std())
    if template_spread <= 1e-6:
        return 1.0
    return float(region[active].astype(np.float32).std()) / template_spread


def independent_pixel_valid_matches(
    response: np.ndarray,
    search: np.ndarray,
    template: np.ndarray,
    mask: Optional[np.ndarray],
    *,
    template_threshold: float,
    pixel_threshold: float,
    zncc_threshold: Optional[float] = None,
    center_bounds: Optional[tuple[int, int, int, int]] = None,
    suppression_radius: Optional[Union[int, tuple[int, int]]] = None,
    max_matches: int = 60,
    max_independent_candidates: int = 4096,
) -> tuple[PixelValidMatch, ...]:
    """Enumerate independent dual-valid candidates in template-score order."""
    if response.ndim != 2 or response.size == 0:
        return ()

    sanitize_template_response(response)
    working = response.copy()
    height, width = template.shape[:2]

    if center_bounds is not None:
        center_left, center_top, center_right, center_bottom = center_bounds
        x_start = max(0, int(np.ceil(center_left - width / 2)))
        y_start = max(0, int(np.ceil(center_top - height / 2)))
        x_stop = min(working.shape[1], int(np.ceil(center_right - width / 2)))
        y_stop = min(working.shape[0], int(np.ceil(center_bottom - height / 2)))
        if x_start >= x_stop or y_start >= y_stop:
            return ()
        allowed = np.full(working.shape, -1.0, dtype=working.dtype)
        allowed[y_start:y_stop, x_start:x_stop] = working[y_start:y_stop, x_start:x_stop]
        working = allowed

    if suppression_radius is None:
        suppression_x = max(2, width // 2)
        suppression_y = max(2, height // 2)
    elif isinstance(suppression_radius, tuple):
        suppression_x = max(1, int(suppression_radius[0]))
        suppression_y = max(1, int(suppression_radius[1]))
    else:
        suppression_x = suppression_y = max(1, int(suppression_radius))

    matches: list[PixelValidMatch] = []
    for _ in range(max(1, int(max_independent_candidates))):
        _min_val, score, _min_loc, location = cv2.minMaxLoc(working)
        if not np.isfinite(score) or score < template_threshold or score > 1.000001:
            break

        x, y = int(location[0]), int(location[1])
        region = search[y : y + height, x : x + width]
        candidate_pixel_score = pixel_similarity(region, template, mask)
        candidate_zncc_score = (
            masked_zncc(region, template, mask)
            if zncc_threshold is not None
            else -1.0
        )
        blank = (
            mask is not None
            and masked_contrast_ratio(region, template, mask) < MASKED_MIN_CONTRAST_RATIO
        )
        if not blank and candidate_pixel_score >= pixel_threshold and (
            zncc_threshold is None or candidate_zncc_score >= zncc_threshold
        ):
            matches.append(
                PixelValidMatch(
                    score=float(score),
                    pixel_score=float(candidate_pixel_score),
                    location=(x, y),
                    zncc_score=float(candidate_zncc_score),
                )
            )
            if len(matches) >= max(1, int(max_matches)):
                break

        left = max(0, x - suppression_x)
        top = max(0, y - suppression_y)
        right = min(working.shape[1], x + suppression_x + 1)
        bottom = min(working.shape[0], y + suppression_y + 1)
        working[top:bottom, left:right] = -1.0

    return tuple(matches)


def best_pixel_valid_match(
    response: np.ndarray,
    search: np.ndarray,
    template: np.ndarray,
    mask: Optional[np.ndarray],
    *,
    template_threshold: float,
    pixel_threshold: float,
    zncc_threshold: Optional[float] = None,
    center_bounds: Optional[tuple[int, int, int, int]] = None,
    max_independent_candidates: int = 128,
) -> Optional[PixelValidMatch]:
    """Return the best independent peak that passes template and pixel gates."""
    matches = independent_pixel_valid_matches(
        response,
        search,
        template,
        mask,
        template_threshold=template_threshold,
        pixel_threshold=pixel_threshold,
        zncc_threshold=zncc_threshold,
        center_bounds=center_bounds,
        max_matches=1,
        max_independent_candidates=max_independent_candidates,
    )
    return matches[0] if matches else None


def independent_match_candidates(
    response: np.ndarray,
    search: np.ndarray,
    template: np.ndarray,
    mask: Optional[np.ndarray],
    *,
    template_threshold: float = -1.0,
    center_bounds: Optional[tuple[int, int, int, int]] = None,
    suppression_radius: Optional[Union[int, tuple[int, int]]] = None,
    max_matches: int = 60,
    max_independent_candidates: int = 4096,
) -> tuple[TemplateCandidate, ...]:
    """Enumerate response peaks retaining full structural evidence."""
    if response.ndim != 2 or response.size == 0:
        return ()

    sanitize_template_response(response)
    working = response.copy()
    height, width = template.shape[:2]

    if center_bounds is not None:
        center_left, center_top, center_right, center_bottom = center_bounds
        x_start = max(0, int(np.ceil(center_left - width / 2)))
        y_start = max(0, int(np.ceil(center_top - height / 2)))
        x_stop = min(working.shape[1], int(np.ceil(center_right - width / 2)))
        y_stop = min(working.shape[0], int(np.ceil(center_bottom - height / 2)))
        if x_start >= x_stop or y_start >= y_stop:
            return ()
        allowed = np.full(working.shape, -1.0, dtype=working.dtype)
        allowed[y_start:y_stop, x_start:x_stop] = working[y_start:y_stop, x_start:x_stop]
        working = allowed

    if suppression_radius is None:
        suppression_x = max(2, width // 2)
        suppression_y = max(2, height // 2)
    elif isinstance(suppression_radius, tuple):
        suppression_x = max(1, int(suppression_radius[0]))
        suppression_y = max(1, int(suppression_radius[1]))
    else:
        suppression_x = suppression_y = max(1, int(suppression_radius))

    matches: list[TemplateCandidate] = []
    for _ in range(max(1, int(max_independent_candidates))):
        _min_val, score, _min_loc, location = cv2.minMaxLoc(working)
        if not np.isfinite(score) or score < template_threshold or score > 1.000001:
            break
        x, y = int(location[0]), int(location[1])
        region = search[y : y + height, x : x + width]
        if region.shape != template.shape:
            break
        pixel_score, zncc_score, grad_score, edge_score = template_candidate_evidence(
            region,
            template,
            mask,
        )
        matches.append(
            TemplateCandidate(
                score=float(score),
                pixel_score=float(pixel_score),
                zncc_score=float(zncc_score),
                gradient_zncc_score=float(grad_score),
                edge_score=float(edge_score),
                location=(x, y),
            )
        )
        if len(matches) >= max(1, int(max_matches)):
            break
        left = max(0, x - suppression_x)
        top = max(0, y - suppression_y)
        right = min(working.shape[1], x + suppression_x + 1)
        bottom = min(working.shape[0], y + suppression_y + 1)
        working[top:bottom, left:right] = -1.0

    return tuple(matches)


# --- Temporal Stabilization Window ---

def stable_match_consensus(
    observations: Iterable[StableMatchObservation],
    *,
    sample_count: int,
    cluster_radius: float = STABLE_MATCH_CLUSTER_RADIUS_REFERENCE,
    maximum_center_spread: float = STABLE_MATCH_MAXIMUM_SPREAD_REFERENCE,
    minimum_hits: int = STABLE_MATCH_MINIMUM_HITS,
    required_trailing_hits: int = STABLE_MATCH_TRAILING_HITS,
) -> Optional[StableMatchConsensus]:
    """Select a persistent, high-confidence and spatially stable match cluster.

    Enforces:
    - Minimum hit count in the window
    - Consecutive trailing hits in the latest frames
    - Spatial drift / spread <= maximum_center_spread (<= 12px)
    """
    total_samples = max(0, int(sample_count))
    values = tuple(observations)
    if total_samples <= 0 or not values:
        return None

    clusters: list[list[StableMatchObservation]] = []
    for observation in sorted(values, key=lambda val: val.sample_index):
        nearest = None
        nearest_distance = float("inf")
        for cluster in clusters:
            center_x = float(median(val.center[0] for val in cluster))
            center_y = float(median(val.center[1] for val in cluster))
            distance = max(
                abs(observation.center[0] - center_x),
                abs(observation.center[1] - center_y),
            )
            if distance <= cluster_radius and distance < nearest_distance:
                nearest = cluster
                nearest_distance = distance
        if nearest is None:
            clusters.append([observation])
        else:
            nearest.append(observation)

    trailing_start = max(0, total_samples - max(0, int(required_trailing_hits)))
    required_indexes = set(range(trailing_start, total_samples))
    candidates: list[tuple[tuple[float, ...], StableMatchConsensus]] = []

    for cluster in clusters:
        if len(cluster) < max(1, int(minimum_hits)):
            continue
        indexes = {val.sample_index for val in cluster}
        if not required_indexes.issubset(indexes):
            continue

        center_x = float(median(val.center[0] for val in cluster))
        center_y = float(median(val.center[1] for val in cluster))
        spread = max(
            max(abs(val.center[0] - center_x), abs(val.center[1] - center_y))
            for val in cluster
        )
        if spread > maximum_center_spread:
            continue

        average_score = fmean(val.score for val in cluster)
        pixel_scores = [val.pixel_score for val in cluster if val.pixel_score >= 0]
        average_pixel = fmean(pixel_scores) if pixel_scores else average_score

        consensus = StableMatchConsensus(
            center=(round(center_x), round(center_y)),
            hit_count=len(cluster),
            sample_count=total_samples,
            average_score=average_score,
            average_pixel_score=average_pixel,
            center_spread=float(spread),
        )
        candidates.append(
            (
                (
                    float(consensus.hit_count),
                    (average_score + average_pixel) / 2.0,
                    -consensus.center_spread,
                ),
                consensus,
            )
        )

    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def stabilize_template_match(
    initial_match: object,
    initial_frame_shape: tuple[int, ...],
    *,
    sample_match: Callable[[], tuple[object, tuple[int, ...]]],
    passes: Callable[[object], bool],
    sleep: Callable[[float], None],
    on_sample: Optional[Callable[[object], None]] = None,
    sample_interval: float = STABLE_MATCH_SAMPLE_INTERVAL,
    window_samples: int = STABLE_MATCH_WINDOW_SAMPLES,
    maximum_samples: int = STABLE_MATCH_MAX_SAMPLES,
    minimum_hits: int = STABLE_MATCH_MINIMUM_HITS,
    required_trailing_hits: int = STABLE_MATCH_TRAILING_HITS,
    cluster_radius: float = STABLE_MATCH_CLUSTER_RADIUS_REFERENCE,
    maximum_center_spread: float = STABLE_MATCH_MAXIMUM_SPREAD_REFERENCE,
) -> Optional[tuple[StableMatchConsensus, tuple[int, ...]]]:
    """Observe candidate matches over a temporal window (default 6 frames) until consensus is reached."""
    wanted_window = max(2, int(window_samples))
    wanted_maximum = max(wanted_window, int(maximum_samples))
    samples: list[Optional[tuple[object, tuple[int, ...]]]] = [
        (initial_match, initial_frame_shape)
    ]
    last_shape = initial_frame_shape
    if on_sample is not None:
        on_sample(initial_match)

    for _sample_index in range(1, wanted_maximum):
        sleep(max(0.0, float(sample_interval)))
        result, frame_shape = sample_match()
        last_shape = frame_shape
        if on_sample is not None:
            on_sample(result)

        samples.append((result, frame_shape) if passes(result) else None)
        if len(samples) < wanted_window:
            continue

        window = samples[-wanted_window:]
        observations: list[StableMatchObservation] = []
        for index, item in enumerate(window):
            if item is None:
                continue
            match, _shape = item
            # Support .center or (.position + .size / 2)
            if hasattr(match, "center"):
                center = getattr(match, "center")
            elif hasattr(match, "position") and hasattr(match, "size"):
                center = (
                    int(match.position[0] + match.size[0] // 2),
                    int(match.position[1] + match.size[1] // 2),
                )
            elif hasattr(match, "location"):
                center = (int(match.location[0]), int(match.location[1]))
            else:
                continue

            score = float(getattr(match, "score", 1.0))
            pixel_score = float(getattr(match, "pixel_score", -1.0))
            observations.append(
                StableMatchObservation(
                    sample_index=index,
                    center=center,
                    score=score,
                    pixel_score=pixel_score,
                )
            )

        frame_height, frame_width = last_shape[:2]
        client_scale = min(frame_width / HD_720_WIDTH, frame_height / HD_720_HEIGHT) if (frame_width and frame_height) else 1.0

        consensus = stable_match_consensus(
            observations,
            sample_count=len(window),
            cluster_radius=max(2.0, cluster_radius * client_scale),
            maximum_center_spread=max(1.0, maximum_center_spread * client_scale),
            minimum_hits=min(minimum_hits, wanted_window),
            required_trailing_hits=min(required_trailing_hits, wanted_window),
        )
        if consensus is not None:
            return consensus, last_shape

    return None


# --- Coordinate & Scaling Utilities ---

def candidate_scales(
    base_scale: float,
    scale_ratios: Iterable[float] = (1.0,),
    minimum: float = 0.2,
) -> list[float]:
    """Build stable template scales from a base scale."""
    lower_bound = max(0.001, float(minimum))
    return [round(max(lower_bound, float(base_scale) * float(ratio)), 3) for ratio in scale_ratios]


def resize_template(template: np.ndarray, scale: float) -> np.ndarray:
    """Resize a template with interpolation suited to shrinking or enlarging."""
    if abs(float(scale) - 1.0) < 0.001:
        return template
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    return cv2.resize(template, None, fx=scale, fy=scale, interpolation=interpolation)


def resize_mask(mask: Optional[np.ndarray], scale: float) -> Optional[np.ndarray]:
    """Resize a template mask using nearest neighbor to preserve binary values."""
    if mask is None or abs(float(scale) - 1.0) < 0.001:
        return mask
    return cv2.resize(mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)


def crop_relative(
    image: np.ndarray,
    bounds: tuple[float, float, float, float],
) -> np.ndarray:
    """Crop fractional left/top/right/bottom bounds from an image."""
    _left, _top, crop = relative_roi_frame(image, bounds)
    return crop


def relative_roi_frame(
    image: np.ndarray,
    bounds: tuple[float, float, float, float],
) -> tuple[int, int, np.ndarray]:
    """Return a clamped relative ROI and its full-frame top-left offset."""
    height, width = image.shape[:2]
    left = max(0, min(width, round(width * bounds[0])))
    top = max(0, min(height, round(height * bounds[1])))
    right = max(left, min(width, round(width * bounds[2])))
    bottom = max(top, min(height, round(height * bounds[3])))
    return left, top, image[top:bottom, left:right]


def scale_reference_roi(
    roi: tuple[int, int, int, int],
    target_size: tuple[int, int],
    reference_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    """Scale and clamp a reference x/y/width/height ROI to a target frame."""
    target_width, target_height = target_size
    reference_width, reference_height = reference_size
    if target_width < 0 or target_height < 0:
        raise ValueError("Target dimensions cannot be negative.")
    if reference_width <= 0 or reference_height <= 0:
        raise ValueError("Reference dimensions must be positive.")

    x, y, roi_width, roi_height = roi
    left = max(0, min(target_width, round(x * target_width / reference_width)))
    top = max(0, min(target_height, round(y * target_height / reference_height)))
    right = max(
        left,
        min(target_width, round((x + roi_width) * target_width / reference_width)),
    )
    bottom = max(
        top,
        min(target_height, round((y + roi_height) * target_height / reference_height)),
    )
    return left, top, right - left, bottom - top


def reference_roi_frame(
    image: np.ndarray,
    roi: Optional[tuple[int, int, int, int]],
    reference_size: tuple[int, int],
) -> tuple[int, int, np.ndarray]:
    """Scale an x/y/width/height reference ROI with its position and size."""
    if roi is None:
        return 0, 0, image

    height, width = image.shape[:2]
    left, top, roi_width, roi_height = scale_reference_roi(
        roi,
        (width, height),
        reference_size,
    )
    right = left + roi_width
    bottom = top + roi_height
    return left, top, image[top:bottom, left:right]
