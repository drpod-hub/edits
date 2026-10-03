# Ranga Playtime — YouTube Short

Vertical (1080x1920, ~62s) edit of Crunchyroll's *"Survive Ranga Playtime Challenge"* clip
(That Time I Got Reincarnated as a Slime).

## What the edit does
- **Cold-open hook (0–3s):** opens on the payoff (the captain spinning like a washing machine,
  Ranga pinning him) with a "HOW IT ENDED 💀" sticker, then a white flash into "HOW IT STARTED 👇".
- **Persistent title:** "HE TRIED TO 1v1 RIMURU'S 'GOOD BOY' 💀".
- **English captions** for the Japanese dialogue, speaker tags for Gobta/Ranga, keywords in yellow.
- **Meme stickers** on each beat: Bowling for Knights 🎳, The 'Puppy' ⚡, Main Character Aura ✨,
  Gobta's Battle Cry, Playtime 🐶, His Idea of 'Gentle' 🐾, The One Name He Fears 😰, Ranga 1 — Knights 0 🏆.
- Cut the slow Gabiru-squad dialogue and the Crunchyroll end card, zoom punches on reaction shots,
  bass "boom" hits on the punchlines, orange progress bar, 1.1x pacing, loudness normalised to -14 LUFS.

## Rebuild
```
python3 build.py SOURCE.mp4 ranga_playtime_short.mp4
```
Needs ffmpeg, Pillow and the Noto Color Emoji font. All cuts, captions and stickers are data
at the top of `build.py` (source-video timestamps), so retiming or rewording is a one-line change.

Fonts: Anton and Bangers (SIL Open Font License, via Fontsource).

## Upload kit
**Title:** He Challenged Rimuru's "Good Boy" to a 1v1 💀 #tensura #anime

**Description:**
Never fight the dog. Ranga just wanted to play 🐺
Anime: That Time I Got Reincarnated as a Slime (Tensura) — clip via Crunchyroll.

**Hashtags:** #shorts #tensura #ranga #slime #anime #animefunny #animeshorts #rimuru #gobta #crunchyroll
