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

Everything runs through Pillow operations that work in C. Where a whole row or
column has to be summed, the image is squashed to one pixel with a box
filter, which averages it.
"""

from __future__ import annotations

import math
import re
import statistics
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Sequence

import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageMath, ImageOps, ImageSequence

from .model import Shot
from .trim import trim_box

SCAN_DPI = 300
MAX_WIDTH = 3600        # wider scans are scaled down: 300 dpi is plenty to print
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"})
SUFFIXES = IMAGE_SUFFIXES | {".pdf"}
MODES = ("bw", "grey")

DARK = 128              # below this a pixel counts as ink
EDGE_COVER = 0.6        # a border row or column is mostly dark
EDGE_LIMIT = 0.08       # borders are never deeper than this share of the page
BACKGROUND_SCALE = 16   # the paper is estimated on a much smaller copy
LINE_SPAN = 0.4         # a staff line runs across at least this share of the page
JOIN_COVER = 0.9        # a barline joining two staves is this unbroken
WHITE_ROW = 1           # a row squashed to this or less holds no ink
GREY_WHITE = 225        # in grey mode, anything this light becomes paper
TRIM_THRESHOLD = 200    # ink for the crop around a system - specks stay out
STRAIGHT_ENOUGH = 0.05  # degrees; smaller tilts are not worth resampling

# A run of ink that may be broken by a gap of up to three pixels: scanned
# staff lines fray, and a notehead or barline never breaks them.
_RUN = re.compile(rb"\xff(?:\xff|\x00{1,3}(?=\xff))*")


@dataclass(frozen=True)
class System:
    """Boxes in page pixels: the whole band, and the system's ink inside it."""

    band: tuple[int, int, int, int]
    content: tuple[int, int, int, int]


@dataclass(frozen=True)
class PageResult:
    shots: list[Shot]
    found_staves: bool


@dataclass(frozen=True)
class ImportResult:
    """What an import produced; page lists name "file, Seite n"."""

    shots: list[Shot]
    pages: int
    whole: list[str]    # no staves found - kept as one capture
    blank: list[str]    # nothing on it - skipped
    errors: list[str]


@dataclass(frozen=True)
class _Line:
    top: int
    bottom: int
    left: int
    right: int

    @property
    def centre(self) -> float:
        return (self.top + self.bottom) / 2.0


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
            raise ValueError(f"{path.name}: kein lesbares PDF.") from error
        with doc:
            for pdf_page in doc:
                pixmap = pdf_page.get_pixmap(dpi=SCAN_DPI, colorspace=pymupdf.csGRAY)
                yield Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)
        return
    if suffix not in IMAGE_SUFFIXES:
        raise ValueError(f"{path.name}: kein unterstütztes Format.")
    try:
        image = Image.open(path)
    except (OSError, Image.UnidentifiedImageError) as error:
        raise ValueError(f"{path.name}: kein lesbares Bild.") from error
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


def _ink(grey: Image.Image) -> Image.Image:
    return grey.point(lambda value: 255 if value < DARK else 0)


def _rows(image: Image.Image) -> bytes:
    return image.resize((1, image.height), Image.BOX).tobytes()


def _columns(image: Image.Image) -> bytes:
    return image.resize((image.width, 1), Image.BOX).tobytes()


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
    ink = _ink(grey)
    width, height = grey.size
    columns, rows = _columns(ink), _rows(ink)

    def depth(profile: bytes, size: int) -> int:
        reach = 0
        while reach < size * EDGE_LIMIT and profile[reach] >= EDGE_COVER * 255:
            reach += 1
        # The border's frayed inner edge is lighter than the border itself.
        return reach + 2 if reach else 0

    left, right = depth(columns, width), depth(columns[::-1], width)
    top, bottom = depth(rows, height), depth(rows[::-1], height)
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
    rows = _rows(ink.rotate(angle, Image.BILINEAR, fillcolor=0))
    return sum(level * level for level in rows)


def _best_angle(ink: Image.Image, centre: float, reach: float, step: float) -> float:
    count = round(reach / step)
    angles = [centre + i * step for i in range(-count, count + 1)]
    # On a tie the smaller correction wins: no reason to rotate needlessly.
    return max(angles, key=lambda angle: (_sharpness(ink, angle), -abs(angle)))


def skew_angle(grey: Image.Image, limit: float = 5.0) -> float:
    """Degrees to rotate the image by (counter-clockwise) to level its lines."""
    ink = _ink(grey)
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


def finish(grey: Image.Image, mode: str) -> Image.Image:
    """Final look: pure black and white (1 bit), or grey on white paper."""
    if mode == "grey":
        return grey.point(
            lambda value: 255 if value >= GREY_WHITE else round(value * 255 / GREY_WHITE)
        )
    # A nearly empty page makes Otsu wander; keep it where ink plausibly ends.
    threshold = max(96, min(200, _otsu(grey)))
    black_white = grey.point(lambda value: 255 if value > threshold else 0)
    return black_white.convert("1", dither=Image.Dither.NONE)


# --- systems ----------------------------------------------------------------


