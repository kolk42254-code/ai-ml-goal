"""
Messi in ASCII - the engine behind the three versions.

The whole photo (Messi with his arms open, the crowd, both flags, the photographers
and the pitch) is drawn with text characters. Every character is chosen from the
photo: denser characters where it is brighter, line characters ( / \\ | _ ( ) ) along
edges, and the words MESSI written with real letters. Each character sits on a dim
version of its own colour and the character makes up the rest, so the picture keeps
the photo's real colours. Glowing particles fly in and build Messi first; then the
stadium lights up around him in a wave.

Run one of the three versions (they all use this file and messi_art.npz):
  python Messi_v1_window_head_first.py   window, small letters, he forms from his head down
  python Messi_v2_window_feet_first.py   window, big letters, he forms from his feet up
  python Messi_v3_terminal.py            in the terminal, filling it (head first)
  (or run this file and choose 1, 2 or 3)
Add --mp4 to save that version as a video, --png for a still picture.
Remake the art from the photo: python messi_ascii.py --photo messi.jpg --save-art
Needs:   pip install numpy opencv-python pillow imageio-ffmpeg
Keys:    R or Space = play again,  Esc or Q = close  (in a window, F = full screen)
"""

import argparse
import math
import os
import shutil
import sys
import time
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------ settings
PHOTO, MASK, ART_FILE = "messi.jpg", "messi_mask.png", "messi_art.npz"
VIDEO_SECONDS = 16.0
FPS = 60
SEED = 10                       # another number gives different particle paths
TINT = 0.40                     # how bright a character's background is, as a part of its colour
PARTICLES = 5000                # about this many particles build Messi in a window (fewer in a terminal)

# ------------------------------------------------------------------ layout
# The picture is 1080 x 1440 pixels (the photo's own shape). Small letters are
# 6 x 12 pixels (180 x 120 characters), big letters 12 x 24 (90 x 60).
W, H = 1080, 1440
GRIDS = {"small": (6, 12), "big": (12, 24)}
TERM_ROWS = tuple(range(16, 64, 2)) + tuple(range(64, 124, 4))   # terminal art: this many rows tall

# what each version does: where it plays, its letters and which way Messi forms
VERSIONS = {1: dict(where="window", grid="small", way="down", name="window, small letters, head first"),
            2: dict(where="window", grid="big", way="up", name="window, big letters, feet first"),
            3: dict(where="terminal", grid="small", way="down", name="terminal, head first")}

# characters
RAMP = " .:-=+*#%@"            # shading: the more ink, the brighter
LINES = "/\\|_()<>^v'`"        # shapes that follow edges
FLICKER = "@#%&*+=$"           # characters flash through these as a particle lands
GLYPHS = "".join(dict.fromkeys(RAMP + LINES + FLICKER + "".join(map(chr, range(32, 127)))))   # every ASCII character
# words in the photo, written with real letters (box as parts of the photo's width and height)
TEXTS = (("MESSI", (237 / 482, 344 / 636, 267 / 482, 354 / 636)),     # on his shirt
         ("MESSI", (87 / 482, 125 / 636, 145 / 482, 143 / 636)))      # on the banner in the crowd
CAPTION = (300 / 482, 26 / 636, 430 / 482, 64 / 636)                  # 'My GOAT', painted out of the photo

# timeline (seconds)
T_BUILD = 1.4                   # the first particles land
T_MESSI = 8.6                   # Messi is complete
FLY = (1.3, 2.4)                # each particle flies this long (shortest, longest)
T_STAGE = 8.9                   # the stadium starts to light up around him...
STAGE = 3.0                     # ...and takes this long to reach the corners
T_ALL = T_STAGE + STAGE + 0.6   # everything is there; the crowd's lights twinkle


