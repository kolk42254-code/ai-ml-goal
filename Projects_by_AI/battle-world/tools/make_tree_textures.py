#!/usr/bin/env python3
"""Paints the leaf pictures for the trees in Battle World.

Run from the project folder:   python3 tools/make_tree_textures.py
Needs the Pillow library:      pip install pillow

Each tree kind gets one 512 x 512 picture with four different leaf clumps
(a 2 x 2 grid). In the game these clumps are put on many small flat cards
around the branches, which together look like a full crown of leaves.

  leaves_cherry.png    pink blossom
  leaves_maple.png     orange and red autumn leaves
  leaves_oak.png       green oak leaves
  leaves_oak_bare.png  twigs with a few brown leaves left
  leaves_spruce.png    spruce branches with needles
"""
import math
import random
from PIL import Image, ImageDraw

OUT = "assets/textures/trees/"
S = 512          # one clump is painted at 512 px and shrunk to 256 for smooth edges
HALF = S // 2


def shade(color, k):
    return tuple(max(0, min(255, round(c * k))) for c in color[:3]) + (255,)


def twigs(draw, rng, color, start, count, length, width, spread=math.tau, direction=0.0, depth=3):
    """Draws branching twigs from `start` and returns points along them (places for leaves)."""
    points = []

    def grow(p, angle, seg, w, level):
        steps = 3
        for _ in range(steps):
            angle += rng.uniform(-0.35, 0.35)
            q = (p[0] + math.cos(angle) * seg / steps, p[1] + math.sin(angle) * seg / steps)
            draw.line([p, q], fill=color, width=max(1, round(w)))
            p = q
            points.append((p, level))
        if level < depth:
            for _ in range(rng.choice([1, 2, 2, 3])):
                grow(p, angle + rng.uniform(-0.9, 0.9), seg * rng.uniform(0.55, 0.8), w * 0.62, level + 1)

    for i in range(count):
        a = direction + spread * (i + rng.uniform(-0.3, 0.3)) / count
        grow(start, a, length * rng.uniform(0.75, 1.1), width, 1)
    return points


def rotate(points, cx, cy, size, angle):
    c, s = math.cos(angle), math.sin(angle)
    return [(cx + (x * c - y * s) * size, cy + (x * s + y * c) * size) for x, y in points]


MAPLE = [(0, -1.0), (0.16, -0.5), (0.6, -0.72), (0.46, -0.28), (0.95, -0.12), (0.52, 0.12),
         (0.6, 0.5), (0.2, 0.34), (0.05, 0.75), (-0.05, 0.75), (-0.2, 0.34), (-0.6, 0.5),
         (-0.52, 0.12), (-0.95, -0.12), (-0.46, -0.28), (-0.6, -0.72), (-0.16, -0.5)]


def oak_leaf():
    pts = []
    n = 16
    for i in range(n + 1):
        t = i / n
        w = 0.36 * math.sin(math.pi * t) ** 0.6 * (1.0 + 0.32 * math.sin(t * 5.0 * math.tau))
        pts.append((w, t * 2.0 - 1.0))
    for i in range(n, -1, -1):
        t = i / n
        w = 0.36 * math.sin(math.pi * t) ** 0.6 * (1.0 + 0.32 * math.sin(t * 5.0 * math.tau + 1.3))
        pts.append((-w, t * 2.0 - 1.0))
    return pts


OAK = oak_leaf()


def in_clump(rng, x, y, radius=0.44):
    """True inside an uneven round clump in the middle of the tile."""
    dx, dy = x / S - 0.5, y / S - 0.5
    a = math.atan2(dy, dx)
    edge = radius * (1.0 + 0.16 * math.sin(a * 3.0 + rng.clump_a) + 0.10 * math.sin(a * 7.0 + rng.clump_b))
    return math.hypot(dx, dy) < edge


def leaf_spots(rng, twig_points, count, jitter, on_twigs=0.7):
    """Places for leaves: most hang near twigs, the rest fill the clump."""
    spots = []
    tries = 0
    while len(spots) < count and tries < count * 30:
        tries += 1
        if twig_points and rng.random() < on_twigs:
            (px, py), level = rng.choice(twig_points)
            x, y = px + rng.gauss(0, jitter), py + rng.gauss(0, jitter)
        else:
            x, y = rng.uniform(0, S), rng.uniform(0, S)
        if in_clump(rng, x, y):
            spots.append((x, y))
    return spots


