"""Pure pagination: image sizes in, page rectangles in PDF points out."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .settings import Settings


@dataclass(frozen=True)
class Placement:
    index: int
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class Page:
    placements: tuple[Placement, ...]
    scale: float


def effective_dpi(size: tuple[int, int], settings: Settings) -> float:
    """Pixels per inch the image ends up with when printed at content width."""
    width_px, _ = size
    return width_px / (settings.content_width_pt / 72.0)


def _required_scale(heights: Sequence[float], content_height: float, gap: float) -> float:
    """Uniform factor needed to fit these full-width heights onto one page."""
    gaps = gap * (len(heights) - 1)
    images = sum(heights)
    if images + gaps <= content_height:
        return 1.0
    available = content_height - gaps
    if available <= 0.0 or images <= 0.0:
        return 0.0
    return available / images


def _group(heights: Sequence[float], settings: Settings) -> list[tuple[list[int], float]]:
    """Greedily assign image indexes to pages, together with each page's scale."""
    content_height = settings.content_height_pt
    gap = settings.gap_min_pt
    groups: list[tuple[list[int], float]] = []
    index = 0
    while index < len(heights):
        members = [index]
        # A lone image always goes on its page, even if that needs a scale
        # below shrink_min - otherwise pagination could not advance.
        scale = _required_scale([heights[index]], content_height, gap)
        probe = index + 1
        while probe < len(heights):
            candidate = [heights[i] for i in (*members, probe)]
            candidate_scale = _required_scale(candidate, content_height, gap)
            if candidate_scale < settings.shrink_min:
                break
            members.append(probe)
            scale = candidate_scale
            probe += 1
        groups.append((members, scale))
        index = probe
    return groups


def paginate(sizes: Sequence[tuple[int, int]], settings: Settings) -> list[Page]:
    content_width = settings.content_width_pt
    content_height = settings.content_height_pt
    gap_min = settings.gap_min_pt
    heights = [content_width * h / w for w, h in sizes]
    groups = _group(heights, settings)

    pages: list[Page] = []
    for position, (members, scale) in enumerate(groups):
        is_last = position == len(groups) - 1
        scaled = [heights[i] * scale for i in members]
        gap = gap_min
        if not is_last and len(members) > 1:
            slack = content_height - sum(scaled)
            gap = min(
                max(slack / (len(members) - 1), gap_min),
                gap_min * settings.gap_max_factor,
            )
        width = content_width * scale
        x = settings.content_x_pt + (content_width - width) / 2.0
        y = settings.content_top_pt
        placements: list[Placement] = []
        for member, height in zip(members, scaled):
            placements.append(Placement(index=member, x=x, y=y, w=width, h=height))
            y += height + gap
        pages.append(Page(placements=tuple(placements), scale=scale))
    return pages
