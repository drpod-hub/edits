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

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

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
        (tts_edge if engine == "edge" else tts_espeak)(b["text"], voice, mp3)
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
        # a sentence break ends the chunk early, like a human editor would
        if re.search(r"[.!?…]$", w):
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


def make_card(img, tilt):
    img = img.copy()
    img.thumbnail(CARD_MAX, Image.LANCZOS)
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


def paste_c(canvas, img, cx, cy):
    canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


# --------------------------------------------------------------------------
# Background per beat (ffmpeg)
# --------------------------------------------------------------------------
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
        # still image: slow push-in (prescale 2x so zoompan doesn't jitter)
        frames = int(math.ceil(dur * fps)) + 1
        speed = b.get("push", 0.10) / max(1, frames)
        cmd += ["-loop", "1", "-framerate", str(fps), "-i", media]
        vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
              f"zoompan=z='{z}+{speed:.6f}*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={frames}:s={W}x{H}:fps={fps},{tail}")
    else:
        bg = cfg.get("card_bg", "#969696").lstrip("#")
        cmd += ["-f", "lavfi", "-i", f"color=c=0x{bg}:s={W}x{H}:r={fps}"]
        vf = tail
    cmd += ["-t", f"{dur:.4f}", "-map", "0:v:0", "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", out]
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
                b["_card"] = make_card(still, tilt)
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
        # per-beat sound effects (whoosh, vine boom...) at the start of the beat
        sfx_mix = []
        for i, b in enumerate(beats):
            sp = resolve(b.get("sfx"), base)
            if sp:
                ins += ["-i", sp]
                ms = int(b["_start"] * 1000)
                fl.append(f"[{n}:a]aresample=44100,volume={b.get('sfx_volume', 0.6)},"
                          f"adelay={ms}|{ms}[s{i}]")
                sfx_mix.append(f"[s{i}]")
                n += 1
        labels = (["[vo]"] if narration else []) + (["[mu]"] if music else []) + sfx_mix
        if labels:
            fl.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest,"
                      f"atrim=0:{total:.4f},apad=whole_dur={total:.4f}[a]")
            run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", ";".join(fl),
                 "-map", "[a]", "-ac", "2", audio])
        else:
            run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", f"{total:.4f}",
                 "-i", "anullsrc=r=44100:cl=stereo", audio])

        print("Overlay + encode…")
        cta = cfg.get("cta")
        bubble = speech_bubble(cta["text"]) if cta and cta.get("text") else None
        handle_img = None
        if cfg.get("handle"):
            hf = font("SemiBold", 30)
            handle_img = Image.new("RGBA", (int(hf.getlength(cfg["handle"])) + 20, 50), (0, 0, 0, 0))
            ImageDraw.Draw(handle_img).text((10, 6), cfg["handle"], font=hf, fill=(255, 255, 255, 150))

        enc = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error", "-i", bg, "-i", audio,
             "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
             "-filter_complex", "[0:v][2:v]overlay=0:0:format=auto,format=yuv420p[v]",
             "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
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
            animating = lt < CARD_POP or cap_t < CAPTION_POP
            key = (bi, ci, show_cta)
            if not animating and key == last_key:
                enc.stdin.write(last_bytes)
                continue

            fr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            card = b.get("_card")
            if card is not None:
                p = min(1.0, lt / CARD_POP)
                paste_c(fr, scaled(card, 0.55 + 0.45 * ease_out_back(p), min(1, p * 2.5)),
                        W / 2, CARD_CY)
            if b.get("_sticker"):
                simg, sx, sy = b["_sticker"]
                paste_c(fr, simg, sx, sy)
            if ci >= 0:
                cimg = renderer.render(b["_caps"][ci][1])
                p = min(1.0, cap_t / CAPTION_POP)
                cy = b.get("caption_y", CAPTION_Y_CARD / H if card is not None else CAPTION_Y_FULL / H) * H
                paste_c(fr, scaled(cimg, 1.18 - 0.18 * p) if p < 1 else cimg, W / 2, cy)
            if show_cta:
                paste_c(fr, bubble, W * 0.58, H * 0.36)
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