def clump_cherry(rng):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pts = twigs(d, rng, (48, 30, 30, 255), (HALF, HALF), 6, S * 0.19, 7)
    palette = [(246, 150, 186), (240, 126, 170), (250, 178, 206), (230, 106, 156), (252, 204, 222)]
    spots = leaf_spots(rng, pts, 620, S * 0.04)
    for layer, (x, y) in enumerate(spots):
        k = 0.74 + 0.34 * layer / len(spots)          # blossoms painted last are brightest (they are in front)
        col = rng.choice(palette)
        size = rng.uniform(6.5, 9.5)
        turn = rng.uniform(0, math.tau)
        for p in range(5):
            a = turn + p * math.tau / 5
            cx, cy = x + math.cos(a) * size * 0.62, y + math.sin(a) * size * 0.62
            r = size * 0.56
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=shade(col, k))
        r = size * 0.26
        d.ellipse([x - r, y - r, x + r, y + r], fill=shade((214, 84, 128), k))
    return img


def clump_leaves(rng, shape, palette, twig_color, count, size_range, twig_count=6, on_twigs=0.7, rare=None):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pts = twigs(d, rng, twig_color, (HALF, HALF), twig_count, S * 0.19, 6)
    spots = leaf_spots(rng, pts, count, S * 0.04, on_twigs)
    for layer, (x, y) in enumerate(spots):
        k = 0.62 + 0.48 * layer / max(1, len(spots))
        col = rng.choice(palette)
        if rare and rng.random() < 0.08:
            col = rng.choice(rare)
        size = rng.uniform(*size_range)
        poly = rotate(shape, x, y, size, rng.uniform(0, math.tau))
        d.polygon(poly, fill=shade(col, k * rng.uniform(0.9, 1.08)))
    return img


def clump_bare(rng):
    """Late-autumn oak: a net of fine twigs with only a few brown leaves left."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pts = twigs(d, rng, (58, 46, 40, 255), (HALF, HALF), 11, S * 0.2, 6, depth=5)
    palette = [(150, 104, 58), (170, 120, 66), (122, 86, 50), (186, 140, 84), (140, 92, 46)]
    spots = leaf_spots(rng, pts, 70, S * 0.02, 0.97)
    for (x, y) in spots:
        size = rng.uniform(11, 17)
        poly = rotate(OAK, x, y, size, rng.uniform(0, math.tau))
        d.polygon(poly, fill=shade(rng.choice(palette), rng.uniform(0.8, 1.1)))
    return img


def needles(d, rng, p, q, length, palette, density=1.0):
    """Short needles on both sides of the twig from p to q."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    dist = math.hypot(dx, dy)
    if dist < 1:
        return
    ux, uy = dx / dist, dy / dist
    n = int(dist / 3.2 * density)
    for i in range(n):
        t = (i + rng.random()) / n
        bx, by = p[0] + dx * t, p[1] + dy * t
        for side in (-1, 1):
            a = math.atan2(uy, ux) + side * rng.uniform(0.6, 1.15)
            ln = length * rng.uniform(0.7, 1.1)
            d.line([(bx, by), (bx + math.cos(a) * ln, by + math.sin(a) * ln)],
                   fill=shade(rng.choice(palette), rng.uniform(0.8, 1.15)), width=3)


