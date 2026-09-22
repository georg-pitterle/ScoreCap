"""Turn scanned pages into one clean capture per system.

A scan is not a screenshot: the page sits slightly askew, the paper is
yellowed, a book casts a shadow along its spine and the scanner lid leaves a
dark border. Each page is cleaned up first - background flattened, edges
cleared, rotation undone - and then cut into systems. Staff lines do most of
the work: they are the one thing on the page known to be straight, long and
horizontal, so they give both the rotation and the systems.

Each system is saved as its own image: the band of the page between the
whitespace that separates it from its neighbours, straightened once more on
its own. The capture's crop is the system's content inside that band, so the
crop dialog can still widen it - to take in a title, say.

Everything runs through Pillow operations that work in C: where the ink sits
is read off the profiles `ink.py` builds.
"""

from __future__ import annotations

import math
import statistics
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Sequence

import pymupdf
from PySide6.QtCore import QCoreApplication
from PIL import Image, ImageDraw, ImageFilter, ImageMath, ImageOps, ImageSequence

from .ink import DARK, Line, binary, columns, rows, staff_lines
from .model import PageSource, Shot
from .trim import trim_box, trim_within

SCAN_DPI = 300
MAX_WIDTH = 3600        # wider scans are scaled down: 300 dpi is plenty to print
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"})
SUFFIXES = IMAGE_SUFFIXES | {".pdf"}

EDGE_COVER = 0.6        # a border row or column is mostly dark
EDGE_LIMIT = 0.08       # borders are never deeper than this share of the page
EDGE_MARGIN = 0.03      # ink this close to the page edge is a scanner mark
BACKGROUND_SCALE = 16   # the paper is estimated on a much smaller copy
LINE_SPAN = 0.4         # a staff line runs across at least this share of the page
JOIN_COVER = 0.9        # a barline joining two staves is this unbroken
WHITE_ROW = 1           # a row squashed to this or less holds no ink
GREY_WHITE = 225        # on import, anything this light becomes paper
SOFT_BELOW = 60         # grey print: this far below the threshold is solid ink
SOFT_ABOVE = 30         # ... and this far above it is paper
BW_SMOOTHING = 0.7      # blur radius at double size; irons out Lanczos ringing
TRIM_THRESHOLD = 200    # ink for the crop around a system - specks stay out
STRAIGHT_ENOUGH = 0.05  # degrees; smaller tilts are not worth resampling


@dataclass(frozen=True)
class System:
    """Boxes in page pixels: the whole band, and the system's ink inside it."""

    band: tuple[int, int, int, int]
    content: tuple[int, int, int, int]


@dataclass(frozen=True)
class PageResult:
    shots: list[Shot]
    found_staves: bool
    # Where each shot came from, so a cut between systems can be taken back.
    sources: dict[Path, PageSource] = field(default_factory=dict)


@dataclass(frozen=True)
class ImportResult:
    """What an import produced; page lists name "file, page n"."""

    shots: list[Shot]
    pages: int
    whole: list[str]    # no staves found - kept as one capture
    blank: list[str]    # nothing on it - skipped
    errors: list[str]
    sources: dict[Path, PageSource] = field(default_factory=dict)


@dataclass(frozen=True)
class _Staff:
    top: int
    bottom: int
    left: int
    right: int
    space: float


# --- loading ----------------------------------------------------------------


