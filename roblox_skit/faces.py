"""Roblox-style face decals and chat bubbles, drawn with Pillow."""

from PIL import Image, ImageDraw, ImageFont

S = 512  # face texture size; the face plane is 1x1 stud on the head front
INK = (20, 20, 20, 255)
WHITE = (255, 255, 255, 255)
EYE_Y, EYE_DX, MOUTH_Y = 215, 82, 330


def _ellipse(d, cx, cy, rx, ry, fill, outline=None, width=0):
    d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=fill, outline=outline, width=width)


def _bean_eyes(d, look=0, lid=0.0):
    """Classic solid black oval eyes; look shifts them, lid covers the top fraction."""
    for side in (-1, 1):
        cx = S // 2 + side * EYE_DX + look * 34
        _ellipse(d, cx, EYE_Y, 30, 52, INK)
        _ellipse(d, cx - 9, EYE_Y - 22, 9, 13, WHITE)
        if lid:
            top = EYE_Y - 56
            d.rectangle((cx - 40, top, cx + 40, top + int(112 * lid)), fill=(0, 0, 0, 0))
            d.line((cx - 36, top + int(112 * lid), cx + 36, top + int(112 * lid)), fill=INK, width=12)


def _wide_eyes(d, pupil=12):
    for side in (-1, 1):
        cx = S // 2 + side * EYE_DX
        _ellipse(d, cx, EYE_Y, 50, 56, WHITE, INK, 9)
        _ellipse(d, cx, EYE_Y + 4, pupil, pupil, INK)


def _brows(d, inner, outer, y=128):
    """inner/outer: vertical offsets of each brow end (negative = up)."""
    for side in (-1, 1):
        cx = S // 2 + side * EYE_DX
        d.line((cx - side * 40, y + inner, cx + side * 44, y + outer), fill=INK, width=14)


def _arc(d, cx, cy, w, h, start, end, width=12):
    d.arc((cx - w, cy - h, cx + w, cy + h), start, end, fill=INK, width=width)


def face(name):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = S // 2
    if name in ("smile", "look_l", "look_r"):
        _bean_eyes(d, look={"look_l": -1, "look_r": 1}.get(name, 0))
        _arc(d, c, MOUTH_Y - 40, 70, 50, 20, 160)
    elif name == "happy":
        for side in (-1, 1):
            _arc(d, c + side * EYE_DX, EYE_Y + 20, 34, 34, 200, 340, 14)
        d.chord((c - 85, MOUTH_Y - 70, c + 85, MOUTH_Y + 70), 0, 180, fill=INK)
        d.chord((c - 55, MOUTH_Y + 20, c + 55, MOUTH_Y + 66), 0, 180, fill=(230, 80, 90, 255))
    elif name in ("smirk", "sneaky_l", "sneaky_r"):
        _bean_eyes(d, look={"sneaky_l": -1, "sneaky_r": 1}.get(name, 0), lid=0.42)
        _brows(d, 14, -14, y=140)
        d.line((c - 60, MOUTH_Y + 8, c + 30, MOUTH_Y + 8), fill=INK, width=12)
        _arc(d, c + 30, MOUTH_Y - 22, 30, 30, 0, 90, 12)
    elif name == "deadpan":
        for side in (-1, 1):
            cx = c + side * EYE_DX
            _ellipse(d, cx, EYE_Y, 46, 40, WHITE, INK, 8)
            d.pieslice((cx - 46, EYE_Y - 40, cx + 46, EYE_Y + 40), 180, 360, fill=INK)
            _ellipse(d, cx, EYE_Y + 14, 11, 11, INK)
        d.line((c - 55, MOUTH_Y + 10, c + 55, MOUTH_Y + 10), fill=INK, width=12)
    elif name == "shock":
        _wide_eyes(d)
        _brows(d, -30, -10, y=118)
        _ellipse(d, c, MOUTH_Y + 18, 38, 52, INK)
    elif name == "scream":
        _wide_eyes(d, pupil=9)
        _brows(d, 22, -18, y=125)
        d.rounded_rectangle((c - 90, MOUTH_Y - 40, c + 90, MOUTH_Y + 90), 40, fill=INK)
        d.rounded_rectangle((c - 70, MOUTH_Y - 28, c + 70, MOUTH_Y - 6), 8, fill=WHITE)
        _ellipse(d, c, MOUTH_Y + 60, 50, 22, (230, 80, 90, 255))
    elif name == "sad":
        _bean_eyes(d, look=0)
        _brows(d, -26, 10, y=128)
        d.rounded_rectangle((c + EYE_DX - 12, EYE_Y + 40, c + EYE_DX + 12, EYE_Y + 130), 12,
                            fill=(90, 170, 255, 230))
        _arc(d, c, MOUTH_Y + 50, 55, 38, 200, 340)
    elif name == "blink":
        for side in (-1, 1):
            d.line((c + side * EYE_DX - 30, EYE_Y, c + side * EYE_DX + 30, EYE_Y), fill=INK, width=12)
        _arc(d, c, MOUTH_Y - 40, 70, 50, 20, 160)
    elif name == "counting":
        for side in (-1, 1):
            _arc(d, c + side * EYE_DX, EYE_Y - 20, 32, 28, 20, 160, 12)
        _ellipse(d, c, MOUTH_Y + 10, 20, 16, INK)
    else:
        raise ValueError(name)
    return img


FACES = ["smile", "look_l", "look_r", "happy", "smirk", "sneaky_l", "sneaky_r", "deadpan",
         "shock", "scream", "sad", "blink", "counting"]


def bubble(text, font_path):
    """White rounded chat bubble with a tail, Roblox chat style. Returns RGBA image."""
    font = ImageFont.truetype(font_path, 96)
    l, t, r, b = font.getbbox(text)
    pad_x, pad_y, tail = 56, 34, 34
    w, h = (r - l) + 2 * pad_x, 120 + 2 * pad_y
    img = Image.new("RGBA", (w, h + tail), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(255, 255, 255, 245))
    d.polygon([(w / 2 - 30, h - 2), (w / 2 + 30, h - 2), (w / 2, h + tail)], fill=(255, 255, 255, 245))
    d.text((w / 2, h / 2), text, font=font, fill=(25, 25, 25, 255), anchor="mm")
    return img


if __name__ == "__main__":
    import sys
    out = sys.argv[1]
    sheet = Image.new("RGBA", (S * 5, S * 3), (240, 200, 60, 255))
    for i, n in enumerate(FACES):
        f = face(n)
        sheet.alpha_composite(f, ((i % 5) * S, (i // 5) * S))
    sheet.save(out)
