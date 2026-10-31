"""
Special letter - cinematic edition 2 (more realistic).

A handwritten love letter is sealed with a heart of red wax. A match is struck
just out of view and slides in, its flame bending as it moves; the wax melts and
the seal bursts into flame. The paper burns away with a thin glowing edge,
brown scorch, black char, smoke and ash. A rose bud forms in the fire and opens
petal by petal (a real 3D rose shape), its stem and leaves grow, light rays open
behind it, and sparks fly up from the rose to write the message in the sky.
Everything solid is drawn with text characters (1.5x finer than the first
edition); light (fire glow, sparks, rays) is added on top, like in a film.

Needs:   pip install numpy opencv-python pillow imageio-ffmpeg
Run:     python Special_letter_cinematic_v2.py                 plays it in a window
         python Special_letter_cinematic_v2.py "Riya"          any name or words on the letter
         python Special_letter_cinematic_v2.py "Riya" --mp4    saves special_letter.mp4 (1080x1920, 60 fps)
Keys:    R or Space = play again,  F = full screen,  Esc or Q = close
The window fits your screen; drag its edge to make it any size.
"""

import argparse
import math
import os
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------------ settings
MESSAGE = "For You"             # the words written on the letter: change them to anything
VIDEO_FILE = "special_letter.mp4"
VIDEO_SECONDS = 15.0
FPS = 60
SEED = 14                       # another number gives a different take of the same story

# ------------------------------------------------------------------ layout
# Positions are pixels of the 1080x1920 video. The picture is a grid of
# character cells, each 6 pixels wide and 12 tall.
COLS, ROWS = 180, 159
CW, CH = 6.0, 12.0
PAD = 6.0                       # empty pixels above and below the grid
SR, SC = ROWS * 2, COLS         # the fire is simulated on square 6x6 cells
GS = 9.0 / CW                   # cells per cell of the first version (sizes below were tuned on 9x18 cells)

ENV = (72.0, 690.0, 1008.0, 1326.0)      # envelope: left, top, right, bottom (on cell edges)
SEAL = (540.0, 985.0)                     # centre of the wax seal
HEAD = (540.0, 640.0)                     # centre of the rose
WORDS = (540.0, 395.0)                    # where the glowing message is written above the rose
ROSE_BASE = (540.0, 674.0)                # where the petals meet the stem (the rose is seen a little from above)
ROSE_SIZE = 205.0                         # radius of the open rose in pixels
ROSE_KEYS = 16                            # the bloom is worked out at this many stages and blended between them
MATCH_PATH = ((1240, 1350), (930, 1295), (705, 1150), (600, 1068))   # the match slides in along this
STRIKE = (1110.0, 1340.0)                 # where the match is struck, just off the right edge

# ------------------------------------------------------------------ timeline (seconds)
T_LETTER = 0.4      # the letter appears
T_SHINE = 1.85      # a soft light sweeps over the paper
T_STRIKE = 2.05     # a match is struck just out of view: a flash, sparks and a puff of smoke
T_MATCH = 2.3       # the lit match slides in
T_TOUCH = 3.55      # its flame touches the wax seal
T_IGNITE = 4.3      # the seal bursts into flame and the paper starts to burn
T_OUT = T_IGNITE + 0.55   # the match is shaken out and leaves a thread of smoke
T_ROSE = 6.3        # a rose blooms inside the fire
T_RAYS = 8.4        # light rays open behind the rose
T_WORDS = 9.7       # sparks rise from the rose and write the message in the sky
SCORCH = 0.30       # paper turns brown this long before it catches fire
RIM = 0.08          # the thin, bright burning edge lasts this long on each bit of paper
COOL = 0.45         # then the burnt paper glows orange, red and goes black in this long

# ------------------------------------------------------------------ the rose
STEM = ((540, 690), (508, 1200), (552, 1660))                 # start, bend, end
LEAVES = [((530, 1035), (430, 945), (290, 960), 46),         # base, bend, tip, half width
          ((524, 1110), (650, 1010), (800, 1035), 50),
          ((520, 1290), (430, 1225), (318, 1285), 42),
          ((528, 1400), (630, 1335), (740, 1395), 38)]
SEPALS = [((540, 700), (455, 760), (420, 885), 11), ((540, 700), (625, 760), (662, 880), 11),
          ((536, 705), (500, 790), (488, 895), 9), ((544, 705), (582, 790), (596, 893), 9)]
THORNS = ((0.30, 1), (0.42, -1), (0.57, 1), (0.70, -1), (0.84, 1))     # place along the stem, side

# ------------------------------------------------------------------ characters
GLYPHS = "".join(chr(i) for i in range(32, 127)) + "\u2022\u00b7"     # ASCII, bullet, middle dot
PALETTES = {  # characters for each material (sorted by ink later, so the order here does not matter)
    "paper": "#8@", "ink": "*%&#@", "wax": ".:oO0@", "fire": ".':;~+*%#@", "smoke": ".,:;~",
    "ember": "*%#@", "petal": ":;+*%&8#@", "leaf": ":;+*%&#", "flame": ":+*#@", "flicker": "@#%&*+=",
    "ash": ".,'`:;~"}

# particles: one row per particle with these columns
PX, PY, PVX, PVY, PAGE, PLIFE, PHEAT, PLIFT, PSEED = range(9)
KINDS = {  # air drag, sideways sway, flutter, most alive at once
    "spark": (1.6, 160.0, 0.0, 2500), "ember": (0.8, 70.0, 0.0, 600), "ash": (1.4, 50.0, 110.0, 900),
    "glint": (0.0, 0.0, 0.0, 60), "petal": (1.2, 30.0, 70.0, 12)}
TONE_E = 200.0      # how finely dark values are kept when turning light into screen colours


