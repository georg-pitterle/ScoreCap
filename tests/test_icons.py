from scorecap import icons


def test_icon_renders_at_the_requested_size(qapp):
    result = icons.icon(icons.CROP, "#23459B", size=16)
    assert not result.isNull()
    pixmap = result.pixmap(16, 16)
    assert pixmap.width() == 16 and pixmap.height() == 16
