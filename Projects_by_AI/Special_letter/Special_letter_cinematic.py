"""
Special letter - cinematic edition.

A love letter sealed with red wax is lit by a match. It burns with moving
flames, a glowing edge, ash and smoke, and a rose blooms out of the fire while
light rays open behind it. Everything solid is drawn with text characters;
light (fire glow, sparks, rays) is added on top, like in a film.

Needs:   pip install numpy opencv-python pillow imageio-ffmpeg
Run:     python Special_letter_cinematic.py                 plays it in a window
         python Special_letter_cinematic.py "Riya"          any name or words on the letter
         python Special_letter_cinematic.py "Riya" --mp4    saves special_letter.mp4 (1080x1920, 60 fps)
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
# character cells, each 9 pixels wide and 18 tall.
COLS, ROWS = 120, 106
CW, CH = 9.0, 18.0
PAD = 6.0                       # empty pixels above and below the grid
SR, SC = ROWS * 2, COLS         # the fire is simulated on square 9x9 cells

ENV = (75.0, 695.0, 1005.0, 1325.0)      # envelope: left, top, right, bottom
SEAL = (540.0, 985.0)                     # centre of the wax seal
HEAD = (540.0, 640.0)                     # centre of the rose
MATCH_PATH = ((1240, 1350), (930, 1295), (705, 1150), (600, 1068))   # the match slides in along this

# ------------------------------------------------------------------ timeline (seconds)
T_LETTER = 0.4      # the letter appears
T_SHINE = 1.85      # a soft light sweeps over the paper
T_MATCH = 2.3       # a lit match slides in
T_TOUCH = 3.55      # its flame touches the wax seal
T_IGNITE = 4.3      # the seal bursts into flame and the paper starts to burn
T_ROSE = 6.3        # a rose blooms inside the fire
T_RAYS = 8.4        # light rays open behind the rose
SCORCH = 0.38       # paper turns brown this long before it catches fire
RIM = 0.24          # the glowing edge lasts this long on each bit of paper

# ------------------------------------------------------------------ the rose
STEM = ((540, 868), (512, 1250), (552, 1660))                 # start, bend, end
LEAVES = [((532, 1065), (430, 965), (296, 975), 50),         # base, bend, tip, half width
          ((548, 1125), (680, 1025), (795, 1045), 52),
          ((534, 1300), (440, 1235), (322, 1290), 44),
          ((546, 1405), (640, 1345), (735, 1405), 40)]
SEPALS = [((540, 875), (480, 890), (418, 955), 13), ((540, 875), (600, 892), (660, 952), 13),
          ((532, 880), (515, 925), (492, 980), 10), ((548, 880), (566, 925), (586, 976), 10)]
THORNS = ((0.30, 1), (0.46, -1), (0.62, 1), (0.79, -1))     # place along the stem, side

# ------------------------------------------------------------------ characters
GLYPHS = "".join(chr(i) for i in range(32, 127)) + "\u2022\u00b7"     # ASCII, bullet, middle dot
PALETTES = {  # characters for each material (sorted by ink later, so the order here does not matter)
    "paper": "%&$8#@", "ink": "*%&#@", "wax": "o*%&8#@", "fire": ".':;~+*%#@", "smoke": ".,:;~",
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


def tile_noise(rng, h, w, sigma):
    """Smooth random pattern (about -2..2) that wraps around at the edges."""
    spec = np.fft.fft2(rng.standard_normal((h, w)))
    ky, kx = np.fft.fftfreq(h)[:, None], np.fft.fftfreq(w)[None, :]
    n = np.real(np.fft.ifft2(spec * np.exp(-2.0 * (np.pi * sigma) ** 2 * (kx * kx + ky * ky))))
    return (n / (n.std() + 1e-9)).astype(np.float32)


def bezier(points, u):
    """Point and direction at u (0..1) along a Bezier curve with these control points."""
    p = np.asarray(points, np.float64)
    while len(p) > 2:
        p = p[:-1] + (p[1:] - p[:-1]) * u
    return p[0] + (p[1] - p[0]) * u, p[1] - p[0]


def curve_field(X, Y, points, n=80):
    """For every cell: how far along the curve its nearest point is (0..1),
    the signed distance to the curve, and the curve's direction there (degrees)."""
    us = np.linspace(0.0, 1.0, n, dtype=np.float32)
    pts = np.array([bezier(points, u)[0] for u in us], np.float32)
    px, py = pts[:, 0], pts[:, 1]
    d2 = (X[..., None] - px) ** 2 + (Y[..., None] - py) ** 2
    i = d2.argmin(-1)
    tx, ty = np.gradient(px)[i], np.gradient(py)[i]
    dist = np.sqrt(np.take_along_axis(d2, i[..., None], -1)[..., 0])
    side = np.sign(tx * (Y - py[i]) - ty * (X - px[i]))
    return us[i], dist * side, np.degrees(np.arctan2(ty, tx))


def line_index(deg):
    """Which of '-', '\\', '|', '/' (0..3) best follows a line at this angle (y points down)."""
    a = np.mod(deg, 180.0)
    return np.select([a < 22.5, a < 67.5, a < 112.5, a < 157.5], [0, 1, 2, 3], 0)


