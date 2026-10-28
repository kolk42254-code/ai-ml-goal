"""
Eye -> Space  |  realistic ASCII-art animation that plays right in the terminal
                 (Python + numpy only: no window, no tkinter, no Pillow)

What happens (about 14 seconds):
  1. A closed eye fades in from black, then opens. The pupil got used to the dark
     under the lid, so it shrinks a little in the light (like a real pupil).
  2. The eye jumps a little to the left, blinks, jumps to the right, then looks
     straight at you. Eye jumps are very fast with a tiny overshoot, like real eyes.
  3. The camera zooms into the pupil. The iris shows more and more fine fibres.
  4. Inside the pupil there is deep space: coloured gas clouds (a nebula) and
     coloured stars that fly past and leave short light trails.
  5. A glowing pink heart grows in the middle of space and beats (lub-dub).

How it draws in the terminal (no window at all):
  - The terminal is "painted" with ANSI escape codes: ESC[row;colH moves the
    cursor, ESC[38;2;R;G;Bm sets the colour of the letter and ESC[48;2;R;G;Bm the
    background colour of its cell (24-bit "true colour").
  - Every cell gets a dim background in its own colour and a brighter letter on
    top, so the picture is solid (no black holes) but still all letters.
  - The brightness of a cell picks the letter (letters sorted by how much ink
    they have). Lashes, brow hairs, iris fibres and star trails use  - / | \\
    turned the same way as the hair or the light; thick lash roots are bold.
  - Only the cells that changed visibly since the last frame are sent, and a
    colour code only when the colour changes visibly (almost half as much to
    send, so the terminal has less work). Each frame is sent in one go as a
    "synchronized update", so it does not tear or flicker.
  - All frames are made before playing (on half of the CPU threads, so the
    computer stays cool and smooth) and kept in a cache
    file for this terminal size, so it always plays smoothly. Next start: instant.
    (The cache files are in the temp folder; only the newest 4 are kept.)
  - It uses the terminal's "alternate screen": when it ends, your terminal looks
    exactly like before.

Install:  pip install numpy
Run:      python eye_to_space.py       (make the terminal big or full screen first)
Options:  --loop         play again and again (good for an exhibition)
          --stay         after the end, keep flying through the stars
          --colors 256   for terminals without 24-bit colour (like macOS Terminal.app)
          --ascii        plain ASCII letters only (no  \u25cf \u2022 \u00b7 \u2500 )
          --bg 0         black background, only coloured letters (0 .. 1, default 0.5)
          --code         use this program's own code as the letters
          --aspect 2.2   letter height / width, if the eye looks too tall or too flat
Keys:     Q or Esc = quit   R = play again   Space = pause
"""

import argparse
import hashlib
import math
import os
import signal
import sys
import tempfile
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool

try:
    import numpy as np
except ImportError:
    sys.exit("This program needs numpy. Install it with:  pip install numpy")

try:                                # Linux / macOS: keys without Enter, terminal size in pixels
    import fcntl
    import select
    import struct
    import termios
    import tty
except ImportError:                 # Windows
    termios = None

# ----------------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------------
COLS, ROWS = 150, 44        # size of the letter grid (set to the terminal size at the start)
TERM_ASPECT = 2.05          # letter height / width, if the terminal does not tell us
GRID_ASPECT = TERM_ASPECT
VIEW_H = 0.627              # half the height of the picture (the width follows the terminal)
VIEW_W = VIEW_H * COLS / (ROWS * GRID_ASPECT)
VIEW_MIN_W = 0.62           # narrow terminals: at least the iris and some white must fit,
VIEW_MAX_H = 1.45           # so the picture gets taller instead (but not more than this)
PIC_H = VIEW_H              # half the height of the picture in use
MAX_COLS, MAX_ROWS = 320, 100   # bigger terminals get a centred picture of this size
FPS = 30                    # frames per second
SS = 2                      # super-sampling: SS x SS colour samples per letter
END_TIME = 14.25            # seconds until the animation ends
WHEN_DONE = "close"         # "close" (like the video), "loop" or "stay"
FG_MAX = 2.4                # a letter is at most this much brighter than its cell
BG_MAX = 0.5                # the cell background is at most this bright (x the cell colour)
DITHER = 0.08               # small fixed random change per cell -> fewer rows of the same letter
USE_CACHE = True            # keep the finished frames in a file -> instant next start
CACHE_FILES = 4             # keep the frames for this many terminal sizes (newest first)
SAME_COLOUR = 4             # colours this close (0..255) look the same, so they are not sent again

# letters from dark to bright (sorted again by their ink, see INK below)
RAMP = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
LINES = "-/|\\"             # letters for hairs, fibres and light trails
BOLD = "\ue000\ue001\ue002\ue003"  # the same four letters in bold (thick hair roots)
DOTS = "\u25cf\u2022\u00b7"          # star centres:  big, middle, small dot
SPIKE = "\u2500"                     # star spike (a line through the whole cell)
CHARS = RAMP + DOTS + SPIKE + BOLD
CH = {c: i for i, c in enumerate(CHARS)}    # letter -> its number


def configure(cols, rows, aspect, bg=None):
    """Use a letter grid of cols x rows. aspect = height / width of one letter."""
    global COLS, ROWS, GRID_ASPECT, VIEW_W, PIC_H, BG_MAX
    COLS, ROWS, GRID_ASPECT = cols, rows, aspect
    ratio = cols / (rows * aspect)              # width / height of the picture
    PIC_H = VIEW_H
    if PIC_H * ratio < VIEW_MIN_W:              # a narrow terminal: show more height
        PIC_H = min(VIEW_MIN_W / ratio, VIEW_MAX_H)
    VIEW_W = PIC_H * ratio
    if bg is not None:
        BG_MAX = bg


def rgb(r, g, b):
    return np.array([r, g, b], np.float32)


# colours (red, green, blue) from 0 to 1
# skin colour for brightness 0 .. 1.65: shadows are redder, like real skin
SKIN_RAMP = np.array([[0.035, 0.012, 0.010], [0.24, 0.10, 0.075], [0.47, 0.25, 0.18],
                      [0.66, 0.42, 0.31], [0.84, 0.59, 0.46], [0.97, 0.79, 0.67]], np.float32)
SKIN_MAX = 1.65
RED_TINT = rgb(0.22, -0.08, -0.07)        # thin eyelid skin is redder
LASH = rgb(0.035, 0.024, 0.020)           # dark line of the lash roots
MARGIN = rgb(0.66, 0.40, 0.33)            # thin skin edge of the upper lid
# hair colours at the root and at the tip (thin tips let some light through)
UP_LASH = (rgb(0.025, 0.018, 0.015), rgb(0.26, 0.18, 0.13))
LO_LASH = (rgb(0.09, 0.06, 0.05), rgb(0.33, 0.24, 0.19))
BROW_HAIR = (rgb(0.08, 0.055, 0.04), rgb(0.30, 0.21, 0.15))
WATERLINE = rgb(0.78, 0.40, 0.36)
TEAR = rgb(1.0, 0.97, 0.94)               # wet shine on the edge of the lower lid
SHEEN = rgb(1.0, 0.88, 0.80)
CARUNCLE = rgb(0.80, 0.38, 0.36)
SCLERA = rgb(0.93, 0.90, 0.86)
SHADOW_TINT = rgb(0.80, 0.84, 0.97)       # the white of the eye looks cool in shadow
VEIN = rgb(0.80, 0.25, 0.22)
# iris colour for "tone" 0 .. 1 (dark brown -> amber -> golden fibres)
IRIS_RAMP = np.array([[0.05, 0.02, 0.010], [0.18, 0.08, 0.035], [0.38, 0.19, 0.07],
                      [0.62, 0.34, 0.12], [0.86, 0.55, 0.20], [1.0, 0.77, 0.42]], np.float32)
PUPIL = rgb(0.008, 0.007, 0.012)
CATCH = rgb(0.97, 0.98, 1.0)
SPACE = rgb(0.004, 0.006, 0.020)
NEB_A = rgb(0.34, 0.06, 0.34)             # magenta gas
NEB_B = rgb(0.06, 0.13, 0.38)             # blue gas
NEB_C = rgb(0.03, 0.26, 0.30)             # teal gas
HEART_RAMP = np.array([[0.40, 0.02, 0.08], [0.82, 0.12, 0.30], [1.0, 0.36, 0.55],
                       [1.0, 0.62, 0.76], [1.0, 0.93, 0.95]], np.float32)
HEART_GLOW = rgb(0.80, 0.10, 0.30)
# star colours: hot blue-white ... white ... cool orange
STAR_T = [0.0, 0.15, 0.50, 0.80, 1.0]
STAR_RGB = np.array([[0.66, 0.76, 1.0], [0.82, 0.88, 1.0], [1.0, 0.98, 0.95],
                     [1.0, 0.89, 0.70], [1.0, 0.74, 0.50]], np.float32)

# eye shape (measured from the video). "u" goes left -> right (-1 .. 1 across
# the window), "v" goes top -> bottom, in the same units so circles stay round.
EYE_U0, EYE_HW = 0.214, 1.369          # centre and half width of the eye
CORNER_A, CORNER_B = -0.066, -0.117    # line through the two corners: v = A + B*u
UP_H, UP_P, UP_SKEW = 0.318, 0.97, 0.408
LO_H, LO_P = 0.363, 1.195
MEET = 0.025                           # height where the lids meet when closed (middle)
IRIS_R = 0.38
PUPIL_R = 0.135                        # pupil radius (normal size)
HEART_SIZE = 0.0497                    # final heart height (before the zoom)
HEART_WIDE = 0.581                     # half width / height of the heart
LID_FOLLOW = 0.6                       # how much the upper lid follows the eye sideways

