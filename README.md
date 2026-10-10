# edits

Vertical YouTube Shorts built from anime/animation clips with ffmpeg + Pillow.

- `shortkit.py`: shared renderer (layout, captions, meme stickers, hook flash, progress bar, audio)
- `fonts/`: Anton + Bangers (SIL OFL)
- `ranga-playtime/`: That Time I Got Reincarnated as a Slime, "Survive Ranga Playtime Challenge"
- `invincible-conquest/`: Invincible S4, "Invincible vs. Conquest Rematch"

Each folder's `build.py` holds the cut list, captions and stickers as data:
`python3 <folder>/build.py SOURCE.mp4 OUTPUT.mp4`. Rendered videos are not committed.
