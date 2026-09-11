from scorecap import icons


def test_glyphs_are_single_characters():
    glyphs = [
        icons.CAPTURE,
        icons.RECAPTURE,
        icons.CROP,
        icons.DELETE,
        icons.SETTINGS,
        icons.EXPORT,
        icons.UNDO,
        icons.ZOOM_FIT,
        icons.ZOOM_IN,
        icons.ZOOM_OUT,
        icons.WARNING,
        icons.MISSING,
    ]
    assert all(len(g) == 1 for g in glyphs)
    assert len(set(glyphs)) == len(glyphs)  # no button shares another's symbol


def test_availability_is_a_plain_bool(qapp):
    assert isinstance(icons.available(), bool)


def test_icon_renders_at_the_requested_size(qapp):
    result = icons.icon(icons.CROP, "#23459B", size=16)
    assert not result.isNull()
    pixmap = result.pixmap(16, 16)
    assert pixmap.width() == 16 and pixmap.height() == 16
