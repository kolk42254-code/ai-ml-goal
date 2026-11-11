#!/usr/bin/env python3
"""Draws the app icon and the start-up picture for Battle World.

Run from the project folder:   python3 tools/make_icons.py
Needs the Pillow library:      pip install pillow

It writes into assets/ui/:
  icon_192.png      the normal app icon
  icon_fg_432.png   front layer of the Android "adaptive" icon (the crosshair)
  icon_bg_432.png   back layer of the adaptive icon (sunset sky and skyline)
  splash.png        the picture shown while the game starts
"""
from PIL import Image, ImageDraw, ImageFont

OUT = "assets/ui/"
SKY = [(0.0, (27, 42, 74)), (0.6, (232, 116, 59)), (1.0, (255, 197, 107))]
DARK = (13, 19, 33, 255)


def sky_color(t):
    for (t0, c0), (t1, c1) in zip(SKY, SKY[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            return tuple(round(a + (b - a) * k) for a, b in zip(c0, c1)) + (255,)
    return SKY[-1][1] + (255,)


def background(size):
    img = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(img)
    for y in range(size):
        d.line([(0, y), (size, y)], fill=sky_color(y / (size - 1)))
    # skyline: (left, top, width) as shares of the icon size
    for left, top, width in [(0.06, 0.52, 0.13), (0.21, 0.38, 0.12), (0.35, 0.60, 0.10),
                             (0.47, 0.46, 0.09), (0.66, 0.43, 0.12), (0.80, 0.56, 0.14)]:
        d.rectangle([left * size, top * size, (left + width) * size, size], fill=DARK)
    return img


def crosshair(size, radius, width):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size / 2
    d.ellipse([c - radius, c - radius, c + radius, c + radius], outline=(255, 255, 255, 255), width=width)
    gap, arm = radius * 0.45, radius * 1.38
    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        d.line([(c + dx * gap, c + dy * gap), (c + dx * arm, c + dy * arm)], fill=(255, 255, 255, 255), width=width)
    dot = radius * 0.16
    d.ellipse([c - dot, c - dot, c + dot, c + dot], fill=(255, 59, 59, 255))
    return img


def rounded(img, corner):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1], corner, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


# Draw big, then shrink: this gives smooth edges.
big = 768
icon = Image.alpha_composite(background(big), crosshair(big, big * 0.225, round(big * 0.04)))
rounded(icon, round(big * 0.19)).resize((192, 192), Image.LANCZOS).save(OUT + "icon_192.png")
background(big).resize((432, 432), Image.LANCZOS).save(OUT + "icon_bg_432.png")
# The launcher may cut the icon to a circle, so the crosshair stays inside the middle two thirds.
crosshair(big, big * 0.15, round(big * 0.028)).resize((432, 432), Image.LANCZOS).save(OUT + "icon_fg_432.png")

splash = Image.new("RGBA", (1024, 320), (0, 0, 0, 0))
d = ImageDraw.Draw(splash)
title = ImageFont.truetype("assets/fonts/Rajdhani-Bold.ttf", 150)
small = ImageFont.truetype("assets/fonts/Rajdhani-SemiBold.ttf", 40)
d.text((512, 130), "BATTLE WORLD", font=title, fill=(255, 179, 31, 255), anchor="mm")
d.text((512, 245), "L O A D I N G", font=small, fill=(158, 173, 189, 255), anchor="mm")
splash.save(OUT + "splash.png")
print("icons written to", OUT)
