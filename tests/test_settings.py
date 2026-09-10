import pytest

from scorecap.settings import A4_HEIGHT_PT, A4_WIDTH_PT, MM_TO_PT, Settings


def test_defaults_describe_a4_content_box():
    s = Settings()
    assert s.content_x_pt == pytest.approx(12.0 * MM_TO_PT)
    assert s.content_top_pt == pytest.approx(12.0 * MM_TO_PT)
    assert s.content_width_pt == pytest.approx(A4_WIDTH_PT - 24.0 * MM_TO_PT)
    assert s.content_height_pt == pytest.approx(A4_HEIGHT_PT - 27.0 * MM_TO_PT)
    assert s.gap_min_pt == pytest.approx(4.0 * MM_TO_PT)


def test_content_box_shrinks_with_bigger_margins():
    s = Settings(margin_side_mm=20.0, margin_top_mm=20.0, margin_bottom_mm=20.0)
    assert s.content_width_pt == pytest.approx(A4_WIDTH_PT - 40.0 * MM_TO_PT)
    assert s.content_height_pt == pytest.approx(A4_HEIGHT_PT - 40.0 * MM_TO_PT)


def test_settings_are_immutable():
    s = Settings()
    with pytest.raises(Exception):
        s.shrink_min = 0.5
