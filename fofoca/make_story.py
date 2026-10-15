#!/usr/bin/env python3
"""Render a vertical (1080x1920) "internet drama / fofoca" story short.

Format modelled on the Laestro-style commentary shorts: a narrator tells a
story in short punchy sentences, every sentence ("beat") cuts to a new visual
(meme, clip, screenshot), and big orange captions pop in 2-3 words at a time.

Each beat is one of two looks:
  full  - the media fills the screen (clip or image with a slow push-in),
          caption in the middle.
  card  - flat grey background, the media shown as a tilted "photo card"
          that pops in, caption near the top.

Narration comes from one of:
  edge    - Microsoft Edge neural TTS (pip install edge-tts), word-level sync
  piper   - offline neural TTS (pip install piper-tts; voice.model = .onnx)
  espeak  - offline espeak-ng (robotic; for previews only)
  file    - your own recorded voice-over (voice.file); beats are timed by
            their "at" field, or spread over the recording by text length
  none    - silent; beat length estimated from text length

Usage:  python3 fofoca/make_story.py [roteiro.json]

Missing media never breaks the render: the beat falls back to a grey card
that names the file it expected, so you can preview a script before you have
collected any media.
"""
import asyncio
import json
import math
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1920
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT_DIR = os.path.join(ROOT, "fonts")

# Measured from the reference (720x1280, scaled to 1080x1920).
CAPTION_Y_FULL = 0.50 * H     # caption centre over full-screen media
CAPTION_Y_CARD = 0.19 * H     # caption centre above a card
CARD_CY = 0.52 * H            # card centre
CARD_MAX = (560, 640)         # card bounding box
GREY = (150, 150, 150)
ORANGE = (255, 165, 0)

CAPTION_POP = 0.10            # seconds for the caption pop
CARD_POP = 0.22               # seconds for the card pop
FLASH = 0.16                  # seconds for the white flash on "flash" beats
CHARS_PER_SEC = 15.0          # speaking-rate estimate for engine "none"
VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv", ".gif")


def font(weight, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, f"Poppins-{weight}.ttf"), size)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def resolve(path, base):
    if not path:
        return None
    for b in (base, ROOT, HERE):
        p = path if os.path.isabs(path) else os.path.join(b, path)
        if os.path.exists(p):
            return p
    return None


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        sys.exit("command failed:\n" + " ".join(cmd) + "\n" + r.stderr[-3000:])


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def has_audio(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                        "stream=index", "-of", "csv=p=0", path], capture_output=True, text=True)
    return bool(r.stdout.strip())


# --------------------------------------------------------------------------
# Narration
# --------------------------------------------------------------------------
def tts_edge(text, voice, out):
    try:
        import edge_tts
        import edge_tts.communicate as comm
    except ImportError:
        sys.exit("engine 'edge' needs:  pip install edge-tts")
    # Honour a custom CA bundle (corporate proxies); edge-tts pins certifi otherwise.
    if os.environ.get("SSL_CERT_FILE"):
        comm._SSL_CTX = ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])

    async def go():
        c = edge_tts.Communicate(text, voice.get("name", "pt-BR-AntonioNeural"),
                                 rate=voice.get("rate", "+10%"), pitch=voice.get("pitch", "+0Hz"),
                                 proxy=os.environ.get("HTTPS_PROXY"))
        await c.save(out)
    asyncio.run(go())


def tts_espeak(text, voice, out):
    if not shutil.which("espeak-ng"):
        sys.exit("engine 'espeak' needs espeak-ng installed")
    wav = out + ".wav"
    run(["espeak-ng", "-v", voice.get("espeak_voice", "pt-br"), "-s", str(voice.get("wpm", 185)),
         "-w", wav, text])
    run(["ffmpeg", "-y", "-v", "error", "-i", wav, out])
    os.remove(wav)