def border(mask):
    """Cells of the mask that touch a cell outside it."""
    return mask & ~(np.roll(mask, 1, 0) & np.roll(mask, -1, 0) & np.roll(mask, 1, 1) & np.roll(mask, -1, 1))


def find_font(names):
    folders = [os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"),
               "/usr/share/fonts/truetype/dejavu", "/Library/Fonts", "/System/Library/Fonts"]
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


def text_coverage(message):
    """How much of each cell the handwritten message covers (0..1)."""
    img = Image.new("L", (1080, 1920), 0)
    message = message.strip()
    message = message[:1].upper() + message[1:]              # first letter always a capital
    if message:
        path = find_font(["georgiab.ttf", "georgia.ttf", "segoescb.ttf", "consolab.ttf", "DejaVuSans-Bold.ttf"])
        draw, size = ImageDraw.Draw(img), 200
        while True:
            font = ImageFont.truetype(path, size) if path else ImageFont.load_default()
            box = draw.textbbox((540, 1195), message, font=font, anchor="mm")
            if (box[2] - box[0] <= 760 and box[3] - box[1] <= 200) or size <= 30 or not path:
                break
            size -= 6
        draw.text((540, 1195), message, fill=255, font=font, anchor="mm")
    a = np.asarray(img, np.float32)[int(PAD):int(PAD) + ROWS * int(CH)] / 255.0
    return cv2.resize(a, (COLS, ROWS), interpolation=cv2.INTER_AREA)


# ------------------------------------------------------------------ colours (linear light; above 1 glows)
def rgb(r, g, b):
    return np.array([r, g, b], np.float32)


PAPER, INK, CHAR, SCORCHED = rgb(0.95, 0.60, 0.53), rgb(0.30, 0.004, 0.035), rgb(0.050, 0.038, 0.032), rgb(0.20, 0.085, 0.03)
AIR_RED, AIR_BLUE = rgb(0.85, 0.040, 0.050), rgb(0.050, 0.11, 0.60)
WOOD, MATCH_HEAD, THORN = rgb(1.0, 0.66, 0.28), rgb(0.40, 0.035, 0.025), rgb(0.30, 0.07, 0.03)
STAR, SMOKE, WHITE = rgb(0.70, 0.78, 1.00), rgb(0.060, 0.055, 0.052), rgb(1.0, 0.86, 0.78)
AMBIENT, FIRE_TINT, FLAME_TINT = rgb(0.92, 0.90, 0.96), rgb(1.0, 0.42, 0.10), rgb(1.0, 0.55, 0.18)
RIM_LIGHT, BLUE_FLAME = rgb(0.9, 0.42, 0.50), rgb(0.15, 0.30, 1.4)
RAY_CORE, RAY_BEAM, RAY_STREAK = rgb(1.5, 1.05, 0.78), rgb(0.95, 0.62, 0.85), rgb(0.30, 0.50, 1.60)
FIRE = Gradient((0.00, (0, 0, 0)), (0.10, (0.07, 0.005, 0.0)), (0.25, (0.40, 0.035, 0.005)),
                (0.45, (1.15, 0.22, 0.025)), (0.65, (2.1, 0.80, 0.11)), (0.85, (3.1, 1.9, 0.60)),
                (1.00, (4.2, 3.3, 2.1)), (1.30, (5.2, 4.8, 4.0)))
WAX = Gradient((0.0, (0.06, 0.002, 0.008)), (0.4, (0.45, 0.015, 0.035)), (0.7, (0.95, 0.06, 0.08)),
               (0.88, (1.35, 0.20, 0.20)), (1.0, (2.2, 0.90, 0.85)))
