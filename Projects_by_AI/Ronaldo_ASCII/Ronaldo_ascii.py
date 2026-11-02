"""
Ronaldo in ASCII - particle edition.

Thousands of glowing particles drift in the dark, then fly in one by one and
build Cristiano Ronaldo (No. 7, red kit, seen from behind) out of coloured text
characters, from his boots up to his head. Every character is chosen from the
photo: denser characters where it is brighter, line characters ( / \\ | _ ( ) )
along edges, the photo's own colour, and the name on his shirt in real letters.

Needs:   pip install numpy opencv-python pillow imageio-ffmpeg
Files:   ronaldo_art.npz (the finished art) next to this script; that is all it needs
Run:     python Ronaldo_ascii.py                  plays it in a window
         python Ronaldo_ascii.py --mp4            saves ronaldo_ascii.mp4 (1080x1920, 60 fps)
         python Ronaldo_ascii.py --png            saves ronaldo_ascii.png (2160x3840 still picture)
Remake:  python Ronaldo_ascii.py --photo ronaldo.jpg --save-art
         works the art out again from the photo (with his outline, ronaldo_mask.png) and saves it
Keys:    R or Space = play again,  F = full screen,  Esc or Q = close
"""

import argparse
import math
import os
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
# cells 6 pixels wide and 12 tall: 180 columns and 160 rows.
W, H = 1080, 1920
CW, CH = 6, 12
COLS, ROWS = W // CW, H // CH
FILL, FILL_W = 0.88, 0.92       # at most this tall and this wide, as parts of the picture (his feet are wide apart)

# characters
RAMP = " .:-=+*#%@"            # shading: the more ink, the brighter
LINES = "/\\|_()<>^v'`"        # shapes that follow edges
NAME = "RONALDO"               # printed on his shirt, written with real letters
NAME_BOX = (215 / 495, 92 / 619, 274 / 495, 110 / 619)   # where the name is, as parts of the photo's size
FLICKER = "@#%&*+=$"           # characters flash through these as a particle lands
GLYPHS = "".join(dict.fromkeys(RAMP + LINES + NAME + FLICKER))

# timeline (seconds)
T_BUILD = 1.4                   # the first particles land on his boots
T_DONE = 9.6                    # the last ones land on his head
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