def spruce_spray(rng, hanging=False):
    """One spruce branch. Normal: base at the left, tip at the right. Hanging: strands from the top edge."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    palette = [(26, 62, 40), (34, 78, 48), (22, 52, 36), (46, 92, 56), (30, 70, 52)]
    wood = (52, 38, 28, 255)
    if hanging:
        for i in range(9):
            x = S * (0.08 + 0.84 * (i + rng.uniform(-0.3, 0.3)) / 8)
            y, length = 0.0, S * rng.uniform(0.45, 0.97)
            p = (x, y)
            for s in range(6):
                q = (p[0] + rng.uniform(-9, 9), p[1] + length / 6)
                d.line([p, q], fill=wood, width=3)
                needles(d, rng, p, q, 15, palette, 1.3)
                p = q
        return img
    spine = []
    for i in range(13):
        t = i / 12
        spine.append((S * (0.02 + 0.96 * t), S * (0.5 + 0.035 * math.sin(t * 3.0 + rng.clump_a))))
    for i in range(12):
        d.line([spine[i], spine[i + 1]], fill=wood, width=5 if i < 6 else 3)
    for i in range(1, 12):
        t = i / 12
        # side twigs are longest a third of the way along, which gives the feather shape
        reach = S * 0.36 * math.sin(math.pi * min(1.0, t * 0.9 + 0.12)) ** 0.8 * rng.uniform(0.8, 1.1)
        for side in (-1, 1):
            a = side * rng.uniform(0.75, 1.0)
            p = spine[i]
            segs = 4
            for s in range(segs):
                q = (p[0] + math.cos(a) * reach / segs, p[1] + math.sin(a) * reach / segs)
                d.line([p, q], fill=wood, width=2)
                needles(d, rng, p, q, 14, palette, 1.25)
                a *= 0.93
                p = q
    for i in range(12):
        needles(d, rng, spine[i], spine[i + 1], 15, palette, 1.3)
    return img


def atlas(name, makers, back_color):
    """Puts four clumps in a 2 x 2 grid. See-through pixels get the leaf colour, so edges do not turn dark."""
    sheet = Image.new("RGBA", (S * 2, S * 2), (0, 0, 0, 0))
    for i, maker in enumerate(makers):
        rng = random.Random(1000 + i * 77 + sum(map(ord, name)))
        rng.clump_a, rng.clump_b = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
        sheet.paste(maker(rng), ((i % 2) * S, (i // 2) * S))
    small = sheet.resize((S, S), Image.LANCZOS)
    back = Image.new("RGBA", small.size, back_color + (0,))
    pixels = small.load()
    out = back.load()
    for y in range(small.size[1]):
        for x in range(small.size[0]):
            r, g, b, a = pixels[x, y]
            if a > 0:
                k = a / 255.0
                out[x, y] = (round(r * k + back_color[0] * (1 - k)), round(g * k + back_color[1] * (1 - k)),
                             round(b * k + back_color[2] * (1 - k)), a)
    back.save(OUT + name)
    print("wrote", OUT + name)


def far_pictures(photo_dir):
    """Turns the raw tree photos from tools/bake_trees.gd into the small far-away pictures."""
    import glob
    import os
    for path in sorted(glob.glob(os.path.join(photo_dir, "far_*_raw.png"))):
        name = os.path.basename(path).replace("_raw", "")
        img = Image.open(path).convert("RGBA")
        scale = 256.0 / img.size[1]
        img = img.resize((max(8, round(img.size[0] * scale / 4) * 4), 256), Image.LANCZOS)
        # Fill the see-through pixels with the tree's average colour, so edges do not turn dark.
        px = img.load()
        total, count = [0, 0, 0], 0
        for y in range(img.size[1]):
            for x in range(img.size[0]):
                r, g, b, a = px[x, y]
                if a > 128:
                    total[0] += r
                    total[1] += g
                    total[2] += b
                    count += 1
        mean = tuple(round(c / max(1, count)) for c in total)
        for y in range(img.size[1]):
            for x in range(img.size[0]):
                r, g, b, a = px[x, y]
                k = a / 255.0
                px[x, y] = (round(r * k + mean[0] * (1 - k)), round(g * k + mean[1] * (1 - k)),
                            round(b * k + mean[2] * (1 - k)), a)
        img.save(OUT + name)
        print("wrote", OUT + name, img.size)


import sys
if len(sys.argv) > 2 and sys.argv[1] == "far":
    far_pictures(sys.argv[2])
    sys.exit(0)

maple_palette = [(232, 84, 22), (245, 120, 25), (214, 52, 20), (250, 150, 40), (190, 40, 18), (238, 100, 20), (172, 34, 16)]
oak_palette = [(50, 80, 28), (64, 92, 30), (40, 66, 24), (84, 102, 36), (34, 56, 22), (74, 96, 32)]

atlas("leaves_cherry.png", [clump_cherry] * 4, (240, 140, 180))
atlas("leaves_maple.png",
      [lambda r: clump_leaves(r, MAPLE, maple_palette, (60, 40, 32, 255), 300, (17, 26),
                              rare=[(246, 190, 60), (160, 140, 44)])] * 4, (232, 96, 24))
atlas("leaves_oak.png",
      [lambda r: clump_leaves(r, OAK, oak_palette, (58, 46, 36, 255), 380, (17, 25),
                              rare=[(124, 126, 46), (140, 134, 48)])] * 4, (58, 86, 30))
atlas("leaves_oak_bare.png", [clump_bare] * 4, (84, 64, 50))
atlas("leaves_spruce.png", [spruce_spray, spruce_spray, lambda r: spruce_spray(r, True), spruce_spray], (30, 68, 44))
