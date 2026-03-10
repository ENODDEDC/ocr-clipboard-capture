from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def make_base(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = max(2, size // 16)
    stroke = max(2, size // 22)

    d.ellipse(
        (pad, pad, size - pad, size - pad),
        fill=(20, 22, 26, 255),
        outline=(0, 229, 255, 255),
        width=stroke,
    )

    def rr(rect, r, fill):
        d.rounded_rectangle(rect, radius=r, fill=fill)

    back = (size * 0.28, size * 0.34, size * 0.66, size * 0.72)
    front = (size * 0.34, size * 0.25, size * 0.72, size * 0.63)
    r = max(2, size // 18)
    rr(back, r, (255, 255, 255, 200))
    rr(front, r, (255, 255, 255, 255))

    bar = (size * 0.40, size * 0.50, size * 0.66, size * 0.55)
    d.rectangle(bar, fill=(0, 229, 255, 255))
    return img


def main() -> int:
    out = Path(__file__).resolve().parents[1] / "icon.ico"
    base = make_base(256)
    out.parent.mkdir(parents=True, exist_ok=True)
    base.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