def convert(rgb, alpha):
    """Choose a character and a colour for every cell.

    The shading of the photo picks a character from RAMP (more ink = brighter). Where the photo has a
    real edge, a character from LINES whose shape lines up with that edge can win instead. Colours are
    the photo's own, a little brightened so thin characters still show them. Returns the character
    numbers (ROWS x COLS, -1 = empty) and colours (sRGB)."""
    big, a, M = place(rgb, alpha)
    # pixels on his outline are mixed with the stadium behind him: take their colour from just inside
    sure = (a > 0.92).astype(np.float32)
    near = cv2.GaussianBlur(big * sure[..., None], (0, 0), 5.0) / np.maximum(cv2.GaussianBlur(sure, (0, 0), 5.0), 1e-4)[..., None]
    big = np.where(sure[..., None] > 0, big, near)
    atlas = build_atlas(CW, CH)                           # shapes are compared at the video's cell size
    chars = RAMP + LINES
    idx = np.array([GLYPHS.index(c) for c in chars])
    G = atlas[idx]
    K, nr = len(chars), len(RAMP)
    tone_g = G.mean((1, 2)) / G[:nr].mean((1, 2)).max()  # how bright each character looks (0..1)
    # each character's shape: softened, without its average, scaled to length 1
    Gs = np.stack([cv2.GaussianBlur(g, (0, 0), 0.8) for g in G]).reshape(K, -1)
    Gs -= Gs.mean(1, keepdims=True)
    Gs /= np.maximum(np.linalg.norm(Gs, axis=1, keepdims=True), 1e-6)
    # brightness of the photo: vivid red counts as bright, as it looks; black where he is not
    light = (0.5 * (big * np.array([0.299, 0.587, 0.114], np.float32)).sum(-1) + 0.5 * big.max(-1)) * a
    soft = cv2.GaussianBlur(light, (0, 0), 0.8)
    P = soft.reshape(ROWS, CH, COLS, CW).transpose(0, 2, 1, 3).reshape(-1, CH * CW)
    Pz = P - P.mean(1, keepdims=True)
    contrast = np.linalg.norm(Pz, axis=1) / math.sqrt(CH * CW)             # how much edge is in the cell
    match = (Pz @ Gs.T) / np.maximum(contrast * math.sqrt(CH * CW), 1e-6)[:, None]   # -1..1 shape match
    cover = a.reshape(ROWS, CH, COLS, CW).mean((1, 3)).ravel()
    tone = cv2.GaussianBlur(light, (0, 0), CW).reshape(ROWS, CH, COLS, CW).mean((1, 3)).ravel()
    inside = cover > 0.12
    lo, hi = np.percentile(tone[inside], [2, 99.5])
    T = 0.30 + 0.70 * np.clip((tone - lo) / (hi - lo), 0.0, 1.0) ** 0.75   # wanted brightness 0..1
    T = np.where(tone < lo * 0.6, T * tone / max(lo * 0.6, 1e-6), T)      # real blacks stay black
    edge = np.clip((contrast - 0.015) / 0.030, 0.0, 1.0) ** 1.5           # 0 flat .. 1 a clear edge
    score = 4.0 * (tone_g[None, :] - T[:, None]) ** 2 - 0.6 * edge[:, None] * match
    score[:, nr:] += 0.08 + 2.0 * (1.0 - edge[:, None])                    # line characters only on edges
    score[:, 0] += np.where(T > 0.06, 1.0, 0.0)                            # a blank only for black
    k = np.where(inside, idx[score.argmin(1)], -1)
    col = (big * a[..., None]).reshape(ROWS, CH, COLS, CW, 3).mean((1, 3)).reshape(-1, 3)
    col /= np.maximum(cover, 1e-3)[:, None]
    v = col.max(1, keepdims=True)
    boost = np.clip(0.95 / np.maximum(v, 1e-3), 1.0, 3.0) ** 0.7
    col *= 1.0 + (boost - 1.0) * (0.3 + 0.7 * smoothstep(0.12, 0.45, v))   # dark hair stays dark
    k, col = k.reshape(ROWS, COLS), np.clip(col, 0.0, 1.0).reshape(ROWS, COLS, 3)
    k[k == GLYPHS.index(" ")] = -1

    # the printed name: real letters in white, spaced out over the red shirt
    x0, y0, x1, y1 = NAME_BOX
    hgt, wid = rgb.shape[:2]
    cx0, cx1 = M[0, 0] * x0 * wid + M[0, 2], M[0, 0] * x1 * wid + M[0, 2]
    cy0, cy1 = M[1, 1] * y0 * hgt + M[1, 2], M[1, 1] * y1 * hgt + M[1, 2]
    r0, r1 = int(cy0 // CH), int(cy1 // CH)
    c0, c1 = int(cx0 // CW), int(cx1 // CW) + 1
    shirt = np.median(col[max(0, r0 - 2), c0:c1], axis=0)
    for r in range(r0, r1 + 1):
        k[r, c0:c1] = GLYPHS.index("#")
        col[r, c0:c1] = shirt
    mid = int(((cy0 + cy1) / 2) // CH)
    for i, letter in enumerate(NAME):
        c = int((cx0 + (i + 0.5) * (cx1 - cx0) / len(NAME)) // CW)
        k[mid, c], col[mid, c] = GLYPHS.index(letter), (0.97, 0.97, 0.97)
    return k, col


# ------------------------------------------------------------------ the film
class Film:
    """The animation: build once, then render(t) for any time t (seconds)."""

    def __init__(self, k, col, cw, ch, seed=SEED):
        self.cw, self.ch = cw, ch
        self.s = cw / CW                                  # screen pixels per layout pixel
        self.w, self.h = COLS * cw, ROWS * ch
        self.end = None                                   # fade to black at this time (for the video)
        self.atlas = build_atlas(cw, ch)
        self.atlas_rows = self.atlas.reshape(-1, cw)      # each pixel row of each character
        self.row_of_cell = np.arange(ch, dtype=np.int32)[None, :, None]
        self.k = k
        self.col = to_linear(col) * 1.12                  # colours as light, a touch brighter
        rng = np.random.default_rng(seed)

        # one particle for every character
        cells = np.argwhere(k >= 0)
        self.cr, self.cc = cells[:, 0], cells[:, 1]
        n = len(cells)
        tx, ty = (self.cc + 0.5) * CW, (self.cr + 0.5) * CH
        y_top, y_bot = ty.min(), ty.max()
        up = (y_bot - ty) / max(y_bot - y_top, 1.0)       # 0 at his boots .. 1 at the top of his head
        wave = 0.04 * np.sin(tx / 70.0)                   # the build-up line is a little wavy
        land = T_BUILD + (T_DONE - T_BUILD - 0.5) * np.clip(up + wave, 0, 1) ** 0.95 + 0.5 * rng.random(n)
        fly = rng.uniform(*FLY, n)
        self.land = np.full((ROWS, COLS), np.inf, np.float32)
        self.land[self.cr, self.cc] = land
        self.p_land, self.p_fly = land.astype(np.float32), fly.astype(np.float32)
        self.p_to = np.stack([tx, ty], 1).astype(np.float32)
        # before they fly, particles drift slowly upwards all over the picture, swaying
        self.p0 = np.stack([rng.uniform(-40, W + 40, n), rng.uniform(0, H + 80, n)], 1).astype(np.float32)
        self.p_vy = rng.uniform(12.0, 40.0, n).astype(np.float32)
        self.p_sw = rng.uniform(8.0, 26.0, n).astype(np.float32)
        self.p_ph = rng.uniform(0.0, 6.3, (n, 2)).astype(np.float32)
        self.p_hz = rng.uniform(0.25, 0.7, (n, 2)).astype(np.float32)
        start = self._drift(land - fly, np.arange(n))     # where each one is when it sets off
        d = self.p_to - start
        normal = np.stack([-d[:, 1], d[:, 0]], 1) / np.maximum(np.hypot(d[:, 0], d[:, 1]), 1.0)[:, None]
        self.p_from = start
        self.p_mid = ((start + self.p_to) / 2 + normal * rng.normal(0.0, 0.35, (n, 1)) * np.hypot(d[:, 0], d[:, 1])[:, None]
                      - np.array([0.0, 60.0], np.float32)).astype(np.float32)   # a curved path, bowing upwards a little
        lin = self.col[self.cr, self.cc]
        self.p_col = (0.55 * lin / np.maximum(lin.max(1, keepdims=True), 0.05) + 0.45 * SPARK).astype(np.float32)
        self.p_tw = rng.uniform(1.0, 3.5, n).astype(np.float32)                 # how fast each one twinkles
        # a few faint embers keep rising round him the whole time
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
        cy = (np.arange(ROWS, dtype=np.float32) + 0.5) * CH
        self.sweep_y = cy[:, None]
        # turning light into screen colours: kept true to the photo, bright glows roll off softly
        self.enc = 255.0 / math.log1p(400.0 * 8.0)
        x = np.expm1(np.arange(256) / self.enc) / 400.0
        soft = np.where(x < 0.8, x, 0.8 + 0.2 * (1.0 - np.exp(-(x - 0.8) / 0.2)))
        self.tone = np.clip(to_srgb(soft) * 255.0 + 0.5, 0, 255).astype(np.uint8)
        self.buf_glyph = np.empty((ROWS, ch, COLS, cw), np.float32)
        self.buf_img, self.buf_up, self.buf_a3 = (np.empty((self.h, self.w, 3), np.float32) for _ in range(3))
        self.buf_u8, self.buf_tone = (np.empty((self.h, self.w, 3), np.uint8) for _ in range(2))
        self.out = np.zeros((self.h, self.w, 3), np.uint8)
        self.glints = rng.random((ROWS, COLS)).astype(np.float32)

    def _drift(self, t, i):
        """Where particles i are at time(s) t while they drift (layout pixels)."""
        t = np.asarray(t, np.float32)
        x = self.p0[i, 0] + self.p_sw[i] * np.sin(t * self.p_hz[i, 0] + self.p_ph[i, 0])
        y = self.p0[i, 1] - self.p_vy[i] * t + 0.6 * self.p_sw[i] * np.cos(t * self.p_hz[i, 1] + self.p_ph[i, 1])
        return np.stack([x, np.mod(y + 40.0, H + 80.0) - 40.0], 1).astype(np.float32)

    def _flight(self, i, f):
        """Points along the curved paths of particles i, f = 0 (set off) .. 1 (landed)."""
        e = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)      # slow start, slow landing
        a, b, c = self.p_from[i], self.p_mid[i], self.p_to[i]
        e = e[:, None]
        return (1 - e) ** 2 * a + 2 * e * (1 - e) * b + e * e * c

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
        if particles:                                      # faint embers rising
            ex = self.e0[:, 0] + 14.0 * np.sin(t * 0.8 + self.e_ph)
            ey = np.mod(self.e0[:, 1] - self.e_vy * t + 40.0, H + 80.0) - 40.0
            b = (0.06 + 0.05 * np.sin(t * 3.0 + self.e_ph * 3.0)) * float(smoothstep(0.0, 1.5, t))
            self._dots(lb, np.stack([ex, ey], 1), self.e_col * b[:, None], s2)
        flash = (heat > 0.08)
        if flash.any():                                    # each landing gives a small flash of light
            r, c = np.nonzero(flash)
            p = np.stack([(c + 0.5) * CW, (r + 0.5) * CH], 1)
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


# ------------------------------------------------------------------ playing and saving
def make_art(photo=None, save=False):
    """The art: a character number (-1 = empty) and an sRGB colour for every cell. Worked out from the
    photo when one is given, otherwise read from ART_FILE (made from the same photo)."""
    art = os.path.join(HERE, ART_FILE)
    if photo:
        rgb, alpha = load_photo(photo, os.path.join(HERE, MASK))
        k, col = convert(rgb, alpha)
        if save:                                             # characters as text, colours as 0..255
            text = np.where(k >= 0, np.array(list(GLYPHS))[np.maximum(k, 0)], " ")
            np.savez_compressed(art, text=text, col=np.round(col * 255.0).astype(np.uint8))
            print(f"saved {art}")
        return k, col
    if not os.path.exists(art):
        sys.exit(f"{ART_FILE} should be next to this script (or make it: --photo {PHOTO} --save-art).")
    with np.load(art) as f:
        text, col = f["text"], f["col"]
    if text.shape != (ROWS, COLS):
        sys.exit(f"{ART_FILE} was made for another size; make it again with --photo {PHOTO} --save-art.")
    number = {c: i for i, c in enumerate(GLYPHS)}
    k = np.vectorize(lambda c: -1 if c == " " else number.get(c, -1))(text).astype(np.int32)
    return k, col.astype(np.float32) / 255.0


def play(photo=None):
    try:                                                     # sharp pixels on high-DPI Windows screens
        import ctypes
        from ctypes import wintypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        area = wintypes.RECT()                               # the screen without the taskbar
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(area), 0)
        screen_w, screen_h = area.right - area.left, area.bottom - area.top
    except (ImportError, AttributeError, OSError):
        screen_w, screen_h = 1920, 1040
    k, col = make_art(photo)
    film = Film(k, col, 4, 8)                                # drawn at 720x1280, then fitted to the screen
    rows = np.nonzero((k >= 0).any(1))[0]                    # the window shows the part where he is
    top = max(0, int(((rows[0] * CH) - 80) * film.s))
    bottom = min(film.h, int(((rows[-1] + 1) * CH + 80) * film.s))
    scale = min((screen_h - 60) / (bottom - top), (screen_w - 40) / film.w, 1.5)
    size = (int(film.w * scale), int((bottom - top) * scale))
    title = "Ronaldo ASCII"
    cv2.namedWindow(title, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(title, *size)
    cv2.moveWindow(title, max(0, (screen_w - size[0]) // 2), 0)
    start, full = time.perf_counter(), False
    while True:
        t = time.perf_counter() - start
        frame = cv2.cvtColor(film.render(t)[top:bottom], cv2.COLOR_RGB2BGR)
        if frame.shape[1] != size[0]:
            frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
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
    k, col = make_art(photo)
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
    k, col = make_art(photo)
    film = Film(k, col, CW * 2, CH * 2)                      # twice as big: 2160x3840, sharp characters
    frame = film.render(60.0, still=True)                    # long after he is finished, without effects
    path = os.path.join(HERE, IMAGE_FILE)
    cv2.imwrite(path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    print(f"saved {path}")


def main():
    parser = argparse.ArgumentParser(description="Ronaldo in ASCII - particle edition")
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
    else:
        play(args.photo)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