# ------------------------------------------------------------------ small helpers
def smoothstep(e0, e1, x):
    x = np.clip((np.asarray(x, np.float32) - e0) / (e1 - e0), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


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


def tile_noise(rng, h, w, sigma, sigma_y=None):
    """Smooth random pattern (about -2..2) that wraps around at the edges (taller blobs if sigma_y is bigger)."""
    spec = np.fft.fft2(rng.standard_normal((h, w)))
    ky, kx = np.fft.fftfreq(h)[:, None], np.fft.fftfreq(w)[None, :]
    sy = sigma if sigma_y is None else sigma_y
    n = np.real(np.fft.ifft2(spec * np.exp(-2.0 * np.pi ** 2 * ((sigma * kx) ** 2 + (sy * ky) ** 2))))
    return (n / (n.std() + 1e-9)).astype(np.float32)


def scroll(tex, dy, dx):
    """A wrapping texture moved up by dy and left by dx cells (smooth up and down, whole cells sideways)."""
    iy, fy = int(math.floor(dy)), dy - math.floor(dy)
    a = np.roll(tex, (-iy, -int(round(dx))), axis=(0, 1))
    return a + (np.roll(a, -1, axis=0) - a) * np.float32(fy)


def bezier(points, u):
    """Point and direction at u (0..1) along a Bezier curve with these control points."""
    p = np.asarray(points, np.float64)
    while len(p) > 2:
        p = p[:-1] + (p[1:] - p[:-1]) * u
    return p[0] + (p[1] - p[0]) * u, p[1] - p[0]


def curve_field(X, Y, points, n=24):
    """For every point: how far along the curve (a Bezier curve with three control points) its nearest
    point is (0..1), the signed distance to the curve, and the curve's direction there (degrees).
    A rough search over n points is refined by a few exact steps along the curve."""
    (ax, ay), (bx, by), (cx, cy) = points
    X, Y = np.asarray(X, np.float32), np.asarray(Y, np.float32)
    us = np.linspace(0.0, 1.0, n, dtype=np.float32)
    px = (1 - us) ** 2 * ax + 2 * us * (1 - us) * bx + us ** 2 * cx
    py = (1 - us) ** 2 * ay + 2 * us * (1 - us) * by + us ** 2 * cy
    best = np.full(X.shape, np.inf, np.float32)
    u = np.zeros(X.shape, np.float32)
    for k in range(n):                                   # the nearest of the rough points
        d2 = (X - px[k]) ** 2 + (Y - py[k]) ** 2
        closer = d2 < best
        best = np.where(closer, d2, best)
        u = np.where(closer, us[k], u)
    for _ in range(4):                                   # slide along the curve to the true nearest point
        qx = (1 - u) ** 2 * ax + 2 * u * (1 - u) * bx + u ** 2 * cx
        qy = (1 - u) ** 2 * ay + 2 * u * (1 - u) * by + u ** 2 * cy
        tx = 2 * (1 - u) * (bx - ax) + 2 * u * (cx - bx)
        ty = 2 * (1 - u) * (by - ay) + 2 * u * (cy - by)
        u = np.clip(u + ((X - qx) * tx + (Y - qy) * ty) / (tx * tx + ty * ty + 1e-6), 0.0, 1.0)
    qx = (1 - u) ** 2 * ax + 2 * u * (1 - u) * bx + u ** 2 * cx
    qy = (1 - u) ** 2 * ay + 2 * u * (1 - u) * by + u ** 2 * cy
    tx = 2 * (1 - u) * (bx - ax) + 2 * u * (cx - bx)
    ty = 2 * (1 - u) * (by - ay) + 2 * u * (cy - by)
    dist = np.hypot(X - qx, Y - qy)
    side = np.sign(tx * (Y - qy) - ty * (X - qx))
    return u, dist * side, np.degrees(np.arctan2(ty, tx))


def line_index(deg):
    """Which of '-', '\\', '|', '/' (0..3) best follows a line at this angle (y points down)."""
    a = np.mod(deg, 180.0)
    return np.select([a < 22.5, a < 67.5, a < 112.5, a < 157.5], [0, 1, 2, 3], 0)


def border(mask):
    """Cells of the mask that touch a cell outside it."""
    return mask & ~(np.roll(mask, 1, 0) & np.roll(mask, -1, 0) & np.roll(mask, 1, 1) & np.roll(mask, -1, 1))


def find_font(names):
    folders = [os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"),
               "/usr/share/fonts/truetype/dejavu", "/Library/Fonts", "/System/Library/Fonts",
               "/System/Library/Fonts/Supplemental"]
    for name in names:
        for folder in folders:
            if os.path.exists(os.path.join(folder, name)):
                return os.path.join(folder, name)
    return None


def build_atlas(cw, ch):
    """Every character drawn once into a cw x ch greyscale cell (0..1)."""
    path = find_font(["consolab.ttf", "consola.ttf", "DejaVuSansMono-Bold.ttf", "Menlo.ttc"])
    font = ImageFont.truetype(path, max(6, round(cw / 0.55))) if path else ImageFont.load_default()
    atlas = np.zeros((len(GLYPHS), ch, cw), np.float32)
    for i, g in enumerate(GLYPHS):
        im = Image.new("L", (cw * 3, ch * 3), 0)
        ImageDraw.Draw(im).text((cw * 1.5, ch * 1.5), g, fill=255, font=font, anchor="mm")
        atlas[i] = np.asarray(im, np.float32)[ch:2 * ch, cw:2 * cw] / 255.0
    return atlas


def text_coverage(message, at=(540, 1195), box=(760, 200), size=200):
    """How much of each cell the handwritten message covers (0..1)."""
    img = Image.new("L", (1080, 1920), 0)
    message = message.strip()
    message = message[:1].upper() + message[1:]              # first letter always a capital
    if message:
        path = find_font(["segoescb.ttf", "segoesc.ttf", "LHANDW.TTF", "Inkfree.ttf", "SnellRoundhand.ttc",
                          "Brush Script.ttf", "georgiab.ttf", "DejaVuSerif-Bold.ttf", "DejaVuSans-Bold.ttf"])
        draw = ImageDraw.Draw(img)
        while True:
            font = ImageFont.truetype(path, size) if path else ImageFont.load_default()
            tb = draw.textbbox(at, message, font=font, anchor="mm")
            if (tb[2] - tb[0] <= box[0] and tb[3] - tb[1] <= box[1]) or size <= 30 or not path:
                break
            size -= 6
        draw.text(at, message, fill=255, font=font, anchor="mm")
    a = np.asarray(img, np.float32)[int(PAD):int(PAD) + ROWS * int(CH)] / 255.0
    return cv2.resize(a, (COLS, ROWS), interpolation=cv2.INTER_AREA)


def cell_box(x0, y0, x1, y1):
    """The cells (first column, first row, end column, end row) that cover this part of the layout."""
    return (max(0, int(x0 // CW)), max(0, int((y0 - PAD) // CH)),
            min(COLS, int(math.ceil(x1 / CW))), min(ROWS, int(math.ceil((y1 - PAD) / CH))))


def fine_grid(box):
    """The centre of every pixel in a box of cells (layout pixels)."""
    c0, r0, c1, r1 = box
    return np.meshgrid(np.arange(c0 * CW, c1 * CW, dtype=np.float32) + 0.5,
                       PAD + np.arange(r0 * CH, r1 * CH, dtype=np.float32) + 0.5)


def to_cells(a, box):
    """Average a pixel image (made on fine_grid(box)) over every cell."""
    c0, r0, c1, r1 = box
    return np.asarray(a, np.float32).reshape(r1 - r0, int(CH), c1 - c0, int(CW), *a.shape[2:]).mean(axis=(1, 3))


def paste(full, part, box):
    """Put a box of cells into a full-size cell image."""
    c0, r0, c1, r1 = box
    full[r0:r1, c0:c1] = part
    return full


_HEART = np.linspace(0.0, 2.0 * np.pi, 720, endpoint=False)


def heart_radius(ang, size=6.3, drop=20.0, wobble=1.0):
    """Distance from the seal centre to the edge of the heart-shaped wax, for each angle."""
    a = _HEART
    ex = size * 16.0 * np.sin(a) ** 3                                    # the classic heart curve
    ey = -size * (13.0 * np.cos(a) - 5.0 * np.cos(2 * a) - 2.0 * np.cos(3 * a) - np.cos(4 * a)) - drop
    ea = np.arctan2(ey, ex)
    order = np.argsort(ea)
    r = np.interp(ang, ea[order], np.hypot(ex, ey)[order], period=2.0 * np.pi)
    return r * (1.0 + wobble * (0.03 * np.sin(3 * ang + 1.3) + 0.02 * np.sin(5 * ang + 0.4)
                                + 0.0125 * np.sin(9 * ang + 2.0)))                # a slightly uneven wax edge


def rose_head(b, n_th=1800, n_x=40, elev=0.62):
    """A rose as a 3D surface of spiralling petals (the well-known parametric rose), opened by b (0 = bud,
    1 = full bloom) and seen from a little above. Returns screen x, y (in rose radii, y down), how near
    each point is, its brightness and which petal it belongs to."""
    th = np.linspace(-2.0 * np.pi, 15.0 * np.pi, n_th)
    TH, XX = np.meshgrid(th, np.linspace(0.0, 1.0, n_x))
    inner = (TH - th[0]) / (th[-1] - th[0])                         # 0 = outermost petal .. 1 = the heart
    phi_open = (np.pi / 2.0) * np.exp(-TH / (8.0 * np.pi))           # how far each petal leans out when open
    phi_bud = 0.42 - 0.30 * inner                                    # in the bud the petals wrap round the heart
    k = smoothstep(0.55 * inner, 0.55 * inner + 0.45, b)             # the outer petals open first
    phi = phi_bud + (phi_open - phi_bud) * k
    lip = 1.0 - 0.5 * ((1.25 * (1.0 - np.mod(3.6 * TH, 2.0 * np.pi) / np.pi) ** 2 - 0.25) ** 2)   # petal outline
    cup = 1.95653 * XX ** 2 * (1.27689 * XX - 1.0) ** 2 * np.sin(phi)                               # petals curl back
    r = lip * (XX * np.sin(phi) + cup * np.cos(phi))
    h = lip * (XX * np.cos(phi) - cup * np.sin(phi))
    P = np.stack([r * np.sin(TH), r * np.cos(TH), h], -1)           # x right, y away from us, z up
    ce, se = math.cos(elev), math.sin(elev)
    sx, sy = P[..., 0], -(P[..., 2] * ce + P[..., 1] * se)
    near = -P[..., 1] * ce + P[..., 2] * se
    n = np.cross(np.gradient(P, axis=1), np.gradient(P, axis=0))
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
    nx, ny, nz = n[..., 0], -(n[..., 2] * ce + n[..., 1] * se), -n[..., 1] * ce + n[..., 2] * se
    back = nz < 0                                                    # we see the back of this bit of petal
    nx, ny, nz = np.where(back, -nx, nx), np.where(back, -ny, ny), np.abs(nz)
    lx, ly, lz = -0.45, -0.55, 0.70                                  # light from the upper left
    diffuse = np.clip(nx * lx + ny * ly + nz * lz, 0.0, 1.0)
    velvet = (1.0 - nz) ** 2.5                                       # petals seen edge-on look paler, like velvet
    hidden = (0.30 + 0.70 * smoothstep(0.0, 0.85, XX)) * (1.0 - 0.45 * inner ** 1.5)   # deep inside is darker
    shade = ((0.12 + 0.88 * diffuse) + 0.35 * velvet) * hidden * np.where(back, 0.85, 1.0)
    petal = np.floor(3.6 * TH / (2.0 * np.pi))
    return sx.ravel(), sy.ravel(), near.ravel(), shade.ravel(), petal.ravel()


def splat(fx, fy, near, values, w, h):
    """Draw points into a w x h image, the nearest point winning in every pixel; NaN where nothing is."""
    ix = np.concatenate([np.floor(fx), np.floor(fx) + 1.0]).astype(np.int64)   # each point is two pixels wide
    iy = np.concatenate([np.round(fy), np.round(fy)]).astype(np.int64)
    near = np.concatenate([near, near])
    ok = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h)
    idx, near = (iy * w + ix)[ok], near[ok]
    o = np.argsort(near, kind="stable")[::-1]                        # nearest first
    u, first = np.unique(idx[o], return_index=True)
    pick = o[first]
    out = []
    for v in values:
        a = np.full(w * h, np.nan, np.float32)
        a[u] = np.concatenate([v, v])[ok][pick]
        out.append(a.reshape(h, w))
    return out


# ------------------------------------------------------------------ colours (linear light; above 1 glows)
def rgb(r, g, b):
    return np.array([r, g, b], np.float32)


PAPER, INK, CHAR, SCORCHED = rgb(0.90, 0.72, 0.60), rgb(0.42, 0.012, 0.040), rgb(0.050, 0.038, 0.032), rgb(0.20, 0.085, 0.03)
WAX_BASE, WAX_SHINE = rgb(0.62, 0.018, 0.045), rgb(1.0, 0.80, 0.80)
AIR_RED, AIR_BLUE = rgb(0.85, 0.040, 0.050), rgb(0.050, 0.11, 0.60)
WOOD, MATCH_HEAD, THORN = rgb(1.0, 0.66, 0.28), rgb(0.40, 0.035, 0.025), rgb(0.30, 0.07, 0.03)
STAR, SMOKE, WHITE = rgb(0.70, 0.78, 1.00), rgb(0.060, 0.055, 0.052), rgb(1.0, 0.86, 0.78)
AMBIENT, FIRE_TINT, FLAME_TINT = rgb(0.92, 0.90, 0.96), rgb(1.0, 0.42, 0.10), rgb(1.0, 0.55, 0.18)
RIM_LIGHT, BLUE_FLAME = rgb(0.9, 0.42, 0.50), rgb(0.15, 0.30, 1.4)
STRIKE_TINT, SMOKE_LIT = rgb(1.0, 0.78, 0.50), rgb(0.16, 0.15, 0.15)
RAY_CORE, RAY_BEAM, RAY_STREAK = rgb(1.5, 1.05, 0.78), rgb(1.0, 0.70, 0.62), rgb(0.40, 0.55, 1.40)
FIRE = Gradient((0.00, (0, 0, 0)), (0.10, (0.07, 0.005, 0.0)), (0.25, (0.40, 0.035, 0.005)),
                (0.45, (1.15, 0.22, 0.025)), (0.65, (2.1, 0.80, 0.11)), (0.85, (3.1, 1.9, 0.60)),
                (1.00, (4.2, 3.3, 2.1)), (1.30, (5.2, 4.8, 4.0)))
WAX = Gradient((0.0, (0.06, 0.002, 0.008)), (0.4, (0.45, 0.015, 0.035)), (0.7, (0.95, 0.06, 0.08)),
               (0.88, (1.35, 0.20, 0.20)), (1.0, (2.2, 0.90, 0.85)))
ROSE = Gradient((0.0, (0.03, 0.0, 0.004)), (0.3, (0.22, 0.003, 0.018)), (0.55, (0.62, 0.012, 0.045)),
                (0.75, (1.0, 0.045, 0.08)), (0.9, (1.25, 0.12, 0.15)), (1.0, (1.45, 0.30, 0.32)))
LEAF_EDGE = rgb(0.30, 0.06, 0.03)              # young rose leaves have bronze-red edges
LEAF = Gradient((0.0, (0.003, 0.02, 0.005)), (0.4, (0.02, 0.14, 0.03)), (0.7, (0.07, 0.36, 0.07)),
                (0.9, (0.20, 0.62, 0.16)), (1.0, (0.45, 0.85, 0.32)))


# ------------------------------------------------------------------ the film
class Film:
    """The animation. Build it once, then call step(dt) and render() for every frame."""

    def __init__(self, cw, ch, seed=SEED, message=MESSAGE, view=None):
        self.cw, self.ch, self.seed, self.message = cw, ch, seed, message
        self.s = cw / CW                                   # screen pixels per layout pixel
        self.w, self.h = COLS * cw, ROWS * ch              # size of the character grid on screen
        self.r0, self.r1 = view or (0, ROWS)               # the rows that are drawn (a window can show less)
        self.vh = (self.r1 - self.r0) * ch                 # height of the drawn part
        self.pad = round(PAD * self.s) if view is None else 0
        self.end = None                                    # fade to black at this time (for the video)
        self.atlas = build_atlas(cw, ch)
        big = build_atlas(9, 18)
        ink = big.mean(axis=(1, 2))                        # how much ink each character has
        rows = big.sum(axis=2)
        self.ink_y = (rows * (np.arange(18) + 0.5)).sum(1) / np.maximum(rows.sum(1), 1e-6) / 18.0   # where the ink sits
        self.gi = {g: i for i, g in enumerate(GLYPHS)}
        self.pal = {k: np.array(sorted((self.gi[g] for g in v), key=lambda i: ink[i]), np.int32)
                    for k, v in PALETTES.items()}
        self.line = np.array([self.gi[g] for g in "-\\|/"], np.int32)
        rng = np.random.default_rng(seed)
        self._build_letter(rng)
        self._build_rose()
        self._build_screen(rng)
        self.reset()

    def pick(self, name, v):
        """A character of this material for brightness v (0..1): brighter means more ink."""
        p = self.pal[name]
        return p[(np.clip(v, 0.0, 1.0) * (len(p) - 1) + 0.5).astype(np.int32)]

    def line_at(self, off, slope):
        """A character that draws a thin, nearly flat line passing this far (pixels) below the top of the
        cell; steeper lines get a slash. slope is the line's rise to the right (y up)."""
        cand = np.array([self.gi[g] for g in "`'-~._"], np.int32)
        ys = self.ink_y[cand]
        pick = cand[np.abs(np.clip(off, 0.0, CH)[..., None] - ys * CH).argmin(-1)]
        steep = np.abs(slope) > 1.2
        return np.where(steep, np.where(slope > 0, self.gi["/"], self.gi["\\"]), pick)

    # ---------------------------------------------------------- building the scene
    def _build_letter(self, rng):
        X, Y = np.meshgrid((np.arange(COLS, dtype=np.float32) + 0.5) * CW,
                           PAD + (np.arange(ROWS, dtype=np.float32) + 0.5) * CH)
        self.X, self.Y = X, Y
        self.rnd = rng.random((3, ROWS, COLS), dtype=np.float32)       # fixed random numbers per cell
        fine, broad, burn1, burn2 = (tile_noise(rng, ROWS, COLS, s) for s in (0.7 * GS, 5.0 * GS, 4.0 * GS, 1.2 * GS))
        x0, y0, x1, y1 = ENV
        sx, sy = SEAL
        inside = (X > x0) & (X < x1) & (Y > y0) & (Y < y1)
        edge = inside & ((X - x0 < 2 * CW) | (x1 - X < 2 * CW) | (Y - y0 < CH) | (y1 - Y < CH))

        # four flaps folded over the back, worked out for every pixel and then averaged into the cells
        box = cell_box(x0, y0, x1, y1)
        FX, FY = fine_grid(box)
        top_tip, bot_tip = sy + 32.0, sy - 80.0

        def into_top(x, y):                                # how far (pixels) a point is inside the top flap
            return (top_tip + (y0 - top_tip) * np.abs(x - sx) / (sx - x0) - y) / math.hypot(1.0, (top_tip - y0) / (sx - x0))

        def into_bottom(x, y):
            return (y - bot_tip - (y1 - bot_tip) * np.abs(x - sx) / (sx - x0)) / math.hypot(1.0, (y1 - bot_tip) / (sx - x0))

        d_top, d_bot = into_top(FX, FY), into_bottom(FX, FY)
        flap = np.where(d_top > 0, 0, np.where(d_bot > 0, 3, np.where(FX < sx, 1, 2)))
        light = np.array([1.0, 0.83, 0.92, 0.95], np.float32)[flap]           # each flap faces the light a bit differently
        light *= 1.0 + 0.08 * (-(FX - sx) / (x1 - x0) - (FY - sy) / (y1 - y0))  # key light from the upper left
        light *= 1.0 + 0.05 * np.where(flap == 0, smoothstep(0.0, 60.0, d_top), 0.0)   # the top flap bulges a little
        ox, oy = 3.5, 6.0                                  # flaps cast soft shadows down and to the right
        light *= 1.0 - 0.42 * smoothstep(-9.0, 2.0, into_top(FX - ox, FY - oy)) * (d_top <= 0)
        light *= 1.0 - 0.34 * smoothstep(-8.0, 2.0, into_bottom(FX - ox, FY - oy)) * ((d_top <= 0) & (d_bot <= 0))
        light *= 1.0 + 0.10 * ((np.abs(d_top) < 1.5) & (FX < sx))              # the lit cut edge of the top flap
        light = paste(np.ones((ROWS, COLS), np.float32), to_cells(light, box), box)
        cut_t = paste(np.zeros((ROWS, COLS), np.float32), to_cells(d_top > 0, box), box)
        cut_b = paste(np.zeros((ROWS, COLS), np.float32), to_cells((d_bot > 0) & (d_top <= 0), box), box)
        light *= 1.0 + 0.035 * fine + 0.03 * broad                              # paper fibres and soft waves
        light *= 1.0 - 0.08 * ((X - sx) / 470.0) ** 2 - 0.05 * ((Y - 1010.0) / 320.0) ** 2
        glyph = self.pick("paper", 0.55 + 0.35 * fine + 0.9 * (light - 0.9))
        # the flap edges are drawn as fine lines: - _ ' . chosen by where the edge crosses each cell
        for cut, tip, corner in ((cut_t, top_tip, y0), (cut_b, bot_tip, y1)):
            on = inside & ~edge & (cut > 0.04) & (cut < 0.96)
            ey = tip + (corner - tip) * np.abs(X - sx) / (sx - x0)              # where the edge is in this column
            glyph = np.where(on, self.line_at(ey - (Y - CH / 2.0), np.where(X < sx, 1.0, -1.0) * (corner - tip) / (sx - x0)), glyph)
        albedo = PAPER * light[..., None]

        # red and blue airmail stripes round the edge, slanted like real ones
        phase = np.floor((X + Y) / 23.0).astype(np.int32) % 4
        stripes = np.where((phase == 0)[..., None], AIR_RED, np.where((phase == 2)[..., None], AIR_BLUE, PAPER * 1.05))
        albedo = np.where(edge[..., None], stripes * (0.92 + 0.08 * light[..., None]), albedo)
        glyph = np.where(edge, np.where(phase % 2 == 0, self.gi["/"], self.pick("paper", 0.6 + 0.3 * fine)), glyph)

        # the handwritten message: ink soaks into the paper and darkens it
        cover = text_coverage(self.message)
        k = smoothstep(0.08, 0.55, cover)[..., None] * (0.9 + 0.1 * broad[..., None])
        albedo = albedo * (1.0 - k) + INK * k
        glyph = np.where(inside & ~edge & (cover > 0.18), self.pick("ink", cover), glyph)

        # the wax seal: a heart of red wax with rounded edges and a heart stamped into it
        dx, dy = X - sx, Y - sy
        rho = np.hypot(dx, dy)
        wbox = cell_box(sx - 130.0, sy - 125.0, sx + 130.0, sy + 115.0)
        WX, WY = fine_grid(wbox)
        wdx, wdy = WX - sx, WY - sy
        wax_px = np.hypot(wdx, wdy) < heart_radius(np.arctan2(wdy, wdx))
        edge_d = cv2.distanceTransform(wax_px.astype(np.uint8), cv2.DIST_L2, 5)   # pixels to the edge of the wax
        hx, hy = wdx / 50.0, 0.25 - wdy / 45.0
        stamp = ((hx * hx + hy * hy - 1.0) ** 3 - hx * hx * hy ** 3 < 0).astype(np.uint8)
        s_in = cv2.distanceTransform(stamp, cv2.DIST_L2, 5)
        s_out = cv2.distanceTransform(1 - stamp, cv2.DIST_L2, 5)
        height = 16.0 * np.sqrt(1.0 - (1.0 - np.minimum(edge_d / 16.0, 1.0)) ** 2)    # rounded rim, flat top
        height += 5.0 * smoothstep(0.0, 70.0, edge_d)                            # a low dome
        height -= 7.0 * smoothstep(0.0, 6.0, s_in)                               # the stamp is pressed in
        height += 2.2 * np.exp(-((s_out - 3.5) / 3.0) ** 2) * (edge_d > 6)       # wax pushed up round the stamp
        height += 0.6 * tile_noise(rng, *height.shape, 3.0)                      # small ripples in the wax
        height = cv2.GaussianBlur(height.astype(np.float32), (0, 0), 1.2)
        gy_, gx_ = np.gradient(height)
        nz = 1.0 / np.sqrt(gx_ * gx_ + gy_ * gy_ + 1.0)
        nx, ny = -gx_ * nz, -gy_ * nz
        lx, ly, lz = -0.50, -0.62, 0.61                                          # light from the upper left
        diffuse = np.clip(nx * lx + ny * ly + nz * lz, 0.0, 1.0)
        hl = np.array([lx, ly, lz + 1.0]) / np.linalg.norm([lx, ly, lz + 1.0])   # half way to the viewer
        spec = np.clip(nx * hl[0] + ny * hl[1] + nz * hl[2], 0.0, 1.0)
        spec = 0.5 * spec ** 16 + 1.4 * spec ** 80                              # a soft sheen and a sharp glint
        hollow = smoothstep(0.0, 6.0, s_in)                                      # inside the stamp, less light gets in
        shade = (0.08 + 1.05 * diffuse ** 1.3) * (1.0 - 0.40 * hollow)
        w_col = WAX_BASE * shade[..., None] + WAX_SHINE * spec[..., None]
        # the raised wax casts a small shadow on the paper, down and to the right
        drop = cv2.GaussianBlur(np.roll(wax_px.astype(np.float32), (7, 5), axis=(0, 1)), (0, 0), 4.0)
        drop = paste(np.zeros((ROWS, COLS), np.float32), to_cells(drop * ~wax_px, wbox), wbox)
        albedo = albedo * (1.0 - 0.55 * drop[..., None])
        w_cov = to_cells(wax_px.astype(np.float32), wbox)
        w_col = to_cells(w_col * wax_px[..., None], wbox) / np.maximum(w_cov, 1e-3)[..., None]
        wax = paste(np.zeros((ROWS, COLS), bool), w_cov > 0.45, wbox)
        w_col = paste(np.zeros((ROWS, COLS, 3), np.float32), w_col, wbox)
        w_lum = w_col @ np.array([0.30, 0.59, 0.11], np.float32)
        albedo = np.where(wax[..., None], w_col, albedo)
        glyph = np.where(wax, self.pick("wax", np.sqrt(np.clip(w_lum / 0.45, 0.0, 1.0)) + 0.08 * fine), glyph)

        self.letter, self.wax = inside, wax & inside
        self.l_glyph, self.l_albedo = glyph.astype(np.int32), albedo.astype(np.float32)
        self.shine_pos = ((X - x0) / (x1 - x0) + 0.5 * (Y - y0) / (y1 - y0)).astype(np.float32)
        # when each cell appears, catches fire (spreading from the seal, faster upwards) and crumbles
        self.ta = (T_LETTER + 1.15 * ((X - x0) / (x1 - x0) * 0.62 + (Y - y0) / (y1 - y0) * 0.38)
                   + 0.14 * self.rnd[0]).astype(np.float32)
        spread = np.hypot(dx, dy * np.where(dy < 0, 0.55, 1.45)) / 245.0
        ti = T_IGNITE + 0.10 + spread * np.maximum(0.3, 1.0 + 0.28 * burn1) + 0.05 * burn2 + 0.012 * fine
        self.ti = np.where(wax, T_IGNITE + rho / 500.0, ti).astype(np.float32)
        self.tc = (self.ti + RIM + COOL + 0.35 + 0.9 * self.rnd[1]).astype(np.float32)

        # background: twinkling stars and dust that only shows where light falls on it
        self.star = rng.random((ROWS, COLS)) < 0.013 / GS ** 2
        self.star_b = rng.uniform(0.10, 0.55, (ROWS, COLS)).astype(np.float32)
        self.star_sp = rng.uniform(0.6, 2.5, (ROWS, COLS)).astype(np.float32)
        self.star_ph = rng.uniform(0.0, 6.3, (ROWS, COLS)).astype(np.float32)
        self.star_glyph = np.where(self.star_b > 0.47, self.gi["+"],
                                   np.where(self.star_b > 0.3, self.gi["\u00b7"], self.gi["."]))
        self.dust = rng.random((ROWS, COLS)) < 0.35
        self.dust_glyph = np.array([self.gi[g] for g in ".'`\u00b7,"], np.int32)[rng.integers(0, 5, (ROWS, COLS))]
        self.dust_amp = rng.uniform(0.3, 1.0, (ROWS, COLS)).astype(np.float32)
        self.dust_rc = np.nonzero(self.dust)
        # fire simulation grid and two moving noise patterns that break the flames up
        self.tex1 = tile_noise(rng, SR, SC, 1.6 * GS, 3.2 * GS)              # taller than wide: flame tongues
        self.tex2 = tile_noise(rng, SR, SC, 3.5 * GS, 6.5 * GS)
        gy, gx = np.mgrid[0:SR, 0:SC].astype(np.float32)
        self.gx, self.gy = gx, gy

    def _build_rose(self):
        X, Y = self.X, self.Y
        # the flower head, worked out for ROSE_KEYS stages of the bloom (2 x 2 samples per cell)
        bx, by = ROSE_BASE
        box = cell_box(bx - ROSE_SIZE * 1.12, by - ROSE_SIZE * 1.1, bx + ROSE_SIZE * 1.12, by + ROSE_SIZE * 0.95)
        c0, r0, c1, r1 = box
        hw, hh = (c1 - c0) * 2, (r1 - r0) * 2
        self.h_box = box
        masks, shades, glyphs = [], [], []
        for b in np.linspace(0.0, 1.0, ROSE_KEYS):
            sx, sy, near, shade, petal = rose_head(b)
            size = ROSE_SIZE * (0.55 + 0.45 * b)
            fx = (bx + size * sx - c0 * CW) / (CW / 2.0) - 0.5
            fy = (by + size * sy - PAD - r0 * CH) / (CH / 2.0) - 0.5
            sh, pe, ne = splat(fx, fy, near, [shade, petal, near], hw, hh)
            got = ~np.isnan(sh)
            # a dark line where one petal lies over another
            cut = np.zeros((hh, hw), bool)
            for ax in (0, 1):
                a, b2 = np.nan_to_num(pe, nan=-99.0), np.nan_to_num(ne, nan=-9.0)
                gap = np.abs(np.diff(b2, axis=ax))
                jump = ((np.abs(np.diff(a, axis=ax)) > 0) & (gap > 0.05)) | (gap > 0.16)   # one petal over another
                if ax == 0:
                    cut[1:] |= jump & got[1:] & got[:-1]
                else:
                    cut[:, 1:] |= jump & got[:, 1:] & got[:, :-1]
            cov = got.reshape(hh // 2, 2, hw // 2, 2).mean(axis=(1, 3))
            mean = np.nan_to_num(sh).reshape(hh // 2, 2, hw // 2, 2).sum(axis=(1, 3)) / np.maximum(cov * 4.0, 1.0)
            line = cut.reshape(hh // 2, 2, hw // 2, 2).sum(axis=(1, 3)) >= 2
            # which way the petal edge runs in each cell, from the nearness image
            nb = cv2.GaussianBlur(np.nan_to_num(ne, nan=float(np.nanmin(ne)) if got.any() else 0.0), (0, 0), 1.0)
            gyy, gxx = np.gradient(nb)
            gx_c = cv2.resize(gxx / (CW / 2.0), (hw // 2, hh // 2), interpolation=cv2.INTER_AREA)
            gy_c = cv2.resize(gyy / (CH / 2.0), (hw // 2, hh // 2), interpolation=cv2.INTER_AREA)
            ang = np.degrees(np.arctan2(gy_c, gx_c)) + 90.0
            mean = np.where(line, mean * 0.5, mean)
            glyph = np.where(line, self.line[line_index(ang)], self.pick("petal", np.clip(mean / 1.05, 0.0, 1.0)))
            masks.append(cov > 0.45)
            shades.append(np.clip(mean, 0.0, 1.3).astype(np.float32))
            glyphs.append(glyph.astype(np.int32))
        self.h_mask, self.h_shade, self.h_glyph = np.array(masks), np.array(shades), np.array(glyphs)
        head = paste(np.zeros((ROWS, COLS), bool), self.h_mask[-1], box)        # the open rose

        # stem, thorns, leaves and sepals: worked out for every pixel, then averaged into cells
        gbox = cell_box(230.0, ROSE_BASE[1] - 4.0, 870.0, 1700.0)
        FX, FY = fine_grid(gbox)
        f_col = np.zeros(FX.shape + (3,), np.float32)
        f_cov = np.zeros(FX.shape, np.float32)
        f_tr = np.full(FX.shape, 99.0, np.float32)
        lx, ly, lz = -0.50, -0.60, 0.62                                          # light from the upper left
        hx_, hy_, hz_ = np.array([lx, ly, lz + 1.0]) / np.linalg.norm([lx, ly, lz + 1.0])

        def stem_time(u):
            return T_ROSE + 0.55 + 0.95 * u

        def put(sub, m, col, tr):                                               # draw on top of what is there
            ys, xs = sub
            f_cov[ys, xs] = np.where(m, 1.0, f_cov[ys, xs])
            f_col[ys, xs] = np.where(m[..., None], col, f_col[ys, xs])
            f_tr[ys, xs] = np.where(m, tr, f_tr[ys, xs])

        def window(x0, y0, x1, y1):
            gx0, gy0 = FX[0, 0] - 0.5, FY[0, 0] - 0.5
            xs = slice(max(0, int(x0 - gx0)), min(FX.shape[1], int(x1 - gx0)))
            ys = slice(max(0, int(y0 - gy0)), min(FX.shape[0], int(y1 - gy0)))
            return (ys, xs), FX[ys, xs], FY[ys, xs]

        # the stem: a round green stalk, lit on its left side, a little browner lower down
        sub, sx_, sy_ = window(470, ROSE_BASE[1], 610, 1690)
        u, d, ang = curve_field(sx_, sy_, STEM)
        rad = 8.5 - 1.5 * u
        m = np.abs(d) < rad
        across = np.clip(d / rad, -1.0, 1.0)
        t_x, t_y = np.cos(np.radians(ang)), np.sin(np.radians(ang))
        nx, ny = -across * t_y, across * t_x                                     # the stalk is a cylinder
        nz = np.sqrt(1.0 - across * across)
        light = np.clip(nx * lx + ny * ly + nz * lz, 0.0, 1.0)
        spec = np.clip(nx * hx_ + ny * hy_ + nz * hz_, 0.0, 1.0) ** 30
        col = LEAF(0.22 + 0.55 * light)[...] * (1.0 - 0.25 * u)[..., None] + THORN * (0.35 * u)[..., None] + WHITE * (0.25 * spec)[..., None]
        put(sub, m, col, stem_time(u))

        # thorns: broad at the base, hooked downwards, red-brown and shiny
        for uu, side in THORNS:
            (px, py), (tx2, ty2) = bezier(STEM, uu)
            n = math.hypot(tx2, ty2)
            ax_, ay_ = tx2 / n, ty2 / n                                          # along the stem (downwards)
            ox_, oy_ = -ay_ * side, ax_ * side                                   # outwards
            sub, sx_, sy_ = window(px - 40, py - 40, px + 40, py + 40)
            o = (sx_ - px) * ox_ + (sy_ - py) * oy_ - 7.0
            a = (sx_ - px) * ax_ + (sy_ - py) * ay_
            L = 20.0
            curve = 0.45 * L * (np.clip(o, 0, L) / L) ** 2                       # the point bends down
            wid = 8.0 * np.clip(1.0 - o / L, 0.0, 1.0) ** 1.3
            m = (o > -3.0) & (o < L) & (np.abs(a - curve) < wid)
            shade = 0.45 + 0.55 * np.clip(-(a - curve) / np.maximum(wid, 1.0), -1.0, 1.0) * -0.5 + 0.25
            col = THORN * shade[..., None] + WHITE * (0.4 * np.exp(-((a - curve + 0.4 * wid) / 2.0) ** 2))[..., None] * (o > 2)[..., None]
            put(sub, m, col, stem_time(uu) + 0.05)

        # leaves and sepals: serrated, folded a little along the middle vein, one half catching the light
        for parts, start, grow in ((LEAVES, None, 0.6), (SEPALS, T_ROSE + 0.25, 0.4)):
            for base, bend, tip, half in parts:
                xs_ = [base[0], bend[0], tip[0]]
                ys_ = [base[1], bend[1], tip[1]]
                sub, lx_, ly_ = window(min(xs_) - half - 8, min(ys_) - half - 8, max(xs_) + half + 8, max(ys_) + half + 8)
                u, d, ang = curve_field(lx_, ly_, (base, bend, tip))
                uc = np.clip(u, 0.0, 1.0)
                teeth = 1.0 - (0.10 if start is None else 0.0) * ((uc * 13.0) % 1.0)
                width = half * np.clip(np.sin(np.pi * uc ** 0.85), 0.0, 1.0) ** 0.8 * teeth
                m = (np.abs(d) < width) & (u > 0.004) & (u < 0.996)
                rel = d / np.maximum(width, 1.0)
                t_x, t_y = np.cos(np.radians(ang)), np.sin(np.radians(ang))
                fold = 0.45 * np.sign(d) * np.clip(np.abs(rel) * 3.0, 0.0, 1.0)  # the two halves tilt apart
                nx = -t_y * fold
                ny = t_x * fold
                nz = np.sqrt(np.clip(1.0 - nx * nx - ny * ny, 0.0, 1.0))
                light = np.clip(nx * lx + ny * ly + nz * lz, 0.0, 1.0)
                spec = np.clip(nx * hx_ + ny * hy_ + nz * hz_, 0.0, 1.0) ** 24
                vein = np.exp(-(((uc * 7.0 - np.abs(rel) * 0.7) % 1.0 - 0.5) * 2.0 / 0.12) ** 2) * (np.abs(rel) < 0.85)
                mid = np.exp(-(d / 2.2) ** 2)
                b = 0.18 + 0.62 * light + 0.18 * vein + 0.25 * mid
                col = LEAF(np.clip(b, 0.0, 1.0)) + WHITE * (0.30 * spec)[..., None]
                bronze = 0.55 * smoothstep(0.72, 1.0, np.abs(rel)) * (1.0 if start is None else 0.3)
                col = col * (1.0 - bronze[..., None]) + LEAF_EDGE * bronze[..., None]
                if start is None:
                    t0 = stem_time(float(curve_field(np.array([[base[0]]], np.float32), np.array([[base[1]]], np.float32), STEM)[0][0, 0])) + 0.1
                else:
                    t0 = start
                put(sub, m, col, t0 + grow * uc)

        cov = to_cells(f_cov, gbox)
        g_col = to_cells(f_col * f_cov[..., None], gbox) / np.maximum(cov, 1e-3)[..., None]
        g_tr = to_cells(np.where(f_cov > 0, f_tr, 0.0) * f_cov, gbox) / np.maximum(cov, 1e-3)
        g_mask = paste(np.zeros((ROWS, COLS), bool), cov > 0.35, gbox)
        g_col = paste(np.zeros((ROWS, COLS, 3), np.float32), g_col, gbox)
        g_tr = paste(np.full((ROWS, COLS), 99.0, np.float32), g_tr, gbox)
        g_cov = paste(np.zeros((ROWS, COLS), np.float32), cov, gbox)
        lum = g_col @ np.array([0.30, 0.59, 0.11], np.float32)
        g_glyph = np.where(g_cov < 0.7, self.pick("ash", g_cov), self.pick("leaf", np.clip(lum / 0.30, 0.0, 1.0)))
        # fine lines on top: the stem's middle, the leaves' middle veins
        u, d, ang = curve_field(X, Y, STEM)
        g_glyph = np.where(g_mask & (np.abs(d) < CW * 0.5), self.gi["|"], g_glyph)
        for base, bend, tip, half in LEAVES + SEPALS:
            u, d, ang = curve_field(X, Y, (base, bend, tip))
            t_x, t_y = np.cos(np.radians(ang)), np.sin(np.radians(ang))
            off = CH / 2.0 - d * t_x
            on = g_mask & (np.abs(d * t_x) < CH / 2.0) & (u > 0.03) & (u < 0.9) & (np.abs(d) < half * 0.4)
            g_glyph = np.where(on, self.line_at(off, -t_y / np.where(np.abs(t_x) < 1e-3, 1e-3, t_x)), g_glyph)

        self.r_head = head
        self.r_mask = head | g_mask                             # the whole rose once it is open
        self.r_glyph, self.r_col, self.r_tr = g_glyph.astype(np.int32), g_col.astype(np.float32), g_tr.astype(np.float32)
        self.g_mask = g_mask
        self.r_edge = border(head) & head                       # outline of the open flower, lit from behind later
        # the message in the sky: each cell is written by a spark that flies up out of the rose
        rng = np.random.default_rng(self.seed + 7)
        cover = text_coverage(self.message, at=WORDS, box=(820, 125), size=140)
        self.w_cells = np.argwhere(cover > 0.22)
        wc = self.w_cells
        self.w_cover = cover[wc[:, 0], wc[:, 1]].astype(np.float32)
        if len(wc):
            xn = (wc[:, 1] - wc[:, 1].min()) / max(1, np.ptp(wc[:, 1]))
            self.w_t = (T_WORDS + 0.5 + 1.7 * xn + 0.18 * rng.random(len(wc))).astype(np.float32)   # left to right
            src = np.argwhere(head)
            pick = src[rng.integers(0, len(src), len(wc))]
            self.w_from = np.stack([X[pick[:, 0], pick[:, 1]], Y[pick[:, 0], pick[:, 1]]], 1).astype(np.float32)
            self.w_to = np.stack([X[wc[:, 0], wc[:, 1]], Y[wc[:, 0], wc[:, 1]]], 1).astype(np.float32)
            self.w_fly = rng.uniform(0.7, 1.1, len(wc)).astype(np.float32)        # seconds in the air
            self.w_bend = rng.normal(0.0, 70.0, len(wc)).astype(np.float32)      # each flies a slightly curved path
        self.edge_cells = np.argwhere(self.r_edge)
        self.petal_from = np.argwhere(self.r_edge & (Y > ROSE_BASE[1]))

    def bloom(self, t):
        """How open the rose is at time t: 0 = bud .. 1 = full bloom."""
        return float(smoothstep(T_ROSE + 0.15, T_ROSE + 2.7, t))

    def head_now(self, t):
        """The flower head at time t in its box: mask, brightness and characters (blended between stages)."""
        k = self.bloom(t) * (ROSE_KEYS - 1)
        k0 = int(k)
        k1 = min(k0 + 1, ROSE_KEYS - 1)
        f = k - k0
        near = k1 if f >= 0.5 else k0
        both = self.h_mask[k0] & self.h_mask[k1]
        shade = np.where(both, self.h_shade[k0] * (1.0 - f) + self.h_shade[k1] * f, self.h_shade[near])
        return self.h_mask[near], shade, self.h_glyph[near]

    def _build_screen(self, rng):
        s = self.s
        self.lh, self.lw = self.h // 2, self.w // 2         # light is drawn at half resolution
        ly, lx = np.mgrid[0:self.lh, 0:self.lw].astype(np.float32)
        self.lx, self.ly = (lx + 0.5) * 2.0 / s, PAD + (ly + 0.5) * 2.0 / s
        r = np.hypot((self.lx - 540.0) / 700.0, (self.ly - 900.0) / 1100.0)
        self.bg = (rgb(0.010, 0.011, 0.028) * np.exp(-1.6 * r * r)[..., None] + rgb(0.0015, 0.0015, 0.004))

        def vignette(x, y):
            v = np.hypot((x - 540.0) / 600.0, (y - 960.0) / 1050.0)
            return (1.0 - 0.45 * smoothstep(0.55, 1.25, v))[..., None]

        self.vig_light = np.repeat(vignette(self.lx, self.ly), 3, axis=2)
        self.vig_cell = vignette(self.X, self.Y)
        self.qh, self.qw = self.h // 4, self.w // 4         # rays, bloom and heat shimmer: quarter resolution
        qy, qx = np.mgrid[0:self.qh, 0:self.qw].astype(np.float32)
        self.q_px, self.q_py = (qx + 0.5) * 4.0 - 0.5, (qy + 0.5) * 4.0 - 0.5      # in screen pixels
        self.q_x, self.q_y = (qx + 0.5) * 4.0 / s, PAD + (qy + 0.5) * 4.0 / s      # in layout pixels
        self.q_dx, self.q_dy = self.q_x - HEAD[0], self.q_y - (HEAD[1] - 20.0)
        self.q_r, self.q_a = np.hypot(self.q_dx, self.q_dy), np.arctan2(self.q_dy, self.q_dx)
        m = cv2.resize(self.r_mask.astype(np.float32), (self.qw, self.qh), interpolation=cv2.INTER_NEAREST)
        self.q_rose = cv2.GaussianBlur(m, (0, 0), 0.8)[..., None]          # the rose blocks the rays behind it
        r = self.q_r                                                      # the parts of the rays that never change
        self.ray_fade = (np.exp(-r / 560.0) * smoothstep(40.0, 220.0, r)).astype(np.float32)
        self.ray_core = np.exp(-(r / 150.0) ** 1.6).astype(np.float32)
        self.ray_flare = (np.exp(-(self.q_dy / 10.0) ** 2) * np.exp(-np.abs(self.q_dx) / 650.0)
                          + 0.35 * np.exp(-(self.q_dx / 9.0) ** 2) * np.exp(-np.abs(self.q_dy) / 420.0)).astype(np.float32)
        self.ray_bin = ((self.q_a + np.pi) / (2.0 * np.pi) * 4095.0).astype(np.int32)
        self.ray_open = (1.0 - self.q_rose).astype(np.float32)
        # turning light into screen colours: a film-like curve, looked up from a table
        self.enc = 255.0 / math.log1p(TONE_E * 16.0)
        x = np.expm1(np.arange(256) / self.enc) / TONE_E
        aces = x * (2.51 * x + 0.03) / (x * (2.43 * x + 0.59) + 0.14)
        self.tone = np.clip(np.sqrt(np.clip(aces, 0.0, 1.0)) * 255.0 + 0.5, 0, 255).astype(np.uint8)
        g = rng.standard_normal((self.vh + 64, self.w + 64, 1)).astype(np.float32) / self.enc
        self.grain = np.repeat(g, 3, axis=2)                 # film grain
        self.seal_d = np.hypot(self.q_x - SEAL[0], self.q_y - SEAL[1])
        # big images are made once and reused for every frame
        self.atlas_rows = self.atlas.reshape(-1, self.cw)                    # each pixel row of each character
        self.row_of_cell = np.arange(self.ch, dtype=np.int32)[None, :, None]
        self.buf_glyph = np.empty((self.r1 - self.r0, self.ch, COLS, self.cw), np.float32)
        self.buf_img, self.buf_up, self.buf_a3 = (np.empty((self.vh, self.w, 3), np.float32) for _ in range(3))
        self.buf_u8, self.buf_tone = (np.empty((self.vh, self.w, 3), np.uint8) for _ in range(2))
        self.out = np.zeros((self.vh + 2 * self.pad, self.w, 3), np.uint8)

    def _rows(self, a):
        """The part of a full-height (lower resolution) image that lies in the drawn rows."""
        n = a.shape[0] / ROWS
        return a[round(self.r0 * n):round(self.r1 * n)]

    # ---------------------------------------------------------- running
    def reset(self):
        self.t = 0.0
        self.frame_no = 0
        self.rng = np.random.default_rng(self.seed + 1)
        self.H = np.zeros((SR, SC), np.float32)             # heat of the fire
        self.S = np.zeros((SR, SC), np.float32)             # smoke
        self.parts = {k: np.zeros((0, 9), np.float32) for k in KINDS}
        self.next_petal = T_RAYS + 1.6

    def _spawn(self, kind, x, y, vx, vy, life, heat, lift):
        p = np.zeros((len(x), 9), np.float32)
        p[:, PX], p[:, PY], p[:, PVX], p[:, PVY] = x, y, vx, vy
        p[:, PLIFE], p[:, PHEAT], p[:, PLIFT] = life, heat, lift
        p[:, PSEED] = self.rng.random(len(x)) * 100.0
        self.parts[kind] = np.concatenate([self.parts[kind], p])

    def step(self, dt):
        """Move everything forward by dt seconds."""
        t0, t = self.t, self.t + dt
        self.t = t
        rng, L = self.rng, self.letter
        burning = L & (t >= self.ti) & (t < self.ti + RIM)
        smoulder = L & (t >= self.ti + RIM) & (t < self.tc)
        src = np.where(burning, 1.0, 0.0)
        src = np.maximum(src, np.where(smoulder, 0.5 * (1.0 - np.clip((t - self.ti - RIM) / COOL, 0, 1)) ** 1.5, 0.0))
        if T_IGNITE <= t < T_IGNITE + 0.7:
            src = np.where(self.wax, 1.25, src)
        if T_ROSE <= t < T_ROSE + 0.9:                      # the bud forms inside the fire
            c0, r0, c1, r1 = self.h_box
            hm, _, _ = self.head_now(t)
            src[r0:r1, c0:c1] = np.maximum(src[r0:r1, c0:c1], hm * 0.7 * (1.0 - (t - T_ROSE) / 0.9))
        self._fire(dt, t, src.astype(np.float32))

        if t0 < T_STRIKE <= t:                              # the match is struck just out of view
            n = 70
            a = rng.uniform(-2.9, -1.9, n)                  # sparks fly up and to the left, into the picture
            sp = rng.uniform(250.0, 900.0, n)
            self._spawn("spark", STRIKE[0] + rng.normal(0, 6, n), STRIKE[1] + rng.normal(0, 4, n),
                        np.cos(a) * sp, np.sin(a) * sp, rng.uniform(0.25, 0.8, n), rng.uniform(1.0, 1.3, n),
                        np.full(n, 500.0))
        if T_STRIKE <= t < T_STRIKE + 0.35:                 # its puff of smoke drifts in
            self._smoke_at(STRIKE[0] - 40.0, STRIKE[1] - 30.0, 34.0, 2.2 * dt / 0.35)
        mt = self._match(t)
        if mt and T_OUT <= t and mt["ember"] > 0.05:        # a thin thread of smoke from the put-out match
            self._smoke_at(mt["x"], mt["y"] - 8.0, 5.0, 3.5 * dt * mt["ember"])
        if t0 < T_IGNITE <= t:                              # the seal bursts
            n = 280
            a = rng.uniform(0.0, 2.0 * np.pi, n)
            sp = rng.uniform(250.0, 980.0, n) * np.sqrt(rng.uniform(0.25, 1.0, n))
            self._spawn("spark", SEAL[0] + rng.normal(0, 8, n), SEAL[1] + rng.normal(0, 6, n),
                        np.cos(a) * sp, np.sin(a) * sp * 0.8 - 120.0,
                        rng.uniform(0.5, 1.5, n), rng.uniform(1.0, 1.3, n), np.full(n, 420.0))
        n = int(burning.sum())
        if n:                                               # sparks and embers fly off the burning edge
            ys, xs = np.nonzero(burning)
            for kind, rate in (("spark", 0.9 / GS ** 2), ("ember", 0.12 / GS ** 2)):
                k = rng.poisson(n * rate * dt)
                if not k:
                    continue
                i = rng.integers(0, n, k)
                x = self.X[ys[i], xs[i]] + rng.uniform(-4, 4, k)
                y = self.Y[ys[i], xs[i]] + rng.uniform(-8, 8, k)
                if kind == "spark":
                    self._spawn(kind, x, y, rng.normal(0, 70, k), -rng.uniform(150, 520, k),
                                rng.uniform(0.35, 1.0, k), rng.uniform(0.85, 1.15, k), -rng.uniform(150, 420, k))
                else:
                    self._spawn(kind, x, y, rng.normal(0, 30, k), -rng.uniform(60, 170, k),
                                rng.uniform(1.2, 2.6, k), rng.uniform(0.6, 0.8, k), -rng.uniform(20, 60, k))
        crumble = L & (t0 < self.tc) & (t >= self.tc) & (self.rnd[2] < 0.55 / GS ** 2)
        if crumble.any():                                   # black char breaks up into floating ash
            ys, xs = np.nonzero(crumble)
            k = len(ys)
            self._spawn("ash", self.X[ys, xs], self.Y[ys, xs], rng.normal(0, 25, k), -rng.uniform(30, 110, k),
                        rng.uniform(1.2, 2.8, k), np.zeros(k), -rng.uniform(10, 40, k))
        born = self.g_mask & (t0 < self.r_tr) & (t >= self.r_tr) & (self.rnd[0] < 0.2 / GS ** 2)
        if T_ROSE <= t < T_ROSE + 1.2:                      # white-hot sparks while the rose forms
            c0, r0, c1, r1 = self.h_box
            hm, _, _ = self.head_now(t)
            born[r0:r1, c0:c1] |= hm & (self.rnd[0][r0:r1, c0:c1] < 0.9 * dt)
        if born.any():
            ys, xs = np.nonzero(born)
            k = len(ys)
            self._spawn("spark", self.X[ys, xs], self.Y[ys, xs], rng.normal(0, 60, k), -rng.uniform(80, 300, k),
                        rng.uniform(0.3, 0.8, k), rng.uniform(1.0, 1.25, k), -rng.uniform(80, 200, k))
        if t >= T_RAYS:                                     # the calm ending
            k = rng.poisson(7.0 * dt)
            if k:
                self._spawn("ember", rng.uniform(180, 900, k), rng.uniform(1250, 1850, k), rng.normal(0, 12, k),
                            -rng.uniform(25, 75, k), rng.uniform(3.0, 6.0, k), rng.uniform(0.5, 0.7, k),
                            -rng.uniform(2, 8, k))
            k = rng.poisson(6.0 * dt)
            if k and len(self.edge_cells):
                rc = self.edge_cells[rng.integers(0, len(self.edge_cells), k)]
                self._spawn("glint", self.X[rc[:, 0], rc[:, 1]] + rng.normal(0, 25, k),
                            self.Y[rc[:, 0], rc[:, 1]] + rng.normal(0, 25, k), np.zeros(k), np.zeros(k),
                            rng.uniform(0.6, 1.0, k), np.zeros(k), np.zeros(k))
            if t >= self.next_petal and len(self.petal_from):
                self.next_petal = t + rng.uniform(1.3, 2.2)
                r, c = self.petal_from[rng.integers(len(self.petal_from))]
                self._spawn("petal", [self.X[r, c]], [self.Y[r, c]], [rng.normal(0, 20)], [rng.uniform(5, 30)],
                            [9.0], [0.0], [140.0])
        self._move(dt, t)
        self.frame_no += 1

    def _fire(self, dt, t, src):
        """Flames: heat rises, sways, cools down in uneven patches and turns into smoke."""
        gx, gy = self.gx, self.gy
        n1 = scroll(self.tex1, t * 15.0 * GS, 0.0)
        n2 = scroll(self.tex2, t * 24.0 * GS, t * 4.0 * GS)
        turb = 0.6 * n1 + 0.4 * n2
        H, S = self.H, self.S
        vy = -(16.0 + 38.0 * np.minimum(H, 1.2)) * GS                         # cells per second, upwards
        vx = (7.0 * np.sin(gy * 0.19 / GS + t * 2.1 + 2.0 * np.sin(gx * 0.11 / GS - t * 0.8)) + 6.0 * n2) * GS
        H = cv2.remap(H, gx - vx * dt, gy - vy * dt, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        S = cv2.remap(S, gx - vx * dt * 0.6, gy - vy * dt * 0.45, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        cool = np.maximum(1.25 * (1.0 + 0.85 * turb), 0.2)
        S += np.minimum(H, 0.6) * cool * dt * 0.6
        H = np.maximum(H - cool * dt, 0.0)
        S *= 1.0 - 0.45 * dt
        if src.any():
            H = np.maximum(H, np.repeat(src, 2, axis=0) * (0.82 + 0.3 * turb))
        self.H, self.S = H.astype(np.float32), S.astype(np.float32)

    def _smoke_at(self, x, y, radius, amount):
        """Add smoke round a point (layout pixels) to the fire simulation."""
        c, r = x / CW, (y - PAD) / CW                       # the simulation cells are CW pixels square
        rad = max(radius / CW, 0.8)
        c0, c1 = int(max(0, c - 3 * rad)), int(min(SC, c + 3 * rad + 1))
        r0, r1 = int(max(0, r - 3 * rad)), int(min(SR, r + 3 * rad + 1))
        if c1 > c0 and r1 > r0:
            gy, gx = np.mgrid[r0:r1, c0:c1]
            self.S[r0:r1, c0:c1] += amount * np.exp(-((gx + 0.5 - c) ** 2 + (gy + 0.5 - r) ** 2) / (2.0 * rad * rad))

    def _move(self, dt, t):
        for kind, p in self.parts.items():
            if not len(p):
                continue
            drag, sway, flutter, most = KINDS[kind]
            f = math.exp(-drag * dt)
            p[:, PVX] *= f
            p[:, PVY] *= f
            p[:, PVY] += p[:, PLIFT] * dt                                  # gravity, or hot air lifting it
            p[:, PVX] += np.sin(p[:, PY] * 0.013 + t * 2.7 + p[:, PSEED]) * sway * dt
            p[:, PVX] += np.sin(p[:, PAGE] * 5.0 + p[:, PSEED]) * flutter * dt
            p[:, PX] += p[:, PVX] * dt
            p[:, PY] += p[:, PVY] * dt
            p[:, PAGE] += dt
            keep = ((p[:, PAGE] < p[:, PLIFE]) & (p[:, PX] > -60) & (p[:, PX] < 1140)
                    & (p[:, PY] > -120) & (p[:, PY] < 2000))
            self.parts[kind] = p[keep][-most:]

    def _match(self, t):
        """The match at time t (None while it is out of view): where its head is, how fast it moves,
        how strong the flame is, how much the head still glows and how far the stick has burnt."""
        if t < T_MATCH or t > T_IGNITE + 1.5:
            return None

        def where(t):
            if t < T_TOUCH:
                u = float(smoothstep(T_MATCH, T_TOUCH, t))
            else:
                u = 1.0 - float(smoothstep(T_IGNITE + 0.05, T_IGNITE + 1.45, t))
            (x, y), _ = bezier(MATCH_PATH, u)
            return x, y

        x, y = where(t)
        x2, y2 = where(t + 0.02)
        hand = 1.0 if T_TOUCH <= t < T_IGNITE else 0.4                    # a slightly shaking hand
        x += hand * (2.0 * math.sin(t * 23.0) + 1.2 * math.sin(t * 37.0))
        y += hand * 1.5 * math.sin(t * 19.0 + 1.0)
        shake = float(smoothstep(T_OUT - 0.3, T_OUT - 0.2, t) * smoothstep(T_OUT + 0.15, T_OUT, t))
        wag = 16.0 * shake * math.sin((t - T_OUT) * 60.0)                  # shaken to put it out
        x += wag
        y -= 0.6 * wag
        vx = (x2 - x) / 0.02 + 16.0 * shake * 60.0 * math.cos((t - T_OUT) * 60.0)
        flare = 1.0 + 1.5 * math.exp(-(t - T_STRIKE) / 0.22)                # the head flares when struck
        flame = flare * (1.0 - float(smoothstep(T_OUT - 0.12, T_OUT + 0.02, t)))
        ember = 1.0 - float(smoothstep(T_OUT, T_OUT + 0.9, t))              # the head glows a little longer
        char = 9.0 + 24.0 * float(smoothstep(T_STRIKE, T_OUT, t))          # black, burnt part of the stick
        return {"x": float(x), "y": float(y), "vx": float(vx), "flame": flame, "ember": ember, "char": char}

    @staticmethod
    def _flame(x, y, m, t):
        """The match flame at layout point(s) x, y: brightness, how hot (white in the middle, orange at
        the tip) and the faint blue round its bottom."""
        f = m["flame"]
        ln = 90.0 * f ** 0.6 * (1.0 + 0.10 * math.sin(t * 13.0) + 0.06 * math.sin(t * 31.0 + 1.0)
                                + 0.04 * math.sin(t * 57.0 + 2.0))
        v = (m["y"] + 10.0 - y) / max(ln, 1.0)                                 # 0 at the head, 1 at the tip
        vc = np.clip(v, 0.0, 1.0)
        lean = (6.0 * math.sin(t * 7.3) + 3.0 * math.sin(t * 17.0)) * vc * vc - m["vx"] * 0.035 * vc ** 1.5
        width = (6.5 + 19.0 * np.sqrt(vc) * (1.0 - vc) ** 0.85) * max(f, 0.05) ** 0.35
        r = (x - m["x"] - lean) / width
        inside = (v > -0.1) & (v < 1.0)
        bright = np.where(inside, np.exp(-r * r) * (1.0 - 0.6 * vc) * smoothstep(-0.1, 0.12, v), 0.0)
        bright *= 1.0 - 0.5 * np.exp(-((v - 0.09) / 0.08) ** 2 - (r / 0.5) ** 2)   # the darker zone just above the head
        temp = 0.98 - 0.45 * vc - 0.22 * np.minimum(r * r, 1.0)
        blue = np.where(inside, np.exp(-((v - 0.03) / 0.10) ** 2 - (r / 1.2) ** 2), 0.0)
        return bright * min(f, 1.8), temp, blue * min(f, 1.0)

    def _rays(self, t):
        """Light rays from behind the rose (quarter resolution), or None before they start."""
        k = float(smoothstep(T_RAYS, T_RAYS + 1.4, t))
        if k <= 0.0:
            return None
        a = np.linspace(-np.pi, np.pi, 4096, dtype=np.float32)
        spin = 0.05 * (t - T_RAYS)
        table = ((0.5 + 0.5 * np.cos(7.0 * a + 0.4 + spin)) ** 8
                 + 0.7 * (0.5 + 0.5 * np.cos(11.0 * a + 2.1 - 1.3 * spin)) ** 10
                 + 0.5 * (0.5 + 0.5 * np.cos(17.0 * a + 4.0 + 0.7 * spin)) ** 12)
        beams = table[self.ray_bin] * self.ray_fade
        if t < T_RAYS + 1.6:                                # the beams reach out at the start
            reach = 1900.0 * float(smoothstep(T_RAYS, T_RAYS + 1.6, t))
            beams *= smoothstep(reach + 1.0, reach - 300.0, self.q_r)
        core = self.ray_core * (0.5 + 1.2 * math.exp(-(t - T_RAYS) / 0.3))
        out = beams[..., None] * (RAY_BEAM * 0.22) + core[..., None] * RAY_CORE + self.ray_flare[..., None] * (RAY_STREAK * 0.4)
        out *= k * (1.0 + 0.08 * math.sin(t * 2.0)) * self.ray_open
        return out.astype(np.float32)

    # ---------------------------------------------------------- drawing
    def render(self):
        """The current frame as an RGB image (uint8). The same array is reused by the next call."""
        t, X, Y, rnd = self.t, self.X, self.Y, self.rnd
        G = np.zeros((ROWS, COLS), np.int32)                # character in each cell
        C = np.zeros((ROWS, COLS, 3), np.float32)           # its colour (linear light)
        heat = 0.5 * (self.H[0::2] + self.H[1::2])
        smoke = 0.5 * (self.S[0::2] + self.S[1::2])
        tick = math.floor(t * 15.0)                         # flickering characters change 15 times a second
        flick = np.abs(np.modf(np.sin(rnd[0] * 91.7 + tick * 12.9898) * 43758.547)[0])

        # light falling on solid things: soft ambient light, the fire, the match, the flash
        fire_light = cv2.GaussianBlur(heat, (0, 0), 3.0 * GS, sigmaY=1.6 * GS) * 2.2
        lit = AMBIENT + fire_light[..., None] * FIRE_TINT
        mt = self._match(t)
        if mt:
            d2 = ((X - mt["x"]) ** 2 + (Y - mt["y"] + 40.0) ** 2) / 170.0 ** 2
            glow = 2.0 * min(mt["flame"], 2.0) * (0.92 + 0.08 * math.sin(t * 29.0)) + 0.15 * mt["ember"]
            lit = lit + (glow / (1.0 + d2))[..., None] * FLAME_TINT
        strike = 4.0 * math.exp(-(t - T_STRIKE) / 0.10) if t >= T_STRIKE else 0.0
        if strike > 0.01:                                   # the flash of the match being struck
            d2 = ((X - STRIKE[0]) ** 2 + (Y - STRIKE[1]) ** 2) / 260.0 ** 2
            lit = lit + (strike / (1.0 + d2))[..., None] * STRIKE_TINT
        flash = 5.0 * math.exp(-(t - T_IGNITE) / 0.16) if t >= T_IGNITE else 0.0
        if flash > 0.01:
            d2 = ((X - SEAL[0]) ** 2 + (Y - SEAL[1]) ** 2) / 200.0 ** 2
            lit = lit + (flash / (1.0 + d2))[..., None] * FLAME_TINT
        rays = self._rays(t)
        ray_k = float(smoothstep(T_RAYS, T_RAYS + 1.4, t))

        # far away: stars, and dust floating in the light
        m = self.star
        sb = self.star_b[m] * (0.7 + 0.3 * np.sin(t * self.star_sp[m] + self.star_ph[m])) * float(smoothstep(0, 1.2, t))
        G[m], C[m] = self.star_glyph[m], STAR * sb[:, None]
        if rays is not None or fire_light.max() > 0.05:
            dr, dc = self.dust_rc                             # only the dust cells are looked at
            dl = fire_light[dr, dc][:, None] * FIRE_TINT * 0.35
            if rays is not None:
                rays_cells = cv2.resize(self._rows(rays), (COLS, self.r1 - self.r0), interpolation=cv2.INTER_AREA)
                inview = (dr >= self.r0) & (dr < self.r1)
                dl[inview] += rays_cells[dr[inview] - self.r0, dc[inview]] * 0.55
            dl *= self.dust_amp[dr, dc][:, None]
            ok = dl.max(-1) > 0.03
            G[dr[ok], dc[ok]], C[dr[ok], dc[ok]] = self.dust_glyph[dr[ok], dc[ok]], dl[ok]

        # smoke, ash and flames (only the cells that show them are worked out)
        m = smoke > 0.04
        if m.any():
            sm = np.minimum(smoke[m], 1.2)
            G[m] = self.pick("smoke", sm)
            C[m] = (SMOKE + fire_light[m][:, None] * FIRE_TINT * 0.05) * sm[:, None]
        p = self.parts["ash"]
        if len(p):
            r, c = ((p[:, PY] - PAD) // CH).astype(np.int32), (p[:, PX] // CW).astype(np.int32)
            ok = (r >= 0) & (r < ROWS) & (c >= 0) & (c < COLS)
            r, c, p = r[ok], c[ok], p[ok]
            fade = 1.0 - p[:, PAGE] / p[:, PLIFE]
            ash = self.pal["ash"]
            G[r, c] = ash[(p[:, PSEED] + p[:, PAGE] * 7.0).astype(np.int32) % len(ash)]
            C[r, c] = (CHAR * 3.0 * fade[:, None] * lit[r, c]
                       + FIRE(0.45 * np.clip(1.0 - p[:, PAGE] / 0.5, 0.0, 1.0)))
        m = heat > 0.05
        if m.any():
            hv = np.minimum(heat[m], 1.2)
            G[m] = self.pick("fire", np.minimum(hv, 1.0) ** 0.75 + 0.15 * (flick[m] - 0.5))
            C[m] = FIRE(hv * 0.78) * 0.7

        # the letter: paper, scorching, the glowing edge, black char
        L = self.letter & (t >= self.ta) & (t < self.tc)
        if L.any():
            pre = self.ti - t
            front_fire = heat > 0.38 + 0.15 * flick          # strong flames are in front of the paper
            paper = L & (pre > 0) & ~front_fire
            if paper.any():
                ap, fk, lp = t - self.ta[paper], flick[paper], lit[paper]
                k = np.clip(1.0 - pre[paper] / SCORCH, 0.0, 1.0)   # 0 = untouched, 1 = about to burn
                col = self.l_albedo[paper] * lp * (smoothstep(0.0, 0.3, ap) * (1.0 - k) ** 1.6)[:, None]
                col += SCORCHED * lp * (0.6 * np.sin(np.pi * k))[:, None]
                glow = smoothstep(0.55, 1.0, k)
                col += FIRE(0.55 * glow) * glow[:, None]
                col += WHITE * (3.2 * np.clip(1.0 - ap / 0.22, 0.0, 1.0) ** 2)[:, None]    # arrival sparkle
                if T_SHINE <= t < T_SHINE + 1.1:
                    c0 = -0.3 + 2.0 * (t - T_SHINE) / 1.1
                    col += WHITE * (0.55 * np.exp(-((self.shine_pos[paper] - c0) / 0.07) ** 2))[:, None]
                glyph = np.where(ap < 0.12, self.pick("flicker", fk), self.l_glyph[paper])
                if T_TOUCH <= t < T_IGNITE + 0.2:            # the wax glows and bubbles under the flame
                    hk = float(smoothstep(T_TOUCH, T_IGNITE, t))
                    wx = self.wax[paper]
                    col[wx] += FIRE(0.35 + 0.35 * hk + 0.15 * fk[wx]) * hk * hk
                    bubble = wx & (fk > 1.0 - 0.35 * hk)
                    glyph[bubble] = self.pick("wax", fk[bubble])
                G[paper], C[paper] = glyph, col
            char = L & (t >= self.ti + RIM) & ~front_fire
            if char.any():
                ti, r1, fk = self.ti[char], rnd[1][char], flick[char]
                cool = np.clip((t - ti - RIM) / COOL, 0.0, 1.0)            # 0 just burnt .. 1 cold and black
                ca = np.clip((t - ti - RIM) / (self.tc[char] - ti - RIM), 0.0, 1.0)
                glow = (1.0 - cool) ** 1.6 * (0.85 + 0.3 * fk)              # burnt paper still glowing
                ember = (rnd[2][char] < 0.30) * (1.0 - ca) * (0.55 + 0.45 * np.sin(t * 9.0 + r1 * 40.0)) * cool
                G[char] = np.where(glow > 0.25, self.pick("ember", 0.4 * glow + 0.3 * fk), self.pick("ash", r1))
                C[char] = (CHAR * lit[char] * (1.5 - 0.7 * ca)[:, None] + FIRE(0.25 + 0.38 * glow) * (1.3 * glow)[:, None]
                           + FIRE(0.30 + 0.15 * ember) * ember[:, None])
            burn = L & (pre <= 0) & (t < self.ti + RIM)
            if burn.any():                                  # the thin, bright burning edge
                G[burn] = self.pick("ember", 0.6 + 0.4 * flick[burn])
                C[burn] = FIRE(0.74 + 0.18 * flick[burn]) * 1.1

        # smoke drifts in front of everything solid, like a thin grey veil
        vr, vc = np.nonzero(smoke > 0.03)
        if len(vr):
            ok = C[vr, vc].max(-1) > 0.02
            vr, vc = vr[ok], vc[ok]
            a = np.minimum(smoke[vr, vc] * 0.5, 0.6)[:, None]
            C[vr, vc] = C[vr, vc] * (1.0 - a) + (SMOKE_LIT * lit[vr, vc] + fire_light[vr, vc][:, None] * FIRE_TINT * 0.08) * a

        # the rose: each part appears white-hot and cools to its colour
        ra = t - self.r_tr
        m = self.g_mask & (ra >= 0)
        if m.any():
            a = ra[m]
            col = (self.r_col[m] * lit[m] * smoothstep(0.05, 0.85, a)[:, None]
                   + FIRE(np.clip(1.05 - a * 1.25, 0.0, 1.1)) * (1.3 * (1.0 - smoothstep(0.3, 1.2, a)))[:, None])
            if ray_k > 0:
                col = col * (1.0 + 0.12 * ray_k)
            G[m] = np.where(a < 0.12, self.pick("flicker", flick[m]), self.r_glyph[m])
            C[m] = col
        if t >= T_ROSE:                                         # the flower head opens from a glowing bud
            c0, r0, c1, r1 = self.h_box
            hm, hs, hg = self.head_now(t)
            a = t - T_ROSE
            heat_k = 1.0 - float(smoothstep(0.1, 1.9, a))
            fade = float(smoothstep(0.0, 0.25, a))
            sub = (slice(r0, r1), slice(c0, c1))
            col = ROSE(hs) * lit[sub] * float(smoothstep(0.1, 1.2, a)) + FIRE(0.25 + 0.75 * heat_k * (0.4 + 0.6 * hs)) * (1.4 * heat_k)
            if ray_k > 0:                                       # backlight from the rays round the outline
                col = col * (1.0 + 0.12 * ray_k) + RIM_LIGHT * (border(hm) * ray_k * 0.6)[..., None]
            gl = np.where(flick[sub] > 1.0 - 0.7 * heat_k * heat_k, self.pick("flicker", flick[sub]), hg)
            G[sub] = np.where(hm, gl, G[sub])
            C[sub] = np.where(hm[..., None], col * fade, C[sub])
        for kind, chars in (("petal", "(@)o"), ("glint", "+")):
            p = self.parts[kind]
            if not len(p):
                continue
            r, c = ((p[:, PY] - PAD) // CH).astype(np.int32), (p[:, PX] // CW).astype(np.int32)
            ok = (r >= 0) & (r < ROWS) & (c >= 0) & (c < COLS)
            r, c, p = r[ok], c[ok], p[ok]
            if kind == "petal":
                G[r, c] = np.array([self.gi[g] for g in chars])[(p[:, PAGE] * 3.0 + p[:, PSEED]).astype(np.int32) % 4]
                C[r, c] = ROSE(np.full(len(p), 0.74)) * (lit[r, c] + 0.3 * ray_k)
            else:
                G[r, c] = self.gi["+"]
                C[r, c] = WHITE[None] * (2.5 * np.sin(np.pi * p[:, PAGE] / p[:, PLIFE]) ** 2)[:, None]
        if mt:
            self._draw_match(G, C, lit, mt, t, flick)
        if t >= T_WORDS and len(self.w_cells):                  # the message written in glowing embers
            age = t - self.w_t
            on = age >= 0.0
            if on.any():
                r, c, a, cv = self.w_cells[on, 0], self.w_cells[on, 1], age[on], self.w_cover[on]
                fk = flick[r, c]
                heat = 0.62 + 0.30 * np.exp(-a / 0.35) + 0.06 * (fk - 0.5)       # white-hot, then a warm gold
                G[r, c] = np.where(a < 0.1, self.pick("flicker", fk), self.pick("ink", cv))
                C[r, c] = FIRE(heat) * (0.55 + 0.35 * cv + 0.1 * np.sin(t * 3.0 + c * 0.3))[:, None]

        # characters -> picture, then the light in the air, a lens glow and the film look
        C *= self.vig_cell
        G, C = G[self.r0:self.r1], C[self.r0:self.r1]        # only the rows that are drawn
        np.take(self.atlas_rows, G[:, None, :] * self.ch + self.row_of_cell, axis=0, out=self.buf_glyph)
        alpha = self.buf_glyph.reshape(self.vh, self.w)    # every cell: its character's shape times its colour
        img = cv2.resize(C, (self.w, self.vh), dst=self.buf_img, interpolation=cv2.INTER_NEAREST)
        cv2.multiply(img, cv2.merge([alpha, alpha, alpha], dst=self.buf_a3), dst=img)
        lb = self._light(t, mt)                             # sparks and the match flame, half resolution
        q = self._rows(self._glow(t, rays))                 # fire glow, the burst and the rays, quarter resolution
        qs, ls = (q.shape[1], q.shape[0]), (lb.shape[1], lb.shape[0])
        q += self._bloom(cv2.resize(img, qs, interpolation=cv2.INTER_AREA) + q
                         + cv2.resize(lb, qs, interpolation=cv2.INTER_AREA))
        lb += cv2.resize(q, ls, interpolation=cv2.INTER_LINEAR)
        cv2.multiply(lb, self._rows(self.vig_light), dst=lb)
        exposure = float(smoothstep(0.0, 0.5, t))
        if self.end is not None:
            exposure *= 1.0 - float(smoothstep(self.end - 0.8, self.end, t))
        k = TONE_E * exposure                               # picture + light, scaled for the tone curve, in one pass
        cv2.addWeighted(lb, k, lb, 0.0, 1.0, dst=lb)
        up = cv2.resize(lb, (self.w, self.vh), dst=self.buf_up, interpolation=cv2.INTER_LINEAR)
        cv2.scaleAdd(img, k, up, dst=img)
        return self._camera(self._tonemap(img), t)

    def _draw_match(self, G, C, lit, m, t, flick):
        c0, r0, c1, r1 = cell_box(m["x"] - 60.0, m["y"] - 150.0, m["x"] + 300.0, m["y"] + 215.0)
        if c1 <= c0 or r1 <= r0:
            return
        sub = (slice(r0, r1), slice(c0, c1))                 # only the cells near the match are worked out
        G, C, lit, flick = G[sub], C[sub], lit[sub], flick[sub]
        X, Y = self.X[sub], self.Y[sub]
        ox, oy = X - m["x"], Y - m["y"]
        along = ox * 0.82 + oy * 0.57                        # the stick points down to the right
        across = ox * 0.57 - oy * 0.82
        stick = (along > 6.0) & (along < 330.0) & (np.abs(across) < 6.5)
        shadow = np.roll(stick, (1, 2), axis=(0, 1)) & ~stick  # the match casts a soft shadow
        C[shadow] *= 0.45
        side = 0.78 + 0.22 * np.clip(across / 6.5, -1.0, 1.0)  # rounded wood, lit from above
        grain = 0.9 + 0.1 * np.sin(along * 0.35 + 2.0 * np.sin(along * 0.05))
        wood = WOOD * (side * grain)[..., None]
        burnt = smoothstep(m["char"] + 6.0, m["char"] - 4.0, along)    # wood turns black near the head
        col = wood * lit * (1.0 - burnt[..., None]) + CHAR * lit * burnt[..., None]
        edge = np.exp(-((along - m["char"]) / 4.0) ** 2) * (0.3 + 0.7 * min(m["flame"], 1.0)) * m["ember"]
        col += FIRE(0.55 + 0.1 * flick)[...] * edge[..., None]       # a glowing line where it is burning
        G[stick] = np.where(burnt > 0.5, self.gi["%"], np.where(np.abs(across) < 3.5, self.gi["#"], self.gi["="]))[stick]
        C[stick] = col[stick]
        head = (ox * 0.82 + oy * 0.57) ** 2 / 13.0 ** 2 + across ** 2 / 9.5 ** 2 < 1.0
        hot = 0.25 + 0.5 * min(m["flame"], 1.0) * (0.7 + 0.3 * flick) + 0.35 * m["ember"]
        G[head] = self.gi["@"]
        C[head] = (CHAR * lit * 1.5 + FIRE(0.45 + 0.15 * flick) * (hot * m["ember"])[..., None])[head]
        if m["flame"] > 0.02:
            fl, temp, blue = self._flame(X, Y, m, t)
            on = fl > 0.16
            G[on] = self.pick("flame", np.minimum(fl, 1.0))[on]
            C[on] = (FIRE(0.30 + 0.5 * temp) * (1.15 * fl)[..., None] + BLUE_FLAME * (0.7 * blue)[..., None])[on]

    def _glow(self, t, rays):
        """Wide soft light, at quarter resolution: the fire's glow, the burst and the rays."""
        q = rays if rays is not None else np.zeros((self.qh, self.qw, 3), np.float32)
        if self.H.max() > 0.02:
            g = cv2.resize(FIRE(np.minimum(self.H, 1.2) * 0.75), (self.qw, self.qh), interpolation=cv2.INTER_LINEAR)
            q = q + cv2.GaussianBlur(g, (0, 0), 6.0 * self.s) * 0.085
        a = t - T_STRIKE
        if 0.0 <= a < 0.8:                                   # the flash of the match being struck
            d2 = (self.q_x - STRIKE[0]) ** 2 + (self.q_y - STRIKE[1]) ** 2
            q = q + (1.6 * math.exp(-a / 0.08) * np.exp(-d2 / (2.0 * 100.0 ** 2)))[..., None] * STRIKE_TINT
        a = t - T_IGNITE
        if 0.0 <= a < 1.0:                                   # flash and shock ring when the seal bursts
            d = self.seal_d
            ring = 0.45 * math.exp(-a / 0.12) * np.exp(-((d - 650.0 * a ** 0.6) / 16.0) ** 2)
            q = q + (3.0 * math.exp(-a / 0.12) * np.exp(-(d / 110.0) ** 2) + ring)[..., None] * FLAME_TINT
        return q

    def _light(self, t, m):
        """Small bright things in the air, at half resolution."""
        lb = self.bg.copy()
        s2 = self.s / 2.0
        if m and (m["flame"] > 0.02 or m["ember"] > 0.02):  # the match flame and its halo
            mx, my = m["x"], m["y"]
            x0, x1 = int(max(0, (mx - 260) * s2)), int(min(self.lw, (mx + 260) * s2))
            y0, y1 = int(max(0, (my - 320 - PAD) * s2)), int(min(self.lh, (my + 220 - PAD) * s2))
            if x1 > x0 and y1 > y0:
                lx, ly = self.lx[y0:y1, x0:x1], self.ly[y0:y1, x0:x1]
                d2 = (lx - mx) ** 2 + (ly - my + 40.0) ** 2
                k = min(m["flame"], 2.0)
                halo = (0.8 * np.exp(-d2 / (2.0 * 70.0 ** 2)) + 0.25 * np.exp(-d2 / (2.0 * 30.0 ** 2))) * k
                halo += 0.25 * m["ember"] * np.exp(-((lx - mx) ** 2 + (ly - my) ** 2) / (2.0 * 12.0 ** 2))
                lb[y0:y1, x0:x1] += FLAME_TINT * halo[..., None]
                fx0, fx1 = int(max(0, (mx - 90) * s2)), int(min(self.lw, (mx + 90) * s2))
                fy0, fy1 = int(max(0, (my - 190 - PAD) * s2)), int(min(self.lh, (my + 25 - PAD) * s2))
                if m["flame"] > 0.02 and fx1 > fx0 and fy1 > fy0:
                    fl, temp, blue = self._flame(self.lx[fy0:fy1, fx0:fx1], self.ly[fy0:fy1, fx0:fx1], m, t)
                    lb[fy0:fy1, fx0:fx1] += FIRE(0.30 + 0.5 * temp) * (1.1 * fl)[..., None] + BLUE_FLAME * (0.35 * blue)[..., None]
        for kind, trail, gain in (("spark", 6, 1.9), ("ember", 2, 1.4)):
            p = self.parts[kind]
            if not len(p):
                continue
            life = 1.0 - p[:, PAGE] / p[:, PLIFE]
            col = FIRE(p[:, PHEAT] * life ** 0.55) * (gain * np.clip(life * 4.0, 0.0, 1.0))[:, None]
            if kind == "ember":
                col *= (0.65 + 0.35 * np.sin(p[:, PAGE] * 11.0 + p[:, PSEED]))[:, None]
            for j in range(trail):                           # short motion trails
                f = j / trail
                xs = ((p[:, PX] - p[:, PVX] * f * 0.034) * s2).astype(np.int32)
                ys = ((p[:, PY] - PAD - p[:, PVY] * f * 0.034) * s2).astype(np.int32)
                ok = (xs >= 0) & (xs < self.lw) & (ys >= 0) & (ys < self.lh)
                np.add.at(lb, (ys[ok], xs[ok]), col[ok] * (1.0 - 0.7 * f))
        if t >= T_WORDS and len(self.w_cells):                  # sparks flying from the rose to their letters
            fly = (t - (self.w_t - self.w_fly)) / self.w_fly
            on = (fly > 0.0) & (fly < 1.0)
            if on.any():
                f, a, b = fly[on], self.w_from[on], self.w_to[on]
                bend = self.w_bend[on]
                for j, back in enumerate((0.0, 0.04, 0.08)):    # a short glowing trail behind each
                    e = np.clip(f - back, 0.0, 1.0)
                    e = e * e * (3.0 - 2.0 * e)
                    x = a[:, 0] + (b[:, 0] - a[:, 0]) * e + bend * np.sin(np.pi * e)
                    y = a[:, 1] + (b[:, 1] - a[:, 1]) * e
                    xs, ys = (x * s2).astype(np.int32), ((y - PAD) * s2).astype(np.int32)
                    ok = (xs >= 0) & (xs < self.lw) & (ys >= 0) & (ys < self.lh)
                    col = FIRE(np.full(int(ok.sum()), 0.85)) * (1.6 * (1.0 - 0.3 * j))
                    np.add.at(lb, (ys[ok], xs[ok]), col)
        n = int(16 * self.s)
        for x, y, age, life in self.parts["glint"][:, [PX, PY, PAGE, PLIFE]]:
            k = 3.0 * math.sin(math.pi * age / life) ** 2
            cx, cy = int(x * s2), int((y - PAD) * s2)
            if 0 <= cy < self.lh and 0 <= cx < self.lw:      # a little four-pointed star
                a0, a1 = max(0, cx - n), min(self.lw, cx + n + 1)
                lb[cy, a0:a1] += WHITE * (k * np.exp(-np.abs(np.arange(a0, a1) - cx) / (4.0 * self.s)))[:, None]
                a0, a1 = max(0, cy - n), min(self.lh, cy + n + 1)
                lb[a0:a1, cx] += WHITE * (k * np.exp(-np.abs(np.arange(a0, a1) - cy) / (4.0 * self.s)))[:, None]
        return cv2.GaussianBlur(self._rows(lb), (0, 0), 0.9)

    def _bloom(self, q):
        """Soft light that bright parts spread around them, like in a camera lens (quarter resolution)."""
        bright = np.maximum(q - 1.3, 0.0)
        acc = 0.3 * cv2.GaussianBlur(bright, (0, 0), 2.0)
        level = bright
        for weight in (0.45, 0.35, 0.28, 0.22):
            level = cv2.pyrDown(level)
            acc += weight * cv2.resize(cv2.GaussianBlur(level, (0, 0), 1.5), (q.shape[1], q.shape[0]),
                                       interpolation=cv2.INTER_LINEAR)
        return acc

    def _tonemap(self, x):
        """Light values (already scaled and plus one) -> screen colours through a film-like curve, with grain."""
        cv2.log(x, dst=x)
        oy, ox = (self.frame_no * 37) % 64, (self.frame_no * 23) % 64
        cv2.add(x, self.grain[oy:oy + self.vh, ox:ox + self.w], dst=x)
        return cv2.LUT(cv2.convertScaleAbs(x, dst=self.buf_u8, alpha=self.enc), self.tone, dst=self.buf_tone)

    def _camera(self, frame, t):
        """A slow push in, a jolt when the seal bursts, and heat shimmer above the fire."""
        s = self.s
        zoom = 1.0 + 0.045 * float(smoothstep(0.0, 14.0, t))
        shake = 6.0 * math.exp(-(t - T_IGNITE) / 0.2) if t > T_IGNITE else 0.0
        ox, oy = shake * math.sin(t * 93.0) * s, shake * math.cos(t * 71.0) * s
        top = self.r0 * self.ch                              # where the drawn part starts in the whole grid
        cx, cy = 540.0 * s, (900.0 - PAD) * s - top
        out = self.out[self.pad:self.pad + self.vh]          # the picture goes between the black bars
        if self.H.max() < 0.08:
            M = np.float32([[zoom, 0, cx - zoom * cx + ox], [0, zoom, cy - zoom * cy + oy]])
            cv2.warpAffine(frame, M, (self.w, self.vh), dst=out, flags=cv2.INTER_LINEAR)
            return self.out
        q = cv2.GaussianBlur(cv2.resize(self.H, (self.qw, self.qh), interpolation=cv2.INTER_LINEAR), (0, 0), 3.0)
        q, qx, qy, px, py = (self._rows(a) for a in (q, self.q_x, self.q_y, self.q_px, self.q_py))
        mapx = (px - cx - ox) / zoom + cx + q * (2.2 * s) * np.sin(qy * 0.11 - t * 11.0 + qx * 0.03)
        mapy = (py - top - cy - oy) / zoom + cy + q * (1.4 * s) * np.cos(qy * 0.07 - t * 8.0)
        mapx = cv2.resize(mapx, (self.w, self.vh), interpolation=cv2.INTER_LINEAR)
        mapy = cv2.resize(mapy, (self.w, self.vh), interpolation=cv2.INTER_LINEAR)
        cv2.remap(frame, mapx, mapy, cv2.INTER_LINEAR, dst=out)
        return self.out


# ------------------------------------------------------------------ playing and saving
def window_layout(screen_w, screen_h):
    """Character size, drawn rows and window size for a screen. The window shows the part of the picture
    where the story happens (the empty starry sky above and below is left out), as big as the screen allows."""
    top, bottom = 330.0, 1680.0
    r0 = int((top - PAD) // CH) // 2 * 2                     # an even row, so the light layers line up
    r1 = min(ROWS, math.ceil((bottom - PAD) / CH))
    fit = min((screen_h - 60) / (r1 - r0), 2.0 * (screen_w - 40) / COLS)   # screen pixels per row that fit
    ch = int(max(6, min(12, fit))) // 2 * 2
    scale = max(1.0, min(fit / ch, 1.5))
    size = (int(COLS * ch / 2 * scale), int((r1 - r0) * ch * scale))
    return (ch // 2, ch), (r0, r1), size


def play(message):
    try:                                                     # sharp pixels on high-DPI Windows screens
        import ctypes
        from ctypes import wintypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        area = wintypes.RECT()                               # the screen without the taskbar
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(area), 0)
        screen_w, screen_h = area.right - area.left, area.bottom - area.top
    except (ImportError, AttributeError, OSError):
        screen_w, screen_h = 1920, 1040
    (cw, ch), view, size = window_layout(screen_w, screen_h)
    film = Film(cw, ch, message=message, view=view)
    title = message.strip() or "Special letter"
    cv2.namedWindow(title, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(title, *size)
    cv2.moveWindow(title, max(0, (screen_w - size[0]) // 2), 0)
    start, full = time.perf_counter(), False
    while True:
        target, steps = time.perf_counter() - start, 0
        while film.t + 1.0 / FPS <= target and steps < 4:
            film.step(1.0 / FPS)
            steps += 1
        if steps == 4:                                       # too slow to keep up: slow down, don't skip
            start = time.perf_counter() - film.t
        if steps:
            frame = cv2.cvtColor(film.render(), cv2.COLOR_RGB2BGR)
            if frame.shape[1] != size[0]:                    # drawn a little smaller and scaled up: stays smooth
                frame = cv2.resize(frame, size, interpolation=cv2.INTER_LINEAR)
            cv2.imshow(title, frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q")):
            break
        if key in (ord("r"), ord(" ")):
            film.reset()
            start = time.perf_counter()
        if key == ord("f"):
            full = not full
            cv2.setWindowProperty(title, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN if full else cv2.WINDOW_NORMAL)
        if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
            break
    cv2.destroyAllWindows()


def save_video(seconds, message):
    try:
        import imageio_ffmpeg
    except ImportError:
        sys.exit("Saving the video needs imageio-ffmpeg:  pip install imageio-ffmpeg")
    film = Film(int(CW), int(CH), message=message)
    film.end = seconds
    size = (film.w, film.h + 2 * film.pad)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), VIDEO_FILE)
    writer = imageio_ffmpeg.write_frames(path, size, fps=FPS, codec="libx264", quality=None, macro_block_size=8,
                                         output_params=["-crf", "17", "-preset", "slow", "-movflags", "+faststart"])
    writer.send(None)
    frames, started = int(round(seconds * FPS)), time.perf_counter()
    for i in range(frames):
        film.step(1.0 / FPS)
        writer.send(np.ascontiguousarray(film.render()))
        if (i + 1) % FPS == 0 or i + 1 == frames:
            print(f"\rrendering {i + 1}/{frames} frames ({time.perf_counter() - started:.0f}s)", end="", flush=True)
    writer.close()
    print(f"\nsaved {path}")


def main():
    parser = argparse.ArgumentParser(description="Special letter - cinematic edition")
    parser.add_argument("name", nargs="?", default=MESSAGE, help=f'words written on the letter (default "{MESSAGE}")')
    parser.add_argument("--mp4", action="store_true", help=f"save {VIDEO_FILE} (1080x1920, {FPS} fps) instead of playing")
    parser.add_argument("--seconds", type=float, default=VIDEO_SECONDS, help="length of the video")
    args = parser.parse_args()
    if args.mp4:
        save_video(args.seconds, args.name)
    else:
        play(args.name)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
