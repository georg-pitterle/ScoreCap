import pytest

from scorecap.layout import Page, effective_dpi, paginate
from scorecap.settings import Settings

SETTINGS = Settings()


def total_height(page: Page) -> float:
    return sum(p.h for p in page.placements)


def test_single_image_sits_in_top_left_of_content_box():
    pages = paginate([(1000, 500)], SETTINGS)
    assert len(pages) == 1
    (placement,) = pages[0].placements
    assert placement.index == 0
    assert placement.x == pytest.approx(SETTINGS.content_x_pt)
    assert placement.y == pytest.approx(SETTINGS.content_top_pt)
    assert placement.w == pytest.approx(SETTINGS.content_width_pt)
    assert placement.h == pytest.approx(SETTINGS.content_width_pt / 2)
    assert pages[0].scale == pytest.approx(1.0)


def test_empty_input_yields_no_pages():
    assert paginate([], SETTINGS) == []


def test_aspect_ratio_is_preserved():
    pages = paginate([(800, 200)], SETTINGS)
    (placement,) = pages[0].placements
    assert placement.w / placement.h == pytest.approx(4.0)


def test_shrinking_packs_one_more_image_onto_the_page():
    height = (SETTINGS.content_height_pt * 1.04 - 3 * SETTINGS.gap_min_pt) / 4
    size = (1000, round(1000 * height / SETTINGS.content_width_pt))
    pages = paginate([size] * 4, SETTINGS)
    assert len(pages) == 1
    assert SETTINGS.shrink_min <= pages[0].scale < 1.0


def test_shrink_limit_forces_a_new_page():
    height = SETTINGS.content_height_pt * 0.75
    size = (1000, round(1000 * height / SETTINGS.content_width_pt))
    pages = paginate([size] * 2, SETTINGS)
    assert len(pages) == 2
    assert all(page.scale == pytest.approx(1.0) for page in pages)


def test_oversized_single_image_is_scaled_below_the_limit():
    height = SETTINGS.content_height_pt * 2.0
    size = (1000, round(1000 * height / SETTINGS.content_width_pt))
    pages = paginate([size], SETTINGS)
    assert len(pages) == 1
    assert pages[0].scale < SETTINGS.shrink_min
    assert total_height(pages[0]) <= SETTINGS.content_height_pt + 0.01


def test_last_page_is_top_aligned_with_minimum_gap():
    size = (1000, 200)
    pages = paginate([size, size], SETTINGS)
    assert len(pages) == 1
    first, second = pages[0].placements
    assert second.y - (first.y + first.h) == pytest.approx(SETTINGS.gap_min_pt)


def test_full_pages_are_justified_with_a_capped_gap():
    size = (1000, 150)
    pages = paginate([size] * 10, SETTINGS)
    assert len(pages) >= 2
    first_page = pages[0]
    gaps = [
        b.y - (a.y + a.h)
        for a, b in zip(first_page.placements, first_page.placements[1:])
    ]
    assert gaps
    assert all(g >= SETTINGS.gap_min_pt - 0.01 for g in gaps)
    assert all(
        g <= SETTINGS.gap_min_pt * SETTINGS.gap_max_factor + 0.01 for g in gaps
    )


def test_nothing_overlaps_or_leaves_the_content_box():
    sizes = [(1000, h) for h in (200, 640, 150, 900, 300, 210, 480)]
    pages = paginate(sizes, SETTINGS)
    seen = []
    for page in pages:
        for a, b in zip(page.placements, page.placements[1:]):
            assert b.y >= a.y + a.h - 0.01
        for placement in page.placements:
            seen.append(placement.index)
            assert placement.x >= SETTINGS.content_x_pt - 0.01
            assert (
                placement.x + placement.w
                <= SETTINGS.content_x_pt + SETTINGS.content_width_pt + 0.01
            )
            assert placement.y >= SETTINGS.content_top_pt - 0.01
            assert (
                placement.y + placement.h
                <= SETTINGS.content_top_pt + SETTINGS.content_height_pt + 0.01
            )
    assert seen == list(range(len(sizes)))


def test_images_stay_horizontally_centred_when_shrunk():
    height = (SETTINGS.content_height_pt * 1.04 - 3 * SETTINGS.gap_min_pt) / 4
    size = (1000, round(1000 * height / SETTINGS.content_width_pt))
    pages = paginate([size] * 4, SETTINGS)
    for placement in pages[0].placements:
        left = placement.x - SETTINGS.content_x_pt
        right = (
            SETTINGS.content_x_pt + SETTINGS.content_width_pt
        ) - (placement.x + placement.w)
        assert left == pytest.approx(right)


def test_effective_dpi_uses_the_content_width():
    dpi = effective_dpi((1000, 400), SETTINGS)
    assert dpi == pytest.approx(1000 / (SETTINGS.content_width_pt / 72.0))