def _staff_lines(ink: Image.Image) -> list[_Line]:
    width = ink.width
    pixels = ink.tobytes()
    found: list[tuple[int, int, int]] = []
    for y, level in enumerate(_rows(ink)):
        if level < LINE_SPAN * 255:
            continue
        row = pixels[y * width : (y + 1) * width]
        run = max(_RUN.finditer(row), key=lambda match: match.end() - match.start())
        if run.end() - run.start() >= LINE_SPAN * width:
            found.append((y, run.start(), run.end()))
    lines: list[_Line] = []
    group: list[tuple[int, int, int]] = []
    for row in found + [(-2, 0, 0)]:  # a sentinel flushes the last group
        if group and row[0] != group[-1][0] + 1:
            lines.append(
                _Line(
                    top=group[0][0],
                    bottom=group[-1][0],
                    left=round(statistics.median(r[1] for r in group)),
                    right=round(statistics.median(r[2] for r in group)),
                )
            )
            group = []
        group.append(row)
    return lines


def _staves(lines: list[_Line]) -> list[_Staff]:
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
    return max(_columns(ink.crop((left, top, right, bottom)))) >= JOIN_COVER * 255


def _split(rows: bytes, top: int, bottom: int) -> int:
    """Where to cut between two systems: in their widest band of white.

    Lyrics sit close under their staff and dynamics close above theirs, so
    the widest stretch of white is the one between the systems.
    """
    middle = (top + bottom) / 2.0
    runs: list[tuple[int, int]] = []
    start = None
    for y in range(top, bottom + 1):
        white = y < bottom and rows[y] <= WHITE_ROW
        if white and start is None:
            start = y
        elif not white and start is not None:
            runs.append((start, y))
            start = None
    if runs:
        start, end = max(runs, key=lambda r: (r[1] - r[0], -abs((r[0] + r[1]) / 2 - middle)))
        return (start + end) // 2
    least = min(rows[top:bottom])
    return min(
        (y for y in range(top, bottom) if rows[y] == least),
        key=lambda y: abs(y - middle),
    )


def _reach(rows: bytes, start: int, step: int, limit: int, gap: int) -> int:
    """Follow ink from a system outwards until a gap of white or the limit.

    Returns the last row with ink, or `start` when there is none - titles and
    page numbers lie beyond a wide white gap and are left out.
    """
    last = start
    white = 0
    y = start + step
    while 0 <= y < len(rows) and abs(y - start) <= limit:
        if rows[y] <= WHITE_ROW:
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
    ink = _ink(grey)
    width, height = grey.size
    staves = _staves(_staff_lines(ink))
    if not staves:
        return []
    groups: list[list[_Staff]] = [[staves[0]]]
    for upper, lower in zip(staves, staves[1:]):
        if _joined(ink, upper, lower):
            groups[-1].append(lower)
        else:
            groups.append([lower])

    space = statistics.median(staff.space for staff in staves)
    staff_height = round(4 * space)
    left = max(0, min(staff.left for staff in staves) - 3 * staff_height)
    right = min(width, max(staff.right for staff in staves) + 2 * staff_height)
    rows = _rows(ink.crop((left, 0, right, height)))
    padding = max(2, round(space / 2))

    splits = [
        _split(rows, upper[-1].bottom + 1, lower[0].top)
        for upper, lower in zip(groups, groups[1:])
    ]
    bounds = [0, *splits, height]
    systems = []
    for number, group in enumerate(groups):
        band_top, band_bottom = bounds[number], bounds[number + 1]
        if number == 0:
            top = _reach(rows, group[0].top, -1, 4 * staff_height, round(3 * space))
        else:
            top = band_top
        if number == len(groups) - 1:
            bottom = _reach(rows, group[-1].bottom, 1, 4 * staff_height, round(3 * space)) + 1
        else:
            bottom = band_bottom
        region = (left, max(top, band_top), right, min(bottom, band_bottom))
        box = trim_box(grey.crop(region), DARK, padding)
        if box is None:
            content = region
        else:
            content = (
                region[0] + box[0],
                region[1] + box[1],
                region[0] + box[2],
                region[1] + box[3],
            )
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
    return Shot(path=path, width=width, height=height, crop=crop)


def _crop_within(
    image: Image.Image, region: tuple[int, int, int, int], padding: int
) -> tuple[int, int, int, int]:
    box = trim_box(image.crop(region), TRIM_THRESHOLD, padding)
    if box is None:
        return region
    return (region[0] + box[0], region[1] + box[1], region[0] + box[2], region[1] + box[3])


def process_page(image: Image.Image, mode: str, target_dir: Path) -> PageResult:
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
        finished = finish(grey, mode)
        return PageResult(
            shots=[_save(finished, _crop_within(finished, whole, 4), target_dir)],
            found_staves=False,
        )

    shots = []
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
        finished = finish(band, mode)
        shots.append(_save(finished, _crop_within(finished, content, padding), target_dir))
    return PageResult(shots=shots, found_staves=True)


def import_scans(
    paths: Sequence[Path],
    mode: str,
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
    for path in paths:
        try:
            for number, image in enumerate(load_pages(path), start=1):
                if cancelled():
                    return ImportResult(shots, pages, whole, blank, errors)
                label = f"{path.name}, Seite {number}"
                progress(f"{label} wird bereinigt …")
                result = process_page(image, mode, target_dir)
                pages += 1
                shots.extend(result.shots)
                if not result.shots:
                    blank.append(label)
                elif not result.found_staves:
                    whole.append(label)
        except ValueError as error:
            errors.append(str(error))
        except (OSError, Image.DecompressionBombError) as error:
            errors.append(f"{path.name}: {error}")
    return ImportResult(shots, pages, whole, blank, errors)
