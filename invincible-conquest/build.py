#!/usr/bin/env python3
"""Build a vertical YouTube Short from Prime Video's "Invincible vs. Conquest Rematch" clip
(Invincible Season 4).

Usage: python3 build.py SOURCE.mp4 OUTPUT.mp4 [WORKDIR]

Cuts the 5-minute clip down to the planet fight (drops the space subplot and the
end card), opens on the blood-spray climax as the hook, and keeps the
"Where's Mark?" cutaway as a comedic beat before the final round.
Rendering lives in ../shortkit.py.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import shortkit  # noqa: E402

SPEED = 1.1  # global speed-up for pacing (pitch preserved)
# The source is only 640x360: upscale with lanczos and sharpen a little.
SCALE_FLAGS = "lanczos"
SRC_FILTER = "unsharp=5:5:0.7:5:5:0.0"

# (src_start, src_end, zoom). First entry is the cold-open hook.
SEGMENTS = [
    (277.99, 280.80, 1.00),  # HOOK: blood spray + Mark's scream
    (1.42, 6.26, 1.00),      # "You're never breathing again." + Conquest choked
    (6.26, 12.10, 1.00),     # flies him up into the sky by the throat
    (139.72, 144.50, 1.00),  # Mark gets thrown, explosion
    (149.61, 152.78, 1.12),  # Mark screams, then pins Conquest (zoom)
    (157.16, 161.12, 1.00),  # slams Conquest into the ground
    (169.75, 174.09, 1.00),  # Mark punches and screams
    (177.39, 181.06, 1.00),  # Conquest's grin close-up
    (181.06, 184.10, 1.00),  # crater
    (213.84, 216.80, 1.10),  # Conquest choked, Mark yells (zoom)
    (219.72, 224.06, 1.00),  # Conquest choked
    (236.00, 240.50, 1.00),  # Conquest's hand, Mark's bloody mouth
    (255.21, 263.05, 1.00),  # Nolan & Oliver: "Where's Mark?"
    (267.18, 282.57, 1.00),  # meanwhile Mark: stomp, blood spray, scream
    (290.00, 292.50, 1.12),  # Conquest's bloody grin (zoom)
    (295.55, 299.50, 1.00),  # final wide shot
]

TITLE = "CONQUEST WANTED\nA *REMATCH...* 💀"

# Subtitles: (speaker or None, text with *highlight*, src_start, src_end)
SUBS = [
    ("MARK", "You're *NEVER* breathing again.", 1.60, 4.80),
    ("NOLAN", "Oliver! You're okay.", 255.30, 257.60),
    ("NOLAN", "Where's *Mark?*", 258.30, 259.40),
    ("OLIVER", "I don't know... they were moving too *fast.*", 259.40, 262.40),
]
SPEAKER_COLORS = {"MARK": (255, 214, 10), "NOLAN": (235, 70, 70), "OLIVER": (255, 130, 90)}

# Meme stickers: (text, bg color, rotation deg, src_start, src_end, segment index or None)
RED, DARK, BLUE, PURPLE, ORANGE = (220, 30, 40), (25, 25, 25), (30, 120, 230), (110, 70, 230), (240, 150, 0)
POPS = [
    ("ROUND 2 GOT BRUTAL 😳", RED, -4, 277.99, 280.80, 0),
    ("RUN IT BACK ⏪", DARK, 3, 1.42, 4.67, None),
    ("HE MEANT THAT 💀", DARK, -3, 4.67, 6.26, None),
    ("AIR MAIL ✈️", BLUE, 4, 6.26, 12.10, None),
    ("MARK GOT YEETED 🚀", PURPLE, -3, 139.72, 144.50, None),
    ("MARK HAS HAD ENOUGH 😠", DARK, 3, 149.61, 151.60, None),
    ("FREE LANDSCAPING 🪨", ORANGE, -4, 157.16, 161.12, None),
    ("UNLIMITED RAGE MODE 😤", RED, 3, 169.75, 174.09, None),
    ("CONQUEST IS ENJOYING THIS 💀", DARK, -3, 177.39, 181.06, None),
    ("NEW CRATER UNLOCKED 🌋", ORANGE, 4, 181.06, 184.10, None),
    ("NO MORE MR. NICE GUY 😡", RED, -3, 214.90, 216.80, None),
    ("BREATHING: OPTIONAL 😵", PURPLE, 3, 219.72, 224.06, None),
    ("DENTAL PLAN: CANCELLED 🦷", BLUE, -4, 236.00, 240.50, None),
    ("DAD OF THE YEAR 🏆", ORANGE, 3, 255.21, 263.05, None),
    ("MEANWHILE, MARK: 🩸", DARK, -3, 267.18, 273.27, None),
    ("NOT THE FOOT 😭", PURPLE, 4, 273.27, 276.28, None),
    ("HE SNAPPED 💥", RED, -4, 277.99, 282.57, None),
    ("WHY IS HE SMILING?! 😳", DARK, 3, 290.00, 292.50, None),
    ("WHO WINS ROUND 3? 👇", RED, -3, 295.55, 299.50, None),
]

# Bass "boom" hits on the big impacts (src time, segment index or None)
BOOMS = [(277.99, 0), (157.16, None), (277.99, None), (290.00, None)]


if __name__ == "__main__":
    shortkit.main(globals())