# the lids are a 3D skin surface (height towards us) lying over the round eyeball
DOME_U, DOME_V = 0.10, 0.02            # centre of the eyeball bulge
DOME_A, DOME_B = 1.25, 0.58            # its half width and half height
DOME_H = 0.55                          # how far it bulges out
LID_T = 0.030                          # thickness of the lids at their edge
LID_ROLL = 0.035                       # the upper lid is a round roll between its edge and the crease
MARGIN_W = 0.010                       # skin edge of the upper lid, where the lashes grow
RIM_W = 0.016                          # wet rim of the lower lid
CREASE_D = 0.15                        # height of the lid crease above the lid edge
CREASE_DEEP = 0.045                    # depth of the crease fold
LIGHT = np.array([0.35, -0.45, 0.82], np.float32)     # light from the upper right, in front
LIGHT /= np.linalg.norm(LIGHT)
HALF = LIGHT + np.array([0.0, 0.0, 1.0], np.float32)  # half way between light and viewer (for shine)
HALF /= np.linalg.norm(HALF)
FILL = np.array([-0.25, 0.55, 0.80], np.float32)      # weak light bounced up from the cheek
FILL /= np.linalg.norm(FILL)

# iris brightness from the pupil edge (0) to the iris edge (1): dark ruff at the
# pupil, golden inner ring, brown outside, dark ring at the edge
IRIS_W = [0.00, 0.03, 0.08, 0.22, 0.32, 0.45, 0.70, 0.86, 0.94, 1.00]
IRIS_K = [0.10, 0.22, 0.64, 0.74, 0.70, 0.55, 0.48, 0.38, 0.20, 0.12]


# ----------------------------------------------------------------------------
# Small maths helpers
# ----------------------------------------------------------------------------
def ss(a, b, x):
    """smoothstep: 0 when x is at a, 1 when x is at b, smooth in between."""
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def mix(a, b, t):
    """Blend from a (t=0) to b (t=1)."""
    return a + (b - a) * t


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1.0 - (1.0 - x) ** 2


def interp(x, xp, fp):
    """np.interp, but keeps the result in float32 (faster)."""
    return np.interp(x, xp, fp).astype(np.float32)


def colour_ramp(cols, k):
    """Colour for every value k (0..1), blending between evenly spaced colours."""
    n = len(cols) - 1
    x = np.clip(k, 0.0, 1.0) * n
    i = np.minimum(x.astype(np.int64), n - 1)
    f = (x - i)[..., None]
    return cols[i] * (1.0 - f) + cols[i + 1] * f


_rng = np.random.default_rng(2024)
TEX = _rng.random((256, 256)).astype(np.float32)     # random textures for noise
TEX128 = _rng.random((128, 128)).astype(np.float32)
TEX64 = _rng.random((64, 64)).astype(np.float32)
TEX32 = _rng.random((32, 32)).astype(np.float32)
TEX16 = _rng.random((16, 16)).astype(np.float32)


def noise(x, y, tex=TEX):
    """Smooth random value at (x, y). The texture repeats, so any x, y works."""
    m = tex.shape[0] - 1
    x0 = np.floor(x)
    y0 = np.floor(y)
    fx = x - x0
    fy = y - y0
    fx = fx * fx * (3.0 - 2.0 * fx)
    fy = fy * fy * (3.0 - 2.0 * fy)
    xi = x0.astype(np.int64) & m
    yi = y0.astype(np.int64) & m
    xj = (xi + 1) & m
    yj = (yi + 1) & m
    top = tex[yi, xi] * (1.0 - fx) + tex[yi, xj] * fx
    bot = tex[yj, xi] * (1.0 - fx) + tex[yj, xj] * fx
    return top * (1.0 - fy) + bot * fy




def smooth_table(times, values, width):
    """Turn a few (time, value) points into a smooth curve (moving average)."""
    grid = np.arange(-5.0, 65.0, 0.01)
    curve = np.interp(grid, times, values)
    n = max(1, int(width / 0.01))
    kernel = np.ones(n) / n
    padded = np.concatenate([np.full(n, curve[0]), curve, np.full(n, curve[-1])])
    curve = np.convolve(padded, kernel, mode="same")[n:-n]
    return grid, curve


# ----------------------------------------------------------------------------
# Timeline (seconds after the start) - the main moments are measured from the video
# ----------------------------------------------------------------------------
def fade(t):
    """Black -> picture between 0.33 s and 1.03 s."""
    x = min(max((t - 0.33) / 0.70, 0.0), 1.0)
    return math.sin(x * math.pi / 2)


def lid_open(x):
    """0 -> 1 for an eyelid: fast at first, a tiny overshoot, then it settles."""
    x = min(max(x, 0.0), 1.0)
    return 1.0 - (1.0 - x) ** 3 + 0.10 * math.sin(math.pi * x) * x * x


BLINK_T = 1.96


def blink(t):
    """0 = open, 1 = shut. A real blink: closes fast (0.13 s, shut at 2.09 s like
    the video), stays shut a moment, then opens more slowly (0.19 s)."""
    x = t - BLINK_T
    if x <= 0.0 or x >= 0.34:
        return 0.0
    if x < 0.13:
        return (x / 0.13) ** 2
    if x < 0.15:
        return 1.0
    return (1.0 - (x - 0.15) / 0.19) ** 2


def openness(t):
    """(upper lid, lower lid): 0 = closed, 1 = open. Opens at 0.93 s."""
    b = blink(t)
    up = lid_open((t - 0.93) / 0.95) * (1.0 - b)
    lo = ease_out((t - 0.93) / 0.45) * (1.0 - 0.2 * b)   # the lower lid opens faster
    return up, lo


GAZE_START = (-0.016, 0.004)
GAZE_MOVES = [                    # (start, length, where the eye looks)
    (1.32, 0.11, (-0.044, 0.004)),    # small jump to the left
    (2.40, 0.13, (0.073, 0.004)),     # bigger jump to the right
    (2.95, 0.13, (-0.012, 0.016)),    # back to the middle (we zoom into this point)
]
GAZE_END = GAZE_MOVES[-1][2]


