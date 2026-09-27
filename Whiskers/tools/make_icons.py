"""Draw the Whiskers icon and build the app icon set from it.

    python tools/make_icons.py

The artwork is drawn here from the same geometry as the logo in index.html, so the icon
can always be reproduced exactly and nothing binary has to be trusted from elsewhere.
The .ico/.icns writers come from Mittens & Pence, where both were learned the hard way:

Windows reads PNG-compressed entries inside an .ico, but every icon editor and every
Microsoft tool writes the small sizes as uncompressed BMP and only the 256px entry as
PNG. Pillow writes PNG for all of them. That is legal but unconventional, and this
build cannot be tested here — the executable is made on Windows — so the icon is
assembled by hand in the layout Windows has always been given.

A BMP entry inside an .ico is not a .bmp file: no file header, the height in the info
header is **doubled** (colour rows plus the AND mask), and the rows run bottom-up.
Getting any of that wrong produces a file that opens fine in a viewer and shows as a
blank square in the taskbar.
"""

from __future__ import annotations

import io
import pathlib
import struct
import sys

from PIL import Image

#: BMP below this, PNG at and above it — what Windows tooling produces.
PNG_FROM = 256
SIZES = (16, 24, 32, 48, 64, 128, 256)


def square(src: Image.Image, faint: int = 8) -> Image.Image:
    """Crop to the real artwork, wipe near-transparent haze, pad to a square."""
    import numpy as np
    im = src.convert("RGBA")
    a = np.array(im)[:, :, 3]
    w = im.width
    rows = np.where((a > 40).sum(axis=1) > w * 0.15)[0]
    cols = np.where((a > 40).sum(axis=0) > w * 0.15)[0]
    if len(rows) and len(cols):
        im = im.crop((int(cols.min()), int(rows.min()),
                      int(cols.max()) + 1, int(rows.max()) + 1))
    arr = np.array(im)
    # Faint speckle is invisible at full size and grey dirt at 16px.
    arr[:, :, 3][arr[:, :, 3] < faint] = 0
    im = Image.fromarray(arr, "RGBA")
    side = max(im.size)
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    out.paste(im, ((side - im.width) // 2, (side - im.height) // 2), im)
    return out


def _bmp_entry(im: Image.Image) -> bytes:
    """One BMP image as an .ico stores it: doubled height, bottom-up, AND mask after."""
    w, h = im.size
    px = im.convert("RGBA").load()
    colour = bytearray()
    for y in range(h - 1, -1, -1):                 # bottom-up
        for x in range(w):
            r, g, b, a = px[x, y]
            colour += bytes((b, g, r, a))          # BGRA

    # The 1-bit AND mask is ignored for 32bpp images but must still be present and
    # 4-byte aligned, or the entry is malformed.
    row_bytes = ((w + 31) // 32) * 4
    mask = bytearray(row_bytes * h)

    header = struct.pack("<IiiHHIIiiII",
                         40,          # header size
                         w, h * 2,    # doubled: colour rows + mask rows
                         1, 32,       # planes, bits per pixel
                         0,           # BI_RGB, uncompressed
                         len(colour) + len(mask),
                         0, 0, 0, 0)
    return bytes(header + colour + mask)


def write_ico(square_img: Image.Image, path: pathlib.Path, sizes=SIZES) -> None:
    entries, blobs = [], []
    for n in sizes:
        im = square_img.resize((n, n), Image.LANCZOS)
        if n >= PNG_FROM:
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            blobs.append(buf.getvalue())
        else:
            blobs.append(_bmp_entry(im))
        entries.append(n)

    offset = 6 + 16 * len(entries)
    out = bytearray(struct.pack("<HHH", 0, 1, len(entries)))
    for n, blob in zip(entries, blobs):
        dim = 0 if n >= 256 else n                 # 0 means 256 in an icon directory
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    for blob in blobs:
        out += blob
    path.write_bytes(bytes(out))


#: The macOS tiers worth carrying, and the pixel size each one holds. Pillow's ICNS
#: writer emits the whole ladder at full quality whatever you feed it — 3 MB for one
#: icon file — so the chunks are written here instead, with optimised PNGs.
ICNS_TIERS = (
    (b"icp4", 16), (b"icp5", 32), (b"ic11", 32), (b"ic12", 64),
    (b"ic07", 128), (b"ic13", 256), (b"ic08", 256), (b"ic14", 512), (b"ic09", 512),
)


def write_icns(square_img: Image.Image, path: pathlib.Path) -> None:
    """An ICNS is a magic word, a length, then typed chunks each holding a PNG."""
    chunks = bytearray()
    for tag, n in ICNS_TIERS:
        buf = io.BytesIO()
        square_img.resize((n, n), Image.LANCZOS).save(buf, format="PNG", optimize=True)
        blob = buf.getvalue()
        chunks += tag + struct.pack(">I", len(blob) + 8) + blob
    path.write_bytes(b"icns" + struct.pack(">I", len(chunks) + 8) + bytes(chunks))


# The logo, in the 64-unit space index.html draws it in.
HEAD = [("M", (14.5, 27)), ("L", (16.5, 10.5)), ("L", (27, 19.2)), ("Q", (32, 17.6), (37, 19.2)),
        ("L", (47.5, 10.5)), ("L", (49.5, 27)), ("Q", (53.5, 34.5), (49.8, 42.2)),
        ("Q", (44.5, 52), (32, 52)), ("Q", (19.5, 52), (14.2, 42.2)), ("Q", (10.5, 34.5), (14.5, 27))]
WHISKERS = [[(22, 40), (3.5, 36.5)], [(22, 43.2), (3, 44)], [(23, 46.2), (6, 51.5)],
            [(42, 43.2), (61, 44)], [(41, 46.2), (58, 51.5)]]
#: The one whisker that has noticed something: it kinks upward like a rising trace.
ALERT = [(42, 40), (49, 38.2), (53.5, 40.2), (61, 30.5)]
TILE, FACE, ACCENT = (11, 110, 110), (243, 245, 247), (245, 176, 65)


def _flatten(path, steps: int = 24) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for seg in path:
        if seg[0] in ("M", "L"):
            pts.append(seg[1])
        else:
            (x0, y0), (cx, cy), (x1, y1) = pts[-1], seg[1], seg[2]
            for i in range(1, steps + 1):
                t = i / steps
                pts.append(((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1,
                            (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1))
    return pts


def draw(size: int = 1024) -> Image.Image:
    from PIL import ImageDraw
    big = size * 4                                   # drawn large, scaled down: smooth edges
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, big - 1, big - 1], radius=int(big * 0.22), fill=TILE + (255,))
    scale, off = big * 0.84 / 64, big * 0.08
    P = lambda x, y: (off + x * scale, off + (y + 1.5) * scale)   # noqa: E731
    d.polygon([P(*q) for q in _flatten(HEAD)], fill=FACE + (255,))
    for cx in (25, 39):
        r = 2.9 * scale
        x, y = P(cx, 32.5)
        d.ellipse([x - r, y - r, x + r, y + r], fill=TILE + (255,))
    d.polygon([P(29.8, 38.6), P(34.2, 38.6), P(32, 41.4)], fill=TILE + (255,))
    w = int(2.2 * scale)
    for line in WHISKERS:
        d.line([P(*q) for q in line], fill=FACE + (255,), width=w, joint="curve")
    d.line([P(*q) for q in ALERT], fill=ACCENT + (255,), width=int(2.6 * scale), joint="curve")
    for x, y in (ALERT[0], ALERT[-1]):
        cx, cy = P(x, y)
        r = 1.3 * scale
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT + (255,))
    return im.resize((size, size), Image.LANCZOS)


def main() -> None:
    root = pathlib.Path(__file__).resolve().parent.parent
    res = root / "folio" / "resources"
    res.mkdir(exist_ok=True)
    img = draw(1024)
    img.resize((512, 512), Image.LANCZOS).save(res / "whiskers-512.png", optimize=True)
    img.resize((256, 256), Image.LANCZOS).save(res / "whiskers.png", optimize=True)
    img.resize((64, 64), Image.LANCZOS).save(root / "folio" / "web" / "static" / "favicon.png",
                                             optimize=True)
    write_icns(img, res / "whiskers.icns")
    write_ico(img, res / "whiskers.ico")
    print("wrote whiskers.ico, .icns, .png, -512.png and web/static/favicon.png")


if __name__ == "__main__":
    main()
