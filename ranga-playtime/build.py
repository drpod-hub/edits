#!/usr/bin/env python3
"""Build a vertical YouTube Short from the Crunchyroll "Survive Ranga Playtime Challenge" clip.

Usage: python3 build.py SOURCE.mp4 OUTPUT.mp4 [WORKDIR]

Japanese audio with English captions. Opens with the payoff as a cold-open hook,
then "HOW IT STARTED". Rendering lives in ../shortkit.py.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import shortkit  # noqa: E402

SPEED = 1.1  # global speed-up for pacing (pitch preserved)

# (src_start, src_end, zoom). First entry is the cold-open hook.
SEGMENTS = [
    (58.30, 61.50, 1.00),  # HOOK: washing-machine spin + Ranga pinning him
    (2.00, 10.60, 1.00),   # general / captain challenge
    (10.60, 19.60, 1.00),  # Ranga bowls through the knights
    (19.60, 22.70, 1.20),  # captain's shocked face (zoom punch)
    (24.19, 33.87, 1.00),  # captain powers up, Gobta rides in
    (48.09, 58.30, 1.00),  # Gobta's battle cry
    (58.30, 63.81, 1.00),  # spin + "playtime"
    (63.81, 70.20, 1.00),  # Gobta: stop, he'll die
    (70.20, 76.45, 1.18),  # Ranga: doesn't he want to play more? (zoom)
    (76.45, 79.50, 1.00),
    (79.50, 82.60, 1.18),  # "...that would be bad."
]

TITLE = "HE TRIED TO 1v1\nRIMURU'S *'GOOD BOY'* 💀"

# Subtitles: (speaker or None, text with *highlight*, src_start, src_end)
SUBS = [
    (None, "You! Take on *THAT* thing!", 2.50, 4.60),
    (None, "Bison! Garcia! Guard the *GENERAL!*", 4.90, 10.50),
    (None, "N-NOOO!", 12.47, 13.40),
    (None, "*HYAAAH!*", 19.90, 21.00),
    (None, "You *BASTARD!*", 21.50, 22.70),
    (None, "*WHAT?!*", 25.40, 26.60),
    ("GOBTA", "*AAAAAAAAH!*", 51.60, 53.20),
    ("GOBTA", "H-HYAH!", 55.70, 58.20),
    ("GOBTA", "Ranga-san, *STOP!* Any more and he'll *DIE!*", 64.40, 67.30),
    (None, "Oh no! We need to *heal* him, quick!", 67.40, 70.15),
    ("RANGA", "Hm? But doesn't he want to *PLAY* some more?", 70.20, 74.70),
    ("GOBTA", "Nonono, he does *NOT!*", 74.70, 76.40),
    (None, "Exactly! Stop now, or *Lord Rimuru* will...", 76.45, 79.45),
    ("RANGA", "...That would be *BAD.*", 79.50, 81.40),
]
SPEAKER_COLORS = {"GOBTA": (120, 220, 90), "RANGA": (150, 170, 255)}

# Meme stickers: (text, bg color, rotation deg, src_start, src_end, segment index or None)
POPS = [
    ("HOW IT ENDED 💀", (230, 40, 40), -4, 58.30, 61.50, 0),
    ("HOW IT STARTED 👇", (25, 25, 25), 3, 2.00, 4.20, None),
    ("BOWLING FOR KNIGHTS 🎳", (230, 40, 40), -3, 13.30, 17.68, None),
    ("THE 'PUPPY' ⚡", (110, 70, 230), 4, 17.68, 19.60, None),
    ("BRO JUST REALIZED 😨", (25, 25, 25), -3, 19.60, 22.70, None),
    ("MAIN CHARACTER AURA ✨", (240, 150, 0), 3, 24.19, 31.20, None),
    ("...MEANWHILE GOBTA 🐺", (60, 160, 60), -4, 31.20, 33.87, None),
    ("GOBTA'S BATTLE CRY 🗣️", (60, 160, 60), 3, 51.63, 53.68, None),
    ("WASHING MACHINE MODE 🌀", (30, 120, 230), -4, 58.31, 60.06, 6),
    ("PLAYTIME 🐶", (230, 40, 40), 4, 60.06, 63.81, 6),
    ("HIS IDEA OF 'GENTLE' 🐾", (110, 70, 230), -3, 70.20, 74.70, None),
    ("THE ONE NAME HE FEARS 😰", (25, 25, 25), 3, 79.50, 81.46, None),
    ("RANGA 1 — KNIGHTS 0 🏆", (240, 150, 0), -3, 81.46, 82.60, None),
]

# Bass "boom" hits on the punchlines (src time, segment index or None)
BOOMS = [(58.31, 0), (70.20, None), (79.50, None)]


if __name__ == "__main__":
    shortkit.main(globals())