# ------------------------------------------------------------------ small helpers
def smoothstep(e0, e1, x):
    x = np.clip((np.asarray(x, np.float32) - e0) / (e1 - e0), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def to_linear(c):
    """sRGB colour (0..1) -> linear light."""
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def to_srgb(c):
    """Linear light (0..1) -> sRGB colour."""
    c = np.clip(np.asarray(c, np.float32), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055).astype(np.float32)


class Gradient:
    """Colour at any position between colour stops; works on whole arrays at once."""

    def __init__(self, *stops, n=512):
        pos = np.array([p for p, _ in stops], np.float32)
        cols = np.array([c for _, c in stops], np.float32)
        self.lo, self.k = float(pos[0]), (n - 1) / float(pos[-1] - pos[0])
        grid = np.linspace(pos[0], pos[-1], n)
        self.lut = np.stack([np.interp(grid, pos, cols[:, i]) for i in range(3)], 1).astype(np.float32)

    def __call__(self, v):
        i = ((np.asarray(v, np.float32) - self.lo) * self.k).astype(np.int32)
        return self.lut[np.clip(i, 0, len(self.lut) - 1)]


HOT = Gradient((0.0, (0.0, 0.0, 0.0)), (0.3, (0.5, 0.06, 0.01)), (0.55, (1.6, 0.55, 0.08)),
               (0.8, (2.6, 1.7, 0.6)), (1.0, (3.4, 3.0, 2.4)))       # glowing: dark red .. orange .. white
SPARK = np.array([1.0, 0.85, 0.62], np.float32)                      # warm glow of a flying particle
WHITE = np.array([1.0, 0.97, 0.92], np.float32)
EMPTY_BG = (10, 8, 14)                                               # the dark background (terminal)
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def find_font(names):
    folders = [os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"),
               "/usr/share/fonts/truetype/dejavu", "/Library/Fonts", "/System/Library/Fonts"]
    for name in names:
        for folder in folders:
            if os.path.exists(os.path.join(folder, name)):
                return os.path.join(folder, name)
    return None


@lru_cache(maxsize=None)
def build_atlas(cw, ch):
    """Every character of GLYPHS drawn once into a cw x ch greyscale cell (0..1)."""
    path = find_font(["consolab.ttf", "consola.ttf", "DejaVuSansMono-Bold.ttf", "Menlo.ttc"])
    font = ImageFont.truetype(path, max(6, round(cw / 0.55))) if path else ImageFont.load_default()
    atlas = np.zeros((len(GLYPHS), ch, cw), np.float32)
    for i, g in enumerate(GLYPHS):
        im = Image.new("L", (cw * 3, ch * 3), 0)
        ImageDraw.Draw(im).text((cw * 1.5, ch * 1.5), g, fill=255, font=font, anchor="mm")
        atlas[i] = np.asarray(im, np.float32)[ch:2 * ch, cw:2 * cw] / 255.0
    return atlas


GLYPH_OF = np.zeros(256, np.int32)                                   # character code -> its place in GLYPHS
GLYPH_OF[np.frombuffer(GLYPHS.encode(), np.uint8)] = np.arange(len(GLYPHS))


# ------------------------------------------------------------------ photo -> ASCII art
def load_photo(photo_path, mask_path):
    """The photo (sRGB 0..1, with 'My GOAT' painted out) and how much of each pixel is Messi (0..1)."""
    photo = cv2.imread(photo_path)
    if photo is None:
        sys.exit(f"Could not read the photo '{photo_path}'.")
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        sys.exit(f"Could not read his outline '{mask_path}' ({MASK} should be next to this script).")
    h, w = photo.shape[:2]
    if mask.shape != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
    x0, y0, x1, y1 = (int(CAPTION[0] * w), int(CAPTION[1] * h), int(CAPTION[2] * w), int(CAPTION[3] * h))
    text = np.zeros((h, w), np.uint8)
    text[y0:y1, x0:x1] = (photo[y0:y1, x0:x1].min(-1) > 140) * 255  # white letters of the caption
    if text.any():
        photo = cv2.inpaint(photo, cv2.dilate(text, np.ones((5, 5), np.uint8)), 6, cv2.INPAINT_TELEA)
    rgb = cv2.cvtColor(photo, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    return rgb, mask.astype(np.float32) / 255.0


def place(rgb, alpha, size):
    """Scale and centre the photo so it covers a picture of this size (a sliver may be cut off)."""
    pw, ph = size
    h, w = rgb.shape[:2]
    s = max(pw / w, ph / h)
    M = np.float32([[s, 0, pw / 2 - s * w / 2], [0, s, ph / 2 - s * h / 2]])
    big = cv2.warpAffine(rgb, M, (pw, ph), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    a = cv2.warpAffine(alpha, M, (pw, ph), flags=cv2.INTER_LINEAR, borderValue=0)
    return np.clip(big, 0.0, 1.0), np.clip(a, 0.0, 1.0), M


def convert(rgb, alpha, cw, ch, size=(W, H)):
    """Choose a character, its colour and its background colour for every cell (cw x ch pixels of a picture
    of this size). The shading of the photo picks a character from RAMP (more ink = brighter); where the
    photo has a real edge, a character from LINES whose shape lines up with it can win instead. The
    background is a dim version of the cell's colour and the character makes up the rest, so the cell
    looks as bright as the photo there. Returns ASCII codes, colours, background colours (sRGB 0..1) and
    which cells are Messi."""
    cols, rows = size[0] // cw, size[1] // ch
    big, a, M = place(rgb, alpha, size)
    chars = RAMP + LINES
    G = build_atlas(cw, ch)[[GLYPHS.index(c) for c in chars]]
    K, nr = len(chars), len(RAMP)
    ink = G.mean((1, 2))
    tone_g = ink / ink[:nr].max()                         # how bright each character looks (0..1)
    blur = 0.8 * cw / 6
    Gs = np.stack([cv2.GaussianBlur(g, (0, 0), blur) for g in G]).reshape(K, -1)
    Gs -= Gs.mean(1, keepdims=True)                       # each character's shape, scaled to length 1
    Gs /= np.maximum(np.linalg.norm(Gs, axis=1, keepdims=True), 1e-6)
    light = 0.5 * (big * LUMA).sum(-1) + 0.5 * big.max(-1)   # vivid colours count as bright, as they look
    soft = cv2.GaussianBlur(light, (0, 0), blur)
    P = soft.reshape(rows, ch, cols, cw).transpose(0, 2, 1, 3).reshape(-1, ch * cw)
    Pz = P - P.mean(1, keepdims=True)
    contrast = np.linalg.norm(Pz, axis=1) / math.sqrt(ch * cw)             # how much edge is in the cell
    match = (Pz @ Gs.T) / np.maximum(contrast * math.sqrt(ch * cw), 1e-6)[:, None]   # -1..1 shape match
    tone = cv2.GaussianBlur(light, (0, 0), cw * 0.6).reshape(rows, ch, cols, cw).mean((1, 3)).ravel()
    lo, hi = np.percentile(tone, [1, 99.7])
    T = 0.12 + 0.88 * np.clip((tone - lo) / (hi - lo), 0.0, 1.0) ** 0.8   # wanted brightness 0..1
    edge = np.clip((contrast - 0.015) / 0.030, 0.0, 1.0) ** 1.5           # 0 flat .. 1 a clear edge
    score = 4.0 * (tone_g[None, :] - T[:, None]) ** 2 - 0.6 * edge[:, None] * match
    score[:, nr:] += 0.08 + 2.0 * (1.0 - edge[:, None])                    # line characters only on edges
    score[:, 0] += np.where(T > 0.04, 1.0, 0.0)                            # a blank only for black
    k = score.argmin(1).reshape(rows, cols)
    lin = to_linear(big).reshape(rows, ch, cols, cw, 3).mean((1, 3))      # the cell's colour, as light
    fore, back = colours_for(lin, ink[k])
    codes = np.frombuffer(chars.encode(), np.uint8)[k]
    messi = a.reshape(rows, ch, cols, cw).mean((1, 3)) > 0.4

    # the words MESSI, as printed: dark letters on their light background
    ph_h, ph_w = rgb.shape[:2]
    for word, (fx0, fy0, fx1, fy1) in TEXTS:
        cx0, cx1 = M[0, 0] * fx0 * ph_w + M[0, 2], M[0, 0] * fx1 * ph_w + M[0, 2]
        cy0, cy1 = M[1, 1] * fy0 * ph_h + M[1, 2], M[1, 1] * fy1 * ph_h + M[1, 2]
        width, height = (cx1 - cx0) / cw, (cy1 - cy0) / ch
        if width < 0.8 * len(word):                        # too small to write: the shading shows it
            continue
        r0, r1 = max(0, int(cy0 // ch)), min(rows, int(math.ceil(cy1 / ch)))
        c0, c1 = max(0, int(cx0 // cw)), min(cols, int(math.ceil(cx1 / cw)))
        box = to_linear(big[r0 * ch:r1 * ch, c0 * cw:c1 * cw])        # the cells round the word, as light
        lum = box @ LUMA
        y0, x0 = int(cy0) - r0 * ch, int(cx0) - c0 * cw
        inside = lum[y0:int(cy1) - r0 * ch + 1, x0:int(cx1) - c0 * cw + 1]
        ink_lum, paper_lum = np.percentile(inside, 12), np.percentile(inside, 80)
        cut = (ink_lum + paper_lum) / 2.0
        inked = np.clip((cut - lum) / max(0.25 * (paper_lum - ink_lum), 1e-6) + 0.5, 0.0, 1.0)   # 1 = letter
        dark = (box * inked[..., None]).sum((0, 1)) / max(inked.sum(), 1e-6)       # the letters' colour
        n_r, n_c = r1 - r0, c1 - c0
        wpaper = (1.0 - inked).reshape(n_r, ch, n_c, cw)[..., None]
        paper = (box.reshape(n_r, ch, n_c, cw, 3) * wpaper).sum((1, 3)) / np.maximum(wpaper.sum((1, 3)), 1e-6)
        whole = (box * (1.0 - inked)[..., None]).sum((0, 1)) / max((1.0 - inked).sum(), 1e-6)
        some = np.clip(wpaper.mean((1, 3)) / 0.25, 0.0, 1.0)              # cells that are nearly all letter:
        paper = paper * some + whole * (1.0 - some)                        # the word's paper colour instead
        # where each printed letter is: the runs of inked columns, if there is one run for every letter
        prof = inked[y0:int(cy1) - r0 * ch + 1].mean(0) > 0.12
        edges = np.flatnonzero(np.diff(np.r_[0, prof.astype(np.int8), 0]))
        runs = list(zip(edges[::2], edges[1::2]))
        if width / len(word) < 1.6:                                        # letters close together: side by side
            first = int(round((cx0 + cx1) / 2 / cw - len(word) / 2))
            centres = [first + i + 0.5 for i in range(len(word))]
        elif len(runs) == len(word):
            centres = [(a + b) / 2.0 / cw + c0 for a, b in runs]          # in cells
        else:                                                              # evenly over the word's width
            centres = [(cx0 + (i + 0.5) * (cx1 - cx0) / len(word)) / cw for i in range(len(word))]
        places = [int(math.floor(c)) for c in centres]
        for i in range(1, len(places)):                                    # never two letters in one cell
            places[i] = max(places[i], places[i - 1] + 1)
        shift = max(0, places[-1] - (cols - 1))
        places = [p - shift for p in places]
        # the word on one row, each letter where it is printed, on the paper it is printed on
        r = min(rows - 1, int(((cy0 + cy1) / 2) // ch))
        rr = slice(r0, r1) if height > 2.2 else slice(r, r + 1)            # a tall word: its whole band is paper
        codes[rr, c0:c1] = 32
        fore[rr, c0:c1] = back[rr, c0:c1] = paper[rr.start - r0:rr.stop - r0]
        for letter, c in zip(word, places):
            if 0 <= c < cols:
                codes[r, c], fore[r, c] = ord(letter), dark
                if not c0 <= c < c1:
                    back[r, c] = paper[r - r0, min(max(c - c0, 0), n_c - 1)]
    return codes, to_srgb(fore), to_srgb(back), messi


def colours_for(lin, cov, back=None):
    """A character's colour and its background colour (both as light) so that a cell with this much ink
    looks, on average, exactly like the photo's colour lin there. The background is a dim version of the
    colour; the character makes up the rest, and where it cannot (too little ink), the background helps."""
    cov = np.asarray(cov, np.float32)[..., None]
    back = lin * TINT if back is None else back
    fore = np.clip((lin - back * (1.0 - cov)) / np.maximum(cov, 1e-3), 0.0, 1.0)
    back = np.clip((lin - fore * cov) / np.maximum(1.0 - cov, 1e-3), 0.0, 1.0)
    return fore.astype(np.float32), back.astype(np.float32)


def term_cols(rows):
    """Columns of the terminal art that is `rows` tall (terminal characters are twice as tall as wide)."""
    return int(round(rows * W / H * 2.0))


# ------------------------------------------------------------------ the art file
def art_from_photo(photo, grid):
    rgb, alpha = load_photo(photo, os.path.join(HERE, MASK))
    if grid in GRIDS:
        return convert(rgb, alpha, *GRIDS[grid])
    rows = int(grid[4:])
    return convert(rgb, alpha, 12, 24, size=(term_cols(rows) * 12, rows * 24))


def save_art(photo):
    """Work out every art (small, big and every terminal size) from the photo and save them all."""
    data = {}
    for grid in list(GRIDS) + [f"term{n}" for n in TERM_ROWS]:
        codes, fore, back, messi = art_from_photo(photo, grid)
        data[grid + "_text"] = np.array([chr(c) for c in codes.ravel()]).reshape(codes.shape)
        data[grid + "_fg"] = np.round(fore * 255.0).astype(np.uint8)
        data[grid + "_bg"] = np.round(back * 255.0).astype(np.uint8)
        data[grid + "_messi"] = messi
        print(f"\rmade the art: {grid}    ", end="", flush=True)
    path = os.path.join(HERE, ART_FILE)
    np.savez_compressed(path, **data)
    print(f"\nsaved {path}")


def load_art(grid, f=None):
    """One art from the art file: ASCII codes, colours, background colours (sRGB 0..1), Messi's cells."""
    if f is None:
        path = os.path.join(HERE, ART_FILE)
        if not os.path.exists(path):
            sys.exit(f"{ART_FILE} should be next to this script (or make it: --photo {PHOTO} --save-art).")
        with np.load(path) as f:
            return load_art(grid, f)
    text = f[grid + "_text"]
    codes = np.frombuffer(np.ascontiguousarray(text, dtype="<U1").tobytes(), np.uint32).reshape(text.shape).astype(np.uint8)
    return codes, f[grid + "_fg"] / 255.0, f[grid + "_bg"] / 255.0, f[grid + "_messi"].astype(bool)


# ------------------------------------------------------------------ particles
def lit_up(on, age, messi):
    """How a cell looks just after it appears: Messi's characters land white-hot and cool to their colour;
    the stadium fades in out of the dark with a faint touch of white stadium light.
    Returns how much of the cell's own colour shows (0..1), the light added to it, and Messi's heat."""
    heat = np.where(on & messi, np.exp(-age / 0.30), 0.0).astype(np.float32)
    glow = HOT(0.55 + 0.45 * heat) * (1.3 * heat)[..., None]
    fade = smoothstep(0.0, 0.35, age)
    keep = np.where(messi, 1.0 - heat, fade) * on
    add = np.where(messi[..., None], glow, WHITE * (0.10 * np.exp(-age / 0.25) * on)[..., None])
    return keep.astype(np.float32)[..., None], add.astype(np.float32), heat


CROWD = 0.70                    # the crowd fills the photo down to here (as a part of its height)


def in_crowd(messi, rows, area=None):
    """The cells of the crowd in the stands (above the photographers), not Messi."""
    area = np.ones(messi.shape, bool) if area is None else area
    r, _ = np.nonzero(area)
    top, bottom = (r.min(), r.max() + 1) if len(r) else (0, rows)
    return area & ~messi & (np.arange(rows)[:, None] < top + CROWD * (bottom - top))


def twinkle(t, glints, crowd):
    """Light added to the few cells of the crowd where a phone light twinkles at time t."""
    g = np.sin(t * 2.2 + glints * 40.0) * 0.5 + 0.5
    return WHITE * (0.45 * np.clip((g - 0.996) / 0.004, 0, 1) * crowd)[..., None]


class Particles:
    """Paths of the particles: drifting slowly (p0, p_vy, p_sw, p_hz, p_ph), then flying along a curve
    (p_from, p_mid, p_to) to the character they light up."""

    def _drift(self, t, i):
        t = np.asarray(t, np.float32)
        x = self.p0[i, 0] + self.p_sw[i] * np.sin(t * self.p_hz[i, 0] + self.p_ph[i, 0])
        y = self.p0[i, 1] + self.p_vy[i] * t + 0.6 * self.p_sw[i] * np.cos(t * self.p_hz[i, 1] + self.p_ph[i, 1])
        return np.stack([x, y], 1).astype(np.float32)

    def _flight(self, i, f):
        e = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)      # slow start, slow landing
        e = e[:, None]
        return (1 - e) ** 2 * self.p_from[i] + 2 * e * (1 - e) * self.p_mid[i] + e * e * self.p_to[i]

    def _plan(self, messi, cell_w, cell_h, width, height, way, count, rng, area=None):
        """When every cell appears, and the particles that build Messi. Positions are in units where a
        cell is cell_w x cell_h; the picture is width x height; area marks the cells the picture covers."""
        area = np.ones(messi.shape, bool) if area is None else area
        rows, cols = messi.shape
        self.land = np.full((rows, cols), np.inf, np.float32)
        mr, mc = np.nonzero(messi)
        cy, cx = (mr + 0.5) * cell_h, (mc + 0.5) * cell_w
        top, bottom = cy.min(), cy.max()
        tall = max(bottom - top, 1e-6)
        d = (cy - top) / tall if way == "down" else (bottom - cy) / tall    # 0 where he starts forming
        wave = 0.04 * np.sin(cx / (0.11 * tall))                            # the building line is a little wavy
        first = T_BUILD + (T_MESSI - T_BUILD - 0.5) * np.clip(d + wave, 0, 1) ** 0.95 + 0.5 * rng.random(len(mr))
        self.land[mr, mc] = first
        # the stadium lights up in a wave going out from him
        self.centre = np.array([cx.mean(), cy.mean()], np.float32)
        sr, sc = np.nonzero(~messi & area)
        dist = np.hypot((sc + 0.5) * cell_w - self.centre[0], (sr + 0.5) * cell_h - self.centre[1])
        rough = cv2.GaussianBlur(rng.standard_normal(messi.shape).astype(np.float32), (0, 0), max(2.0, rows / 40))
        rough /= max(float(rough.std()), 1e-6)                              # an uneven, cloudy wave front
        self.land[sr, sc] = (T_STAGE + STAGE * (dist / max(dist.max(), 1e-6)) ** 0.85
                             + 0.12 * rough[sr, sc] + 0.08 * rng.random(len(sr)))
        self.messi = messi
        # particles: several for every character of Messi, so the swarm looks full
        per = max(1, int(round(count / max(len(mr), 1))))
        self.pr, self.pc = np.repeat(mr, per), np.repeat(mc, per)
        n = len(self.pr)
        extra = np.arange(n) % per > 0
        land = np.repeat(first, per) + np.where(extra, rng.uniform(0.03, 0.35, n), 0.0)
        tx = (self.pc + 0.5) * cell_w + extra * rng.uniform(-0.3, 0.3, n) * cell_w
        ty = (self.pr + 0.5) * cell_h + extra * rng.uniform(-0.3, 0.3, n) * cell_h
        self.p_land, self.p_fly = land.astype(np.float32), rng.uniform(*FLY, n).astype(np.float32)
        self.p_to = np.stack([tx, ty], 1).astype(np.float32)
        # before they fly, they drift: falling from the top (head first) or rising from the bottom (feet first)
        sign = 1.0 if way == "down" else -1.0
        y0 = rng.uniform(-0.25, 0.42, n) if way == "down" else rng.uniform(0.58, 1.25, n)
        self.p0 = np.stack([rng.uniform(-0.04, 1.04, n) * width, y0 * height], 1).astype(np.float32)
        self.p_vy = (sign * rng.uniform(0.008, 0.028, n) * tall).astype(np.float32)
        self.p_sw = (rng.uniform(0.006, 0.018, n) * tall).astype(np.float32)
        self.p_ph = rng.uniform(0.0, 6.3, (n, 2)).astype(np.float32)
        self.p_hz = rng.uniform(0.25, 0.7, (n, 2)).astype(np.float32)
        start = self._drift(self.p_land - self.p_fly, np.arange(n))
        dd = self.p_to - start
        dist = np.maximum(np.hypot(dd[:, 0], dd[:, 1]), 1e-6)
        normal = np.stack([-dd[:, 1], dd[:, 0]], 1) / dist[:, None]
        self.p_from = start
        self.p_mid = ((start + self.p_to) / 2 + normal * rng.normal(0.0, 0.30, (n, 1)) * dist[:, None]).astype(np.float32)
        self.tall, self.sign = tall, sign


# ------------------------------------------------------------------ the film (window and video)
class Film(Particles):
    """The animation: build once, then render(t) for any time t (seconds)."""

    def __init__(self, art, cw, ch, way="down", seed=SEED):
        codes, fore, back, messi = art
        self.rows, self.cols = codes.shape
        self.lcw, self.lch = W / self.cols, H / self.rows   # a cell on the 1080 x 1440 picture
        self.cw, self.ch = cw, ch                         # a cell on the screen
        self.s = cw / self.lcw                            # screen pixels per picture pixel
        self.w, self.h = self.cols * cw, self.rows * ch
        self.end = None                                   # fade to black at this time (for the video)
        self.atlas_rows = build_atlas(cw, ch).reshape(-1, cw)
        self.row_of_cell = np.arange(ch, dtype=np.int32)[None, :, None]
        self.g = GLYPH_OF[codes]
        # the art's colours were worked out for characters of its own size; characters drawn at another
        # size have a little more or less ink, so the colours are worked out again for this size
        fore, back = to_linear(fore), to_linear(back)
        made = build_atlas(int(round(self.lcw)), int(round(self.lch))).mean((1, 2))[self.g][..., None]
        lin = back * (1.0 - made) + fore * made                # the photo's colour in each cell
        self.fore, self.back = colours_for(lin, build_atlas(cw, ch).mean((1, 2))[self.g], back)
        rng = np.random.default_rng(seed)
        self._plan(messi, self.lcw, self.lch, W, H, way, PARTICLES, rng)
        lin = self.fore[self.pr, self.pc]
        self.p_col = (0.55 * lin / np.maximum(lin.max(1, keepdims=True), 0.05) + 0.45 * SPARK).astype(np.float32)
        self.p_tw = rng.uniform(1.0, 3.5, len(self.pr)).astype(np.float32)
        m = 220                                           # faint embers drifting the whole time
        self.e0 = np.stack([rng.uniform(0, W, m), rng.uniform(0, H + 80, m)], 1).astype(np.float32)
        self.e_vy = (self.sign * rng.uniform(25.0, 70.0, m)).astype(np.float32)
        self.e_ph = rng.uniform(0.0, 6.3, m).astype(np.float32)
        # some stadium cells throw a small spark outwards as they light up
        sr, sc = np.nonzero(~messi & (rng.random(messi.shape) < 0.04))
        self.s_r, self.s_c = sr, sc
        pos = np.stack([(sc + 0.5) * self.lcw, (sr + 0.5) * self.lch], 1)
        out = pos - self.centre
        self.s_pos = pos.astype(np.float32)
        self.s_dir = (out / np.maximum(np.hypot(out[:, 0], out[:, 1]), 1.0)[:, None]).astype(np.float32)
        self.s_col = (0.4 * self.fore[sr, sc] / np.maximum(self.fore[sr, sc].max(1, keepdims=True), 0.05)
                      + 0.6 * WHITE).astype(np.float32)
        self.glints = rng.random((self.rows, self.cols)).astype(np.float32)
        self.crowd = in_crowd(messi, self.rows)
        # light in the air is drawn at half size
        self.lh, self.lw = self.h // 2, self.w // 2
        ly, lx = np.mgrid[0:self.lh, 0:self.lw].astype(np.float32)
        r = np.hypot((lx + 0.5) / self.lw - 0.5, ((ly + 0.5) / self.lh - 0.52) * 1.3)
        self.bg = (np.array([0.008, 0.006, 0.012], np.float32) * np.exp(-3.0 * r * r)[..., None]
                   + np.array([0.0012, 0.0012, 0.0022], np.float32))
        self.qh, self.qw = self.h // 4, self.w // 4
        self.enc = 255.0 / math.log1p(400.0 * 8.0)         # light -> screen colours, true to the photo
        x = np.expm1(np.arange(256) / self.enc) / 400.0
        soft = np.where(x < 0.85, x, 0.85 + 0.15 * (1.0 - np.exp(-(x - 0.85) / 0.15)))
        self.tone = np.clip(to_srgb(soft) * 255.0 + 0.5, 0, 255).astype(np.uint8)
        self.buf_glyph = np.empty((self.rows, ch, self.cols, cw), np.float32)
        self.buf_fg, self.buf_bg, self.buf_up, self.buf_a3 = (np.empty((self.h, self.w, 3), np.float32) for _ in range(4))
        self.buf_u8, self.buf_tone = (np.empty((self.h, self.w, 3), np.uint8) for _ in range(2))
        self.out = np.zeros((self.h, self.w, 3), np.uint8)

    def render(self, t, still=False):
        """The picture at time t as an RGB image (uint8); the same array is reused by the next call.
        still=True leaves out everything that moves (particles, sparks, glints, the push in)."""
        s2 = self.s / 2.0
        age = t - self.land
        on = age >= 0.0
        a = np.maximum(age, 0.0)
        keep, add, heat = lit_up(on, a, self.messi)
        FG = np.where(on[..., None], self.fore * keep + add, 0.0)
        BG = np.where(on[..., None], self.back * keep + 0.3 * add, 0.0)
        G = np.where(on, self.g, 0).astype(np.int32)
        flick = on & self.messi & (age < 0.08)
        if flick.any():
            pick = (self.glints[flick] * 997 + t * 60).astype(np.int32) % len(FLICKER)
            G[flick] = np.array([GLYPHS.index(c) for c in FLICKER])[pick]
        if t >= T_ALL and not still:                      # phone lights twinkle in the crowd
            FG = FG + twinkle(t, self.glints, self.crowd)

        # ---- characters -> picture: the background colour, and the character's colour where its ink is
        np.take(self.atlas_rows, G[:, None, :] * self.ch + self.row_of_cell, axis=0, out=self.buf_glyph)
        alpha = self.buf_glyph.reshape(self.h, self.w)
        fimg = cv2.resize(FG.astype(np.float32), (self.w, self.h), dst=self.buf_fg, interpolation=cv2.INTER_NEAREST)
        img = cv2.resize(BG.astype(np.float32), (self.w, self.h), dst=self.buf_bg, interpolation=cv2.INTER_NEAREST)
        cv2.subtract(fimg, img, dst=fimg)
        cv2.multiply(fimg, cv2.merge([alpha, alpha, alpha], dst=self.buf_a3), dst=fimg)
        cv2.add(img, fimg, dst=img)

        # ---- light in the air: drifting and flying particles, landing flashes, sparks; the faint glow
        # behind Messi fades away as the stadium appears, so the finished picture has only the photo's light
        lb = self.bg * (0.0 if still else 1.0 - float(smoothstep(T_STAGE, T_STAGE + STAGE, t)))
        if not still:
            fade = float(smoothstep(0.0, 1.2, t))
            n = len(self.p_land)
            idx = np.arange(n)
            launch = self.p_land - self.p_fly
            drifting = t < launch
            if drifting.any():
                i = idx[drifting]
                p = self._drift(np.full(len(i), t, np.float32), i)
                b = (0.10 + 0.08 * np.sin(t * self.p_tw[i] + self.p_ph[i, 0])) * fade
                self._dots(lb, p, self.p_col[i] * b[:, None], s2)
            flying = (~drifting) & (t < self.p_land)
            if flying.any():
                i = idx[flying]
                f = (t - launch[i]) / self.p_fly[i]
                glow = 0.35 + 0.65 * f
                for j, back in enumerate((0.0, 0.025, 0.05, 0.08)):      # a short glowing trail
                    p = self._flight(i, np.clip(f - back, 0.0, 1.0))
                    self._dots(lb, p, self.p_col[i] * (glow * (1.0 - 0.22 * j))[:, None], s2)
            ex = self.e0[:, 0] + 14.0 * np.sin(t * 0.8 + self.e_ph)
            ey = np.mod(self.e0[:, 1] + self.e_vy * t + 40.0, H + 80.0) - 40.0
            b = (0.06 + 0.05 * np.sin(t * 3.0 + self.e_ph * 3.0)) * fade * (1.0 - float(smoothstep(T_STAGE, T_ALL, t)) * 0.7)
            self._dots(lb, np.stack([ex, ey], 1), SPARK * b[:, None], s2)
            sa = t - self.land[self.s_r, self.s_c]
            live = (sa >= 0) & (sa < 0.7)
            if live.any():                                 # sparks thrown out by the stadium lighting up
                k = 1.0 - sa[live] / 0.7
                p = self.s_pos[live] + self.s_dir[live] * (sa[live] * 90.0)[:, None] - np.array([0.0, 25.0]) * sa[live, None]
                self._dots(lb, p, self.s_col[live] * (0.6 * k * k)[:, None], s2)
            flash = self.messi & (heat > 0.08)
            if flash.any():                                # each landing gives a small flash of light
                r, c = np.nonzero(flash)
                p = np.stack([(c + 0.5) * self.lcw, (r + 0.5) * self.lch], 1)
                self._dots(lb, p, HOT(np.full(len(r), 0.9)) * (0.5 * heat[r, c])[:, None], s2)
        lb = cv2.GaussianBlur(lb, (0, 0), 0.9)
        # ---- a soft glow round the bright light (the picture itself stays sharp), then screen colours
        q = cv2.resize(lb, (self.qw, self.qh), interpolation=cv2.INTER_AREA)
        bright = np.maximum(q - 0.15, 0.0)
        glow = 0.45 * cv2.GaussianBlur(bright, (0, 0), 4.0 * self.s) + 0.3 * cv2.GaussianBlur(bright, (0, 0), 16.0 * self.s)
        lb += cv2.resize(glow, (self.lw, self.lh), interpolation=cv2.INTER_LINEAR)
        exposure = float(smoothstep(0.0, 0.6, t))
        if self.end is not None:
            exposure *= 1.0 - float(smoothstep(self.end - 0.8, self.end, t))
        k = 400.0 * exposure
        cv2.addWeighted(lb, k, lb, 0.0, 1.0, dst=lb)
        up = cv2.resize(lb, (self.w, self.h), dst=self.buf_up, interpolation=cv2.INTER_LINEAR)
        cv2.scaleAdd(img, k, up, dst=img)
        cv2.log(img, dst=img)
        frame = cv2.LUT(cv2.convertScaleAbs(img, dst=self.buf_u8, alpha=self.enc), self.tone, dst=self.buf_tone)
        zoom = 1.0 if still else 1.0 + 0.03 * float(smoothstep(0.0, VIDEO_SECONDS, t))   # a slow push in
        cx, cy = self.w / 2.0, self.h * 0.5
        M = np.float32([[zoom, 0, cx - zoom * cx], [0, zoom, cy - zoom * cy]])
        cv2.warpAffine(frame, M, (self.w, self.h), dst=self.out, flags=cv2.INTER_LINEAR)
        return self.out

    def _dots(self, lb, p, col, s2):
        """Add small points of light (picture pixel positions) to the half-size light image."""
        xs = (p[:, 0] * s2).astype(np.int32)
        ys = (p[:, 1] * s2).astype(np.int32)
        ok = (xs >= 0) & (xs < self.lw) & (ys >= 0) & (ys < self.lh)
        np.add.at(lb, (ys[ok], xs[ok]), col[ok].astype(np.float32))


# ------------------------------------------------------------------ the terminal
class TermFilm(Particles):
    """The animation drawn with the terminal's own characters: render(t) gives, for every cell, a
    character code (0 = empty), its colour and its background colour (sRGB 0..255).
    Positions are measured in rows (a column is half a row wide)."""

    def __init__(self, codes, fore, back, messi, way="down", seed=SEED):
        self.rows, self.cols = codes.shape
        self.codes = codes
        self.fore, self.back = to_linear(fore), to_linear(back)
        self.inside = codes > 0
        self.flicker = np.frombuffer(FLICKER.encode(), np.uint8)
        rng = np.random.default_rng(seed)
        self._plan(messi, 0.5, 1.0, self.cols * 0.5, self.rows, way, 1000, rng, area=self.inside)
        lin = self.fore[self.pr, self.pc]
        self.p_col = 0.55 * lin / np.maximum(lin.max(1, keepdims=True), 0.05) + 0.45 * SPARK
        self.p_tw = rng.uniform(1.0, 3.5, len(self.pr))
        m = max(1, self.rows * self.cols // 90)
        self.e0 = np.stack([rng.uniform(0, self.cols * 0.5, m), rng.uniform(0, self.rows, m)], 1)
        self.e_vy = self.sign * rng.uniform(0.017, 0.049, m) * self.tall
        self.e_ph = rng.uniform(0.0, 6.3, m)
        self.glints = rng.random((self.rows, self.cols))
        self.crowd = in_crowd(messi, self.rows, self.inside)

    def render(self, t):
        G = np.zeros((self.rows, self.cols), np.uint8)
        F = np.zeros((self.rows, self.cols, 3), np.float32)
        B = np.zeros((self.rows, self.cols, 3), np.float32)

        def put(p, char, colour, behind):
            c, r = np.floor(p[:, 0] * 2.0).astype(np.int64), np.floor(p[:, 1]).astype(np.int64)
            ok = (c >= 0) & (c < self.cols) & (r >= 0) & (r < self.rows)
            if behind:                                        # only where nothing is drawn yet
                ok[ok] = G[r[ok], c[ok]] == 0
            G[r[ok], c[ok]] = char[ok] if np.ndim(char) else char
            F[r[ok], c[ok]] = np.broadcast_to(colour, (len(ok), 3))[ok]

        fade = float(smoothstep(0.0, 1.2, t))
        ex = self.e0[:, 0] + 0.007 * self.tall * np.sin(t * 0.8 + self.e_ph)
        ey = np.mod(self.e0[:, 1] + self.e_vy * t, self.rows + 2.0) - 1.0
        b = 0.5 + 0.5 * np.sin(t * 3.0 + self.e_ph * 3.0)
        v = b > 0.45
        put(np.stack([ex, ey], 1)[v], ord("."), SPARK * (0.08 + 0.10 * b[v, None]) * fade, True)
        launch = self.p_land - self.p_fly
        i = np.nonzero(t < launch)[0]
        if len(i):                                            # particles waiting, drifting and twinkling
            p = self._drift(np.full(len(i), t, np.float32), i)
            b = 0.5 + 0.5 * np.sin(t * self.p_tw[i] + self.p_ph[i, 0])
            v = b > 0.5
            put(p[v], np.where(b[v] > 0.92, ord(":"), ord(".")), self.p_col[i[v]] * (0.15 + 0.35 * b[v, None]) * fade, True)
        # the cells that have appeared: white-hot (Messi) or warm (the stadium) at first, then their colours
        age = t - self.land
        on = age >= 0.0
        a = np.maximum(age, 0.0)
        keep, add, heat = lit_up(on, a, self.messi)
        fg = self.fore * keep + add
        if t >= T_ALL:                                        # phone lights twinkle in the crowd
            fg = fg + twinkle(t, self.glints, self.crowd)
        G = np.where(on, self.codes, G)
        flick = on & self.messi & (age < 0.08)
        if flick.any():
            G[flick] = self.flicker[(self.glints[flick] * 997 + t * 60).astype(np.int64) % len(self.flicker)]
        F = np.where(on[..., None], fg, F)
        B = np.where(on[..., None], self.back * keep + 0.3 * add, B)
        i = np.nonzero((t >= launch) & (t < self.p_land))[0]
        if len(i):                                            # particles flying in, with a short trail
            f = (t - launch[i]) / self.p_fly[i]
            glow = (0.4 + 0.6 * f)[:, None]
            for back, k in ((0.10, 0.30), (0.05, 0.55)):
                put(self._flight(i, np.clip(f - back, 0.0, 1.0)), ord("."), self.p_col[i] * k * glow, True)
            put(self._flight(i, f), ord("*"), self.p_col[i] * (0.6 + 0.6 * glow) + WHITE * 0.25, False)
        k = float(smoothstep(0.0, 0.6, t))                    # fade in at the start
        F = (to_srgb(np.clip(F * k, 0, 1)) * 255.0 + 0.5).astype(np.uint8)
        B = (to_srgb(np.clip(B * k, 0, 1)) * 255.0 + 0.5).astype(np.uint8)
        B[~on] = EMPTY_BG                                     # not there yet: the dark background
        return G, F, B


class TerminalArts:
    """The terminal art in many sizes; fit() gives the biggest one that fits a terminal."""

    def __init__(self, photo=None):
        self.photo, self.arts = photo, {}
        if photo:
            self.sizes = list(TERM_ROWS)
            return
        path = os.path.join(HERE, ART_FILE)
        if not os.path.exists(path):
            sys.exit(f"{ART_FILE} should be next to this script (or make it: --photo {PHOTO} --save-art).")
        with np.load(path) as f:
            self.sizes = sorted(int(k[4:-5]) for k in f.files if k.startswith("term") and k.endswith("_text"))
            for n in self.sizes:
                self.arts[n] = load_art(f"term{n}", f)

    def fit(self, cols, rows):
        for n in sorted(self.sizes, reverse=True):
            if n <= rows and term_cols(n) <= cols:
                if n not in self.arts:
                    self.arts[n] = art_from_photo(self.photo, f"term{n}")
                return self.arts[n]
        return None


class TerminalScreen:
    """This terminal as a screen: coloured characters on coloured backgrounds, drawn with escape codes,
    sending only the cells that changed."""

    def __enter__(self):
        self.fd, self.prev, self.esc = None, None, {}
        if os.name == "nt":                                   # let the Windows console understand colour codes
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.windll.kernel32
            k32.GetStdHandle.restype = wintypes.HANDLE
            k32.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
            k32.SetConsoleMode.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            handle, mode = k32.GetStdHandle(-11), wintypes.DWORD()
            if k32.GetConsoleMode(handle, ctypes.byref(mode)):  # 1 = processed output, 4 = colour codes
                k32.SetConsoleMode(handle, mode.value | 0x0001 | 0x0004)
        elif sys.stdin.isatty():                              # read keys one at a time, without Enter
            import termios
            import tty
            self.fd = sys.stdin.fileno()
            self.saved = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        self._write("\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[48;2;%d;%d;%dm\x1b[2J" % EMPTY_BG)
        return self

    def __exit__(self, *exc):
        self._write("\x1b[0m\x1b[2J\x1b[?7h\x1b[?25h\x1b[?1049l")      # everything back as it was
        if self.fd is not None:
            import termios
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)

    def _write(self, text):
        sys.stdout.buffer.write(text.encode("ascii"))
        sys.stdout.buffer.flush()

    def size(self):
        try:                                                  # ask the terminal itself, so resizing is noticed
            s = os.get_terminal_size(sys.stdout.fileno())
        except (OSError, ValueError):
            s = shutil.get_terminal_size((120, 30))
        return s.columns, s.lines

    def keys(self):
        out = []
        if os.name == "nt":
            import msvcrt
            while msvcrt.kbhit():
                out.append(msvcrt.getwch())
        elif self.fd is not None:
            import select
            while select.select([self.fd], [], [], 0)[0]:
                c = os.read(self.fd, 1)
                if not c:
                    break
                out.append(c.decode("ascii", "ignore"))
        return out

    def clear(self):
        self.prev = None
        self._write("\x1b[48;2;%d;%d;%dm\x1b[2J" % EMPTY_BG)

    def _colour(self, key, ground):
        if (key, ground) not in self.esc:
            r, g, b = ((key >> 10) & 31) * 8 + 4, ((key >> 5) & 31) * 8 + 4, (key & 31) * 8 + 4
            self.esc[(key, ground)] = f"\x1b[{ground};2;{r};{g};{b}m"
        return self.esc[(key, ground)]

    def draw(self, G, F, B):
        """Show a frame: G holds character codes (0 = empty), F their colours, B the background colours."""
        G = np.where(G == 0, 32, G).astype(np.int64)
        f, b = (F >> 3).astype(np.int64), (B >> 3).astype(np.int64)
        fk = np.where(G == 32, 0, (f[..., 0] << 10) | (f[..., 1] << 5) | f[..., 2])
        bk = (b[..., 0] << 10) | (b[..., 1] << 5) | b[..., 2]
        key = (G << 30) | (fk << 15) | bk
        changed = np.ones(key.shape, bool) if self.prev is None or self.prev.shape != key.shape else key != self.prev
        self.prev = key
        out, now_f, now_b = [], None, None
        for r in np.nonzero(changed.any(1))[0]:
            cs = np.nonzero(changed[r])[0]
            gaps = np.nonzero(np.diff(cs) > 4)[0]                # runs of changed cells (small gaps drawn again)
            for a, z in zip(np.r_[cs[0], cs[gaps + 1]], np.r_[cs[gaps], cs[-1]]):
                out.append(f"\x1b[{r + 1};{a + 1}H")
                for c in range(a, z + 1):
                    if bk[r, c] != now_b:
                        out.append(self._colour(bk[r, c], 48))
                        now_b = bk[r, c]
                    if G[r, c] != 32 and fk[r, c] != now_f:
                        out.append(self._colour(fk[r, c], 38))
                        now_f = fk[r, c]
                    out.append(chr(G[r, c]))
        if out:
            self._write("".join(out))


def text_row(G, F, B, row, col, text, colour):
    """Write plain text into a frame."""
    if 0 <= row < G.shape[0]:
        text = text[:max(0, G.shape[1] - col)]
        G[row, col:col + len(text)] = np.frombuffer(text.encode("ascii"), np.uint8)
        F[row, col:col + len(text)] = colour
        B[row, col:col + len(text)] = EMPTY_BG


def play_terminal(way="down", photo=None):
    arts = TerminalArts(photo)
    with TerminalScreen() as screen:
        start, size, film = time.perf_counter(), None, None
        while True:
            frame = time.perf_counter()
            keys = "".join(screen.keys())
            if any(c in keys for c in "qQ\x1b"):
                break
            if any(c in keys for c in "rR "):
                start = time.perf_counter()
            if screen.size() != size:                         # the terminal changed size: fit it again
                size = screen.size()
                cols, rows = size
                art, film = arts.fit(cols, rows), None
                if art is not None:                           # the art in the middle of the terminal
                    codes, fore, back, messi = art
                    h, w = codes.shape
                    r0, c0 = (rows - h) // 2, (cols - w) // 2
                    full = [np.zeros((rows, cols), np.uint8), np.zeros((rows, cols, 3), np.float32),
                            np.zeros((rows, cols, 3), np.float32), np.zeros((rows, cols), bool)]
                    for dst, src in zip(full, art):
                        dst[r0:r0 + h, c0:c0 + w] = src
                    film = TermFilm(*full, way=way)
                screen.clear()
            t = time.perf_counter() - start
            if film is None:
                G = np.zeros((size[1], size[0]), np.uint8)
                F, B = np.zeros((size[1], size[0], 3), np.uint8), np.zeros((size[1], size[0], 3), np.uint8)
                B[:] = EMPTY_BG
                text_row(G, F, B, size[1] // 2, max(0, size[0] // 2 - 12), "Make this terminal bigger", (200, 200, 200))
            else:
                G, F, B = film.render(t)
                if t < 4.0:                                   # how to use it, for the first few seconds
                    text_row(G, F, B, size[1] - 1, 1, "R = play again   Q = close", (150, 145, 160))
            screen.draw(G, F, B)
            time.sleep(max(0.0, 1.0 / 30 - (time.perf_counter() - frame)))


# ------------------------------------------------------------------ playing and saving
def get_art(grid, photo=None):
    return art_from_photo(photo, grid) if photo else load_art(grid)


def window_film(screen_w, screen_h, grid, way, photo=None):
    """The film for a window, with characters as big as the screen allows, and the window size."""
    art = get_art(grid, photo)
    rows, cols = art[0].shape
    fit = min((screen_h - 60) / rows, 2.0 * (screen_w - 40) / cols)    # screen pixels per row that fit
    ch = max(6, int(fit) // 2 * 2)                           # drawn at least 3 x 6 pixels a character...
    film = Film(art, ch // 2, ch, way)
    scale = min(fit / ch, 1.5)                               # ...and fitted to the screen
    return film, (int(film.w * scale), int(film.h * scale))


def play_window(version, photo=None):
    v = VERSIONS[version]
    try:                                                     # sharp pixels on high-DPI Windows screens
        import ctypes
        from ctypes import wintypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        area = wintypes.RECT()                               # the screen without the taskbar
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(area), 0)
        screen_w, screen_h = area.right - area.left, area.bottom - area.top
    except (ImportError, AttributeError, OSError):
        screen_w, screen_h = 1920, 1040
    film, size = window_film(screen_w, screen_h, v["grid"], v["way"], photo)
    title = f"Messi ASCII - version {version}"
    cv2.namedWindow(title, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(title, *size)
    cv2.moveWindow(title, max(0, (screen_w - size[0]) // 2), 0)
    start, full = time.perf_counter(), False
    while True:
        frame = cv2.cvtColor(film.render(time.perf_counter() - start), cv2.COLOR_RGB2BGR)
        if frame.shape[1] != size[0]:
            frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA if size[0] < frame.shape[1] else cv2.INTER_LINEAR)
        cv2.imshow(title, frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q")):
            break
        if key in (ord("r"), ord(" ")):
            start = time.perf_counter()
        if key == ord("f"):
            full = not full
            cv2.setWindowProperty(title, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN if full else cv2.WINDOW_NORMAL)
        if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
            break
    cv2.destroyAllWindows()


def save_video(version, seconds, photo=None):
    try:
        import imageio_ffmpeg
    except ImportError:
        sys.exit("Saving the video needs imageio-ffmpeg:  pip install imageio-ffmpeg")
    v = VERSIONS[version]
    cw, ch = GRIDS[v["grid"]]
    film = Film(get_art(v["grid"], photo), cw, ch, v["way"])
    film.end = seconds
    path = os.path.join(HERE, f"messi_v{version}.mp4")
    writer = imageio_ffmpeg.write_frames(path, (film.w, film.h), fps=FPS, codec="libx264", quality=None,
                                         macro_block_size=8,
                                         output_params=["-crf", "17", "-preset", "slow", "-movflags", "+faststart"])
    writer.send(None)
    frames, started = int(round(seconds * FPS)), time.perf_counter()
    for i in range(frames):
        writer.send(np.ascontiguousarray(film.render(i / FPS)))
        if (i + 1) % FPS == 0 or i + 1 == frames:
            print(f"\rrendering {i + 1}/{frames} frames ({time.perf_counter() - started:.0f}s)", end="", flush=True)
    writer.close()
    print(f"\nsaved {path}")


def save_picture(version, photo=None):
    v = VERSIONS[version]
    cw, ch = GRIDS[v["grid"]]
    film = Film(get_art(v["grid"], photo), cw * 2, ch * 2, v["way"])   # twice as big: 2160 x 2880
    frame = film.render(60.0, still=True)
    path = os.path.join(HERE, f"messi_v{version}.png")
    cv2.imwrite(path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    print(f"saved {path}")


def main(version=None):
    parser = argparse.ArgumentParser(description="Messi in ASCII")
    if version is None:
        parser.add_argument("--version", type=int, choices=(1, 2, 3), help="which version to play")
    parser.add_argument("--mp4", action="store_true", help="save this version as a video instead of playing")
    parser.add_argument("--png", action="store_true", help="save this version as a still picture instead of playing")
    parser.add_argument("--seconds", type=float, default=VIDEO_SECONDS, help="length of the video")
    parser.add_argument("--photo", help=f"work the art out again from this photo (e.g. {PHOTO}) instead of {ART_FILE}")
    parser.add_argument("--save-art", action="store_true", help=f"with --photo: save the art as {ART_FILE}")
    args = parser.parse_args()
    if args.photo and not os.path.exists(args.photo):
        sys.exit(f"Could not find the photo '{args.photo}'.")
    if args.save_art:
        if not args.photo:
            sys.exit("--save-art needs --photo")
        save_art(args.photo)
        return
    version = version or getattr(args, "version", None)
    while version not in VERSIONS:                           # run on its own: ask which version
        print("Messi in ASCII")
        for n, v in VERSIONS.items():
            print(f"  {n} = {v['name']}")
        answer = input("Which version (1, 2 or 3)? ").strip()
        version = int(answer) if answer.isdigit() else None
    if args.mp4:
        save_video(version, args.seconds, args.photo)
    elif args.png:
        save_picture(version, args.photo)
    elif VERSIONS[version]["where"] == "terminal" and sys.stdout.isatty():
        play_terminal(VERSIONS[version]["way"], args.photo)
    else:                                                    # a window (also when there is no terminal, e.g. IDLE)
        play_window(version, args.photo)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
