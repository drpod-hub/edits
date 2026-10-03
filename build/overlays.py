"""Render transparent PNG overlays (scoreboard, hook title, end card) for the Short."""
import sys
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
OUT = sys.argv[1] if len(sys.argv) > 1 else "."
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

RED = (225, 30, 45)
GREEN = (40, 215, 90)
WHITE = (255, 255, 255)


def flag_denmark(w, h):
    im = Image.new("RGBA", (w, h), (200, 16, 46, 255))
    d = ImageDraw.Draw(im)
    t = h // 7
    d.rectangle([w * 0.33 - t / 2, 0, w * 0.33 + t / 2, h], fill=WHITE)
    d.rectangle([0, h / 2 - t / 2, w, h / 2 + t / 2], fill=WHITE)
    return im


def flag_portugal(w, h):
    im = Image.new("RGBA", (w, h), (218, 41, 28, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w * 0.4, h], fill=(4, 106, 56))
    r = h * 0.3
    cx, cy = w * 0.4, h / 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 205, 0))
    r2 = r * 0.55
    d.rounded_rectangle([cx - r2 * 0.8, cy - r2, cx + r2 * 0.8, cy + r2 * 0.9], radius=6, fill=WHITE,
                        outline=(218, 41, 28), width=4)
    return im


def text(d, xy, s, size, fill, anchor="mm", stroke=6):
    f = ImageFont.truetype(BOLD, size)
    d.text(xy, s, font=f, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=(0, 0, 0))


def shadowed(draw_fn):
    """Draw onto a layer, then composite a soft drop shadow under it."""
    from PIL import ImageFilter
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_fn(layer)
    alpha = layer.split()[3]
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda a: int(a * 0.7)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.alpha_composite(shadow, (6, 8))
    out.alpha_composite(layer)
    return out


def scoreboard(im):
    d = ImageDraw.Draw(im)
    y = 1400
    fw, fh = 96, 66
    for img, x in ((flag_denmark(fw, fh), 230), (flag_portugal(fw, fh), W - 230 - fw)):
        b = Image.new("RGBA", (fw + 8, fh + 8), (0, 0, 0, 255))
        im.alpha_composite(b, (x - 4, y - fh // 2 - 4))
        im.alpha_composite(img, (x, y - fh // 2))
    text(d, (W / 2 - 110, y), "2", 92, RED)
    text(d, (W / 2, y), "-", 92, WHITE)
    text(d, (W / 2 + 110, y), "4", 92, GREEN)


def hook(im):
    d = ImageDraw.Draw(im)
    text(d, (W / 2, 330), "PORTUGAL", 120, WHITE, stroke=8)
    text(d, (W / 2, 450), "SILENCED COPENHAGEN", 64, (255, 215, 0), stroke=6)


def endcard(im):
    d = ImageDraw.Draw(im)
    text(d, (W / 2, 330), "WHO WINS THE", 78, WHITE, stroke=7)
    text(d, (W / 2, 430), "NATIONS LEAGUE?", 92, (255, 215, 0), stroke=8)


for name, fn in (("score", scoreboard), ("hook", hook), ("end", endcard)):
    shadowed(fn).save(f"{OUT}/{name}.png")
print("ok")