def load_pages(path: Path) -> Iterator[Image.Image]:
    """Every page of a scan, in grey. PDFs are rendered at SCAN_DPI."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            doc = pymupdf.open(path)
        except (pymupdf.FileDataError, RuntimeError) as error:
            message = QCoreApplication.translate("scan", "{name}: not a readable PDF.")
            raise ValueError(message.format(name=path.name)) from error
        with doc:
            for pdf_page in doc:
                pixmap = pdf_page.get_pixmap(dpi=SCAN_DPI, colorspace=pymupdf.csGRAY)
                page = Image.frombytes(
                    "L", (pixmap.width, pixmap.height), pixmap.samples
                )
                yield _limited(page)
        return
    if suffix not in IMAGE_SUFFIXES:
        message = QCoreApplication.translate("scan", "{name}: not a supported format.")
        raise ValueError(message.format(name=path.name))
    try:
        image = Image.open(path)
    except (OSError, Image.UnidentifiedImageError) as error:
        message = QCoreApplication.translate("scan", "{name}: not a readable image.")
        raise ValueError(message.format(name=path.name)) from error
    with image:
        for frame in ImageSequence.Iterator(image):
            # Phone scans are often stored sideways with a rotation tag.
            yield _limited(ImageOps.exif_transpose(frame).convert("L"))


def _limited(grey: Image.Image) -> Image.Image:
    """A 600 dpi scan only makes every step four times slower."""
    if grey.width <= MAX_WIDTH:
        return grey
    height = max(1, round(grey.height * MAX_WIDTH / grey.width))
    return grey.resize((MAX_WIDTH, height), Image.LANCZOS)


# --- cleaning ---------------------------------------------------------------


def flatten_background(grey: Image.Image) -> Image.Image:
    """Divide the page by its paper, so paper turns white everywhere.

    The paper is what remains when the ink is taken away: on a small copy of
    the page, a maximum filter replaces every stroke by the paper around it,
    a minimum filter undoes the spread that leaves on a shadow's slope, and
    a blur smooths the result into a slowly changing shade. Dividing by it
    removes yellowing, a gutter shadow and uneven lighting alike.
    """
    width, height = grey.size
    small = grey.resize(
        (max(1, width // BACKGROUND_SCALE), max(1, height // BACKGROUND_SCALE)), Image.BOX
    )
    # Max then min: strokes vanish, but a shadow's slope keeps its place.
    paper = small.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))
    paper = paper.filter(ImageFilter.GaussianBlur(1))
    paper = paper.resize((width, height), Image.BILINEAR)
    flat = ImageMath.lambda_eval(
        lambda args: args["grey"] * 255 / args["max"](args["paper"], 1),
        grey=grey,
        paper=paper,
    )
    return flat.convert("L")


def clear_edges(grey: Image.Image) -> Image.Image:
    """Whiten dark borders that run in from the edge of the page."""
    ink = binary(grey)
    width, height = grey.size
    across, down = columns(ink), rows(ink)

    def depth(profile: bytes, size: int) -> int:
        reach = 0
        while reach < size * EDGE_LIMIT and profile[reach] >= EDGE_COVER * 255:
            reach += 1
        # The border's frayed inner edge is lighter than the border itself.
        return reach + 2 if reach else 0

    left, right = depth(across, width), depth(across[::-1], width)
    top, bottom = depth(down, height), depth(down[::-1], height)
    if not (left or right or top or bottom):
        return grey
    cleared = grey.copy()
    draw = ImageDraw.Draw(cleared)
    for box in (
        (0, 0, left, height),
        (width - right, 0, width, height),
        (0, 0, width, top),
        (0, height - bottom, width, height),
    ):
        if box[2] > box[0] and box[3] > box[1]:
            draw.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill=255)
    return cleared


def _scaled(image: Image.Image, width: int) -> Image.Image:
    if image.width <= width:
        return image
    height = max(1, round(image.height * width / image.width))
    return image.resize((width, height), Image.BOX)


def _sharpness(ink: Image.Image, angle: float) -> int:
    """How strongly the ink gathers in few rows: large when lines are level."""
    profile = rows(ink.rotate(angle, Image.BILINEAR, fillcolor=0))
    return sum(level * level for level in profile)


def _best_angle(ink: Image.Image, centre: float, reach: float, step: float) -> float:
    count = round(reach / step)
    angles = [centre + i * step for i in range(-count, count + 1)]
    # On a tie the smaller correction wins: no reason to rotate needlessly.
    return max(angles, key=lambda angle: (_sharpness(ink, angle), -abs(angle)))


def skew_angle(grey: Image.Image, limit: float = 5.0) -> float:
    """Degrees to rotate the image by (counter-clockwise) to level its lines."""
    ink = binary(grey)
    if ink.getbbox() is None:
        return 0.0
    coarse_step = 0.2 if limit > 1.0 else 0.05
    coarse = _best_angle(_scaled(ink, 600), 0.0, limit, coarse_step)
    fine = _best_angle(_scaled(ink, 1600), coarse, coarse_step, 0.02)
    fine = max(-limit, min(limit, fine))
    return round(fine, 2)


def _otsu(grey: Image.Image) -> int:
    """The threshold that best splits the histogram into ink and paper."""
    histogram = grey.histogram()
    total = sum(histogram)
    weighted = sum(value * count for value, count in enumerate(histogram))
    below = below_weighted = 0
    best, threshold = -1.0, DARK
    for value, count in enumerate(histogram):
        below += count
        if below == 0:
            continue
        above = total - below
        if above == 0:
            break
        below_weighted += value * count
        mean_below = below_weighted / below
        mean_above = (weighted - below_weighted) / above
        spread = below * above * (mean_below - mean_above) ** 2
        if spread > best:
            best, threshold = spread, value
    return threshold


def _whitened(grey: Image.Image) -> Image.Image:
    """Paper turned white, ink left as scanned: what a capture is kept as."""
    return grey.point(
        lambda value: 255 if value >= GREY_WHITE else round(value * 255 / GREY_WHITE)
    )


def _soft(grey: Image.Image, threshold: int) -> Image.Image:
    """Paper white, ink black, and a narrow grey ramp at the edges between."""
    low = max(0, threshold - SOFT_BELOW)
    high = min(255, threshold + SOFT_ABOVE)

    def ramp(value: int) -> int:
        if value <= low:
            return 0
        if value >= high:
            return 255
        return round((value - low) * 255 / (high - low))

    return grey.point(ramp)


def finish(grey: Image.Image, mode: str) -> Image.Image:
    """Final look for print: black and white (1 bit), or grey with clean paper.

    Black and white is thresholded at twice the scan's resolution: the grey
    shades along an edge then decide where it runs to half a pixel, and
    noteheads come out round instead of stepped.
    """
    # A nearly empty page makes Otsu wander; keep it where ink plausibly ends.
    threshold = max(96, min(200, _otsu(grey)))
    if mode == "grey":
        return _soft(grey, threshold)
    fine = grey.resize((grey.width * 2, grey.height * 2), Image.LANCZOS)
    fine = fine.filter(ImageFilter.GaussianBlur(BW_SMOOTHING))
    black_white = fine.point(lambda value: 255 if value > threshold else 0)
    return black_white.convert("1", dither=Image.Dither.NONE)


# --- systems ----------------------------------------------------------------


def _staves(lines: list[Line]) -> list[_Staff]:
    """Five lines at an even spacing make a staff."""
    staves: list[_Staff] = []
    index = 0
    while index + 5 <= len(lines):
        group = lines[index : index + 5]
        gaps = [b.centre - a.centre for a, b in zip(group, group[1:])]
        if min(gaps) >= 3 and max(gaps) <= 1.3 * min(gaps):
            staves.append(
                _Staff(
                    top=group[0].top,
                    bottom=group[-1].bottom,
                    left=round(statistics.median(line.left for line in group)),
                    right=round(statistics.median(line.right for line in group)),
                    space=statistics.mean(gaps),
                )
            )
            index += 5
        else:
            index += 1
    return staves


def _joined(ink: Image.Image, upper: _Staff, lower: _Staff) -> bool:
    """Do both staves hang on one barline at the left, as a system's do?"""
    space = round(max(upper.space, lower.space))
    left = max(0, min(upper.left, lower.left) - 2 * space)
    right = min(ink.width, max(upper.left, lower.left) + space)
    top, bottom = upper.bottom + 1, lower.top
    if bottom <= top:
        return True
    return max(columns(ink.crop((left, top, right, bottom)))) >= JOIN_COVER * 255