ROSE = Gradient((0.0, (0.03, 0.0, 0.004)), (0.3, (0.22, 0.003, 0.018)), (0.55, (0.62, 0.012, 0.045)),
                (0.75, (1.0, 0.045, 0.08)), (0.9, (1.25, 0.12, 0.15)), (1.0, (1.45, 0.30, 0.32)))
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
        ink = build_atlas(9, 18).mean(axis=(1, 2))         # how much ink each character has
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

    # ---------------------------------------------------------- building the scene
    def _build_letter(self, rng):
        X, Y = np.meshgrid((np.arange(COLS, dtype=np.float32) + 0.5) * CW,
                           PAD + (np.arange(ROWS, dtype=np.float32) + 0.5) * CH)
        self.X, self.Y = X, Y
        self.rnd = rng.random((3, ROWS, COLS), dtype=np.float32)       # fixed random numbers per cell
        fine, broad, burn1, burn2 = (tile_noise(rng, ROWS, COLS, s) for s in (0.7, 5.0, 4.0, 1.2))
        x0, y0, x1, y1 = ENV
        sx, sy = SEAL
        inside = (X > x0) & (X < x1) & (Y > y0) & (Y < y1)
        edge = inside & ((X - x0 < CW) | (x1 - X < CW) | (Y - y0 < CH) | (y1 - Y < CH))

        # four flaps folded over the back, with soft shadows under their edges
        half = np.abs(X - sx) / (sx - x0)
        top_tip, bot_tip = sy + 32.0, sy - 80.0
        d_top = (top_tip + (y0 - top_tip) * half - Y) / math.hypot(1.0, (top_tip - y0) / (sx - x0))
        d_bot = (Y - bot_tip - (y1 - bot_tip) * half) / math.hypot(1.0, (y1 - bot_tip) / (sx - x0))
        flap = np.where(d_top > 0, 0, np.where(d_bot > 0, 3, np.where(X < sx, 1, 2)))
        sides = (flap == 1) | (flap == 2)
        light = np.array([1.0, 0.80, 0.89, 0.94], np.float32)[flap]
        light *= np.where(flap > 0, 0.68 + 0.32 * smoothstep(0.0, 28.0, -d_top), 1.0)
        light *= np.where(sides, 0.80 + 0.20 * smoothstep(0.0, 20.0, -d_bot), 1.0)
        light *= np.where((flap == 0) & (d_top < 8.0), 1.12, 1.0)
        light *= np.where((flap == 3) & (d_bot < 7.0), 1.07, 1.0)
        light *= 1.0 + 0.045 * fine + 0.035 * broad                        # paper fibres
        light *= 1.0 - 0.10 * ((X - sx) / 470.0) ** 2 - 0.06 * ((Y - 1010.0) / 320.0) ** 2
        glyph = self.pick("paper", 0.5 + 0.3 * fine + 0.6 * (light - 0.9))
        fold_t = (flap > 0) & (-d_top < 9.5)
        fold_b = sides & (-d_bot < 8.5)
        glyph = np.where(fold_t, np.where(X < sx, self.line[1], self.line[3]), glyph)
        glyph = np.where(fold_b, np.where(X < sx, self.line[3], self.line[1]), glyph)
        light = light * np.where(fold_t, 0.72, np.where(fold_b, 0.80, 1.0))
        albedo = PAPER * light[..., None]

        # red and blue airmail stripes round the edge
        wc, hc = (x1 - x0) / CW, (y1 - y0) / CH
        u, v = (X - x0) / CW, (Y - y0) / CH
        per = np.where(Y - y0 < CH, u, np.where(x1 - X < CW, wc + v,
                       np.where(y1 - Y < CH, 2 * wc + hc - u, 2 * wc + 2 * hc - v)))
        band = (np.floor(per).astype(np.int32) % 6)[..., None]
        stripes = np.where(band < 2, AIR_RED, np.where((band == 3) | (band == 4), AIR_BLUE, PAPER * 1.05))
        albedo = np.where(edge[..., None], stripes, albedo)
        glyph = np.where(edge, self.line[3], glyph)

        # the handwritten message
        cover = text_coverage(self.message)
        k = smoothstep(0.15, 0.5, cover)[..., None]
        albedo = albedo * (1.0 - k) + INK * k
        glyph = np.where(inside & ~edge & (cover > 0.2), self.pick("ink", cover), glyph)

        # the wax seal: a shiny dome with a heart stamped into it
        dx, dy = X - sx, Y - sy
        rho, ang = np.hypot(dx, dy), np.arctan2(dy, dx)
        r_wax = 86.0 * (1.0 + 0.06 * np.sin(3 * ang + 1.3) + 0.04 * np.sin(5 * ang + 0.4)
                        + 0.025 * np.sin(9 * ang + 2.0))
        wax = rho < r_wax
        nx, ny = dx / r_wax * 0.92, dy / r_wax * 0.92
        nz = np.sqrt(np.clip(1.0 - nx * nx - ny * ny, 0.03, 1.0))
        diffuse = np.clip(-0.48 * nx - 0.58 * ny + 0.66 * nz, 0.0, 1.0)  # light from the upper left
        hx, hy = dx / 50.0, 0.25 - dy / 45.0
        heart = (hx * hx + hy * hy - 1.0) ** 3 - hx * hx * hy ** 3 < 0
        core = heart & ~border(heart)
        wv = 0.22 + 0.62 * diffuse
        wv = np.where(core, wv * 0.8, wv)
        wv = np.where(heart & ~core, np.where(hx - hy < 0, wv * 0.45, wv * 1.2 + 0.12), wv)
        wv = (wv + 0.6 * diffuse ** 22) * (0.72 + 0.28 * smoothstep(1.0, 0.8, rho / r_wax))
        albedo = np.where(wax[..., None], WAX(wv), albedo)
        glyph = np.where(wax, self.pick("wax", wv), glyph)

        self.letter, self.wax = inside, wax & inside
        self.l_glyph, self.l_albedo = glyph.astype(np.int32), albedo.astype(np.float32)
        self.shine_pos = ((X - x0) / (x1 - x0) + 0.5 * (Y - y0) / (y1 - y0)).astype(np.float32)
        # when each cell appears, catches fire (spreading from the seal, faster upwards) and crumbles
        self.ta = (T_LETTER + 1.15 * ((X - x0) / (x1 - x0) * 0.62 + (Y - y0) / (y1 - y0) * 0.38)
                   + 0.14 * self.rnd[0]).astype(np.float32)
        spread = np.hypot(dx, dy * np.where(dy < 0, 0.55, 1.45)) / 245.0
        ti = T_IGNITE + 0.10 + spread * np.maximum(0.3, 1.0 + 0.28 * burn1) + 0.05 * burn2
        self.ti = np.where(wax, T_IGNITE + rho / 500.0, ti).astype(np.float32)
        self.tc = (self.ti + RIM + 0.45 + 0.9 * self.rnd[1]).astype(np.float32)

        # background: twinkling stars and dust that only shows where light falls on it
        self.star = rng.random((ROWS, COLS)) < 0.013
        self.star_b = rng.uniform(0.10, 0.55, (ROWS, COLS)).astype(np.float32)
        self.star_sp = rng.uniform(0.6, 2.5, (ROWS, COLS)).astype(np.float32)
        self.star_ph = rng.uniform(0.0, 6.3, (ROWS, COLS)).astype(np.float32)
        self.star_glyph = np.where(self.star_b > 0.47, self.gi["+"],
                                   np.where(self.star_b > 0.3, self.gi["\u00b7"], self.gi["."]))
        self.dust = rng.random((ROWS, COLS)) < 0.35
        self.dust_glyph = np.array([self.gi[g] for g in ".'`\u00b7,"], np.int32)[rng.integers(0, 5, (ROWS, COLS))]
        self.dust_amp = rng.uniform(0.3, 1.0, (ROWS, COLS)).astype(np.float32)
        # fire simulation grid and two moving noise patterns that break the flames up
        self.tex1, self.tex2 = tile_noise(rng, SR, SC, 2.0), tile_noise(rng, SR, SC, 4.5)
        gy, gx = np.mgrid[0:SR, 0:SC].astype(np.float32)
        self.gx, self.gy = gx, gy

    def _build_rose(self):
        X, Y = self.X, self.Y
        # the flower: a cup-shaped outline filled with petals curling round a spiral
        dx, dy = X - HEAD[0], Y - HEAD[1]
        tips = 1.0 + 0.10 * np.abs(np.sin(dx / 34.0))                       # petal tips along the top
        head = np.where(dy < 0, (dx / 228.0) ** 2 + (dy / (150.0 * tips)) ** 2 < 1.0,
                        np.abs(dx) < 228.0 * np.clip(1.0 - (dy / 240.0) ** 2, 0.0, 1.0) ** 0.9)
        squash = np.where(Y < HEAD[1] - 80.0, 1.55, 1.05)                  # we look at it a little from above
        qx, qy = dx, (Y - (HEAD[1] - 80.0)) * squash
        rho, th = np.hypot(qx, qy), np.arctan2(qy, qx)
        pitch = 66.0
        f = (th / (2.0 * np.pi) + rho / pitch + 0.06 * np.sin(3.0 * th + rho / 40.0)) % 1.0   # 0 = fold, 1 = lip
        hb = (0.32 + 0.55 * f ** 1.6) * (1.0 - 0.35 * np.exp(-rho / 55.0))
        hb += 0.16 * (-dx / 240.0 - dy / 260.0)                             # light from the upper left
        r2 = np.maximum(rho, 1.0)
        gx = -qy / (2.0 * np.pi * r2 * r2) + qx / (r2 * pitch)
        gy = (qx / (2.0 * np.pi * r2 * r2) + qy / (r2 * pitch)) * squash
        fold = head & (f < 0.13) & (rho > 14.0)
        outline = border(head)
        hb = np.where(fold, hb * 0.35, np.where(head & (f > 0.88), hb + 0.12, hb))
        hb = np.where(outline, np.where(dy < 0, hb + 0.2, hb * 0.75), hb)    # outer petal lips catch the light
        h_glyph = np.where(fold, self.line[line_index(np.degrees(np.arctan2(gy, gx)) + 90.0)], self.pick("petal", hb))
        h_tr = T_ROSE + 0.9 * np.clip(rho / 240.0, 0.0, 1.0) + 0.08 * self.rnd[2]   # opens from the centre

        # stem, thorns, leaves and the small green sepals under the flower
        g_mask = np.zeros((ROWS, COLS), bool)
        g_glyph = np.zeros((ROWS, COLS), np.int32)
        g_col = np.zeros((ROWS, COLS, 3), np.float32)
        g_tr = np.zeros((ROWS, COLS), np.float32)

        def add(m, glyph, col, tr):
            g_mask[m] = True
            g_glyph[m] = np.broadcast_to(glyph, m.shape)[m]
            g_col[m] = np.broadcast_to(col, m.shape + (3,))[m]
            g_tr[m] = np.broadcast_to(tr, m.shape)[m]

        def stem_time(u):
            return T_ROSE + 1.0 + 0.75 * u

        u, d, ang = curve_field(X, Y, STEM)
        add(np.abs(d) < 8.5, self.line[line_index(ang)], LEAF(np.where(d < 0, 0.62, 0.42)), stem_time(u))
        us = np.linspace(0.0, 1.0, 200)
        stem_pts = np.array([bezier(STEM, uu)[0] for uu in us])
        for leaves, start, grow in ((LEAVES, None, 0.55), (SEPALS, T_ROSE + 0.9, 0.3)):
            for base, bend, tip, hw in leaves:
                u, d, ang = curve_field(X, Y, (base, bend, tip))
                width = hw * np.clip(np.sin(np.pi * u), 0.0, 1.0) ** 0.75 * (1.0 - 0.12 * ((u * 9.0) % 1.0))
                m = (np.abs(d) < width) & (u > 0.0) & (u < 1.0)                    # serrated leaf edge
                rel = np.abs(d) / np.maximum(width, 1.0)
                b = np.where(d > 0, 0.66, 0.44) + 0.16 * (1.0 - rel)              # one half faces the light
                vein = ((u * 7.0 - rel * 0.6) % 1.0) < 0.16
                mid = np.abs(d) < 4.5
                rim = border(m)
                b = np.where(mid, 0.95, np.where(rim, 0.85, np.where(vein, b + 0.15, b)))
                vang = ang + np.where(d > 0, 40.0, -40.0)
                glyph = np.where(mid, self.line[line_index(ang)],
                                 np.where(rim, self.gi["&"],
                                          np.where(vein, self.line[line_index(vang)], self.gi[":"])))
                if start is None:
                    t0 = stem_time(us[np.hypot(*(stem_pts - base).T).argmin()]) + 0.12
                else:
                    t0 = start
                add(m, glyph, LEAF(b), t0 + grow * u)
        for uu, side in THORNS:
            (px, py), (tx, ty) = bezier(STEM, uu)
            n = math.hypot(tx, ty)
            nx, ny = -ty / n * side, tx / n * side
            r, c = int((py + ny * 14.0 - PAD) // CH), int((px + nx * 14.0) // CW)
            add((np.arange(ROWS)[:, None] == r) & (np.arange(COLS)[None, :] == c),
                self.gi[">" if nx > 0 else "<"], THORN, stem_time(uu))

        self.r_head = head
        self.r_mask = head | g_mask
        self.r_glyph = np.where(head, h_glyph, g_glyph).astype(np.int32)
        self.r_col = np.where(head[..., None], ROSE(hb), g_col).astype(np.float32)
        self.r_tr = np.where(head, h_tr, g_tr).astype(np.float32)
        self.r_edge = border(self.r_mask) & head              # outline of the flower, lit from behind later
        self.edge_cells = np.argwhere(self.r_edge)
        self.petal_from = np.argwhere(head & outline & (Y > HEAD[1]))

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
        # turning light into screen colours: a film-like curve, looked up from a table
        self.enc = 255.0 / math.log1p(TONE_E * 16.0)
        x = np.expm1(np.arange(256) / self.enc) / TONE_E
        aces = x * (2.51 * x + 0.03) / (x * (2.43 * x + 0.59) + 0.14)
        self.tone = np.clip(np.sqrt(np.clip(aces, 0.0, 1.0)) * 255.0 + 0.5, 0, 255).astype(np.uint8)
        g = rng.standard_normal((self.vh + 64, self.w + 64, 1)).astype(np.float32) / self.enc
        self.grain = np.repeat(g, 3, axis=2)                 # film grain
        self.seal_d = np.hypot(self.q_x - SEAL[0], self.q_y - SEAL[1])
        # big images are made once and reused for every frame
        self.buf_glyph = np.empty((self.r1 - self.r0, self.ch, COLS, self.cw), np.float32)
        self.buf_a3, self.buf_img, self.buf_up = (np.empty((self.vh, self.w, 3), np.float32) for _ in range(3))
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
        src = np.maximum(src, np.where(smoulder, 0.3 * (1.0 - np.clip((t - self.ti - RIM) / 0.35, 0, 1)), 0.0))
        if T_IGNITE <= t < T_IGNITE + 0.7:
            src = np.where(self.wax, 1.25, src)
        ra = t - self.r_tr
        src = np.maximum(src, np.where(self.r_head & (ra >= 0) & (ra < 0.45), 0.75 * (1.0 - ra / 0.45), 0.0))
        self._fire(dt, t, src.astype(np.float32))

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
            for kind, rate in (("spark", 0.9), ("ember", 0.12)):
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
        crumble = L & (t0 < self.tc) & (t >= self.tc) & (self.rnd[2] < 0.55)
        if crumble.any():                                   # black char breaks up into floating ash
            ys, xs = np.nonzero(crumble)
            k = len(ys)
            self._spawn("ash", self.X[ys, xs], self.Y[ys, xs], rng.normal(0, 25, k), -rng.uniform(30, 110, k),
                        rng.uniform(1.2, 2.8, k), np.zeros(k), -rng.uniform(10, 40, k))
        born = self.r_head & (t0 < self.r_tr) & (t >= self.r_tr) & (self.rnd[0] < 0.2)
        if born.any():                                      # white-hot sparks while the rose forms
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
        n1 = cv2.remap(self.tex1, gx, (gy + t * 15.0) % SR, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        n2 = cv2.remap(self.tex2, (gx + t * 4.0) % SC, (gy + t * 24.0) % SR, cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_WRAP)
        turb = 0.6 * n1 + 0.4 * n2
        H, S = self.H, self.S
        vy = -(16.0 + 38.0 * np.minimum(H, 1.2))                         # cells per second, upwards
        vx = 7.0 * np.sin(gy * 0.19 + t * 2.1 + 2.0 * np.sin(gx * 0.11 - t * 0.8)) + 6.0 * n2
        H = cv2.remap(H, gx - vx * dt, gy - vy * dt, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        S = cv2.remap(S, gx - vx * dt * 0.6, gy - vy * dt * 0.45, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        cool = np.maximum(1.25 * (1.0 + 0.85 * turb), 0.2)
        S += np.minimum(H, 0.6) * cool * dt * 0.9
        H = np.maximum(H - cool * dt, 0.0)
        S *= 1.0 - 0.45 * dt
        if src.any():
            H = np.maximum(H, np.repeat(src, 2, axis=0) * (0.82 + 0.3 * turb))
        self.H, self.S = H.astype(np.float32), S.astype(np.float32)

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
        """Where the match head is, and whether the match is on screen."""
        if t < T_MATCH or t > T_IGNITE + 0.9:
            return 0.0, 0.0, 0.0
        if t < T_TOUCH:
            u = float(smoothstep(T_MATCH, T_TOUCH, t))
        else:
            u = 1.0 - float(smoothstep(T_IGNITE + 0.05, T_IGNITE + 0.9, t))
        (x, y), _ = bezier(MATCH_PATH, u)
        hand = 1.0 if T_TOUCH <= t < T_IGNITE else 0.4                    # a slightly shaking hand
        x += hand * (2.0 * math.sin(t * 23.0) + 1.2 * math.sin(t * 37.0))
        y += hand * 1.5 * math.sin(t * 19.0 + 1.0)
        return float(x), float(y), 1.0

    @staticmethod
    def _flame(x, y, mx, my, t):
        """Brightness (0..1) of the match flame at layout point(s) x, y."""
        ln = 98.0 * (1.0 + 0.10 * math.sin(t * 13.0) + 0.06 * math.sin(t * 31.0 + 1.0))
        v = (my + 12.0 - y) / ln                                          # 0 at the base, 1 at the tip
        vc = np.clip(v, 0.0, 1.0)
        sway = (6.0 * math.sin(t * 7.3) + 3.0 * math.sin(t * 17.0)) * vc * vc
        width = 8.0 + 24.0 * np.sqrt(vc) * (1.0 - vc) ** 0.8
        return np.where((v > 0.0) & (v < 1.0), np.exp(-((x - mx - sway) / width) ** 2) * (1.0 - 0.55 * vc), 0.0)

    def _rays(self, t):
        """Light rays from behind the rose (quarter resolution), or None before they start."""
        k = float(smoothstep(T_RAYS, T_RAYS + 1.4, t))
        if k <= 0.0:
            return None
        a, r = self.q_a, self.q_r
        spin = 0.05 * (t - T_RAYS)
        beams = ((0.5 + 0.5 * np.cos(7.0 * a + 0.4 + spin)) ** 8
                 + 0.7 * (0.5 + 0.5 * np.cos(11.0 * a + 2.1 - 1.3 * spin)) ** 10
                 + 0.5 * (0.5 + 0.5 * np.cos(17.0 * a + 4.0 + 0.7 * spin)) ** 12)
        reach = 1900.0 * float(smoothstep(T_RAYS, T_RAYS + 1.6, t))
        beams *= np.exp(-r / 560.0) * smoothstep(40.0, 220.0, r) * smoothstep(reach + 1.0, reach - 300.0, r)
        core = np.exp(-(r / 150.0) ** 1.6) * (0.5 + 1.2 * math.exp(-(t - T_RAYS) / 0.3))
        flare = (np.exp(-(self.q_dy / 10.0) ** 2) * np.exp(-np.abs(self.q_dx) / 650.0)
                 + 0.35 * np.exp(-(self.q_dx / 9.0) ** 2) * np.exp(-np.abs(self.q_dy) / 420.0))
        out = beams[..., None] * RAY_BEAM * 0.30 + core[..., None] * RAY_CORE + flare[..., None] * RAY_STREAK * 0.7
        out *= k * (1.0 + 0.08 * math.sin(t * 2.0)) * (1.0 - self.q_rose)
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
        fire_light = cv2.GaussianBlur(heat, (0, 0), 3.0, sigmaY=1.6) * 2.2
        lit = AMBIENT + fire_light[..., None] * FIRE_TINT
        mx, my, match = self._match(t)
        if match:
            d2 = ((X - mx) ** 2 + (Y - my + 40.0) ** 2) / 170.0 ** 2
            lit = lit + (2.0 * (0.92 + 0.08 * math.sin(t * 29.0)) / (1.0 + d2))[..., None] * FLAME_TINT
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
            dl = fire_light[..., None] * FIRE_TINT * 0.35
            if rays is not None:
                dl = dl + cv2.resize(rays, (COLS, ROWS), interpolation=cv2.INTER_AREA) * 0.55
            m = self.dust & (dl.max(-1) * self.dust_amp > 0.03)
            G[m], C[m] = self.dust_glyph[m], dl[m] * self.dust_amp[m][:, None]

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
                ti, r1 = self.ti[char], rnd[1][char]
                ca = np.clip((t - ti - RIM) / (self.tc[char] - ti - RIM), 0.0, 1.0)
                ember = (rnd[2][char] < 0.32) * (1.0 - ca) * (0.6 + 0.4 * np.sin(t * 9.0 + r1 * 40.0))
                G[char] = self.pick("ash", r1)
                C[char] = CHAR * lit[char] * (1.0 - 0.5 * ca)[:, None] + FIRE(0.30 + 0.15 * ember) * ember[:, None]
            burn = L & (pre <= 0) & (t < self.ti + RIM)
            if burn.any():
                G[burn] = self.pick("ember", flick[burn])
                C[burn] = FIRE(0.70 + 0.25 * flick[burn]) * 0.95

        # the rose: each part appears white-hot and cools to its colour
        ra = t - self.r_tr
        m = self.r_mask & (ra >= 0)
        if m.any():
            a = ra[m]
            col = (self.r_col[m] * lit[m] * smoothstep(0.05, 0.85, a)[:, None]
                   + FIRE(np.clip(1.05 - a * 1.25, 0.0, 1.1)) * (1.3 * (1.0 - smoothstep(0.3, 1.2, a)))[:, None])
            if ray_k > 0:                                     # backlight from the rays
                col = col * (1.0 + 0.12 * ray_k) + RIM_LIGHT * (self.r_edge[m] * ray_k * 0.6)[:, None]
            G[m] = np.where(a < 0.12, self.pick("flicker", flick[m]), self.r_glyph[m])
            C[m] = col
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
        if match:
            self._draw_match(G, C, lit, mx, my, t)

        # characters -> picture, then the light in the air, a lens glow and the film look
        C *= self.vig_cell
        G, C = G[self.r0:self.r1], C[self.r0:self.r1]        # only the rows that are drawn
        np.copyto(self.buf_glyph, self.atlas[G].transpose(0, 2, 1, 3))
        alpha = self.buf_glyph.reshape(self.vh, self.w)
        img = cv2.resize(C, (self.w, self.vh), dst=self.buf_img, interpolation=cv2.INTER_NEAREST)
        cv2.multiply(img, cv2.merge([alpha, alpha, alpha], dst=self.buf_a3), dst=img)
        lb = self._rows(self._light(t, mx, my, match))     # sparks and the match flame, half resolution
        q = self._rows(self._glow(t, rays))                 # fire glow, the burst and the rays, quarter resolution
        qs, ls = (q.shape[1], q.shape[0]), (lb.shape[1], lb.shape[0])
        q += self._bloom(cv2.resize(img, qs, interpolation=cv2.INTER_AREA) + q
                         + cv2.resize(lb, qs, interpolation=cv2.INTER_AREA))
        lb += cv2.resize(q, ls, interpolation=cv2.INTER_LINEAR)
        cv2.multiply(lb, self._rows(self.vig_light), dst=lb)
        cv2.add(img, cv2.resize(lb, (self.w, self.vh), dst=self.buf_up, interpolation=cv2.INTER_LINEAR), dst=img)
        exposure = float(smoothstep(0.0, 0.5, t))
        if self.end is not None:
            exposure *= 1.0 - float(smoothstep(self.end - 0.8, self.end, t))
        return self._camera(self._tonemap(img, exposure), t)

    def _draw_match(self, G, C, lit, mx, my, t):
        ox, oy = self.X - mx, self.Y - my
        along = ox * 0.82 + oy * 0.57                        # the stick points down to the right
        stick = (along > 12.0) & (along < 300.0) & (np.abs(ox * 0.57 - oy * 0.82) < 7.5)
        shadow = np.roll(stick, (1, 1), axis=(0, 1)) & ~stick  # the match casts a soft shadow on the paper
        C[shadow] *= 0.45
        G[stick] = self.line[1]
        C[stick] = (WOOD * lit)[stick]
        head = (ox / 13.0) ** 2 + (oy / 10.0) ** 2 < 1.0
        G[head] = self.gi["@"]
        C[head] = (MATCH_HEAD * lit + FIRE(0.5) * 0.35)[head]
        fl = self._flame(self.X, self.Y, mx, my, t)
        m = fl > 0.22
        base = np.clip(1.0 - (my + 12.0 - self.Y) / 18.0, 0.0, 1.0)  # the blue bottom of the flame
        G[m] = self.pick("flame", fl)[m]
        C[m] = (FIRE(0.45 + 0.5 * fl) * (1.1 * fl)[..., None] + BLUE_FLAME * (base * fl)[..., None])[m]

    def _glow(self, t, rays):
        """Wide soft light, at quarter resolution: the fire's glow, the burst and the rays."""
        q = rays if rays is not None else np.zeros((self.qh, self.qw, 3), np.float32)
        if self.H.max() > 0.02:
            g = cv2.resize(FIRE(np.minimum(self.H, 1.2) * 0.75), (self.qw, self.qh), interpolation=cv2.INTER_LINEAR)
            q = q + cv2.GaussianBlur(g, (0, 0), 6.0 * self.s) * 0.13
        a = t - T_IGNITE
        if 0.0 <= a < 1.0:                                   # flash and shock ring when the seal bursts
            d = self.seal_d
            ring = 0.45 * math.exp(-a / 0.12) * np.exp(-((d - 650.0 * a ** 0.6) / 16.0) ** 2)
            q = q + (3.0 * math.exp(-a / 0.12) * np.exp(-(d / 110.0) ** 2) + ring)[..., None] * FLAME_TINT
        return q

    def _light(self, t, mx, my, match):
        """Small bright things in the air, at half resolution."""
        lb = self.bg.copy()
        s2 = self.s / 2.0
        if match:                                            # the match flame and its halo
            x0, x1 = int(max(0, (mx - 260) * s2)), int(min(self.lw, (mx + 260) * s2))
            y0, y1 = int(max(0, (my - 300 - PAD) * s2)), int(min(self.lh, (my + 220 - PAD) * s2))
            if x1 > x0 and y1 > y0:
                lx, ly = self.lx[y0:y1, x0:x1], self.ly[y0:y1, x0:x1]
                fl = self._flame(lx, ly, mx, my, t)
                d2 = (lx - mx) ** 2 + (ly - my + 40.0) ** 2
                halo = 0.8 * np.exp(-d2 / (2.0 * 70.0 ** 2)) + 0.25 * np.exp(-d2 / (2.0 * 30.0 ** 2))
                lb[y0:y1, x0:x1] += FIRE(0.45 + 0.45 * fl) * (1.2 * fl)[..., None] + FLAME_TINT * halo[..., None]
        for kind, trail, gain in (("spark", 4, 2.6), ("ember", 2, 1.4)):
            p = self.parts[kind]
            if not len(p):
                continue
            life = 1.0 - p[:, PAGE] / p[:, PLIFE]
            col = FIRE(p[:, PHEAT] * life ** 0.55) * (gain * np.clip(life * 4.0, 0.0, 1.0))[:, None]
            if kind == "ember":
                col *= (0.65 + 0.35 * np.sin(p[:, PAGE] * 11.0 + p[:, PSEED]))[:, None]
            for j in range(trail):                           # short motion trails
                f = j / trail
                xs = ((p[:, PX] - p[:, PVX] * f * 0.028) * s2).astype(np.int32)
                ys = ((p[:, PY] - PAD - p[:, PVY] * f * 0.028) * s2).astype(np.int32)
                ok = (xs >= 0) & (xs < self.lw) & (ys >= 0) & (ys < self.lh)
                np.add.at(lb, (ys[ok], xs[ok]), col[ok] * (1.0 - 0.7 * f))
        n = int(16 * self.s)
        for x, y, age, life in self.parts["glint"][:, [PX, PY, PAGE, PLIFE]]:
            k = 3.0 * math.sin(math.pi * age / life) ** 2
            cx, cy = int(x * s2), int((y - PAD) * s2)
            if 0 <= cy < self.lh and 0 <= cx < self.lw:      # a little four-pointed star
                a0, a1 = max(0, cx - n), min(self.lw, cx + n + 1)
                lb[cy, a0:a1] += WHITE * (k * np.exp(-np.abs(np.arange(a0, a1) - cx) / (4.0 * self.s)))[:, None]
                a0, a1 = max(0, cy - n), min(self.lh, cy + n + 1)
                lb[a0:a1, cx] += WHITE * (k * np.exp(-np.abs(np.arange(a0, a1) - cy) / (4.0 * self.s)))[:, None]
        return cv2.GaussianBlur(lb, (0, 0), 0.9)

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

    def _tonemap(self, x, exposure):
        """Light values -> screen colours through a film-like curve, with a little grain."""
        k = TONE_E * exposure
        cv2.multiply(x, (k, k, k, 0.0), dst=x)
        cv2.add(x, (1.0, 1.0, 1.0, 0.0), dst=x)
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
    # at least tablet size: the window shows the part of the picture where the story happens
    # (the empty starry sky above and below is left out), as big as the screen allows
    top, bottom = 410.0, 1670.0
    ch = min(18, int((screen_h - 60) * CH / (bottom - top)), 2 * (screen_w // COLS))
    ch = max(6, ch // 2 * 2)
    r0 = int((top - PAD) // CH) // 2 * 2                     # an even row, so the light layers line up
    r1 = min(ROWS, math.ceil((bottom - PAD) / CH))
    draw = min(ch, 12)                                       # drawn a little smaller and scaled up: stays smooth
    film = Film(draw // 2, draw, message=message, view=(r0, r1))
    size = (COLS * ch // 2, (r1 - r0) * ch)                  # window size
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
            if draw < ch:
                frame = cv2.resize(frame, size, interpolation=cv2.INTER_CUBIC)
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
    film = Film(9, 18, message=message)
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
