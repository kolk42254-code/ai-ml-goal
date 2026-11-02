"""
Ronaldo in ASCII - particle edition.

Thousands of glowing particles fall slowly from above, then fly in one by one
and build Cristiano Ronaldo (No. 7, red kit, seen from behind) out of coloured
text characters, from his head down to his boots. Every character is chosen from
the photo: denser characters where it is brighter, line characters ( / \\ | _ ( ) )
along edges, the photo's own colour, and the name on his shirt in real letters.
It plays right in the terminal and fills it; it fits itself again whenever the
terminal changes size. A bigger terminal, or a smaller terminal font, gives more detail.

Needs:   pip install numpy opencv-python pillow imageio-ffmpeg
Files:   ronaldo_art.npz (the finished art) next to this script; that is all it needs
Run:     python Ronaldo_ascii.py                  plays it here in the terminal, filling it
         python Ronaldo_ascii.py --window         plays it in a separate window instead
         python Ronaldo_ascii.py --mp4            saves ronaldo_ascii.mp4 (1080x1920, 60 fps)
         python Ronaldo_ascii.py --png            saves ronaldo_ascii.png (2160x3840 still picture)
Remake:  python Ronaldo_ascii.py --photo ronaldo.jpg --save-art
         works the art out again from the photo (with his outline, ronaldo_mask.png) and saves it
Keys:    R or Space = play again,  Esc or Q = close  (in the window, F = full screen)
Tip:     for more detail, make the terminal bigger (maximise it) or its font smaller
         (Ctrl and minus in Windows Terminal)
"""

import argparse
import math
import os
import shutil
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------ settings
PHOTO, MASK, ART_FILE = "ronaldo.jpg", "ronaldo_mask.png", "ronaldo_art.npz"
VIDEO_FILE, IMAGE_FILE = "ronaldo_ascii.mp4", "ronaldo_ascii.png"
VIDEO_SECONDS = 15.0
FPS = 60
SEED = 7                        # another number gives different particle paths

# ------------------------------------------------------------------ layout
# The picture is 1080x1920 (a phone screen standing up), made of character
# cells 6 pixels wide and 12 tall: 180 columns and 160 rows (the video and the still).
# The window uses cells twice as big: 90 columns and 80 rows, so each character is
# easy to see on a laptop screen.
W, H = 1080, 1920
CW, CH = 6, 12
COLS, ROWS = W // CW, H // CH
WIN_CW, WIN_CH = 12, 24
FILL, FILL_W = 0.88, 0.92       # at most this tall and this wide, as parts of the picture (his feet are wide apart)

# characters
RAMP = " .:-=+*#%@"            # shading: the more ink, the brighter
LINES = "/\\|_()<>^v'`"        # shapes that follow edges
NAME = "RONALDO"               # printed on his shirt, written with real letters
NAME_BOX = (215 / 495, 92 / 619, 274 / 495, 110 / 619)   # where the name is, as parts of the photo's size
FLICKER = "@#%&*+=$"           # characters flash through these as a particle lands
GLYPHS = "".join(dict.fromkeys(RAMP + LINES + NAME + FLICKER))

# timeline (seconds)
T_BUILD = 1.4                   # the first particles land on his head
T_DONE = 9.6                    # the last ones land on his boots
FLY = (1.3, 2.4)                # each particle flies this long (shortest, longest)
T_SWEEP = 10.2                  # a soft light sweeps up over him
SWEEP = 1.6                     # ...and takes this long


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
SPARK = np.array([1.0, 0.72, 0.40], np.float32)                      # warm glow of a flying particle
WHITE = np.array([1.0, 0.95, 0.88], np.float32)


def find_font(names):
    folders = [os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"),
               "/usr/share/fonts/truetype/dejavu", "/Library/Fonts", "/System/Library/Fonts"]
    for name in names:
        for folder in folders:
            if os.path.exists(os.path.join(folder, name)):
                return os.path.join(folder, name)
    return None


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