def tts_piper(text, voice, out):
    model = voice.get("model")
    if not model or not os.path.exists(model):
        sys.exit("engine 'piper' needs voice.model pointing at a .onnx voice (pip install piper-tts)")
    wav = out + ".wav"
    r = subprocess.run([sys.executable, "-m", "piper", "-m", model, "-f", wav,
                        "--length-scale", str(voice.get("length_scale", 0.85))],
                       input=text, text=True, capture_output=True)
    if r.returncode:
        sys.exit("piper failed:\n" + r.stderr[-2000:])
    # trim piper's leading/trailing silence and optionally speed it up
    trim = "silenceremove=start_periods=1:start_threshold=-45dB"
    af = f"{trim},areverse,{trim},areverse,atempo={voice.get('tempo', 1.0)}"
    run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-af", af, out])
    os.remove(wav)


TTS = {"edge": tts_edge, "espeak": tts_espeak, "piper": tts_piper}


def plan_timing(cfg, beats, tmp, base):
    """Set beat['_dur'] and return the narration track path (or None)."""
    voice = cfg.get("voice", {})
    engine = voice.get("engine", "edge")
    gap = voice.get("gap", 0.05)

    if engine == "file":
        vo = resolve(voice.get("file"), base)
        if not vo:
            sys.exit(f"voice.file not found: {voice.get('file')}")
        total = duration(vo)
        if all("at" in b for b in beats):
            starts = [b["at"] for b in beats] + [total]
        else:  # spread by text length
            lens = [max(1, len(b["text"])) + b.get("pause", 0) * CHARS_PER_SEC for b in beats]
            acc, starts = 0.0, []
            for n in lens:
                starts.append(total * acc / sum(lens))
                acc += n
            starts.append(total)
        for b, s, e in zip(beats, starts, starts[1:]):
            b["_dur"] = max(0.3, e - s)
        return vo

    clips = []
    for i, b in enumerate(beats):
        pause = b.get("pause", 0)
        if engine == "none" or not b["text"].strip():
            b["_dur"] = max(0.6, len(b["text"]) / CHARS_PER_SEC) + pause
            continue
        mp3 = os.path.join(tmp, f"vo{i:03d}.mp3")
        print(f"  tts {i + 1}/{len(beats)}: {b['text'][:50]}")
        TTS[engine](b["text"], voice, mp3)
        b["_dur"] = duration(mp3) + gap + pause
        clips.append((i, mp3))
    if engine == "none":
        return None

    # one padded WAV per beat so narration lines up with the cuts exactly
    have = dict(clips)
    parts = []
    for i, b in enumerate(beats):
        wav = os.path.join(tmp, f"vo{i:03d}.wav")
        src = ["-i", have[i]] if i in have else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        run(["ffmpeg", "-y", "-v", "error", *src, "-af",
             f"aresample=44100,apad,atrim=0:{b['_dur']:.4f}", "-ac", "2", wav])
        parts.append(wav)
    lst = os.path.join(tmp, "vo.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{p}'\n" for p in parts)
    out = os.path.join(tmp, "narration.wav")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out])
    return out


# --------------------------------------------------------------------------
# Captions
# --------------------------------------------------------------------------
def chunk_words(text, max_words, max_chars):
    words, chunks, cur = text.split(), [], []
    for w in words:
        trial = " ".join(cur + [w])
        if cur and (len(cur) >= max_words or len(trial) > max_chars):
            chunks.append(" ".join(cur))
            cur = []
        cur.append(w)
        # punctuation ends the chunk early, like a human editor would
        if re.search(r"[.!?…,:;]$", w):
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def caption_times(chunks, dur, pause):
    """Spread chunks over the spoken part of the beat by character count."""
    spoken = max(0.2, dur - pause)
    weights = [len(c) + 3 for c in chunks]
    t, out = 0.0, []
    for c, w in zip(chunks, weights):
        out.append((t, c))
        t += spoken * w / sum(weights)
    return out


