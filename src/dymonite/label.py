"""Render a label: lines of text, optionally with a QR code on the right."""

from __future__ import annotations

import re

import qrcode
from PIL import Image, ImageDraw, ImageFont

DPI = 300  # LabelWriter 400/450 print head
PAD = 30  # px, about 2.5 mm
DETAIL = 0.55  # size of every line after the first, relative to the first
MIN_FONT = 18  # px; anything smaller is unreadable on a thermal label
MIN_MODULE = 3  # px per QR module; smaller ones don't scan once printed
DEFAULT_FONTS = ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf")  # Linux, macOS, Windows


def media_size(media: str) -> tuple[int, int]:
    """CUPS media keyword (w162h90, w154h64.1) -> (width, height) in pixels at DPI.

    The numbers are points (1/72 in); a trailing .N only tells duplicate sizes apart.
    """
    m = re.fullmatch(r"w(\d+)h(\d+)(?:\.\d+)?", media)
    if not m:
        raise ValueError(f"size must be a wNhM keyword from 'dymonite sizes', got {media!r}")
    w, h = (round(int(v) / 72 * DPI) for v in m.groups())
    return w, h


def wifi_qr(ssid: str, password: str = "", security: str = "WPA", hidden: bool = False) -> str:
    """The WIFI: payload phone cameras offer to join."""
    if security not in ("WPA", "WEP"):
        raise ValueError(f"security must be WPA or WEP, got {security!r}")

    def esc(s: str) -> str:
        return re.sub(r'([\\;,:"])', r"\\\1", s)

    payload = f"WIFI:T:{security if password else 'nopass'};S:{esc(ssid)};"
    if password:
        payload += f"P:{esc(password)};"
    if hidden:
        payload += "H:true;"
    return payload + ";"


def load_font(name: str | None = None) -> ImageFont.FreeTypeFont:
    """A font file or name Pillow can find; by default a bold system sans, else Pillow's own."""
    for candidate in [name] if name else DEFAULT_FONTS:
        try:
            return ImageFont.truetype(candidate, MIN_FONT)
        except OSError:
            if name:
                raise ValueError(f"font not found: {name}") from None
    return ImageFont.load_default(MIN_FONT)


def _largest(ok, lo: int, hi: int) -> int:
    """The largest n in [lo, hi] with ok(n), given ok(lo) and that ok only turns false as n grows."""
    while lo < hi:
        mid = (lo + hi + 1) // 2
        lo, hi = (mid, hi) if ok(mid) else (lo, mid - 1)
    return lo


def _fit(lines: list[str], font: ImageFont.FreeTypeFont, width: int, height: int) -> list[ImageFont.FreeTypeFont]:
    """A font per line: the first as large as fits, then the rest as large as fit beside it, never larger.

    The rest are only held to DETAIL of the first while sizing it, so a long second line
    (a Wi-Fi password) still gets whatever room is left instead of shrinking with the first.
    """

    def fonts(first: int, rest: int) -> list[ImageFont.FreeTypeFont]:
        return [font.font_variant(size=first)] + [font.font_variant(size=rest)] * (len(lines) - 1)

    def fits(first: int, rest: int) -> bool:
        fs = fonts(first, rest)
        return all(f.getlength(t) <= width for f, t in zip(fs, lines, strict=True)) and (
            sum(sum(f.getmetrics()) for f in fs) <= height
        )

    if not fits(MIN_FONT, MIN_FONT):
        raise ValueError("text doesn't fit: split it into more lines, shorten it or use a bigger label")
    widest = _largest(
        lambda d: all(font.font_variant(size=d).getlength(t) <= width for t in lines[1:]), MIN_FONT, height
    )
    first = _largest(lambda s: fits(s, max(MIN_FONT, min(round(s * DETAIL), widest))), MIN_FONT, height)
    return fonts(first, _largest(lambda d: fits(first, d), MIN_FONT, first))


def render(
    lines: list[str],
    qr: str | None = None,
    media: str = "w162h90",
    font: ImageFont.FreeTypeFont | None = None,
) -> Image.Image:
    """Lay the label out landscape, then turn it to the media's own orientation for lp.

    The QR code goes on the right, as tall as the label, in whole-pixel modules so it prints
    crisp. It only shrinks when the text would otherwise not fit at a readable size.
    """
    lines = [line for line in lines if line.strip()]
    if not lines and not qr:
        raise ValueError("nothing to print: give some text or a QR code")
    w, h = media_size(media)
    W, H = max(w, h), min(w, h)
    img = Image.new("L", (W, H), 255)

    if qr:
        code = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
        code.add_data(qr)
        code.make(fit=True)
        code.box_size = (H - 2 * PAD) // code.modules_count
        if code.box_size < MIN_MODULE:
            raise ValueError("QR data is too long for this label size")

    if lines:
        font = font or load_font()
        while True:
            width = W - 2 * PAD - (code.box_size * code.modules_count + PAD if qr else 0)
            try:
                fonts = _fit(lines, font, width, H - 2 * PAD)
                break
            except ValueError:
                if not qr or code.box_size == MIN_MODULE:
                    raise
                code.box_size -= 1
        draw = ImageDraw.Draw(img)
        y = (H - sum(sum(f.getmetrics()) for f in fonts)) // 2
        for text, f in zip(lines, fonts, strict=True):
            x = PAD if qr else (W - f.getlength(text)) / 2
            draw.text((x, y), text, font=f, fill=0, anchor="la")
            y += sum(f.getmetrics())

    if qr:
        im = code.make_image().convert("L")
        img.paste(im, (W - PAD - im.width if lines else (W - im.width) // 2, (H - im.height) // 2))

    return img.rotate(90, expand=True) if w < h else img