def saccade(x):
    """0 -> 1 for an eye jump: very fast, a small overshoot, then it settles."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return float(ss(0.0, 0.55, x)) + 0.05 * math.sin(math.pi * min(max((x - 0.30) / 0.70, 0.0), 1.0))


def gaze(t):
    gx, gy = GAZE_START
    for t0, length, (x, y) in GAZE_MOVES:
        k = saccade((t - t0) / length)
        gx += (x - gx) * k
        gy += (y - gy) * k
    return gx, gy


# zoom (natural log of the zoom factor), measured from the size of the iris,
# pupil and heart in the video. It starts at 3 s and stops at about 12.5 s.
_ZOOM_T = [3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0,
           9.5, 10.0, 10.5, 11.0, 11.5, 12.0, 12.3, 12.5, 12.7]
_ZOOM_LN = [0.0, 0.045, 0.08, 0.12, 0.215, 0.30, 0.41, 0.51, 0.625, 0.775, 0.925,
            1.08, 1.24, 1.40, 1.58, 1.79, 1.99, 2.18, 2.37, 2.46, 2.50, 2.505]
_ZG, _ZC = smooth_table(_ZOOM_T, _ZOOM_LN, 0.3)

# heart size (0..1) while it grows
_HG, _HC = smooth_table([6.8, 7.1, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0],
                        [0.0, 0.35, 0.62, 0.78, 0.85, 0.90, 0.98, 1.0], 0.2)


def zoom(t):
    return float(np.exp(np.interp(t, _ZG, _ZC)))


def pupil_radius(t):
    """Big when the eye opens (it was dark under the lid), shrinks in the light
    after a short delay, opens up again as we fly into the dark. Never quite still."""
    k = 1.22 - 0.36 * float(ss(1.15, 1.9, t)) + 0.14 * float(ss(3.2, 6.0, t))
    return PUPIL_R * k * (1.0 + 0.012 * math.sin(2 * math.pi * t / 2.7))


def heartbeat(t):
    """Lub-dub: two quick pulses every 0.95 s (0 = rest, about 1 = strongest)."""
    p = ((t - 9.6) / 0.95) % 1.0
    pulse = math.exp(-((p - 0.08) / 0.055) ** 2) + 0.6 * math.exp(-((p - 0.30) / 0.06) ** 2)
    return pulse * float(ss(9.4, 10.0, t))


def heart_size(t):
    return HEART_SIZE * float(np.interp(t, _HG, _HC)) * (1.0 + 0.05 * heartbeat(t))


# ----------------------------------------------------------------------------
# Heart shape, measured from the video: half width for each height
# (y = 0 is the bottom tip, y = 1 is the top). Returns about the distance to
# the edge: < 0 inside, > 0 outside (x and y in units of the heart size).
# ----------------------------------------------------------------------------
HEART_Y = [0.0, 0.069, 0.138, 0.207, 0.276, 0.345, 0.414, 0.483, 0.552, 0.621,
           0.690, 0.759, 0.828, 0.897, 0.966, 1.0]
HEART_W = [0.06, 0.22, 0.39, 0.556, 0.722, 0.833, 0.917, 0.944, 0.972, 1.0,
           1.0, 0.972, 0.944, 0.92, 0.78, 0.66]


def heart_sdf(x, y):
    hw = interp(y, HEART_Y, HEART_W)
    side = (np.abs(x) - hw) * 0.85
    top = y - (1.0 - 0.035 * np.exp(-(x / 0.14) ** 2))    # tiny dip in the middle
    bottom = -y
    return np.maximum(np.maximum(side, top * 0.7), bottom * 0.7)


# ----------------------------------------------------------------------------
# Eyelids and hairs
# ----------------------------------------------------------------------------
def lid_lines(u, o, ol, skew):
    """The lid edges at u: (s, upper edge, lower edge, upper edge when open, line
    where the lids meet when shut). s = place along the eye (-1 inner .. 1 outer corner)."""
    s = np.clip((u - EYE_U0) / EYE_HW, -0.999, 0.999)
    base = CORNER_A + CORNER_B * u
    s2 = np.clip(s + skew * (1.0 - s * s), -0.999, 0.999)
    up_open = base - UP_H * (1.0 - s2 * s2) ** UP_P
    lo_open = base + LO_H * (1.0 - s * s) ** LO_P
    meet = base + (MEET - CORNER_A - CORNER_B * EYE_U0) * (1.0 - s * s) ** 0.9   # a soft curve
    return s, mix(meet, up_open, o), mix(meet, lo_open, ol), up_open, meet


class Hairs:
    """Eyelashes and eyebrow hairs. Every hair is a thin curved line: thick and dark
    at the root, thin and lighter at the tip. The upper lashes grow in small clumps,
    lean outwards and curl up. Hairs are drawn straight into the letter grid: every
    bit of a hair adds "ink" (how much of the cell it covers) to the cell it is in."""
    STEPS = 36

    def __init__(self, seed=11):
        r = np.random.default_rng(seed)
        # upper lashes: clumps of 2-4 lashes whose tips stick together
        centres = np.sort(r.uniform(-0.92, 0.99, 30))
        k = r.integers(2, 5, len(centres))
        sc = np.repeat(centres, k)
        n = len(sc)
        self.us = sc + r.normal(0.0, 0.010, n)
        length = 0.050 + 0.070 * ss(-0.95, -0.1, sc) * (1.0 - 0.35 * ss(0.75, 1.0, sc))
        self.ul = length * np.repeat(r.uniform(0.75, 1.25, len(centres)), k) * r.uniform(0.88, 1.12, n)
        lean = 10.0 + 40.0 * sc + 18.0 * sc * np.abs(sc) + np.repeat(r.normal(0.0, 5.0, len(centres)), k)
        lean -= np.degrees((self.us - sc) * EYE_HW / self.ul) * 0.8   # lean towards the clump
        self.ulean = lean + r.normal(0.0, 2.5, n)  # degrees from straight up, > 0 = to the right
        self.ucurl = r.uniform(0.35, 0.70, n)
        self.uw = 0.0060 * r.uniform(0.8, 1.2, n)   # thickness at the root
        # lower lashes: a few short thin ones, pointing down and outwards
        n = 24
        self.ls = np.sort(r.uniform(-0.70, 0.98, n))
        self.ll = (0.020 + 0.022 * ss(-0.7, 0.2, self.ls)) * r.uniform(0.7, 1.3, n)
        self.llean = 12.0 + 30.0 * self.ls + r.normal(0.0, 6.0, n)
        self.lw = 0.0030 * r.uniform(0.8, 1.2, n)
        # eyebrow hairs: fixed on the face, at the very top of the window. Steep at
        # the start of the brow, flatter towards its thin end
        n = 170
        bu = r.uniform(-1.15, 0.60, n)
        keep = r.random(n) > ss(0.25, 0.6, bu)
        self.bu, self.bv = bu[keep], r.uniform(-0.72, -0.60, n)[keep]
        m = len(self.bu)
        self.bl = r.uniform(0.04, 0.08, m)
        self.bang = 50.0 - 35.0 * ss(-1.1, 0.3, self.bu) + r.normal(0.0, 7.0, m)
        self.bbend = -15.0 + r.normal(0.0, 5.0, m)
        self.bw = 0.0035 * r.uniform(0.8, 1.2, m)

    def curve(self, u0, v0, phi0, bend, length, width):
        """Points along curved hairs: (u, v, ink area, angle in degrees, 0 at the root .. 1 at the tip)."""
        tau = np.linspace(0.0, 1.0, self.STEPS)[None, :]
        phi = np.radians(phi0[:, None] + bend[:, None] * tau ** 1.5)
        step = (length / (self.STEPS - 1))[:, None]
        du, dv = np.cos(phi) * step, -np.sin(phi) * step
        u = u0[:, None] + np.cumsum(du, axis=1) - du
        v = v0[:, None] + np.cumsum(dv, axis=1) - dv
        area = width[:, None] * (1.0 - 0.80 * tau ** 0.8) * step
        return u, v, area, np.degrees(phi), np.broadcast_to(tau, u.shape)

    def draw(self, o, ol, skew, gx, gy, Z, cw, ch):
        """Returns per cell: ink, ink x cos and sin of twice the hair angle, ink x colour.
        cw, ch = width and height of one letter cell."""
        oc = min(o, 1.0)
        # upper lashes: up and outwards when open, hanging down when shut. Half way
        # (in a blink) they point at us, so they look shorter.
        u0 = EYE_U0 + self.us * EYE_HW
        v0 = lid_lines(u0, o, ol, skew)[1] - MARGIN_W * oc
        phi0 = mix(-90.0 + 0.8 * self.ulean, 90.0 - 1.3 * self.ulean, oc)
        bend = mix(0.5, 1.3, oc) * self.ulean * self.ucurl
        length = self.ul * mix(0.75, 1.0, oc) * (1.0 - 1.6 * oc * (1.0 - oc))
        parts = [self.curve(u0, v0, phi0, bend, length, self.uw) + UP_LASH]
        # lower lashes grow from the outer edge of the wet rim
        u0 = EYE_U0 + self.ls * EYE_HW
        v0 = lid_lines(u0, o, ol, skew)[2] + RIM_W * ol
        parts.append(self.curve(u0, v0, -90.0 + self.llean, 0.4 * self.llean, self.ll, self.lw) + LO_LASH)
        parts.append(self.curve(self.bu, self.bv, self.bang, self.bbend, self.bl, self.bw) + BROW_HAIR)

        u, v, area, ang, tau = (np.concatenate([p[i].reshape(-1) for p in parts]) for i in range(5))
        colour = np.concatenate([mix(p[5], p[6], (p[4].reshape(-1) ** 1.2)[:, None]) for p in parts])
        col = np.floor((gx + (u - gx) * Z) / cw + COLS / 2.0).astype(np.int64)
        row = np.floor((gy + (v - gy) * Z) / ch + ROWS / 2.0).astype(np.int64)
        ok = (col >= 0) & (col < COLS) & (row >= 0) & (row < ROWS)
        cell = (row * COLS + col)[ok]
        ink = area[ok] * (Z * Z / (cw * ch))
        a2 = np.radians(2.0 * ang[ok])
        n = ROWS * COLS

        def add(w):
            return np.bincount(cell, w, minlength=n).reshape(ROWS, COLS).astype(np.float32)

        rgb_ = np.stack([add(ink * colour[ok][:, i]) for i in range(3)], axis=-1)
        return add(ink), add(ink * np.cos(a2)), add(ink * np.sin(a2)), rgb_


# ----------------------------------------------------------------------------
# Stars: a 3D star field inside the pupil, flying towards us
# ----------------------------------------------------------------------------
class StarField:
    TRAIL = 0.07                                    # light trail = last 0.07 s of movement

    def __init__(self, n=2400, seed=7):
        r = np.random.default_rng(seed)
        self.x = r.uniform(-1.1, 1.1, n)            # position (in pupil sizes)
        self.y = r.uniform(-1.1, 1.1, n)
        self.z0 = r.uniform(0.0, 1.0, n)            # depth
        self.born = 4.3 + 4.4 * np.sqrt(r.random(n))  # when each star appears
        self.tw_f = r.uniform(5.0, 13.0, n)         # a faint shimmer
        self.tw_p = r.uniform(0.0, 2 * math.pi, n)
        self.size = 0.40 + 0.60 * r.random(n) ** 2.2  # many faint stars, a few bright ones
        temp = r.random(n)
        self.col = np.stack([np.interp(temp, STAR_T, STAR_RGB[:, c]) for c in range(3)], 1)

    def place(self, depth, cx, cy, scale, cw, ch):
        col = (cx + self.x / depth * scale) / cw + COLS / 2.0
        row = (cy + self.y / depth * scale) / ch + ROWS / 2.0
        return col, row

    def draw(self, t, cx, cy, scale, cw, ch, mask, letters):
        """Returns (letter, brightness, colour) for every cell, 0 brightness = no star.
        cx, cy = screen position of the pupil centre, scale = pupil radius on screen,
        cw, ch = width and height of one letter cell."""
        depth = 0.08 + 0.92 * ((self.z0 - 0.10 * t) % 1.0)
        col, row = self.place(depth, cx, cy, scale, cw, ch)
        col0, row0 = self.place(depth + 0.092 * self.TRAIL, cx, cy, scale, cw, ch)
        bright = np.clip(1.35 * (1.0 - depth) + 0.18, 0.0, 1.0) * self.size
        bright *= ss(1.0, 0.85, depth) * ss(self.born, self.born + 0.5, t)
        bright *= 0.88 + 0.12 * np.sin(self.tw_f * t + self.tw_p)
        c = np.floor(col).astype(np.int64)
        r = np.floor(row).astype(np.int64)
        ok = (bright > 0.06) & (c >= -20) & (c < COLS + 20) & (r >= -10) & (r < ROWS + 10)
        ok &= mask[np.clip(r, 0, ROWS - 1), np.clip(c, 0, COLS - 1)] > 0.02
        b, c, r, sc = bright[ok], c[ok], r[ok], self.col[ok]
        dc, dr = (col - col0)[ok], (row - row0)[ok]

        # the centre of each star
        core = np.select([b > 0.75, b > 0.45, b > 0.22], [CH[DOTS[0]], CH[DOTS[1]], CH[DOTS[2]]], CH["."])
        rows, cols, chars, vals, cols_rgb = [r], [c], [core], [b], [sc]

        # light trail behind each star (pointing away from where it flies)
        length = np.maximum(np.abs(dc), np.abs(dr))
        n = np.minimum(np.round(length), 14).astype(np.int64)
        ang = np.degrees(np.arctan2(-dr * ch, dc * cw)) % 180.0
        trail_ch = letters.line_for(ang)
        k = np.arange(1, 15)[None, :]
        on = k <= n[:, None]
        step = k / np.maximum(length, 1e-6)[:, None]
        rows.append(np.floor(row[ok][:, None] - dr[:, None] * step)[on].astype(np.int64))
        cols.append(np.floor(col[ok][:, None] - dc[:, None] * step)[on].astype(np.int64))
        chars.append(np.broadcast_to(trail_ch[:, None], on.shape)[on])
        vals.append((b[:, None] * 0.75 * (1.0 - k / (n[:, None] + 1.0)))[on])
        cols_rgb.append(np.broadcast_to(sc[:, None, :], on.shape + (3,))[on])

        # short light spikes on the brightest stars
        lh = np.round(np.clip((b - 0.72) / 0.28, 0.0, 1.0) * 4.0).astype(np.int64)
        lv = lh // 3
        kk = np.arange(1, 5)[None, :]
        for sign in (-1, 1):
            for arm, char, dy, dx in ((lh, CH[SPIKE], 0, 1), (lv, CH["|"], 1, 0)):
                on = kk <= arm[:, None]
                f = b[:, None] * (1.0 - kk / (arm[:, None] + 1.0)) * 0.9
                rows.append((r[:, None] + sign * dy * kk)[on] if dy else np.broadcast_to(r[:, None], on.shape)[on])
                cols.append((c[:, None] + sign * dx * kk)[on] if dx else np.broadcast_to(c[:, None], on.shape)[on])
                chars.append(np.full(on.sum(), char))
                vals.append(f[on])
                cols_rgb.append(np.broadcast_to(sc[:, None, :], on.shape + (3,))[on])

        rows, cols = np.concatenate(rows), np.concatenate(cols)
        chars, vals = np.concatenate(chars), np.concatenate(vals)
        cols_rgb = np.concatenate(cols_rgb)
        keep = (rows >= 0) & (rows < ROWS) & (cols >= 0) & (cols < COLS)
        order = np.argsort(vals[keep], kind="stable")   # brightest is written last = wins
        rows, cols = rows[keep][order], cols[keep][order]
        out_ch = np.zeros((ROWS, COLS), np.int64)
        out_i = np.zeros((ROWS, COLS), np.float32)
        out_c = np.zeros((ROWS, COLS, 3), np.float32)
        out_ch[rows, cols] = chars[keep][order]
        out_i[rows, cols] = vals[keep][order]
        out_c[rows, cols] = cols_rgb[keep][order]
        return out_ch, out_i, out_c


# ----------------------------------------------------------------------------
# The scene: paints one frame for time t
# ----------------------------------------------------------------------------
def cells(a):
    """Average the SS x SS samples of every letter cell."""
    return a.reshape(ROWS, SS, COLS, SS, *a.shape[2:]).mean(axis=(1, 3))


class Scene:
    def __init__(self, letters):
        self.letters = letters                     # tells how much ink each letter has
        self.cw = 2.0 * VIEW_W / COLS              # width of one letter cell
        self.ch = self.cw * GRID_ASPECT            # its height
        off = (np.arange(SS) + 0.5) / SS
        cc = (np.arange(COLS)[:, None] + off[None, :]).reshape(-1)
        rr = (np.arange(ROWS)[:, None] + off[None, :]).reshape(-1)
        x = ((cc - COLS / 2.0) * self.cw).astype(np.float32)
        y = ((rr - ROWS / 2.0) * self.ch).astype(np.float32)
        self.X = np.broadcast_to(x[None, :], (ROWS * SS, COLS * SS))
        self.Y = np.broadcast_to(y[:, None], (ROWS * SS, COLS * SS))
        # soft dark corners, like a camera lens
        xc, yc = cells(self.X) / VIEW_W, cells(self.Y) / PIC_H
        self.vignette = np.clip(1.0 - 0.22 * (xc * xc + 0.86 * yc * yc), 0.0, 1.0)[..., None]
        self.step_u = self.cw / SS                 # distance between two samples
        self.step_v = self.ch / SS
        self.hairs = Hairs()
        self.dither = (np.random.default_rng(3).random((ROWS, COLS)) - 0.5).astype(np.float32) * DITHER
        self.stars = StarField()

    # ---- picture -----------------------------------------------------------
    def paint(self, t):
        Z = zoom(t)
        gx, gy = gaze(t)
        o, ol = openness(t)
        oc = min(o, 1.0)
        skew = UP_SKEW - LID_FOLLOW * (gx - GAZE_END[0])    # the lid follows the eye
        u = gx + (self.X - gx) / Z                 # zoom towards the pupil
        v = gy + (self.Y - gy) / Z

        # ---- eyelids: a 3D skin surface lying over the round eyeball -----------
        s, up, lo, up_open, meet = lid_lines(u, o, ol, skew)
        lo_open = lid_lines(u, 1.0, 1.0, skew)[2]
        d = up - v                                  # > 0 above the upper lid edge
        el = v - lo                                 # > 0 below the lower lid edge
        hv = 0.5 * self.step_v / Z                  # half a sample: edges this soft don't flicker

        def thin(dist, width):
            """A thin line, made softer (and fainter) if it is thinner than a sample."""
            w = math.sqrt(width * width + hv * hv)
            return np.exp(-(dist / w) ** 2) * (width / w)

        inside = ss(-hv, hv, -d) * ss(-hv, hv, -el)
        dp, ep = np.maximum(d, 0.0), np.maximum(el, 0.0)
        on_up, on_lo = ss(-hv, hv, d), ss(-hv, hv, el)
        # the crease: a curved fold above the lashes. It belongs to the face, so it
        # moves down only a little when the lid closes, and almost flattens out.
        v_cr = up_open - CREASE_D * (1.0 - s * s) ** 0.5 - 0.02 + 0.35 * (1.0 - oc) * (meet - up_open)
        c = v - v_cr                                # > 0 below the crease
        x = np.clip(d / np.maximum(up - v_cr, 0.02), 0.0, 1.0)   # 0 at the lid edge, 1 at the crease
        fold = 0.75 + 0.25 * oc                     # deep fold when open, softer when shut
        corner = (1.0 - s * s) ** 0.5               # the lid shapes fade out into the corners
        face = v - lo_open                          # below the open lower lid (fixed on the face)
        # height of the skin towards us: the eyeball bulge; the upper lid with its round
        # edge, its roll, the fold and a hollow above it; the lower lid with its round
        # wet rim and a small roll; the hollow under the eye and the cheek
        H = DOME_H * np.exp(-(((u - DOME_U) / DOME_A) ** 2 + ((v - DOME_V) / DOME_B) ** 2))
        H = H + on_up * (LID_T * (1.0 - np.exp(-dp / 0.010))
                         + LID_ROLL * corner * (0.4 + 0.6 * oc) * np.sin(np.float32(math.pi) * x)
                         - CREASE_DEEP * fold * corner * np.exp(-((c + 0.006) / 0.022) ** 2)
                         - 0.02 * oc * corner * np.exp(-((c + 0.07) / 0.05) ** 2))
        H = H + on_lo * (0.8 * LID_T * (1.0 - np.exp(-ep / 0.010)) + 0.03 * corner * np.exp(-((ep - 0.07) / 0.05) ** 2))
        H = H - 0.03 * np.exp(-((face - 0.20) / 0.07) ** 2) + 0.10 * ss(0.22, 0.60, face)
        # light on that surface: its slope tells which way it faces
        hy, hx = np.gradient(H, self.step_v / Z, self.step_u / Z)
        norm = 1.0 / np.sqrt(1.0 + hx * hx + hy * hy)
        diffuse = np.clip((LIGHT[2] - hx * LIGHT[0] - hy * LIGHT[1]) * norm, 0.0, 1.0)
        fill = np.clip((FILL[2] - hx * FILL[0] - hy * FILL[1]) * norm, 0.0, 1.0)
        shine = np.clip((HALF[2] - hx * HALF[0] - hy * HALF[1]) * norm, 0.0, 1.0) ** 14
        # soft shadows: inside the crease, in the deep corners, under the lower lid;
        # and a soft highlight on the lid just below the crease
        # (the skin above the crease hangs over it, so its shadow fades out upwards)
        hood = np.where(c < 0.0, np.exp(np.minimum(c, 0.0) / 0.045), np.exp(-np.maximum(c, 0.0) / 0.010))
        ao = 1.0 - 0.55 * fold * corner * hood * on_up
        ao = ao * (1.0 - 0.38 * ss(0.40, 1.0, np.abs(s)))
        ao = ao * (1.0 - 0.32 * ol * ss(RIM_W - 0.004, RIM_W, el) * np.exp(-np.maximum(el - RIM_W, 0.0) / 0.04))
        glow = 0.14 * fold * corner * np.exp(-((c - 0.03) / 0.02) ** 2) * on_up

        # ---- skin ----------------------------------------------------------
        vt = np.where(d > 0, up_open - d, v)        # skin above the lid moves with it
        tx = 0.55 * noise(u * 130 + 100, vt * 130 + 100) + 0.45 * noise(u * 45 + 7, vt * 45 + 3)
        blot = noise(u * 9 + 5, vt * 9 + 11, TEX16)  # soft red and pale patches
        # under the eyebrow the skin is a bit darker (fixed on the face, top of the window)
        brow = ss(-0.72, -0.69, v) * (1.0 - ss(-0.60, -0.575, v)) * (1.0 - ss(0.30, 0.70, u))
        sh = (((0.05 + 1.15 * diffuse + 0.30 * fill) * ao + glow) * (0.92 + 0.08 * ss(-0.9, 0.1, u))
              * (0.86 + 0.28 * tx) * (1.0 - 0.35 * brow) * (1.0 + 0.30 * ss(0.06, 0.25, face)))
        skin = colour_ramp(SKIN_RAMP, sh / SKIN_MAX)
        red = (0.45 * np.exp(-(dp / 0.07) ** 2) * on_up + 0.35 * np.exp(-(ep / 0.06) ** 2) * on_lo
               + 0.30 * (blot - 0.5))
        skin = skin * (1.0 + red[..., None] * RED_TINT)
        skin = skin + (shine * 0.35 * (0.5 + tx))[..., None] * SHEEN    # shine on the round lid

        # upper lid edge: a thin band of skin where the lashes grow, and the dark line
        # of the lash roots above it (eye shut: the line where the lids meet)
        mw = MARGIN_W * oc
        band = on_up * (1.0 - ss(mw - hv, mw + hv, d)) * oc
        skin = mix(skin, MARGIN * (0.55 + 0.45 * diffuse)[..., None], (0.85 * band)[..., None])
        # lower lid: a wet pink rim with a shiny line along it, the lash line under it
        rim = RIM_W * ol
        on_rim = on_lo * (1.0 - ss(rim - hv, rim + hv, el)) * ol
        skin = mix(skin, WATERLINE * (0.65 + 0.35 * diffuse)[..., None], (0.9 * on_rim)[..., None])
        roots = np.maximum(thin(d - mw, 0.010) * mix(0.85, 0.65, oc), thin(el - rim, 0.008) * 0.40 * ol)
        roots = np.maximum(roots, thin(c, 0.008) * 0.45 * fold * corner * on_up)    # the fold line
        skin = mix(skin, LASH, roots[..., None])
        wet = thin(el - 0.3 * rim, 0.006) * ol * 0.65
        skin = mix(skin, TEAR, wet[..., None])

        # ---- eyeball -------------------------------------------------------
        dx = u - gx
        dy = v - gy
        rho = np.sqrt(dx * dx + dy * dy) / IRIS_R
        ang = np.arctan2(dy, dx) / np.float32(2 * math.pi) + 0.5
        rpw = pupil_radius(t)                       # pupil radius (world units)
        rp = rpw / IRIS_R

        # white of the eye: a few thin red veins towards the corners
        scl = SCLERA * ((0.97 + 0.03 * u) * (0.93 + 0.10 * noise(u * 60 + 31, v * 60 + 17)))[..., None]
        vn = 1.0 - np.abs(2.0 * noise(u * 20 + 3, v * 20 + 7) - 1.0)
        vn = np.maximum(vn, 1.0 - np.abs(2.0 * noise(u * 45 + 13, v * 45 + 5) - 1.0) * 1.3)
        veins = ss(0.80, 0.96, vn) * ss(0.35, 0.80, np.abs(s)) * ss(1.15, 1.6, rho) * 0.45
        scl = mix(scl, VEIN, veins[..., None])
        cu = EYE_U0 - 0.88 * EYE_HW                 # pink corner of the eye (left)
        car = np.exp(-(((u - cu) / 0.045) ** 2 + ((v - (CORNER_A + CORNER_B * cu) - 0.025) / 0.032) ** 2))
        scl = mix(scl, CARUNCLE, (0.85 * car * ss(0.1, 0.5, oc))[..., None])

        # iris: fibres from the pupil to the edge. The pattern stretches when the
        # pupil changes size, and finer fibres show up as the camera comes closer.
        w = np.clip((rho - rp) / (1.0 - rp), 0.0, 1.0)   # 0 at the pupil, 1 at the iris edge
        fib = (0.45 * noise(ang * 64.0, w * 3.0 + 5.0, TEX64)
               + 0.30 * mix(0.5, noise(ang * 128.0, w * 4.0 + 2.0, TEX128), float(ss(1.2, 2.2, Z)))
               + 0.25 * mix(0.5, noise(ang * 256.0, w * 6.0 + 9.0), float(ss(2.2, 4.0, Z)))) / 0.85
        fine = mix(0.5, noise(ang * 512.0, w * 9.0 + 1.0), float(ss(4.0, 7.0, Z)))
        crypt = noise(ang * 32.0, w * 6.0 + 2.0, TEX32)
        patch = noise(ang * 16.0, w * 2.0 + 9.0, TEX16)
        wc = 0.30 + 0.025 * np.sin(ang * np.float32(2 * math.pi * 23)) + 0.03 * (patch - 0.5)
        tone = (interp(w, IRIS_W, IRIS_K) + 0.62 * (fib - 0.5) + 0.25 * (fine - 0.5)
                + 0.25 * (patch - 0.5) + 0.12 * np.exp(-((w - wc) / 0.03) ** 2)
                - 0.32 * ss(0.64, 0.80, crypt) * np.exp(-((w - 0.42) / 0.14) ** 2)
                - 0.10 * float(ss(1.5, 3.0, Z)) * np.exp(-((w - 0.72 - 0.012 * np.sin(ang * np.float32(2 * math.pi * 9))) / 0.015) ** 2))
        iris = colour_ramp(IRIS_RAMP, tone)
        # light shines through the clear cornea and brightens the far side of the iris
        iris = iris * (1.0 + 0.30 * np.exp(-((dx + 0.13) ** 2 + (dy - 0.11) ** 2) / 0.02))[..., None]
        iris = iris * (1.0 - 0.70 * ss(0.84, 1.0, rho))[..., None]          # dark ring
        ball = mix(iris, scl, ss(0.985, 1.05, rho)[..., None])
        fibre = ss(0.55, 0.68, fib) * ss(0.05, 0.12, w) * (1.0 - ss(0.85, 0.95, w)) * (rho < 1.0)

        # the eyeball is round; the upper lid casts a soft shadow on its top part
        shade_b = ((1.0 - 0.50 * np.exp(-np.maximum(-d, 0.0) / 0.05))
                   * (1.0 - 0.15 * np.exp(-np.maximum(-el, 0.0) / 0.03)))
        shade_b = shade_b * (1.0 - 0.20 * ss(0.6, 1.0, np.abs(s)))
        tint = mix(SHADOW_TINT, 1.0, ss(0.55, 1.0, shade_b)[..., None])
        ball = ball * (shade_b[..., None] * tint)

        # ---- pupil = window into space --------------------------------------
        pm = 1.0 - ss(rp - 0.012, rp + 0.012, rho)
        if t > 4.0:
            space = self.space(t, dx, dy, Z)
        else:
            space = np.broadcast_to(PUPIL, dx.shape + (3,))
        ball = mix(ball, space, pm[..., None])

        # reflections on the wet cornea: a window (with its frame) and a small
        # second light. They move less than the eye, like real reflections.
        cr = 1.0 - 0.38 * float(ss(7.9, 9.2, t))   # stops growing, then fades
        lx = (dx - 0.105 + 0.45 * (gx - GAZE_END[0])) / cr
        ly = (dy + 0.045 + 0.45 * (gy - GAZE_END[1])) / cr
        box = (lx / 0.058) ** 4 + (ly / 0.046) ** 4
        bars = 1.0 - 0.6 * np.minimum(1.0, np.exp(-(lx / 0.006) ** 2) + np.exp(-((ly + 0.006) / 0.005) ** 2))
        m1 = (1.0 - ss(0.6, 1.3, box)) * bars * 0.95 * (1.0 - float(ss(8.9, 9.35, t)))
        c2 = np.sqrt((dx + 0.060) ** 2 + (dy - 0.060) ** 2)
        m2 = (1.0 - ss(0.010, 0.026, c2)) * 0.45 * (1.0 - float(ss(7.5, 8.5, t)))
        mc = np.maximum(m1, m2)
        ball = mix(ball, CATCH, mc[..., None])

        # put it together; a thin wet shine where the eye meets the lower lid
        pic = mix(skin, ball, inside[..., None])
        tear = thin(el + 0.004, 0.005) * ol * 0.50 * (1.0 - np.abs(s) ** 4)
        pic = mix(pic, TEAR, tear[..., None])
        k = fade(t)
        ink, ink_c, ink_s, ink_rgb = self.hairs.draw(o, ol, skew, gx, gy, Z, self.cw, self.ch)
        return dict(
            rgb=cells(pic) * k, ink=ink, ink_c=ink_c, ink_s=ink_s, ink_rgb=ink_rgb * k,
            fibre=cells(fibre * inside * (1.0 - pm)), dx=cells(dx), dy=cells(dy),
            space=cells(inside * pm * (1.0 - mc)), pupil=(gx, gy, rpw * Z))

    def space(self, t, dx, dy, Z):
        """Colour of deep space seen through the pupil: dark sky, gas clouds, the heart."""
        # far away gas clouds grow slower than the pupil while we fly in
        k = Z ** 0.7 * 2.2
        nx, ny = dx * k + 0.015 * t, dy * k - 0.010 * t
        fbm = (0.55 * noise(nx * 3 + 11, ny * 3 + 5) + 0.30 * noise(nx * 7 + 2, ny * 7 + 9)
               + 0.15 * noise(nx * 15 + 4, ny * 15 + 1))
        dens = ss(0.40, 0.80, fbm)
        hue = noise(nx * 1.3 + 40, ny * 1.3 + 40, TEX16)
        gas = mix(NEB_B, NEB_A, ss(0.35, 0.65, hue)[..., None])
        gas = mix(gas, NEB_C, (ss(0.6, 0.85, noise(nx * 2 + 7, ny * 2 + 3, TEX16)) * 0.7)[..., None])
        dust = ss(0.70, 0.92, 1.0 - np.abs(2.0 * noise(nx * 5 + 7, ny * 5 + 3) - 1.0))
        out = SPACE + gas * (dens * (1.0 - 0.65 * dust) * 0.85 * float(ss(4.4, 8.0, t)))[..., None]

        hs = heart_size(t)
        if hs > 1e-5:
            beat = heartbeat(t)
            hx = dx / (hs * HEART_WIDE)
            hy = 0.48 - dy / hs
            sd = heart_sdf(hx, hy)
            h_in = 1.0 - ss(-0.025, 0.025, sd)
            deep = np.clip(-sd / 0.30, 0.0, 1.0)
            # glowing gas inside the heart, slowly swirling
            g = (0.6 * noise(hx * 4 + 0.30 * t + 40, hy * 4 - 0.20 * t + 40)
                 + 0.4 * noise(hx * 9 - 0.40 * t + 3, hy * 9 + 0.25 * t + 8))
            # light from the upper left makes it look round
            hl = (np.exp(-(((hx + 0.40) / 0.30) ** 2 + ((hy - 0.70) / 0.16) ** 2))
                  + 0.5 * np.exp(-(((hx - 0.42) / 0.22) ** 2 + ((hy - 0.74) / 0.12) ** 2)))
            tone = 0.18 + 0.42 * np.sqrt(deep) + 0.45 * (g - 0.5) + 0.45 * hl + 0.20 * beat
            hcol = colour_ramp(HEART_RAMP, tone)
            sdo = np.maximum(sd, 0.0)
            glow = (0.55 * np.exp(-sdo / 0.07) + 0.22 * np.exp(-sdo / 0.35)) * (sd > 0) * (1.0 + 0.6 * beat)
            show = float(ss(6.8, 8.0, t))
            out = mix(out, hcol, (h_in * show)[..., None]) + HEART_GLOW * (glow * show)[..., None]
        return out

    # ---- letters -----------------------------------------------------------
    def frame(self, t):
        """Returns (letter, letter colour, background colour) for every cell."""
        P = self.paint(t)
        g = self.letters
        under = np.clip(P["rgb"], 0.0, 1.0) * self.vignette     # the picture without hairs
        ink = P["ink"]
        cover = np.clip(ink, 0.0, 1.0)[..., None]
        hair_rgb = P["ink_rgb"] / np.maximum(ink, 1e-6)[..., None] * self.vignette
        pic = mix(under, hair_rgb, 0.85 * cover)
        lum = 0.2126 * pic[..., 0] + 0.7152 * pic[..., 1] + 0.0722 * pic[..., 2]

        # brighter cell -> letter with more ink (by its place in the sorted letters)
        level = np.clip(lum ** 0.75 + self.dither, 0.0, 1.0)
        idx = g.ramp_idx[np.round(level * (len(g.ramp_idx) - 1)).astype(np.int64)]
        # iris fibres: lines pointing away from the pupil
        radial = np.degrees(np.arctan2(-P["dy"], P["dx"])) % 180.0
        idx = np.where(P["fibre"] > 0.55, g.line_for(radial), idx)

        # letter brighter than the cell, background darker, so that together
        # they give the cell's colour
        bg_k = min(1.0, BG_MAX / 0.5)               # --bg 0: black behind every letter
        cov = g.cov[idx][..., None]
        fg = np.minimum(pic * FG_MAX, 1.0)
        bg = np.clip((pic - fg * cov) / (1.0 - cov), pic * 0.3, pic * BG_MAX)

        # eyelashes and brow hairs: a line letter turned like the hair. Where there is
        # a lot of hair the letter has the hair's dark colour; a thin hair tip keeps
        # almost the skin's letter colour. The background follows the same rule as in
        # every other cell, so hair cells don't look like bright tiles: they get darker.
        hair = ink > 0.04
        hang = np.degrees(0.5 * np.arctan2(P["ink_s"], P["ink_c"])) % 180.0
        idx = np.where(hair, g.line_for(hang, bold=ink > 0.30), idx)
        dense = ss(0.08, 0.30, ink)[..., None]
        hair_fg = mix(fg, hair_rgb * 0.8, dense)
        hair_cov = g.cov[idx][..., None]
        hair_bg = np.clip((pic - hair_fg * hair_cov) / (1.0 - hair_cov), pic * 0.3, pic * BG_MAX)
        fg = np.where(hair[..., None], hair_fg, fg)
        bg = np.where(hair[..., None], hair_bg, bg)

        # stars, only where we can see space through the pupil
        if t > 4.2:
            gx, gy, pr = P["pupil"]
            st_ch, st_i, st_c = self.stars.draw(t, gx, gy, pr, self.cw, self.ch, P["space"], g)
            si = st_i * np.clip(P["space"] * 1.2, 0.0, 1.0)
            use = (si > 0.06) & (si > lum * 0.9)
            idx = np.where(use, st_ch, idx)
            fg = np.where(use[..., None], st_c * (0.35 + 0.65 * np.minimum(1.0, si))[..., None], fg)
            bg = np.where(use[..., None], pic * bg_k, bg)
        return (idx.astype(np.uint8), (np.clip(fg, 0, 1) * 255).astype(np.uint8),
                (np.clip(bg, 0, 1) * 255).astype(np.uint8))


# ----------------------------------------------------------------------------
# Letters: how much "ink" every letter has, measured once from a typical
# terminal font (DejaVu Sans Mono), so no font file and no Pillow are needed.
# ----------------------------------------------------------------------------
INK_ORDER = (" `.',·:-\"~^;_─!*/\\r()|+><?cli[]vLjzxtJ}{Y1fCnuIoawZhX%k•"
             "$U&mbdpqO#08Q@BWM●")
INK = [0.0, 0.02, 0.028, 0.029, 0.037, 0.048, 0.057, 0.058, 0.059, 0.061, 0.062, 0.065,
       0.067, 0.067, 0.088, 0.104, 0.107, 0.107, 0.109, 0.111, 0.112, 0.115, 0.115, 0.116,
       0.116, 0.118, 0.126, 0.135, 0.139, 0.14, 0.14, 0.141, 0.142, 0.147, 0.148, 0.15,
       0.151, 0.151, 0.152, 0.153, 0.154, 0.155, 0.156, 0.156, 0.165, 0.165, 0.172, 0.174,
       0.19, 0.192, 0.194, 0.196, 0.199, 0.199, 0.2, 0.2, 0.206, 0.214, 0.216, 0.219, 0.222,
       0.223, 0.224, 0.224, 0.229, 0.229, 0.233, 0.241, 0.251, 0.267, 0.27, 0.272, 0.276, 0.352]


class Letters:
    def __init__(self):
        self.cov = np.zeros(len(CHARS), np.float32)
        for ch, ink in zip(INK_ORDER, INK):
            self.cov[CH[ch]] = ink
        for line, bold in zip(LINES, BOLD):
            self.cov[CH[bold]] = 1.7 * self.cov[CH[line]]     # bold letters have more ink
        # the ramp letters sorted by their ink (without the line letters: rows of
        # them would look like lines that are not in the picture)
        ramp = np.array([CH[c] for c in RAMP if c not in "_-|/\\"])
        self.ramp_idx = ramp[np.argsort(self.cov[ramp], kind="stable")]
        # the angle of the line letters - / | \ (a "/" is steeper in a taller cell)
        slash = math.degrees(math.atan(1.073 * GRID_ASPECT))
        self.line_idx = np.array([CH[c] for c in LINES])
        self.bold_idx = np.array([CH[c] for c in BOLD])
        self.line_ang = np.array([0.0, slash, 90.0, 180.0 - slash])

    def line_for(self, ang, bold=False):
        """The line letter (- / | \\) closest to each angle (degrees, 0 = to the right)."""
        diff = np.abs((np.asarray(ang)[..., None] - self.line_ang + 90.0) % 180.0 - 90.0)
        k = np.argmin(diff, axis=-1)
        return np.where(bold, self.bold_idx[k], self.line_idx[k])


# ----------------------------------------------------------------------------
# Making the frames: in helper processes (one per CPU core), before playing.
# The finished frames go into a cache file in the temp folder, one per terminal
# size. Its name depends on this program's code, so a changed program makes new frames.
# ----------------------------------------------------------------------------
def cache_file():
    try:
        with open(os.path.abspath(__file__), "rb") as fh:
            code = fh.read()
    except (NameError, OSError):
        return None
    key = hashlib.sha1(code + repr((COLS, ROWS, round(GRID_ASPECT, 3), BG_MAX)).encode()).hexdigest()[:16]
    return os.path.join(tempfile.gettempdir(), f"eye_to_space_{COLS}x{ROWS}_{key}.npz")


_scene = None                       # the scene of a helper process
# Pools we stopped. They must stay alive until the program ends: if Python threw a
# stopped pool away at once, its "cancel the frames we don't need" request would be
# lost, and when you quit, the program would first make all those frames (seconds!).
_stopped_pools = []


def stop_pool(pool):
    """Tell a pool to stop: finish the frames it is making now, forget the rest."""
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except TypeError:                               # Python 3.8 and older
        pool.shutdown(wait=False)
    _stopped_pools.append(pool)


def _make_scene(cols, rows, aspect, bg):
    """Make the scene for this terminal size (in a helper, or here if there are none)."""
    global _scene
    configure(cols, rows, aspect, bg)
    _scene = Scene(Letters())


def _start_helper(cols, rows, aspect, bg):
    """Runs once in every helper process."""
    try:                            # Ctrl+C is for the main program: it stops the helpers
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (ValueError, OSError):
        pass
    lower_priority()
    _make_scene(cols, rows, aspect, bg)


def _make_frame(i):
    return _scene.frame(i / FPS)


def lower_priority():
    """Helpers work a bit politely: everything else on the computer goes first."""
    try:
        if os.name == "nt":
            import ctypes
            k = ctypes.WinDLL("kernel32")
            k.GetCurrentProcess.restype = ctypes.c_void_p
            k.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
            k.SetPriorityClass(k.GetCurrentProcess(), 0x4000)   # BELOW_NORMAL_PRIORITY_CLASS
        else:
            os.nice(5)
    except (AttributeError, OSError):
        pass


def helper_count():
    """Half of the CPU threads (at least 2): fast enough, and the computer stays cooler
    and smooth for showing the animation while the frames are made."""
    return max(2, (os.cpu_count() or 2) // 2)


class Frames:
    """All frames of the animation, made in the background."""

    def __init__(self, cols, rows, aspect):
        configure(cols, rows, aspect)
        self.setup = (cols, rows, aspect, BG_MAX)
        self.n = int(END_TIME * FPS) + 1
        self.frames = [None] * self.n
        self.ready = 0                              # frames 0 .. ready-1 are done
        self.futures, self.pool, self.saver = [], None, None
        self.cache = cache_file() if USE_CACHE else None
        self.t_start = time.perf_counter()
        if self.load():
            return
        try:
            self.pool = ProcessPoolExecutor(helper_count(), initializer=_start_helper,
                                            initargs=self.setup)
            self.futures = [self.pool.submit(_make_frame, i) for i in range(self.n)]
        except (OSError, ImportError, NotImplementedError):
            self.use_threads()

    def use_threads(self):
        """No helper processes on this computer: make the rest of the frames here."""
        if self.pool:
            stop_pool(self.pool)
        _make_scene(*self.setup)
        self.pool = ThreadPoolExecutor(2)
        self.futures = self.futures[:self.ready] + [
            self.pool.submit(_make_frame, i) for i in range(self.ready, self.n)]

    def load(self):
        if not self.cache or not os.path.exists(self.cache):
            return False
        try:
            with np.load(self.cache) as data:
                idx, fg, bg = data["idx"], data["fg"], data["bg"]
            if len(idx) != self.n or idx.shape[1:] != (ROWS, COLS):
                return False
            self.frames = list(zip(idx, fg, bg))
            self.ready = self.n
            return True
        except Exception:                           # a broken file: make new frames instead
            try:
                os.remove(self.cache)
            except OSError:
                pass
            return False

    def save(self):
        try:
            tmp = "%s.%d.tmp" % (self.cache, os.getpid())     # two programs at once can't mix
            with open(tmp, "wb") as fh:
                np.savez_compressed(fh, idx=np.stack([f[0] for f in self.frames]),
                                    fg=np.stack([f[1] for f in self.frames]),
                                    bg=np.stack([f[2] for f in self.frames]))
            os.replace(tmp, self.cache)
        except OSError:
            return
        # every terminal size (and every changed version of this program) makes its
        # own cache file: keep only the newest few, so the temp folder doesn't fill up
        folder = os.path.dirname(self.cache)
        try:
            names = [n for n in os.listdir(folder) if n.startswith("eye_to_space_")]
        except OSError:
            return
        done = sorted((os.path.join(folder, n) for n in names if n.endswith(".npz")),
                      key=os.path.getmtime, reverse=True)
        left = [os.path.join(folder, n) for n in names if n.endswith(".tmp")]
        for path in done[CACHE_FILES:] + [f for f in left if time.time() - os.path.getmtime(f) > 3600]:
            try:
                os.remove(path)
            except OSError:
                pass

    def collect(self):
        """Take the finished frames (in order) from the helpers."""
        while self.ready < self.n and self.futures[self.ready].done():
            try:
                self.frames[self.ready] = self.futures[self.ready].result()
            except BrokenProcessPool:
                self.use_threads()
                return
            self.ready += 1
            if self.ready == self.n:
                self.pool.shutdown(wait=False)
                self.pool = None
                if self.cache:
                    self.saver = threading.Thread(target=self.save, daemon=True)
                    self.saver.start()

    def can_start(self):
        """Start as soon as the frames will be ready before they are needed."""
        if self.ready == self.n:
            return True
        if self.ready < 15:
            return False
        rate = self.ready / (time.perf_counter() - self.t_start)    # frames made per second
        return self.ready >= self.n * (1.0 - 0.85 * rate / FPS)

    def stop(self, wait_for_save=False):
        if self.pool:
            stop_pool(self.pool)
            self.pool = None
        if wait_for_save and self.saver is not None:
            self.saver.join(timeout=2.0)            # let the cache file be finished


# ----------------------------------------------------------------------------
# The terminal: alternate screen, hidden cursor, keys without Enter. Everything
# is put back when we stop (also after Ctrl+C or an error).
# ----------------------------------------------------------------------------
class Terminal:
    def __init__(self):
        self.out = sys.stdout.buffer
        self.windows = os.name == "nt"
        self.fd_in = None
        self.old_tty = None
        self.old_console = None

    def __enter__(self):
        if self.windows:
            self.windows_setup()
        elif termios and sys.stdin.isatty():
            self.fd_in = sys.stdin.fileno()
            self.old_tty = termios.tcgetattr(self.fd_in)
            tty.setcbreak(self.fd_in)               # keys come at once and are not shown
        # alternate screen (your terminal comes back at the end), hide the cursor,
        # no line wrap (so writing the last column never scrolls), clear
        self.write(b"\033[?1049h\033[?25l\033[?7l\033[0m\033[2J")
        return self

    def __exit__(self, *exc):
        self.write(b"\033[0m\033[?7h\033[?25h\033[?1049l")
        if self.old_tty is not None:
            termios.tcsetattr(self.fd_in, termios.TCSADRAIN, self.old_tty)
        if self.old_console is not None:
            import ctypes
            handle, mode, cp = self.old_console
            ctypes.windll.kernel32.SetConsoleMode(handle, mode)
            ctypes.windll.kernel32.SetConsoleOutputCP(cp)
        return False

    def windows_setup(self):
        """Windows: switch on escape codes and UTF-8 in the console."""
        try:
            import ctypes
            k = ctypes.windll.kernel32
            handle = k.GetStdHandle(-11)            # the console output
            mode = ctypes.c_uint32()
            if k.GetConsoleMode(handle, ctypes.byref(mode)):
                self.old_console = (handle, mode.value, k.GetConsoleOutputCP())
                k.SetConsoleMode(handle, mode.value | 0x0004)   # ENABLE_VIRTUAL_TERMINAL_PROCESSING
                k.SetConsoleOutputCP(65001)
        except (AttributeError, OSError):
            pass

    def write(self, data):
        self.out.write(data)
        self.out.flush()

    def size(self):
        try:
            return tuple(os.get_terminal_size(sys.stdout.fileno()))
        except OSError:
            return 100, 30

    def cell_aspect(self):
        """Height / width of one letter. Measured if the terminal tells its size in
        pixels (most Linux and macOS terminals do), otherwise TERM_ASPECT."""
        try:
            if termios:
                size = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\0" * 8)
                rows, cols, xpix, ypix = struct.unpack("HHHH", size)
                if rows and cols and xpix and ypix:
                    aspect = (ypix / rows) / (xpix / cols)
                    if 1.4 < aspect < 3.0:
                        return aspect
        except OSError:
            pass
        return TERM_ASPECT

    def keys(self):
        """The keys pressed since the last call (does not wait)."""
        keys = []
        if self.windows:
            import msvcrt
            while msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in "\x00\xe0":                # arrows, F-keys: a second code follows
                    msvcrt.getwch()
                else:
                    keys.append(ch)
        elif self.fd_in is not None:
            while select.select([self.fd_in], [], [], 0)[0]:
                data = os.read(self.fd_in, 64).decode("utf-8", "ignore")
                if not data:
                    break
                if data.startswith("\x1b") and len(data) > 1:   # arrows and other special keys
                    continue
                keys.extend(data)
        return keys


# ----------------------------------------------------------------------------
# Painter: turns a frame into escape codes. Only the cells that changed since
# the last frame are sent, and a colour code only when the colour changes.
# ----------------------------------------------------------------------------
CUBE = np.array([0, 95, 135, 175, 215, 255])        # the 6 levels of the 256-colour cube


def far(a, b, near):
    """Do two colours (0xRRGGBB numbers) differ by more than `near` in red, green or blue?"""
    return (abs((a >> 16) - (b >> 16)) > near or abs((a >> 8 & 255) - (b >> 8 & 255)) > near
            or abs((a & 255) - (b & 255)) > near)


def far_all(a, b, near):
    """far() for whole arrays of colours at once."""
    return ((np.abs((a >> 16) - (b >> 16)) > near) | (np.abs((a >> 8 & 255) - (b >> 8 & 255)) > near)
            | (np.abs((a & 255) - (b & 255)) > near))


def to_256(c):
    """Nearest colour number in the 256-colour palette (6x6x6 cube or grey ramp)."""
    c = c.astype(np.int32)
    q = np.searchsorted([48, 115, 155, 195, 235], c)  # nearest cube level per channel
    cube = 16 + 36 * q[..., 0] + 6 * q[..., 1] + q[..., 2]
    d_cube = ((CUBE[q] - c) ** 2).sum(-1)
    grey = np.clip((c.mean(-1) - 3) // 10, 0, 23).astype(np.int32)
    d_grey = ((8 + 10 * grey[..., None] - c) ** 2).sum(-1)
    return np.where(d_grey < d_cube, 232 + grey, cube)


class Painter:
    def __init__(self, colors="true", ascii_only=False, code=None):
        self.true = colors == "true"
        self.glyph, self.bold = [], []
        swap = {DOTS[0]: "@", DOTS[1]: "o", DOTS[2]: ".", SPIKE: "-"} if ascii_only else {}
        for ch in CHARS:
            self.bold.append(ch in BOLD)
            ch = LINES[BOLD.index(ch)] if ch in BOLD else swap.get(ch, ch)
            self.glyph.append(ch.encode("utf-8"))
        self.is_ramp = np.array([ch in RAMP and ch not in LINES for ch in CHARS])
        self.code = code                            # text of the program, for --code
        self.codes = {}                             # colour -> its escape code
        self.shown = None                           # what is on the screen now

    def colour(self, c):
        if self.true:
            c = (c & 0xFC).astype(np.int32)         # 64 levels per colour: looks the same, sends less
            return (c[..., 0] << 16) | (c[..., 1] << 8) | c[..., 2]
        return to_256(c)

    def code_of(self, c, ground):
        """Escape code part for a letter (ground 38) or background (ground 48) colour."""
        key = (c, ground)
        code = self.codes.get(key)
        if code is None:
            if self.true:
                code = b"%d;2;%d;%d;%d" % (ground, c >> 16, (c >> 8) & 255, c & 255)
            else:
                code = b"%d;5;%d" % (ground, c)
            if len(self.codes) > 200000:
                self.codes.clear()
            self.codes[key] = code
        return code

    def paint(self, frame, ox=0, oy=0):
        """Escape codes that change the screen from what it shows now to this frame.
        Two tricks send almost half as much (less work for the terminal, a cooler computer):
        a cell is sent again only if its letter changed or a colour changed so much that
        you could see it, and the colour codes are not repeated while the next cells
        have (almost) the same colour. The screen is never more than SAME_COLOUR off."""
        idx, fg, bg = frame
        fg, bg = self.colour(fg), self.colour(bg)
        near = SAME_COLOUR if self.true else 0      # 256 colours: compare exactly
        if self.shown is None:
            changed = np.ones(idx.shape, bool)
            self.shown = (idx.copy(), fg.copy(), bg.copy())
        else:
            s_idx, s_fg, s_bg = self.shown
            changed = (idx != s_idx) | far_all(fg, s_fg, near) | far_all(bg, s_bg, near)
        s_idx, s_fg, s_bg = self.shown              # what the screen shows (kept up to date)
        rows, cols = idx.shape
        if self.code:                               # --code: the program's own letters
            text = (self.code * (rows * cols // len(self.code) + 1))[:rows * cols]
        out = [b"\033[?2026h"]                      # begin a synchronized update
        pen_f = pen_b = pen_bold = None             # the colours the terminal draws with now
        for r in np.flatnonzero(changed.any(axis=1)).tolist():
            row_i, row_f, row_b = idx[r].tolist(), fg[r].tolist(), bg[r].tolist()
            shown_i, shown_f, shown_b = s_idx[r], s_fg[r], s_bg[r]
            last = -2
            for c in np.flatnonzero(changed[r]).tolist():
                if c != last + 1:                   # jump over cells that did not change
                    out.append(b"\033[%d;%dH" % (r + 1 + oy, c + 1 + ox))
                last = c
                i, f, b = row_i[c], row_f[c], row_b[c]
                bold = self.bold[i]
                part = []
                if bold != pen_bold:
                    part.append(b"1" if bold else b"22")
                    pen_bold = bold
                if pen_f is None or far(f, pen_f, near):
                    part.append(self.code_of(f, 38))
                    pen_f = f
                if pen_b is None or far(b, pen_b, near):
                    part.append(self.code_of(b, 48))
                    pen_b = b
                if part:
                    out.append(b"\033[" + b";".join(part) + b"m")
                if self.code and self.is_ramp[i] and i != 0:
                    out.append(text[r * cols + c].encode("utf-8"))
                else:
                    out.append(self.glyph[i])
                shown_i[c], shown_f[c], shown_b[c] = i, pen_f, pen_b
        out.append(b"\033[0m\033[?2026l")          # end of the synchronized update
        return b"".join(out)


def message(lines, cols, rows, true=True):
    """Escape codes for some centred lines of text on a black screen."""
    out = [b"\033[?2026h\033[0m\033[2J"]
    top = rows // 2 - len(lines) // 2
    for n, (text, (r, g, b)) in enumerate(lines):
        left = max(0, (cols - len(text)) // 2)
        if true:
            colour = b"38;2;%d;%d;%d" % (r, g, b)
        else:
            colour = b"38;5;%d" % int(to_256(np.array([r, g, b])))
        out.append(b"\033[%d;%dH\033[%sm" % (top + n + 1, left + 1, colour))
        out.append(text[:cols].encode("utf-8"))
    out.append(b"\033[0m\033[?2026l")
    return b"".join(out)


# ----------------------------------------------------------------------------
# Playing
# ----------------------------------------------------------------------------
def play(term, painter, aspect):
    frames = live = None
    size = None
    settle = None                   # when the terminal size changed last (we wait for it to stop)
    started = paused = False
    t0 = paused_at = 0.0
    shown_i, last_full, last_part = -1, 0.0, -1
    tick = time.perf_counter()
    try:
        while True:
            now = time.perf_counter()
            # the animation clock runs on the beat (the planned time of this frame),
            # not on the moment we woke up: then every frame comes exactly once and
            # evenly spaced, even if the computer wakes us up a little early or late
            beat = tick
            for key in term.keys():
                if key in ("q", "Q", "\x1b", "\x03"):
                    return
                if key in ("r", "R") and started:
                    t0, paused, shown_i = beat, False, -1
                if key == " " and started:
                    if paused:
                        t0 += beat - paused_at
                    else:
                        paused_at = beat
                    paused = not paused

            # first time, or the terminal changed size. While you drag the window edge
            # the size changes many times a second, so first wait until it stays the
            # same for a moment; then make the frames for the new size (only once).
            new_size = term.size()
            if new_size != size:
                settle = now if size is not None else now - 1.0     # the first time: at once
                size = new_size
                if frames:
                    frames.stop()
                frames = live = None
                term.write(b"\033[0m\033[2J")
            if settle is not None and now - settle >= 0.4:
                settle = None
                cols, rows = size
                if cols < 40 or rows < 12:
                    term.write(message([("make the terminal bigger", (200, 200, 200))], cols, rows, painter.true))
                else:
                    gc, gr = min(cols, MAX_COLS), min(rows, MAX_ROWS)
                    ox, oy = (cols - gc) // 2, (rows - gr) // 2
                    frames = Frames(gc, gr, aspect)
                    term.write(b"\033[0m\033[2J")
                    started, shown_i, last_part = False, -1, -1
                    painter.shown = None
            if frames is None:
                time.sleep(0.05)
                continue

            frames.collect()
            if not started and frames.can_start():
                tick = beat = time.perf_counter()   # loading the frames took a moment: the beat starts now
                started, paused, t0, shown_i = True, False, beat, -1
                term.write(b"\033[0m\033[2J")
                painter.shown = None
            if not started:
                part = int(100 * frames.ready / frames.n)
                if part != last_part:
                    last_part = part
                    bar = "#" * (part * 40 // 100) + "." * (40 - part * 40 // 100)
                    term.write(message([
                        ("E Y E   - >   S P A C E", (235, 150, 90)), ("", (0, 0, 0)),
                        (f"getting the frames ready   [{bar}]  {part:3d} %", (170, 170, 170)),
                        ("", (0, 0, 0)),
                        ("(only the first time for this terminal size - next time it starts at once)",
                         (95, 95, 95)), ("", (0, 0, 0)),
                        ("Q / Esc = quit     R = play again     Space = pause", (95, 95, 95))],
                        cols, rows, painter.true))
            else:
                t = (paused_at if paused else beat) - t0
                if t > END_TIME and WHEN_DONE == "close":
                    return                          # the end, like the video
                if t > END_TIME and WHEN_DONE == "loop":
                    t0, t, shown_i = beat, 0.0, -1  # play again from the start
                if now - last_full > 5.0:           # now and then send the whole picture,
                    painter.shown = None            # in case something messed up the screen
                    last_full, shown_i = now, -1
                if t > END_TIME:                    # "stay": keep flying through the stars
                    if live is None:
                        live = Scene(Letters())
                    term.write(painter.paint(live.frame(t), ox, oy))
                else:
                    i = min(int(t * FPS + 0.5), frames.ready - 1)
                    if i != shown_i:
                        term.write(painter.paint(frames.frames[i], ox, oy))
                        shown_i = i

            # wait for the next beat. If we are late, go on at once from the last beat
            # that has passed (skip the ones we missed, don't try to catch up): the
            # frames stay on the same even beat
            tick += 1.0 / FPS
            wait = tick - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
            else:
                tick += math.floor(-wait * FPS) / FPS
    finally:
        if frames:
            frames.stop(wait_for_save=True)


def detect_colors():
    """24-bit colour almost everywhere; macOS Terminal.app only has 256 colours."""
    if "truecolor" in os.environ.get("COLORTERM", "") or "24bit" in os.environ.get("COLORTERM", ""):
        return "true"
    if os.environ.get("TERM_PROGRAM") == "Apple_Terminal":
        return "256"
    return "true"


def main():
    global WHEN_DONE, USE_CACHE
    ap = argparse.ArgumentParser(description="Eye -> Space: an ASCII-art animation in the terminal.")
    ap.add_argument("--loop", action="store_true", help="play again and again")
    ap.add_argument("--stay", action="store_true", help="after the end, keep flying through the stars")
    ap.add_argument("--colors", choices=["auto", "true", "256"], default="auto",
                    help="24-bit colour or the 256-colour palette (default: auto)")
    ap.add_argument("--ascii", action="store_true", help="plain ASCII letters only")
    ap.add_argument("--bg", type=float, default=BG_MAX,
                    help="how bright the cell backgrounds are, 0 = black (default %(default)s)")
    ap.add_argument("--code", action="store_true", help="use this program's own code as the letters")
    ap.add_argument("--aspect", type=float, help="height / width of one letter (default: measured or %s)" % TERM_ASPECT)
    ap.add_argument("--no-cache", action="store_true", help="always make new frames")
    args = ap.parse_args()
    if not sys.stdout.isatty():
        if os.name == "nt":
            sys.exit("Please run this in a terminal, not in IDLE: open Windows Terminal, Command Prompt\n"
                     "or PowerShell (or the VS Code terminal) in this folder and type:  python eye_to_space.py")
        sys.exit("Please run this in a terminal (not in IDLE):  python3 eye_to_space.py")
    WHEN_DONE = "loop" if args.loop else "stay" if args.stay else "close"
    USE_CACHE = not args.no_cache
    configure(COLS, ROWS, GRID_ASPECT, min(max(args.bg, 0.0), 1.0))
    code = None
    if args.code:
        with open(os.path.abspath(__file__), encoding="utf-8") as fh:
            code = " ".join(line.strip() for line in fh if line.strip())
    colors = detect_colors() if args.colors == "auto" else args.colors
    painter = Painter(colors, args.ascii, code)
    try:
        with Terminal() as term:
            play(term, painter, args.aspect or term.cell_aspect())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