class CaptionRenderer:
    def __init__(self, cc):
        self.size = cc.get("size", 80)
        self.color = hex_rgb(cc.get("color", "#FFA500"))
        self.glow = hex_rgb(cc.get("glow", "#FF7A00"))
        self.upper = cc.get("uppercase", False)
        self.cache = {}

    def render(self, text):
        key = text
        if key in self.cache:
            return self.cache[key]
        t = text.upper() if self.upper else text
        f = font("Bold", self.size)
        while f.getlength(t) > W - 90 and f.size > 40:
            f = font("Bold", f.size - 2)
        pad = 40
        asc, desc = f.getmetrics()
        img = Image.new("RGBA", (int(f.getlength(t)) + pad * 2, asc + desc + pad * 2), (0, 0, 0, 0))

        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).text((pad, pad), t, font=f, fill=255, stroke_width=4, stroke_fill=255)
        # orange glow underneath, then a tight dark shadow, then the text
        glow = Image.new("RGBA", img.size, self.glow + (0,))
        glow.putalpha(mask.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.75)))
        img.alpha_composite(glow, (0, 10))
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sh.putalpha(mask.filter(ImageFilter.GaussianBlur(4)).point(lambda v: int(v * 0.8)))
        img.alpha_composite(sh, (0, 4))
        ImageDraw.Draw(img).text((pad, pad), t, font=f, fill=self.color,
                                 stroke_width=3, stroke_fill=(40, 22, 0))
        self.cache[key] = img
        return img


# --------------------------------------------------------------------------
# Cards, stickers, CTA bubble
# --------------------------------------------------------------------------
def load_still(path, at=0.0, tmp=None):
    if path.lower().endswith(VIDEO_EXT):
        png = os.path.join(tmp, f"still_{abs(hash((path, at)))}.png")
        run(["ffmpeg", "-y", "-v", "error", "-ss", str(at), "-i", path, "-frames:v", "1", png])
        path = png
    return ImageOps.exif_transpose(Image.open(path)).convert("RGBA")


def make_card(img, tilt, box=CARD_MAX):
    k = min(box[0] / img.width, box[1] / img.height)  # fit the box, upscaling small images
    img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)
    r = 14
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, img.width - 1, img.height - 1], r, fill=255)
    img.putalpha(m)
    pad = 40
    out = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([pad + 6, pad + 12, pad + img.width + 6, pad + img.height + 12],
                                         r, fill=(0, 0, 0, 120))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
    out.alpha_composite(img, (pad, pad))
    return out.rotate(tilt, resample=Image.BICUBIC, expand=True)


def placeholder_card(label):
    img = Image.new("RGBA", (520, 400), (60, 60, 60, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 519, 399], outline=(255, 165, 0, 255), width=6)
    f = font("Bold", 34)
    d.text((260, 150), "COLOQUE A MÍDIA", font=f, fill=(255, 165, 0), anchor="mm")
    fs = font("SemiBold", 24)
    words, lines, cur = label.replace("/", "/ ").split(), [], ""
    for w in words:
        if fs.getlength(cur + w) > 470 and cur:
            lines.append(cur)
            cur = ""
        cur += w if cur.endswith("/") or not cur else " " + w
    lines.append(cur)
    for k, ln in enumerate(lines[:4]):
        d.text((260, 215 + k * 34), ln.replace("/ ", "/"), font=fs, fill=(235, 235, 235), anchor="mm")
    return img