def _split(profile: bytes, top: int, bottom: int) -> int:
    """Where to cut between two systems: in their widest band of white.

    Lyrics sit close under their staff and dynamics close above theirs, so
    the widest stretch of white is the one between the systems.
    """
    middle = (top + bottom) / 2.0
    runs: list[tuple[int, int]] = []
    start = None
    for y in range(top, bottom + 1):
        white = y < bottom and profile[y] <= WHITE_ROW
        if white and start is None:
            start = y
        elif not white and start is not None:
            runs.append((start, y))
            start = None
    if runs:
        start, end = max(runs, key=lambda r: (r[1] - r[0], -abs((r[0] + r[1]) / 2 - middle)))
        return (start + end) // 2
    least = min(profile[top:bottom])
    return min(
        (y for y in range(top, bottom) if profile[y] == least),
        key=lambda y: abs(y - middle),
    )


def _reach(profile: bytes, start: int, step: int, limit: int, gap: int) -> int:
    """Follow ink from a system outwards until a gap of white or the limit.

    Returns the last row with ink, or `start` when there is none - titles and
    page numbers lie beyond a wide white gap and are left out.
    """
    last = start
    white = 0
    y = start + step
    while 0 <= y < len(profile) and abs(y - start) <= limit:
        if profile[y] <= WHITE_ROW:
            white += 1
            if white >= gap:
                break
        else:
            white = 0
            last = y
        y += step
    return last


