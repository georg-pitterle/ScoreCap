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


# --- systems ending flush -------------------------------------------------

from scorecap.settings import MM_TO_PT


def right_edge(placement) -> float:
    return placement.x + placement.w


def staff_right(placement, width_px: int, span_px: int) -> float:
    return placement.x + placement.w * span_px / width_px


def test_the_staff_end_sits_on_the_right_margin_and_the_mark_hangs_outside():
    # 1241 px wide, staff lines end at 1210: the Perseus page-3 case.
    pages = paginate([(1241, 582), (1220, 711)], SETTINGS, spans=[(0, 1210), None])
    arrow, plain = pages[0].placements
    margin = SETTINGS.content_x_pt + SETTINGS.content_width_pt
    assert staff_right(arrow, 1241, 1210) == pytest.approx(margin)
    assert right_edge(plain) == pytest.approx(margin)
    assert right_edge(arrow) > margin  # the arrow overhangs
    assert arrow.x == pytest.approx(plain.x)  # both start at the left margin


def test_height_follows_the_staff_span_not_the_capture_width():
    pages = paginate([(1241, 582)], SETTINGS, spans=[(0, 1210)])
    (placement,) = pages[0].placements
    assert placement.h == pytest.approx(SETTINGS.content_width_pt * 582 / 1210)


def test_shrunk_pages_keep_staff_ends_flush():
    height = (SETTINGS.content_height_pt * 1.04 - 3 * SETTINGS.gap_min_pt) / 4
    size = (1000, round(1000 * height / SETTINGS.content_width_pt))
    pages = paginate([size] * 4, SETTINGS, spans=[(0, 960), None, (0, 980), None])
    page = pages[0]
    assert page.scale < 1.0
    ends = [
        staff_right(p, 1000, span or 1000)
        for p, span in zip(page.placements, [960, None, 980, None])
    ]
    assert max(ends) - min(ends) == pytest.approx(0, abs=0.01)


def test_an_overhang_reaching_the_paper_edge_is_ignored():
    # Staff ends at 60 % of the capture: the rest would run off the page.
    pages = paginate([(1000, 300)], SETTINGS, spans=[(0, 600)])
    (placement,) = pages[0].placements
    assert right_edge(placement) == pytest.approx(
        SETTINGS.content_x_pt + SETTINGS.content_width_pt
    )


def test_overhang_stays_inside_the_side_margin():
    pages = paginate([(1241, 582)], SETTINGS, spans=[(0, 1210)])
    (placement,) = pages[0].placements
    overhang = right_edge(placement) - (SETTINGS.content_x_pt + SETTINGS.content_width_pt)
    assert 0 < overhang <= (SETTINGS.margin_side_mm - 3) * MM_TO_PT


def test_without_spans_nothing_changes():
    sizes = [(1000, 200), (1200, 340)]
    assert paginate(sizes, SETTINGS) == paginate(sizes, SETTINGS, spans=[None, None])


def staff_left(placement, width_px: int, start_px: int) -> float:
    return placement.x + placement.w * start_px / width_px


def test_the_staff_start_sits_on_the_left_margin_and_the_brace_hangs_outside():
    # Staff lines start at 31 px: a brace stands before them.
    pages = paginate([(1241, 582), (1220, 711)], SETTINGS, spans=[(31, 1241), None])
    brace, plain = pages[0].placements
    assert staff_left(brace, 1241, 31) == pytest.approx(SETTINGS.content_x_pt)
    assert brace.x < SETTINGS.content_x_pt  # the brace overhangs
    assert right_edge(brace) == pytest.approx(right_edge(plain))
    assert brace.h == pytest.approx(SETTINGS.content_width_pt * 582 / 1210)


def test_both_ends_can_overhang_at_once():
    pages = paginate([(1241, 582)], SETTINGS, spans=[(20, 1220)])
    (placement,) = pages[0].placements
    assert staff_left(placement, 1241, 20) == pytest.approx(SETTINGS.content_x_pt)
    assert staff_right(placement, 1241, 1220) == pytest.approx(
        SETTINGS.content_x_pt + SETTINGS.content_width_pt
    )


def test_a_left_overhang_reaching_the_paper_edge_is_ignored():
    # Voice names take 30 % of the capture: too much to hang into the margin.
    pages = paginate([(1000, 300)], SETTINGS, spans=[(300, 1000)])
    (placement,) = pages[0].placements
    assert placement.x == pytest.approx(SETTINGS.content_x_pt)


# --- finding a capture under a point on the page -----------------------------


def test_a_point_on_a_capture_names_it():
    from scorecap.layout import Page, Placement, placement_at

    page = Page(
        placements=(
            Placement(index=3, x=50.0, y=60.0, w=400.0, h=100.0),
            Placement(index=4, x=50.0, y=180.0, w=400.0, h=100.0),
        ),
        scale=1.0,
    )
    assert placement_at(page, 60.0, 70.0) == 3
    assert placement_at(page, 449.0, 279.0) == 4


def test_a_point_beside_every_capture_names_none():
    from scorecap.layout import Page, Placement, placement_at

    page = Page(
        placements=(Placement(index=0, x=50.0, y=60.0, w=400.0, h=100.0),),
        scale=1.0,
    )
    assert placement_at(page, 20.0, 70.0) is None     # in the margin
    assert placement_at(page, 60.0, 170.0) is None    # in the gap below
    assert placement_at(page, 450.0, 60.0) is None    # just past the right edge


def test_an_empty_page_names_none():
    from scorecap.layout import Page, placement_at

    assert placement_at(Page(placements=(), scale=1.0), 100.0, 100.0) is None
