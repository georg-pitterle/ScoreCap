import re

import pytest

from scorecap.theme import DARK, LIGHT, Palette, palette_for, stylesheet

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
COLOURS = [
    field
    for field in Palette.__dataclass_fields__
    if field not in {"name", "font_ui", "font_mono"}
]


@pytest.mark.parametrize("palette", [LIGHT, DARK])
def test_every_colour_token_is_a_hex_value(palette):
    for token in COLOURS:
        assert HEX.match(getattr(palette, token)), f"{token} = {getattr(palette, token)}"


def test_the_two_palettes_differ_everywhere_that_matters():
    same = [t for t in COLOURS if getattr(LIGHT, t) == getattr(DARK, t)]
    # Paper is paper in both themes; everything else has to adapt.
    assert same == ["paper"]


def test_palette_for_picks_the_scheme():
    assert palette_for(dark=True) is DARK
    assert palette_for(dark=False) is LIGHT


def test_stylesheet_uses_the_palette():
    qss = stylesheet(LIGHT)
    assert LIGHT.accent in qss
    assert LIGHT.border in qss
    assert LIGHT.text in qss


def test_stylesheet_stays_flat():
    # Gradients and glass effects are what make an app look generated.
    qss = stylesheet(LIGHT).lower()
    assert "qlineargradient" not in qss
    assert "qradialgradient" not in qss


def test_dark_stylesheet_differs_from_light():
    assert stylesheet(DARK) != stylesheet(LIGHT)


def test_fonts_name_a_fallback():
    for stack in (LIGHT.font_ui, LIGHT.font_mono):
        assert "," in stack, f"{stack} has no fallback"