def find_systems(grey: Image.Image) -> list[System]:
    """The systems on a level page, top to bottom."""
    ink = binary(grey)
    width, height = grey.size
    # On paper, staff lines are thin and never quite straight: a line that
    # sags by two pixels across the page leaves each pixel row only a piece
    # of it, and the piece that looks longest may start mid-system. Grown by
    # a pixel up and down, the pieces merge into one line again.
    lines_ink = ink.filter(ImageFilter.MaxFilter(3))
    staves = _staves(staff_lines(lines_ink, LINE_SPAN))
    if not staves:
        return []
    groups: list[list[_Staff]] = [[staves[0]]]
    for upper, lower in zip(staves, staves[1:]):
        if _joined(lines_ink, upper, lower):
            groups[-1].append(lower)
        else:
            groups.append([lower])

    space = statistics.median(staff.space for staff in staves)
    staff_height = round(4 * space)
    left = max(0, min(staff.left for staff in staves) - 3 * staff_height)
    right = min(width, max(staff.right for staff in staves) + 2 * staff_height)
    down = rows(ink.crop((left, 0, right, height)))
    padding = max(2, round(space / 2))
    gap = round(3 * space)
    side_gap = round(2.5 * staff_height)

    splits = [
        _split(down, upper[-1].bottom + 1, lower[0].top)
        for upper, lower in zip(groups, groups[1:])
    ]
    bounds = [0, *splits, height]
    systems = []
    for number, group in enumerate(groups):
        band_top, band_bottom = bounds[number], bounds[number + 1]
        # Outwards from the staves, up to a wide white gap: lyrics and
        # dynamics sit close, a speck of dust or a page number does not.
        # Outside the first and last system the band ends the search.
        above = 4 * staff_height if number == 0 else group[0].top - band_top - 1
        below = (
            4 * staff_height
            if number == len(groups) - 1
            else band_bottom - group[-1].bottom - 2
        )
        top = _reach(down, group[0].top, -1, above, gap)
        bottom = _reach(down, group[-1].bottom, 1, below, gap) + 1
        # Sideways the same way, with more room: voice names may stand well
        # apart from the bracket. Marks the scanner leaves right at the edge
        # of the page are never part of the music.
        across = columns(ink.crop((0, top, width, bottom)))
        edge = round(width * EDGE_MARGIN)
        staff_left = min(s.left for s in group)
        staff_right = max(s.right for s in group) - 1
        first = _reach(
            across, staff_left, -1, min(3 * staff_height, staff_left - edge), side_gap
        )
        last = (
            _reach(
                across,
                staff_right,
                1,
                min(2 * staff_height, width - edge - staff_right),
                side_gap,
            )
            + 1
        )
        # Room for the padding, so the ink never touches the crop.
        region = (
            max(first - padding, 0),
            max(top - padding, band_top),
            min(last + padding, width),
            min(bottom + padding, band_bottom),
        )
        content = trim_within(grey, region, DARK, padding) or region
        # Padding may spill over the cut; the band is where the file ends.
        content = (
            content[0],
            max(content[1], band_top),
            content[2],
            min(content[3], band_bottom),
        )
        systems.append(System(band=(0, band_top, width, band_bottom), content=content))
    return systems