# ------------------------------------------------------------------ photo -> ASCII art
def load_photo(photo_path, mask_path):
    """The photo (sRGB 0..1) and how much of each pixel is him (0..1)."""
    photo = cv2.imread(photo_path)
    if photo is None:
        sys.exit(f"Could not read the photo '{photo_path}'. Put the photo next to this script as {PHOTO}.")
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        sys.exit(f"Could not read his outline '{mask_path}' ({MASK} should be next to this script).")
    if mask.shape != photo.shape[:2]:                     # the same photo at another size
        mask = cv2.resize(mask, (photo.shape[1], photo.shape[0]), interpolation=cv2.INTER_LINEAR)
    rgb = cv2.cvtColor(photo, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    return rgb, mask.astype(np.float32) / 255.0


def place(rgb, alpha):
    """Scale and centre him on the 1080x1920 picture. Returns the picture, his outline and the transform."""
    ys, xs = np.nonzero(alpha > 0.5)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    s = min(FILL * H / (y1 - y0 + 1), FILL_W * W / (x1 - x0 + 1))
    M = np.float32([[s, 0, W / 2 - s * (x0 + x1) / 2], [0, s, H / 2 - s * (y0 + y1) / 2]])
    big = cv2.warpAffine(rgb, M, (W, H), flags=cv2.INTER_LANCZOS4, borderValue=0)
    a = cv2.warpAffine(alpha, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=0)
    return np.clip(big, 0.0, 1.0), np.clip(a, 0.0, 1.0), M


def convert(rgb, alpha, cw=CW, ch=CH):
    """Choose a character and a colour for every cell (cells cw x ch pixels of the 1080x1920 picture).

    The shading of the photo picks a character from RAMP (more ink = brighter). Where the photo has a
    real edge, a character from LINES whose shape lines up with that edge can win instead. Colours are
    the photo's own, a little brightened so thin characters still show them. Returns the character
    numbers (rows x columns, -1 = empty) and colours (sRGB)."""
    cols, rows = W // cw, H // ch
    big, a, M = place(rgb, alpha)
    # pixels on his outline are mixed with the stadium behind him: take their colour from just inside
    sure = (a > 0.92).astype(np.float32)
    near = cv2.GaussianBlur(big * sure[..., None], (0, 0), 5.0) / np.maximum(cv2.GaussianBlur(sure, (0, 0), 5.0), 1e-4)[..., None]
    big = np.where(sure[..., None] > 0, big, near)
    atlas = build_atlas(cw, ch)                           # shapes are compared at this cell size
    chars = RAMP + LINES
    idx = np.array([GLYPHS.index(c) for c in chars])
    G = atlas[idx]
    K, nr = len(chars), len(RAMP)
    tone_g = G.mean((1, 2)) / G[:nr].mean((1, 2)).max()  # how bright each character looks (0..1)
    # each character's shape: softened, without its average, scaled to length 1
    blur = 0.8 * cw / CW
    Gs = np.stack([cv2.GaussianBlur(g, (0, 0), blur) for g in G]).reshape(K, -1)
    Gs -= Gs.mean(1, keepdims=True)
    Gs /= np.maximum(np.linalg.norm(Gs, axis=1, keepdims=True), 1e-6)
    # brightness of the photo: vivid red counts as bright, as it looks; black where he is not
    light = (0.5 * (big * np.array([0.299, 0.587, 0.114], np.float32)).sum(-1) + 0.5 * big.max(-1)) * a
    soft = cv2.GaussianBlur(light, (0, 0), blur)
    P = soft.reshape(rows, ch, cols, cw).transpose(0, 2, 1, 3).reshape(-1, ch * cw)
    Pz = P - P.mean(1, keepdims=True)
    contrast = np.linalg.norm(Pz, axis=1) / math.sqrt(ch * cw)             # how much edge is in the cell
    match = (Pz @ Gs.T) / np.maximum(contrast * math.sqrt(ch * cw), 1e-6)[:, None]   # -1..1 shape match
    cover = a.reshape(rows, ch, cols, cw).mean((1, 3)).ravel()
    tone = cv2.GaussianBlur(light, (0, 0), cw).reshape(rows, ch, cols, cw).mean((1, 3)).ravel()
    inside = cover > 0.12
    lo, hi = np.percentile(tone[inside], [2, 99.5])
    T = 0.30 + 0.70 * np.clip((tone - lo) / (hi - lo), 0.0, 1.0) ** 0.75   # wanted brightness 0..1
    T = np.where(tone < lo * 0.6, T * tone / max(lo * 0.6, 1e-6), T)      # real blacks stay black
    edge = np.clip((contrast - 0.015) / 0.030, 0.0, 1.0) ** 1.5           # 0 flat .. 1 a clear edge
    score = 4.0 * (tone_g[None, :] - T[:, None]) ** 2 - 0.6 * edge[:, None] * match
    score[:, nr:] += 0.08 + 2.0 * (1.0 - edge[:, None])                    # line characters only on edges
    score[:, 0] += np.where(T > 0.06, 1.0, 0.0)                            # a blank only for black
    k = np.where(inside, idx[score.argmin(1)], -1)
    col = (big * a[..., None]).reshape(rows, ch, cols, cw, 3).mean((1, 3)).reshape(-1, 3)
    col /= np.maximum(cover, 1e-3)[:, None]
    v = col.max(1, keepdims=True)
    boost = np.clip(0.95 / np.maximum(v, 1e-3), 1.0, 3.0) ** 0.7
    col *= 1.0 + (boost - 1.0) * (0.3 + 0.7 * smoothstep(0.12, 0.45, v))   # dark hair stays dark
    k, col = k.reshape(rows, cols), np.clip(col, 0.0, 1.0).reshape(rows, cols, 3)
    k[k == GLYPHS.index(" ")] = -1

    # the printed name: real letters in white, spaced out over the red shirt
    x0, y0, x1, y1 = NAME_BOX
    hgt, wid = rgb.shape[:2]
    cx0, cx1 = M[0, 0] * x0 * wid + M[0, 2], M[0, 0] * x1 * wid + M[0, 2]
    cy0, cy1 = M[1, 1] * y0 * hgt + M[1, 2], M[1, 1] * y1 * hgt + M[1, 2]
    r0, r1 = int(cy0 // ch), int(cy1 // ch)
    c0, c1 = int(cx0 // cw), int(cx1 // cw) + 1
    shirt = np.median(col[max(0, r0 - 2), c0:c1], axis=0)
    for r in range(r0, r1 + 1):
        k[r, c0:c1] = GLYPHS.index("#")
        col[r, c0:c1] = shirt
    mid = int(((cy0 + cy1) / 2) // ch)
    roomy = (cx1 - cx0) / cw >= 2 * len(NAME)                # room for gaps between the letters?
    for i, letter in enumerate(NAME):
        if roomy:                                             # spaced out over the name's width, as printed
            c = int((cx0 + (i + 0.5) * (cx1 - cx0) / len(NAME)) // cw)
        else:                                                 # big characters: one word, in the middle
            c = int((cx0 + cx1) / 2 // cw - len(NAME) // 2 + i)
        k[mid, c], col[mid, c] = GLYPHS.index(letter), (0.97, 0.97, 0.97)
    return k, col


# ------------------------------------------------------------------ the film
class Particles:
    """Paths of the particles: falling slowly (with p0, p_vy, p_sw, p_hz, p_ph), then flying along a
    curve (p_from, p_mid, p_to) to the character they light up."""

    def _drift(self, t, i):
        """Where particles i are at time(s) t while they fall slowly."""
        t = np.asarray(t, np.float32)
        x = self.p0[i, 0] + self.p_sw[i] * np.sin(t * self.p_hz[i, 0] + self.p_ph[i, 0])
        y = self.p0[i, 1] + self.p_vy[i] * t + 0.6 * self.p_sw[i] * np.cos(t * self.p_hz[i, 1] + self.p_ph[i, 1])
        return np.stack([x, y], 1).astype(np.float32)

    def _flight(self, i, f):
        """Points along the curved paths of particles i, f = 0 (set off) .. 1 (landed)."""
        e = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)      # slow start, slow landing
        a, b, c = self.p_from[i], self.p_mid[i], self.p_to[i]
        e = e[:, None]
        return (1 - e) ** 2 * a + 2 * e * (1 - e) * b + e * e * c


class Film(Particles):
    """The animation: build once, then render(t) for any time t (seconds)."""

    def __init__(self, k, col, cw, ch, seed=SEED):
        self.rows, self.cols = k.shape
        self.lcw, self.lch = W / self.cols, H / self.rows  # size of a cell on the 1080x1920 picture
        self.cw, self.ch = cw, ch                         # size of a cell on the screen
        self.s = cw / self.lcw                            # screen pixels per layout pixel
        self.w, self.h = self.cols * cw, self.rows * ch
        self.end = None                                   # fade to black at this time (for the video)
        self.atlas = build_atlas(cw, ch)
        self.atlas_rows = self.atlas.reshape(-1, cw)      # each pixel row of each character
        self.row_of_cell = np.arange(ch, dtype=np.int32)[None, :, None]
        self.k = k
        self.col = to_linear(col) * 1.12                  # colours as light, a touch brighter
        rng = np.random.default_rng(seed)

        # particles: one for every character (more for big characters, so the swarm looks the same)
        cells = np.argwhere(k >= 0)
        per = max(1, int(round(self.lcw * self.lch / (CW * CH))))
        cy, cx = (cells[:, 0] + 0.5) * self.lch, (cells[:, 1] + 0.5) * self.lcw
        y_top, y_bot = cy.min(), cy.max()
        down = (cy - y_top) / max(y_bot - y_top, 1.0)     # 0 at the top of his head .. 1 at his boots
        wave = 0.04 * np.sin(cx / 70.0)                   # the building line is a little wavy
        first = T_BUILD + (T_DONE - T_BUILD - 0.5) * np.clip(down + wave, 0, 1) ** 0.95 + 0.5 * rng.random(len(cells))
        self.land = np.full((self.rows, self.cols), np.inf, np.float32)
        self.land[cells[:, 0], cells[:, 1]] = first       # a character lights up when its first particle lands
        self.cr, self.cc = np.repeat(cells[:, 0], per), np.repeat(cells[:, 1], per)
        n = len(self.cr)
        later = np.where(np.arange(n) % per == 0, 0.0, rng.uniform(0.03, 0.35, n))
        land = np.repeat(first, per) + later
        tx = (self.cc + 0.5) * self.lcw + (np.arange(n) % per > 0) * rng.uniform(-0.3, 0.3, n) * self.lcw
        ty = (self.cr + 0.5) * self.lch + (np.arange(n) % per > 0) * rng.uniform(-0.3, 0.3, n) * self.lch
        fly = rng.uniform(*FLY, n)
        self.p_land, self.p_fly = land.astype(np.float32), fly.astype(np.float32)
        self.p_to = np.stack([tx, ty], 1).astype(np.float32)
        # before they fly, particles fall slowly from the top of the picture, swaying
        self.p0 = np.stack([rng.uniform(-40, W + 40, n), rng.uniform(-0.25 * H, 0.42 * H, n)], 1).astype(np.float32)
        self.p_vy = rng.uniform(12.0, 40.0, n).astype(np.float32)
        self.p_sw = rng.uniform(8.0, 26.0, n).astype(np.float32)
        self.p_ph = rng.uniform(0.0, 6.3, (n, 2)).astype(np.float32)
        self.p_hz = rng.uniform(0.25, 0.7, (n, 2)).astype(np.float32)
        start = self._drift(land - fly, np.arange(n))     # where each one is when it sets off
        d = self.p_to - start
        normal = np.stack([-d[:, 1], d[:, 0]], 1) / np.maximum(np.hypot(d[:, 0], d[:, 1]), 1.0)[:, None]
        self.p_from = start
        self.p_mid = ((start + self.p_to) / 2
                      + normal * rng.normal(0.0, 0.30, (n, 1)) * np.hypot(d[:, 0], d[:, 1])[:, None]).astype(np.float32)   # a curved path
        lin = self.col[self.cr, self.cc]
        self.p_col = (0.55 * lin / np.maximum(lin.max(1, keepdims=True), 0.05) + 0.45 * SPARK).astype(np.float32)
        self.p_tw = rng.uniform(1.0, 3.5, n).astype(np.float32)                 # how fast each one twinkles
        # a few faint embers keep falling round him the whole time
        m = 260
        self.e0 = np.stack([rng.uniform(0, W, m), rng.uniform(0, H + 80, m)], 1).astype(np.float32)
        self.e_vy = rng.uniform(25.0, 70.0, m).astype(np.float32)
        self.e_ph = rng.uniform(0.0, 6.3, m).astype(np.float32)
        self.e_col = (SPARK * rng.uniform(0.6, 1.0, (m, 1)) * np.array([1.0, rng.uniform(0.7, 1.0), 0.9])).astype(np.float32)

        # light in the air is drawn at half size, wide glow at a quarter
        self.lh, self.lw = self.h // 2, self.w // 2
        ly, lx = np.mgrid[0:self.lh, 0:self.lw].astype(np.float32)
        r = np.hypot((lx + 0.5) / self.lw - 0.5, ((ly + 0.5) / self.lh - 0.52) * 1.6)
        self.bg = (np.array([0.010, 0.006, 0.012], np.float32) * np.exp(-3.0 * r * r)[..., None]
                   + np.array([0.0012, 0.0012, 0.0025], np.float32))           # a faint glow behind him
        self.qh, self.qw = self.h // 4, self.w // 4
        self.sweep_y = ((np.arange(self.rows, dtype=np.float32) + 0.5) * self.lch)[:, None]
        # turning light into screen colours: kept true to the photo, bright glows roll off softly
        self.enc = 255.0 / math.log1p(400.0 * 8.0)
        x = np.expm1(np.arange(256) / self.enc) / 400.0
        soft = np.where(x < 0.8, x, 0.8 + 0.2 * (1.0 - np.exp(-(x - 0.8) / 0.2)))
        self.tone = np.clip(to_srgb(soft) * 255.0 + 0.5, 0, 255).astype(np.uint8)
        self.buf_glyph = np.empty((self.rows, ch, self.cols, cw), np.float32)
        self.buf_img, self.buf_up, self.buf_a3 = (np.empty((self.h, self.w, 3), np.float32) for _ in range(3))
        self.buf_u8, self.buf_tone = (np.empty((self.h, self.w, 3), np.uint8) for _ in range(2))
        self.out = np.zeros((self.h, self.w, 3), np.uint8)
        self.glints = rng.random((self.rows, self.cols)).astype(np.float32)

    def render(self, t, still=False):
        """The picture at time t as an RGB image (uint8). The same array is reused by the next call.
        still=True leaves out everything that moves (particles, glints, the light sweep, the push in)."""
        particles = not still
        s2 = self.s / 2.0
        # ---- the characters that have landed: white-hot at first, cooling to the photo's colour
        age = t - self.land
        on = age >= 0.0
        G = np.where(on, self.k, GLYPHS.index(" ")).astype(np.int32)
        heat = np.where(on, np.exp(-np.maximum(age, 0.0) / 0.30), 0.0).astype(np.float32)
        C = self.col * on[..., None] * (1.0 - heat[..., None]) + HOT(0.55 + 0.45 * heat) * (1.3 * heat)[..., None]
        flick = on & (age < 0.08)
        if flick.any():
            pick = (self.glints[flick] * 997 + t * 60).astype(np.int32) % len(FLICKER)
            G[flick] = np.array([GLYPHS.index(c) for c in FLICKER])[pick]
        if T_SWEEP <= t < T_SWEEP + SWEEP and not still:   # a soft light sweeps up over him
            y = H * (1.0 - (t - T_SWEEP) / SWEEP) * 1.1 - 0.05 * H
            C = C + (WHITE * 0.45) * np.exp(-((self.sweep_y - y) / 70.0) ** 2)[..., None] * on[..., None]
        if t >= T_DONE and not still:                      # a few characters glint now and then
            g = np.sin(t * 2.2 + self.glints * 40.0) * 0.5 + 0.5
            C = C + WHITE * (0.35 * np.clip((g - 0.985) / 0.015, 0, 1) * on)[..., None]

        # ---- characters -> picture
        np.take(self.atlas_rows, G[:, None, :] * self.ch + self.row_of_cell, axis=0, out=self.buf_glyph)
        alpha = self.buf_glyph.reshape(self.h, self.w)
        img = cv2.resize(C.astype(np.float32), (self.w, self.h), dst=self.buf_img, interpolation=cv2.INTER_NEAREST)
        cv2.multiply(img, cv2.merge([alpha, alpha, alpha], dst=self.buf_a3), dst=img)

        # ---- light in the air: drifting and flying particles, landing flashes
        lb = self.bg.copy()
        if particles:
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
                for j, back in enumerate((0.0, 0.025, 0.05, 0.08)):    # a short glowing trail behind each
                    p = self._flight(i, np.clip(f - back, 0.0, 1.0))
                    self._dots(lb, p, self.p_col[i] * (glow * (1.0 - 0.22 * j))[:, None], s2)
        if particles:                                      # faint embers falling
            ex = self.e0[:, 0] + 14.0 * np.sin(t * 0.8 + self.e_ph)
            ey = np.mod(self.e0[:, 1] + self.e_vy * t + 40.0, H + 80.0) - 40.0
            b = (0.06 + 0.05 * np.sin(t * 3.0 + self.e_ph * 3.0)) * float(smoothstep(0.0, 1.5, t))
            self._dots(lb, np.stack([ex, ey], 1), self.e_col * b[:, None], s2)
        flash = (heat > 0.08)
        if flash.any():                                    # each landing gives a small flash of light
            r, c = np.nonzero(flash)
            p = np.stack([(c + 0.5) * self.lcw, (r + 0.5) * self.lch], 1)
            self._dots(lb, p, HOT(np.full(len(r), 0.9)) * (0.6 * heat[r, c])[:, None], s2)
        lb = cv2.GaussianBlur(lb, (0, 0), 0.9)

        # ---- lens glow from bright things, then the screen colours
        qs = (self.qw, self.qh)
        q = cv2.resize(img, qs, interpolation=cv2.INTER_AREA) + cv2.resize(lb, qs, interpolation=cv2.INTER_AREA)
        bright = np.maximum(q - 0.6, 0.0)
        glow = 0.35 * cv2.GaussianBlur(bright, (0, 0), 2.0 * self.s * 2) + 0.25 * cv2.GaussianBlur(bright, (0, 0), 8.0 * self.s * 2)
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
        # ---- a slow push in
        zoom = 1.0 if still else 1.0 + 0.04 * float(smoothstep(0.0, VIDEO_SECONDS, t))
        cx, cy = self.w / 2.0, self.h * 0.5
        M = np.float32([[zoom, 0, cx - zoom * cx], [0, zoom, cy - zoom * cy]])
        cv2.warpAffine(frame, M, (self.w, self.h), dst=self.out, flags=cv2.INTER_LINEAR)
        return self.out

    def _dots(self, lb, p, col, s2):
        """Add small points of light (layout pixel positions) to the half-size light image."""
        xs = (p[:, 0] * s2).astype(np.int32)
        ys = (p[:, 1] * s2).astype(np.int32)
        ok = (xs >= 0) & (xs < self.lw) & (ys >= 0) & (ys < self.lh)
        np.add.at(lb, (ys[ok], xs[ok]), col[ok].astype(np.float32))


# ------------------------------------------------------------------ playing in the terminal
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def terminal_art(k, col, cols, rows):
    """The art for a terminal of cols x rows characters, made from the fine art. Terminal characters are
    about twice as tall as wide, like the fine ones, so every terminal character covers a square patch of
    fine ones. Returns ASCII codes (0 = empty) and sRGB colours (0..1) for every cell."""
    ink = np.append(build_atlas(CW, CH).mean((1, 2)), 0.0)  # ink of every character (the last one: empty)
    inside = (k >= 0).astype(np.float64)
    seen = ink[k] * (0.5 * (col * LUMA).sum(-1) + 0.5 * col.max(-1)) * inside   # how bright each fine cell looks
    rr, cc = np.nonzero(inside)
    top, bottom, left, right = rr.min(), rr.max() + 1, cc.min(), cc.max() + 1
    f = max((right - left) / max(cols - 2, 1), (bottom - top) / max(rows - 2, 1))   # fine cells per terminal cell
    us = (left + right) / 2 + (np.arange(cols + 1) - cols / 2) * f                # terminal cell edges, in fine cells
    vs = (top + bottom) / 2 + (np.arange(rows + 1) - rows / 2) * f

    def box(a):
        """The sum of a over every terminal cell, worked out exactly from a summed table of a."""
        a = a.reshape(a.shape[0], a.shape[1], -1)
        S = np.zeros((a.shape[0] + 1, a.shape[1] + 1, a.shape[2]))
        S[1:, 1:] = a.cumsum(0).cumsum(1)
        v, u = np.clip(vs, 0, a.shape[0]), np.clip(us, 0, a.shape[1])
        v0, u0 = np.minimum(v.astype(int), a.shape[0] - 1), np.minimum(u.astype(int), a.shape[1] - 1)
        fv, fu = (v - v0)[:, None, None], (u - u0)[None, :, None]
        I = ((S[v0][:, u0] * (1 - fu) + S[v0][:, u0 + 1] * fu) * (1 - fv)
             + (S[v0 + 1][:, u0] * (1 - fu) + S[v0 + 1][:, u0 + 1] * fu) * fv)
        return I[1:, 1:] - I[:-1, 1:] - I[1:, :-1] + I[:-1, :-1]

    there = box(inside)[..., 0]
    cover = there / (f * f)                                  # how much of each terminal cell is him
    colour = box(col * inside[..., None]) / np.maximum(there, 1e-9)[..., None]
    bright = box(seen)[..., 0] / np.maximum(there, 1e-9)
    on = cover > 0.3
    if not on.any():
        return np.zeros((rows, cols), np.uint8), np.zeros((rows, cols, 3), np.float32)
    lo, hi = np.percentile(bright[on], [2, 99.5])
    want = 0.30 + 0.70 * np.clip((bright - lo) / max(hi - lo, 1e-9), 0.0, 1.0) ** 0.75
    ramp = np.array([GLYPHS.index(c) for c in RAMP[1:]])
    tone = ink[ramp] / ink[ramp].max()
    pick = np.abs(tone[None, None, :] - want[..., None]).argmin(-1)
    codes = np.where(on, np.frombuffer(RAMP[1:].encode(), np.uint8)[pick], 0)
    # along his outline, characters that follow it: _ \ | /
    gy, gx = np.gradient(cover)
    gx = gx * 2.0                                            # a column is half as wide as a row is tall
    along = np.mod(np.degrees(np.arctan2(gy, gx)) + 90.0, 180.0)
    line = np.select([along < 22.5, along < 67.5, along < 112.5, along < 157.5],
                     [ord("_"), ord("\\"), ord("|"), ord("/")], ord("_"))
    codes = np.where(on & (cover < 0.9) & (np.hypot(gx, gy) > 0.25), line, codes).astype(np.uint8)
    # the name on his shirt, when there is room for it
    letters = np.isin(k, [GLYPHS.index(c) for c in set(NAME)])
    if letters.any():
        lr, lc = np.nonzero(letters)
        r = int((lr.mean() + 0.5 - vs[0]) // f)
        c0, c1 = int((lc.min() - us[0]) // f), int((lc.max() + 1 - us[0]) // f)
        if c1 - c0 + 1 >= len(NAME) and 0 <= r < rows:
            first = (c0 + c1 + 1) // 2 - len(NAME) // 2
            codes[r, first:first + len(NAME)] = np.frombuffer(NAME.encode(), np.uint8)
            colour[r, first:first + len(NAME)] = 0.97
    return codes, np.clip(colour, 0.0, 1.0).astype(np.float32)


class TermFilm(Particles):
    """The animation drawn with the terminal's own characters: render(t) gives a character code and a
    colour for every cell. Positions are measured in rows (a column is half a row wide)."""

    def __init__(self, codes, colour, seed=SEED):
        self.rows, self.cols = codes.shape
        self.codes, self.lin = codes, to_linear(colour)
        self.flicker = np.frombuffer(FLICKER.encode(), np.uint8)
        rng = np.random.default_rng(seed)
        cells = np.argwhere(codes > 0)
        n = len(cells)
        cy, cx = cells[:, 0] + 0.5, cells[:, 1] + 0.5
        self.fig = fig = max(float(cy.max() - cy.min()), 1.0) if n else 1.0   # his height in rows
        down = (cy - cy.min()) / fig if n else cy             # 0 at the top of his head .. 1 at his boots
        wave = 0.04 * np.sin(cx * 0.5 / (0.0487 * fig))      # the building line is a little wavy
        first = T_BUILD + (T_DONE - T_BUILD - 0.5) * np.clip(down + wave, 0, 1) ** 0.95 + 0.5 * rng.random(n)
        self.land = np.full((self.rows, self.cols), np.inf, np.float32)
        self.land[cells[:, 0], cells[:, 1]] = first
        self.p_land, self.p_fly = first, rng.uniform(*FLY, n)
        self.p_to = np.stack([cx * 0.5, cy], 1)
        # before they fly, particles fall slowly from the top part, swaying
        self.p0 = np.stack([rng.uniform(0, self.cols * 0.5, n), rng.uniform(-0.25 * self.rows, 0.42 * self.rows, n)], 1)
        self.p_vy = rng.uniform(0.008, 0.028, n) * fig
        self.p_sw = rng.uniform(0.006, 0.018, n) * fig
        self.p_ph, self.p_hz = rng.uniform(0.0, 6.3, (n, 2)), rng.uniform(0.25, 0.7, (n, 2))
        start = self._drift(self.p_land - self.p_fly, np.arange(n))
        d = self.p_to - start
        dist = np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-6)
        normal = np.stack([-d[:, 1], d[:, 0]], 1) / dist[:, None]
        self.p_from = start
        self.p_mid = (start + self.p_to) / 2 + normal * rng.normal(0.0, 0.30, (n, 1)) * dist[:, None]
        lin = self.lin[cells[:, 0], cells[:, 1]]
        self.p_col = 0.55 * lin / np.maximum(lin.max(1, keepdims=True), 0.05) + 0.45 * SPARK
        self.p_tw = rng.uniform(1.0, 3.5, n)
        m = max(1, self.rows * self.cols // 70)               # faint embers falling the whole time
        self.e0 = np.stack([rng.uniform(0, self.cols * 0.5, m), rng.uniform(0, self.rows, m)], 1)
        self.e_vy = rng.uniform(0.017, 0.049, m) * fig
        self.e_ph = rng.uniform(0.0, 6.3, m)
        self.glints = rng.random((self.rows, self.cols))
        self.row_y = (np.arange(self.rows) + 0.5)[:, None]

    def render(self, t):
        """Character codes (0 = empty) and sRGB colours (0..255) of every cell at time t."""
        G = np.zeros((self.rows, self.cols), np.uint8)
        C = np.zeros((self.rows, self.cols, 3), np.float32)

        def put(p, char, colour, behind):
            c, r = np.floor(p[:, 0] * 2.0).astype(np.int64), np.floor(p[:, 1]).astype(np.int64)
            ok = (c >= 0) & (c < self.cols) & (r >= 0) & (r < self.rows)
            if behind:                                        # only where nothing is drawn yet
                ok[ok] = G[r[ok], c[ok]] == 0
            G[r[ok], c[ok]] = char[ok] if np.ndim(char) else char
            C[r[ok], c[ok]] = np.broadcast_to(colour, (len(ok), 3))[ok]

        fade = float(smoothstep(0.0, 1.2, t))
        ex = self.e0[:, 0] + 0.007 * self.fig * np.sin(t * 0.8 + self.e_ph)
        ey = np.mod(self.e0[:, 1] + self.e_vy * t, self.rows + 2.0) - 1.0
        b = 0.5 + 0.5 * np.sin(t * 3.0 + self.e_ph * 3.0)
        v = b > 0.45
        put(np.stack([ex, ey], 1)[v], ord("."), SPARK * (0.08 + 0.10 * b[v, None]) * fade, True)
        launch = self.p_land - self.p_fly
        i = np.nonzero(t < launch)[0]
        if len(i):                                            # particles waiting, falling slowly and twinkling
            p = self._drift(np.full(len(i), t, np.float32), i)
            b = 0.5 + 0.5 * np.sin(t * self.p_tw[i] + self.p_ph[i, 0])
            v = b > 0.5
            put(p[v], np.where(b[v] > 0.92, ord(":"), ord(".")), self.p_col[i[v]] * (0.15 + 0.35 * b[v, None]) * fade, True)
        # the characters that have landed: white-hot at first, cooling to their colour
        age = t - self.land
        on = age >= 0.0
        heat = np.where(on, np.exp(-np.maximum(age, 0.0) / 0.30), 0.0)
        lin = self.lin * (1.0 - heat[..., None]) + HOT(0.55 + 0.45 * heat) * (1.3 * heat)[..., None]
        if T_SWEEP <= t < T_SWEEP + SWEEP:                    # a soft light sweeps up over him
            y = self.rows * (1.0 - (t - T_SWEEP) / SWEEP) * 1.1 - 0.05 * self.rows
            lin = lin + (WHITE * 0.45) * np.exp(-((self.row_y - y) / (0.0487 * self.fig)) ** 2)[..., None]
        if t >= T_DONE:                                       # a few characters glint now and then
            g = np.sin(t * 2.2 + self.glints * 40.0) * 0.5 + 0.5
            lin = lin + WHITE * (0.35 * np.clip((g - 0.985) / 0.015, 0, 1))[..., None]
        G = np.where(on, self.codes, G)
        flick = on & (age < 0.08)
        if flick.any():
            G[flick] = self.flicker[(self.glints[flick] * 997 + t * 60).astype(np.int64) % len(self.flicker)]
        C = np.where(on[..., None], lin, C)
        i = np.nonzero((t >= launch) & (t < self.p_land))[0]
        if len(i):                                            # particles flying in, with a short trail
            f = (t - launch[i]) / self.p_fly[i]
            glow = (0.4 + 0.6 * f)[:, None]
            for back, k in ((0.10, 0.30), (0.05, 0.55)):
                put(self._flight(i, np.clip(f - back, 0.0, 1.0)), ord("."), self.p_col[i] * k * glow, True)
            put(self._flight(i, f), ord("*"), self.p_col[i] * (0.6 + 0.6 * glow) + WHITE * 0.25, False)
        C *= float(smoothstep(0.0, 0.6, t))                   # fade in at the start
        return G, (to_srgb(np.clip(C, 0.0, 1.0)) * 255.0 + 0.5).astype(np.uint8)


class TerminalScreen:
    """This terminal as a screen: coloured characters drawn with escape codes, sending only what changed."""

    BG = "\x1b[48;2;10;8;14m"                                # a dark background whatever the terminal's theme

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
        self._write("\x1b[?1049h\x1b[?25l\x1b[?7l" + self.BG + "\x1b[2J")   # own screen, no cursor, no wrapping
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
        """Keys pressed since the last call."""
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
        self._write(self.BG + "\x1b[2J")

    def _colour(self, key):
        if key not in self.esc:
            r, g, b = ((key >> 10) & 31) * 8 + 4, ((key >> 5) & 31) * 8 + 4, (key & 31) * 8 + 4
            self.esc[key] = f"\x1b[38;2;{r};{g};{b}m"
        return self.esc[key]

    def draw(self, G, rgb):
        """Show a frame: G holds character codes (0 = empty), rgb their colours."""
        G = np.where(G == 0, 32, G).astype(np.int64)
        q = (rgb >> 3).astype(np.int64)
        key = np.where(G == 32, 0, (q[..., 0] << 10) | (q[..., 1] << 5) | q[..., 2]) | (G << 15)
        if self.prev is None or self.prev.shape != key.shape:
            changed = np.ones(key.shape, bool)
        else:
            changed = key != self.prev
        self.prev = key
        out, now = [self.BG], None
        for r in np.nonzero(changed.any(1))[0]:
            cs = np.nonzero(changed[r])[0]
            gaps = np.nonzero(np.diff(cs) > 4)[0]                # runs of changed cells (small gaps drawn again)
            for a, b in zip(np.r_[cs[0], cs[gaps + 1]], np.r_[cs[gaps], cs[-1]]):
                out.append(f"\x1b[{r + 1};{a + 1}H")
                for c in range(a, b + 1):
                    g = G[r, c]
                    if g != 32:
                        colour = key[r, c] & 0x7FFF
                        if colour != now:
                            out.append(self._colour(colour))
                            now = colour
                    out.append(chr(g))
        if len(out) > 1:
            self._write("".join(out))


def text_row(G, rgb, row, col, text, colour):
    """Write plain text into a frame."""
    if 0 <= row < G.shape[0]:
        text = text[:max(0, G.shape[1] - col)]
        G[row, col:col + len(text)] = np.frombuffer(text.encode("ascii"), np.uint8)
        rgb[row, col:col + len(text)] = colour


def play_terminal(photo=None):
    k, col = make_art(photo, grid="fine")
    with TerminalScreen() as screen:
        start, size, film = time.perf_counter(), None, None
        while True:
            frame = time.perf_counter()
            keys = "".join(screen.keys())
            if any(c in keys for c in "qQ\x1b"):
                break
            if any(c in keys for c in "rR "):
                start = time.perf_counter()
            if screen.size() != size:                         # the terminal changed size: fit him again
                size = screen.size()
                cols, rows = size
                film = TermFilm(*terminal_art(k, col, cols, rows)) if cols >= 24 and rows >= 10 else None
                screen.clear()
            t = time.perf_counter() - start
            if film is None:
                G, rgb = np.zeros((size[1], size[0]), np.uint8), np.zeros((size[1], size[0], 3), np.uint8)
                text_row(G, rgb, size[1] // 2, max(0, size[0] // 2 - 12), "Make this terminal bigger", (200, 200, 200))
            else:
                G, rgb = film.render(t)
                if t < 4.0:                                   # how to use it, for the first few seconds
                    text_row(G, rgb, size[1] - 1, 1, "R = play again   Q = close", (110, 105, 120))
            screen.draw(G, rgb)
            time.sleep(max(0.0, 1.0 / 30 - (time.perf_counter() - frame)))


# ------------------------------------------------------------------ playing and saving
GRIDS = {"fine": (CW, CH, ""), "window": (WIN_CW, WIN_CH, "_win")}   # cell size, name in the art file


def make_art(photo=None, save=False, grid="fine"):
    """The art: a character number (-1 = empty) and an sRGB colour for every cell, for the fine grid
    (video and still) or the window grid (bigger characters). Worked out from the photo when one is
    given, otherwise read from ART_FILE (made from the same photo)."""
    art = os.path.join(HERE, ART_FILE)
    cw, ch, key = GRIDS[grid]
    if photo:
        rgb, alpha = load_photo(photo, os.path.join(HERE, MASK))
        if save:                                             # characters as text, colours as 0..255
            data = {}
            for g, (gw, gh, gk) in GRIDS.items():
                k, col = convert(rgb, alpha, gw, gh)
                data["text" + gk] = np.where(k >= 0, np.array(list(GLYPHS))[np.maximum(k, 0)], " ")
                data["col" + gk] = np.round(col * 255.0).astype(np.uint8)
            np.savez_compressed(art, **data)
            print(f"saved {art}")
        return convert(rgb, alpha, cw, ch)
    if not os.path.exists(art):
        sys.exit(f"{ART_FILE} should be next to this script (or make it: --photo {PHOTO} --save-art).")
    with np.load(art) as f:
        if "text" + key not in f:
            sys.exit(f"{ART_FILE} is an older one; make it again with --photo {PHOTO} --save-art.")
        text, col = f["text" + key], f["col" + key]
    if text.shape != (H // ch, W // cw):
        sys.exit(f"{ART_FILE} was made for another size; make it again with --photo {PHOTO} --save-art.")
    number = {c: i for i, c in enumerate(GLYPHS)}
    k = np.vectorize(lambda c: -1 if c == " " else number.get(c, -1))(text).astype(np.int32)
    return k, col.astype(np.float32) / 255.0


def window_film(screen_w, screen_h, photo=None):
    """The film for the window, with characters as big as the screen allows (the window grid), and the
    rows of the picture it shows (where he is) and the window size."""
    k, col = make_art(photo, grid="window")
    rows = np.nonzero((k >= 0).any(1))[0]
    r0, r1 = max(0, rows[0] - 3), min(k.shape[0], rows[-1] + 4)   # a little room above and below him
    fit = min((screen_h - 60) / (r1 - r0), 2.0 * (screen_w - 40) / k.shape[1])   # screen pixels per row
    ch = max(8, int(fit) // 2 * 2)                           # characters are twice as tall as wide
    film = Film(k, col, ch // 2, ch)
    scale = max(1.0, min(fit / ch, 1.5))
    return film, r0 * ch, r1 * ch, (int(film.w * scale), int((r1 - r0) * ch * scale))


def play_window(photo=None):
    try:                                                     # sharp pixels on high-DPI Windows screens
        import ctypes
        from ctypes import wintypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        area = wintypes.RECT()                               # the screen without the taskbar
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(area), 0)
        screen_w, screen_h = area.right - area.left, area.bottom - area.top
    except (ImportError, AttributeError, OSError):
        screen_w, screen_h = 1920, 1040
    film, top, bottom, size = window_film(screen_w, screen_h, photo)
    title = "Ronaldo ASCII"
    cv2.namedWindow(title, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(title, *size)
    cv2.moveWindow(title, max(0, (screen_w - size[0]) // 2), 0)
    start, full = time.perf_counter(), False
    while True:
        t = time.perf_counter() - start
        frame = cv2.cvtColor(film.render(t)[top:bottom], cv2.COLOR_RGB2BGR)
        if frame.shape[1] != size[0]:                        # only on screens too big for the largest characters
            frame = cv2.resize(frame, size, interpolation=cv2.INTER_LINEAR)
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


def save_video(photo, seconds):
    try:
        import imageio_ffmpeg
    except ImportError:
        sys.exit("Saving the video needs imageio-ffmpeg:  pip install imageio-ffmpeg")
    k, col = make_art(photo, grid="fine")
    film = Film(k, col, CW, CH)
    film.end = seconds
    path = os.path.join(HERE, VIDEO_FILE)
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


def save_picture(photo):
    k, col = make_art(photo, grid="fine")
    film = Film(k, col, CW * 2, CH * 2)                      # twice as big: 2160x3840, sharp characters
    frame = film.render(60.0, still=True)                    # long after he is finished, without effects
    path = os.path.join(HERE, IMAGE_FILE)
    cv2.imwrite(path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    print(f"saved {path}")


def main():
    parser = argparse.ArgumentParser(description="Ronaldo in ASCII - particle edition")
    parser.add_argument("--window", action="store_true", help="play in a separate window instead of the terminal")
    parser.add_argument("--photo", help=f"work the art out again from this photo (e.g. {PHOTO}) instead of {ART_FILE}")
    parser.add_argument("--save-art", action="store_true", help=f"with --photo: save the art as {ART_FILE}")
    parser.add_argument("--mp4", action="store_true", help=f"save {VIDEO_FILE} (1080x1920, {FPS} fps) instead of playing")
    parser.add_argument("--png", action="store_true", help=f"save {IMAGE_FILE} (2160x3840) instead of playing")
    parser.add_argument("--seconds", type=float, default=VIDEO_SECONDS, help="length of the video")
    args = parser.parse_args()
    if args.photo and not os.path.exists(args.photo):
        sys.exit(f"Could not find the photo '{args.photo}'.")
    if args.save_art:
        if not args.photo:
            sys.exit("--save-art needs --photo")
        make_art(args.photo, save=True)
        return
    if args.mp4:
        save_video(args.photo, args.seconds)
    elif args.png:
        save_picture(args.photo)
    elif args.window or not sys.stdout.isatty():               # no terminal to draw in (e.g. IDLE): use a window
        play_window(args.photo)
    else:
        play_terminal(args.photo)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
