"""Generate assets/scorecap.ico from the app palette.

A staff on paper, marked with the ultramarine of the accent colour. Kept as a
script so the icon can be regenerated when the palette changes.
"""

from pathlib import Path

from PIL import Image, ImageDraw

from scorecap.theme import LIGHT

SIZES = [16, 24, 32, 48, 64, 128, 256]
TARGET = Path(__file__).resolve().parent.parent / "assets" / "scorecap.ico"


def draw(size: int) -> Image.Image:
    scale = size / 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = max(int(28 * scale), 2)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius, fill=LIGHT.accent)

    paper = [int(34 * scale), int(52 * scale), int(222 * scale), int(204 * scale)]
    draw.rounded_rectangle(paper, max(int(8 * scale), 1), fill=LIGHT.paper)

    line_width = max(int(8 * scale), 1)
    left, right = paper[0] + int(20 * scale), paper[2] - int(20 * scale)
    for index in range(5):
        y = paper[1] + int((30 + index * 26) * scale)
        draw.line([left, y, right, y], fill=LIGHT.text, width=line_width)

    head = int(26 * scale)
    cx, cy = paper[0] + int(74 * scale), paper[1] + int(108 * scale)
    draw.ellipse([cx - head, cy - head // 2, cx + head, cy + head // 2], fill=LIGHT.accent)
    draw.line(
        [cx + head - line_width, cy, cx + head - line_width, cy - int(70 * scale)],
        fill=LIGHT.accent,
        width=max(line_width, 2),
    )
    return image


def main() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    frames = [draw(size) for size in SIZES]
    frames[-1].save(TARGET, format="ICO", sizes=[(s, s) for s in SIZES])
    print("wrote", TARGET, TARGET.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