# --- whole pages ------------------------------------------------------------


def _save(image: Image.Image, crop: tuple[int, int, int, int], target_dir: Path) -> Shot:
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"scan-{uuid.uuid4().hex}.png"
    image.save(path, "PNG")
    width, height = image.size
    if crop == (0, 0, width, height):
        crop = None
    return Shot(path=path, width=width, height=height, crop=crop, scan=True)


def _trimmed(
    image: Image.Image, region: tuple[int, int, int, int], padding: int
) -> tuple[int, int, int, int]:
    """The region closed in on its ink, or the region itself when it is blank."""
    return trim_within(image, region, TRIM_THRESHOLD, padding) or region


def process_page(image: Image.Image, target_dir: Path) -> PageResult:
    """Clean one scanned page and save a capture per system.

    A page without staves - a title page, a page of text - is kept whole,
    trimmed to its ink. A blank page yields nothing.
    """
    grey = clear_edges(flatten_background(image.convert("L")))
    angle = skew_angle(grey)
    if angle:
        grey = grey.rotate(angle, Image.BICUBIC, fillcolor=255)
    systems = find_systems(grey)
    if not systems:
        whole = (0, 0, grey.width, grey.height)
        if trim_box(grey, TRIM_THRESHOLD, 0) is None:
            return PageResult(shots=[], found_staves=False)
        finished = _whitened(grey)
        return PageResult(
            shots=[_save(finished, _trimmed(finished, whole, 4), target_dir)],
            found_staves=False,
        )

    # The page needs no cleaning of its own: _whitened works pixel by pixel,
    # so a band's pixels on the page are the band's pixels.
    whole_page = _save(_whitened(grey), (0, 0, grey.width, grey.height), target_dir)
    shots = []
    sources = {}
    for system in systems:
        band_left, band_top = system.band[:2]
        band = grey.crop(system.band)
        content = (
            system.content[0] - band_left,
            system.content[1] - band_top,
            system.content[2] - band_left,
            system.content[3] - band_top,
        )
        padding = max(2, (content[3] - content[1]) // 60)
        tilt = skew_angle(band.crop(content), limit=0.5)
        if abs(tilt) >= STRAIGHT_ENOUGH:
            band = band.rotate(tilt, Image.BICUBIC, fillcolor=255)
            # Turning about the middle moves the ends up or down a little.
            shift = math.ceil(band.width / 2 * math.tan(math.radians(abs(tilt)))) + 1
            content = (
                content[0],
                max(0, content[1] - shift),
                content[2],
                min(band.height, content[3] + shift),
            )
        finished = _whitened(band)
        shot = _save(finished, _trimmed(finished, content, padding), target_dir)
        shots.append(shot)
        sources[shot.path] = PageSource(page=whole_page, region=system.content)
    return PageResult(shots=shots, found_staves=True, sources=sources)


def import_scans(
    paths: Sequence[Path],
    target_dir: Path,
    progress: Callable[[str], None] = lambda text: None,
    cancelled: Callable[[], bool] = lambda: False,
) -> ImportResult:
    """Process every page of every file. A file that cannot be read is
    reported and skipped; the others still come in."""
    shots: list[Shot] = []
    pages = 0
    whole: list[str] = []
    blank: list[str] = []
    errors: list[str] = []
    sources: dict[Path, PageSource] = {}
    for path in paths:
        try:
            for number, image in enumerate(load_pages(path), start=1):
                if cancelled():
                    return ImportResult(shots, pages, whole, blank, errors, sources)
                label = QCoreApplication.translate("scan", "{name}, page {number}").format(
                    name=path.name, number=number
                )
                progress(QCoreApplication.translate("scan", "Cleaning up {page} …").format(page=label))
                result = process_page(image, target_dir)
                pages += 1
                shots.extend(result.shots)
                sources.update(result.sources)
                if not result.shots:
                    blank.append(label)
                elif not result.found_staves:
                    whole.append(label)
        except ValueError as error:
            errors.append(str(error))
        except (OSError, Image.DecompressionBombError) as error:
            errors.append(f"{path.name}: {error}")
    return ImportResult(shots, pages, whole, blank, errors, sources)