def speech_bubble(text):
    f = font("SemiBold", 30)
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if f.getlength(trial) > 330 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    lines.append(cur)
    lh = 38
    bw = int(max(f.getlength(ln) for ln in lines)) + 70
    bh = lh * len(lines) + 50
    img = Image.new("RGBA", (bw + 10, bh + 50), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([3, 3, bw, bh], fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=4)
    d.polygon([(bw * 0.28, bh - 12), (bw * 0.18, bh + 44), (bw * 0.42, bh - 6)],
              fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
    d.line([(bw * 0.28, bh - 8), (bw * 0.42, bh - 8)], fill=(255, 255, 255, 255), width=8)
    y = (bh - lh * len(lines)) / 2 + lh / 2
    for ln in lines:
        d.text((bw / 2, y), ln, font=f, fill=(20, 20, 20), anchor="mm")
        y += lh
    return img


def ease_out_back(p):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def scaled(img, s, alpha=1.0):
    im = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.BICUBIC)
    if alpha < 1:
        im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    return im


def shake(b, lt):
    """Decaying (dx, dy) offset for beats marked "shake"."""
    if not b.get("shake") or lt > 0.6:
        return 0.0, 0.0
    k = math.exp(-lt * 7) * 26
    return math.sin(lt * 70) * k, math.cos(lt * 55) * k


def paste_c(canvas, img, cx, cy):
    canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


# --------------------------------------------------------------------------
# Background per beat (ffmpeg)
# --------------------------------------------------------------------------
# Per-beat "fx" for full-screen media (ffmpeg filters, applied after the motion).
# "wave" and "pulse" are handled separately in build_bg.
FFMPEG_FX = {
    "wobble": f"scale={int(W * 1.1)}:{int(H * 1.1)},rotate=a='0.045*sin(t*5)',crop={W}:{H}",
    "rgb": "rgbashift=rh=-12:bh=12:edge=smear",
    "glitch": "rgbashift=rh=-24:gv=8:bh=24:edge=smear,noise=alls=30:allf=t",
    "bw": "hue=s=0,eq=contrast=1.3",
    "deepfry": "eq=saturation=2.6:contrast=1.5:brightness=0.04,unsharp=7:7:2.5,noise=alls=14:allf=t",
    "grain": "noise=alls=16:allf=t+u",
    "vignette": "vignette=PI/4.5",
}
# Whole-video fx (top-level "global_fx"), applied over everything in the final encode.
GLOBAL_FX = {"grain": "noise=alls=7:allf=t+u", "vignette": "vignette=PI/5"}


def card_fx_static(img, fx):
    """Colour fx baked into a card once."""
    if "bw" in fx:
        a = img.getchannel("A")
        img = ImageOps.grayscale(img).convert("RGBA")
        img = ImageEnhance.Contrast(img).enhance(1.3)
        img.putalpha(a)
    if "deepfry" in fx:
        a = img.getchannel("A")
        img = ImageEnhance.Color(img).enhance(2.6)
        img = ImageEnhance.Contrast(img).enhance(1.5)
        img = ImageEnhance.Sharpness(img).enhance(4)
        img.putalpha(a)
    return img


def card_fx_frame(im, fx, lt, seed):
    """Per-frame fx on a (scaled) card: wave, rgb split, glitch bands."""
    if not any(f in fx for f in ("wave", "rgb", "glitch")):
        return im
    arr = np.asarray(im)
    h, w = arr.shape[:2]
    if "wave" in fx:
        shift = (14 * np.sin(2 * np.pi * np.arange(h) / 160 + lt * 7)).astype(int)
        idx = np.clip(np.arange(w)[None, :] - shift[:, None], 0, w - 1)
        arr = np.take_along_axis(arr, np.repeat(idx[:, :, None], 4, axis=2), axis=1)
    if "rgb" in fx or "glitch" in fx:
        n = 5 if "rgb" in fx else 11
        out = arr.copy()
        out[..., 0] = np.roll(arr[..., 0], -n, axis=1)
        out[..., 2] = np.roll(arr[..., 2], n, axis=1)
        out[..., 3] = np.maximum(arr[..., 3], np.maximum(np.roll(arr[..., 3], -n, 1), np.roll(arr[..., 3], n, 1)))
        arr = out
    if "glitch" in fx:
        rng = np.random.default_rng(seed + int(lt * 30))
        if rng.random() < 0.45:  # tear a few horizontal bands sideways
            arr = arr.copy()
            for _ in range(3):
                y0, hh = int(rng.integers(0, max(1, h - 40))), int(rng.integers(8, 40))
                arr[y0:y0 + hh] = np.roll(arr[y0:y0 + hh], int(rng.integers(-40, 40)), axis=1)
    return Image.fromarray(arr, "RGBA")


def impact_frame(b, media, tmp):
    """Pre-render the "impact frame" shown at the start of a beat.

    "impact": {"text": "9 PRESOS"}                  -> white screen, huge black text
    "impact": {"style": "invert"}                   -> the beat's own image as a blown-out
                                                       black-and-white negative (anime style)
    Optional "seconds" (default 0.35) for how long it holds.
    """
    imp = b["impact"]
    if imp.get("style") == "invert" and media:
        src = load_still(media, b.get("start", 0), tmp).convert("RGB")
        g = ImageOps.autocontrast(ImageOps.grayscale(ImageOps.fit(src, (W, H), Image.LANCZOS)), cutoff=3)
        g = g.point(lambda v: 0 if v > 110 else 255)  # hard threshold, inverted
        img = g.convert("RGBA")
    else:
        img = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    text = imp.get("text", "")
    if text:
        f = font("ExtraBold", imp.get("size", 190))
        lines = text.upper().split("\n") if "\n" in text else wrap_lines(text.upper(), f, W - 120)
        while max(f.getlength(ln) for ln in lines) > W - 100 and f.size > 60:
            f = font("ExtraBold", f.size - 6)
            lines = wrap_lines(text.upper(), f, W - 120)
        asc, desc = f.getmetrics()
        lh = asc + desc
        layer = Image.new("RGBA", (W, lh * len(lines) + 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        col = (255, 255, 255) if imp.get("style") == "invert" else (0, 0, 0)
        stroke = (0, 0, 0) if imp.get("style") == "invert" else (255, 255, 255)
        for k, ln in enumerate(lines):
            d.text((W / 2, 20 + k * lh), ln, font=f, fill=col, anchor="ma", stroke_width=6, stroke_fill=stroke)
        b["_impact_text"] = layer
    return img


def wrap_lines(text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if fnt.getlength(trial) > max_w and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    return lines + [cur]


def build_bg(i, b, media, cfg, tmp):
    dur, fps = b["_dur"], cfg["fps"]
    out = os.path.join(tmp, f"bg{i:03d}.mp4")
    tail = f"fps={fps},format=yuv420p,setsar=1"
    z = b.get("zoom", 1.0)
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if b["_mode"] == "full" and media and media.lower().endswith(VIDEO_EXT):
        cmd += ["-stream_loop", "-1", "-ss", str(b.get("start", 0)), "-i", media]
        vf = (f"scale={int(W * z)}:{int(H * z)}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H},{tail}")
    elif b["_mode"] == "full" and media:
        # still image (prescaled 2x so zoompan doesn't jitter): a quick punch-in on the
        # cut that settles, then a steady push or pan so the frame never sits still
        frames = int(math.ceil(dur * fps)) + 1
        speed = b.get("push", 0.18) / max(1, frames)
        punch = b.get("punch", 0.14)
        motion = b.get("motion", ("in", "left", "in", "right")[i % 4])
        zexpr = f"{z}+{punch}*exp(-on/4)+{speed:.6f}*on"
        if "pulse" in b.get("fx", []):  # zoom breathing in and out
            zexpr += "+0.05*(1+sin(on*0.35))"
        x = "iw/2-(iw/zoom/2)"
        if motion == "left":
            x = f"(iw-iw/zoom)*(1-on/{frames})"
        elif motion == "right":
            x = f"(iw-iw/zoom)*on/{frames}"
        y = "ih/2-(ih/zoom/2)"
        if b.get("shake"):  # decaying camera shake for impact lines
            x += "+50*sin(on*2.3)*exp(-on/9)"
            y += "+40*cos(on*1.9)*exp(-on/9)"
        cmd += ["-loop", "1", "-framerate", str(fps), "-i", media]
        vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
              f"zoompan=z='{zexpr}':x='{x}':y='{y}'"
              f":d={frames}:s={W}x{H}:fps={fps},{tail}")
    else:
        bg = cfg.get("card_bg", "#969696").lstrip("#")
        cmd += ["-f", "lavfi", "-i", f"color=c=0x{bg}:s={W}x{H}:r={fps}"]
        vf = tail
    fx = b.get("fx", []) if b["_mode"] == "full" else []
    vf += "".join("," + FFMPEG_FX[f] for f in fx if f in FFMPEG_FX)
    if "wave" in fx:
        # horizontal sine wobble: displace with a scrolling sine map
        lam, amp = b.get("wave_length", 220), b.get("wave_amp", 22)
        xmap = os.path.join(tmp, f"wave_{lam}_{amp}.png")
        if not os.path.exists(xmap):
            rows = (128 + amp * np.sin(2 * np.pi * np.arange(H + lam) / lam)).astype(np.uint8)
            Image.fromarray(np.repeat(rows[:, None], W, axis=1), "L").save(xmap)
        cmd += ["-loop", "1", "-framerate", str(fps), "-i", xmap,
                "-f", "lavfi", "-i", f"color=c=0x808080:s={W}x{H}:r={fps}"]
        fc = (f"[0:v]{vf},format=gbrp[m];"
              f"[1:v]crop={W}:{H}:0:'mod(n*9,{lam})',format=gbrp[xm];[2:v]format=gbrp[ym];"
              f"[m][xm][ym]displace=edge=smear,format=yuv420p[v]")
        cmd += ["-filter_complex", fc, "-map", "[v]"]
    else:
        cmd += ["-map", "0:v:0", "-vf", vf]
    cmd += ["-t", f"{dur:.4f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", out]
    run(cmd)
    return out


# --------------------------------------------------------------------------
def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "roteiro.json")
    with open(cfg_path) as f:
        cfg = json.load(f)
    base = os.path.dirname(os.path.abspath(cfg_path))
    cfg.setdefault("fps", 30)
    fps = cfg["fps"]
    out = cfg.get("output", "output/fofoca.mp4")
    out = out if os.path.isabs(out) else os.path.join(ROOT, out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    beats = cfg["beats"]
    cc = cfg.get("caption", {})

    tmp = tempfile.mkdtemp(prefix="fofoca_")
    try:
        print("Narration…")
        narration = plan_timing(cfg, beats, tmp, base)

        print("Media…")
        renderer = CaptionRenderer(cc)
        t0 = 0.0
        for i, b in enumerate(beats):
            media = resolve(b.get("media"), base)
            mode = b.get("mode", "full")
            if not media:
                if b.get("media"):
                    print(f"  ! beat {i + 1}: missing {b['media']} -> placeholder card")
                mode = "card"
            b["_mode"], b["_start"] = mode, t0
            t0 += b["_dur"]
            if mode == "card":
                tilt = b.get("tilt", (-3, 2.5, -1.5, 3)[i % 4])
                still = load_still(media, b.get("start", 0), tmp) if media else \
                    placeholder_card(b.get("media") or "imagem/print/meme")
                b["_card"] = make_card(card_fx_static(still.convert("RGBA"), b.get("fx", [])),
                                       tilt, b.get("card_max", CARD_MAX))
            if b.get("impact"):
                b["_impact"] = impact_frame(b, media, tmp)
                b["_impact_s"] = b["impact"].get("seconds", 0.35)
            st = b.get("sticker")
            if st:
                sp = resolve(st.get("path"), base)
                if sp:
                    simg = load_still(sp, 0, tmp)
                    simg.thumbnail((st.get("w", 160), st.get("w", 160) * 3), Image.LANCZOS)
                    b["_sticker"] = (simg, st.get("x", 0.15) * W, st.get("y", 0.68) * H)
                else:
                    print(f"  ! beat {i + 1}: sticker missing {st.get('path')}")
            b["_caps"] = caption_times(chunk_words(b["text"], cc.get("max_words", 3),
                                                   cc.get("max_chars", 20)),
                                       b["_dur"], b.get("pause", 0))
            for _, c in b["_caps"]:
                renderer.render(c)
        total = t0
        print(f"  {len(beats)} beats, {total:.1f}s total")
        if total < 61 and cfg.get("warn_under_61s", True):
            print(f"  ! {total:.1f}s: TikTok Creator Rewards only pays on videos over 1 minute")

        print("Backgrounds…")
        segs = [build_bg(i, b, resolve(b.get("media"), base), cfg, tmp) for i, b in enumerate(beats)]
        lst = os.path.join(tmp, "bg.txt")
        with open(lst, "w") as f:
            f.writelines(f"file '{p}'\n" for p in segs)
        bg = os.path.join(tmp, "bg.mp4")
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", bg])

        print("Audio mix…")
        audio = os.path.join(tmp, "mix.wav")
        ins, fl, n = [], [], 0
        if narration:
            ins += ["-i", narration]
            fl.append(f"[{n}:a]aresample=44100,loudnorm=I=-14:TP=-1.5:LRA=11[vo]")
            n += 1
        music = resolve(cfg.get("music"), base)
        if music:
            ins += ["-stream_loop", "-1", "-ss", str(cfg.get("music_start", 0)), "-i", music]
            fl.append(f"[{n}:a]aresample=44100,volume={cfg.get('music_volume', 0.12)}[mu]")
            n += 1
        # sound effects: an automatic whoosh/pop on every cut, plus per-beat extras
        # ("sfx": "boom.wav" or [{"path": "riser.wav", "offset": -1.5, "volume": 0.5}])
        auto = cfg.get("auto_sfx", {})
        sfx_mix = []
        for i, b in enumerate(beats):
            hits = b.get("sfx") or []
            hits = [hits] if isinstance(hits, (str, dict)) else list(hits)
            hits = [{"path": h} if isinstance(h, str) else h for h in hits]
            if auto.get(b["_mode"]) and b.get("auto_sfx", True):
                hits.insert(0, {"path": auto[b["_mode"]], "volume": auto.get("volume", 0.35)})
            for j, h in enumerate(hits):
                sp = resolve(h.get("path"), base)
                if not sp:
                    print(f"  ! beat {i + 1}: sfx missing {h.get('path')}")
                    continue
                ins += ["-i", sp]
                ms = max(0, int((b["_start"] + h.get("offset", 0)) * 1000))
                vol = h.get("volume", b.get("sfx_volume", 0.6))
                fl.append(f"[{n}:a]aresample=44100,aformat=channel_layouts=stereo,volume={vol},"
                          f"adelay={ms}|{ms}[s{i}_{j}]")
                sfx_mix.append(f"[s{i}_{j}]")
                n += 1
        labels = (["[vo]"] if narration else []) + (["[mu]"] if music else []) + sfx_mix
        if labels:
            fl.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest,"
                      f"atrim=0:{total:.4f},apad=whole_dur={total:.4f},alimiter=limit=0.89[a]")
            run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", ";".join(fl),
                 "-map", "[a]", "-ac", "2", audio])
        else:
            run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", f"{total:.4f}",
                 "-i", "anullsrc=r=44100:cl=stereo", audio])

        print("Overlay + encode…")
        cta = cfg.get("cta")
        if cta and "beat" in cta:  # pin the bubble to a beat instead of fixed seconds
            cta = dict(cta, start=beats[cta["beat"]]["_start"])
            cta["end"] = cta["start"] + cta.get("seconds", 4)
        bubble = speech_bubble(cta["text"]) if cta and cta.get("text") else None
        handle_img = None
        if cfg.get("handle"):
            hf = font("SemiBold", 30)
            handle_img = Image.new("RGBA", (int(hf.getlength(cfg["handle"])) + 20, 50), (0, 0, 0, 0))
            ImageDraw.Draw(handle_img).text((10, 6), cfg["handle"], font=hf, fill=(255, 255, 255, 150))

        enc = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error", "-i", bg, "-i", audio,
             "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
             "-filter_complex", "[0:v][2:v]overlay=0:0:format=auto"
             + "".join("," + GLOBAL_FX[f] for f in cfg.get("global_fx", []) if f in GLOBAL_FX)
             + ",format=yuv420p[v]",
             "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             # cap the bitrate: film grain would otherwise balloon the file
             "-maxrate", "8M", "-bufsize", "16M",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.4f}", out],
            stdin=subprocess.PIPE)

        nframes = int(round(total * fps))
        bi, last_key, last_bytes = 0, None, None
        for k in range(nframes):
            t = k / fps
            while bi < len(beats) - 1 and t >= beats[bi + 1]["_start"]:
                bi += 1
            b = beats[bi]
            lt = t - b["_start"]
            ci = max(j for j, (s, _) in enumerate(b["_caps"]) if s <= lt + 1e-6) if b["_caps"] else -1
            cap_t = lt - b["_caps"][ci][0] if ci >= 0 else 9
            show_cta = bubble is not None and cta.get("start", 0) <= t < cta.get("end", 0)
            card = b.get("_card")
            # cards, stickers, flashes and shakes move every frame; only a bare caption
            # over full-screen media can reuse the previous frame
            animating = (lt < CARD_POP or cap_t < CAPTION_POP or card is not None
                         or b.get("_sticker") is not None or lt < FLASH or show_cta
                         or lt < b.get("_impact_s", 0) + FLASH)
            key = (bi, ci, show_cta)
            if not animating and key == last_key:
                enc.stdin.write(last_bytes)
                continue

            fr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            sx_, sy_ = shake(b, lt)
            if card is not None:
                p = min(1.0, lt / CARD_POP)
                # pop in, then keep breathing: slow grow, float and sway
                s_ = (0.55 + 0.45 * ease_out_back(p)) * (1 + 0.07 * lt / b["_dur"])
                fx = b.get("fx", [])
                if "pulse" in fx:
                    s_ *= 1 + 0.05 * math.sin(lt * 10)
                im = card_fx_frame(scaled(card, s_, min(1, p * 2.5)), fx, lt, bi)
                sway = math.sin(lt * 1.8 + bi) * (6 if "wobble" in fx else 1.6)
                if p >= 1:
                    im = im.rotate(sway, resample=Image.BILINEAR, expand=True)
                paste_c(fr, im, W / 2 + sx_, CARD_CY + math.sin(lt * 2.4 + bi) * 12 + sy_)
            if b.get("_sticker"):
                simg, stx, sty = b["_sticker"]
                p = min(1.0, lt / CARD_POP)
                im = scaled(simg, 0.3 + 0.7 * ease_out_back(p))
                im = im.rotate(math.sin(lt * 5) * 8, resample=Image.BILINEAR, expand=True)
                paste_c(fr, im, stx, sty + math.sin(lt * 6) * 10)
            if ci >= 0:
                cimg = renderer.render(b["_caps"][ci][1])
                p = min(1.0, cap_t / CAPTION_POP)
                cy = b.get("caption_y", CAPTION_Y_CARD / H if card is not None else CAPTION_Y_FULL / H) * H
                if p < 1:
                    cimg = scaled(cimg, 1.35 - 0.35 * ease_out_back(p))
                paste_c(fr, cimg, W / 2 + sx_ * 0.5, cy + sy_ * 0.5)
            if show_cta:
                p = min(1.0, (t - cta["start"]) / CARD_POP)
                im = scaled(bubble, (0.4 + 0.6 * ease_out_back(p)) * (1 + 0.04 * math.sin(t * 7)))
                paste_c(fr, im, W * 0.58, H * 0.36)
            imp_s = b.get("_impact_s", 0)
            if imp_s and lt < imp_s:
                # impact frame: covers everything, text slams in and shakes
                fr = b["_impact"].copy()
                if b.get("_impact_text") is not None:
                    p = min(1.0, lt / 0.08)
                    k = math.exp(-lt * 9) * 18
                    paste_c(fr, scaled(b["_impact_text"], 1.6 - 0.6 * p),
                            W / 2 + math.sin(lt * 90) * k, H / 2 + math.cos(lt * 70) * k)
            elif imp_s and lt < imp_s + FLASH:  # fade out of the white
                fl_ = Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - (lt - imp_s) / FLASH))))
                fr.alpha_composite(fl_)
            elif b.get("flash") and lt < FLASH:  # white flash on the cut
                fl_ = Image.new("RGBA", (W, H), (255, 255, 255, int(220 * (1 - lt / FLASH))))
                fr.alpha_composite(fl_)
            if handle_img:
                fr.alpha_composite(handle_img, (W - handle_img.width - 30, H - 330))
            data = fr.tobytes()
            if not animating:
                last_key, last_bytes = key, data
            enc.stdin.write(data)
            if k % (fps * 10) == 0:
                print(f"  {t:5.1f}s / {total:.1f}s")
        enc.stdin.close()
        if enc.wait():
            sys.exit("final encode failed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("Done ->", out)


if __name__ == "__main__":
    main()
