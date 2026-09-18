"""Page geometry and user-configurable layout parameters."""

from __future__ import annotations

from dataclasses import dataclass

MM_TO_PT = 72.0 / 25.4
A4_WIDTH_PT = 595.276
A4_HEIGHT_PT = 841.890


@dataclass(frozen=True)
class Settings:
    margin_side_mm: float = 12.0
    margin_top_mm: float = 12.0
    margin_bottom_mm: float = 15.0
    gap_min_mm: float = 4.0
    gap_max_factor: float = 3.0
    shrink_min: float = 0.85
    footer_enabled: bool = True
    min_dpi: float = 120.0
    auto_trim: bool = True
    align_staff_ends: bool = True
    trim_threshold: int = 245
    trim_padding_px: int = 2
    hotkey: str = "Ctrl+Shift+S"

    @property
    def content_x_pt(self) -> float:
        return self.margin_side_mm * MM_TO_PT

    @property
    def content_top_pt(self) -> float:
        return self.margin_top_mm * MM_TO_PT

    @property
    def content_width_pt(self) -> float:
        return A4_WIDTH_PT - 2.0 * self.margin_side_mm * MM_TO_PT

    @property
    def content_height_pt(self) -> float:
        return A4_HEIGHT_PT - (self.margin_top_mm + self.margin_bottom_mm) * MM_TO_PT

    @property
    def gap_min_pt(self) -> float:
        return self.gap_min_mm * MM_TO_PT
