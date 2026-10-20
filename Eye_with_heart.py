import os
import sys
import time
import numpy as np


def lerp(a, b, t):
    return a + (b - a) * t


def render_skin_and_lids(tx, ty, gx, gy, rx, ry, upper, du, dl, eo):
    # Exact skin & eyelid shader math visible in eye.py
    n = np.sin(tx * 180 + ty * 120 + 100) * np.cos(tx * 95 - ty * 140)
    base_skin = np.array([0.62, 0.40, 0.29], np.float32)
    col = base_skin * (0.86 + 0.08 * tx)[..., None] + 0.03 * n[..., None]

    # Orbital socket & lid shading
    socket = np.exp(-((rx / 0.90) ** 2 + ((ry + 0.05) / 0.62) ** 2))
    col *= (0.55 + 0.45 * socket)[..., None]
    col *= (1.0 - 0.22 * np.exp(-((ry - 0.16) / 0.20) ** 2) * (1.0 - eo))[..., None]

    # Upper & lower eyelid highlights
    hl_u = np.exp(-((du - 0.07) / 0.028) ** 2) * upper
    hl_l = np.exp(-((dl - 0.05) / 0.04) ** 2) * (1.0 - upper)
    lid_tone = hl_u * 0.22 + hl_l * 0.14
    col += np.array([0.92, 0.72, 0.56], np.float32) * lid_tone[..., None]

    # Upper eyelid crease
    cr_pos = 0.11 + 0.09 * eo
    cr = np.exp(-((du - cr_pos) / (0.018 + 0.008 * (1.0 - eo))) ** 2) * upper * np.exp(-(tx / 0.58) ** 2)
    col = lerp(col, np.array([0.16, 0.09, 0.06], np.float32), (cr * 0.68)[..., None])

    # Upper lash line & eyelashes
    shb = np.exp(-(tx / 0.52) ** 2)
    lb = np.clip(1.0 - du / (0.048 + 0.012 * shb + 1e-5), 0.0, 1.0) * (du >= 0) * upper * shb
    hair = 0.65 + 0.35 * np.sin(tx * 210 + ry * 35)
    col = lerp(col, np.array([0.05, 0.03, 0.02], np.float32), np.clip(lb * hair, 0.0, 0.92)[..., None])

    # Lower lash line
    line = np.exp(-((dl - 0.011) / 0.012) ** 2) * (dl >= 0) * (1.0 - upper) * np.exp(-(tx / 0.50) ** 2)
    col = lerp(col, np.array([0.09, 0.06, 0.05], np.float32), np.clip(line * (1.0 - 0.3 * eo), 0.0, 0.75)[..., None])

    # Eyebrow
    brow_y = -0.28 + 0.14 * tx ** 2 - 0.04 * tx
    brow = np.exp(-((ry - brow_y) / 0.055) ** 2) * np.exp(-((tx - 0.02) / 0.62) ** 2)
    brow_hair = 0.72 + 0.28 * np.sin(tx * 160 + ty * 40)
    col = lerp(col, np.array([0.10, 0.07, 0.05], np.float32), np.clip(brow * brow_hair * 0.85, 0.0, 0.90)[..., None])

    return np.clip(col, 0.0, 1.0)


def render_eyeball(tx, ty, gx, gy, eo):
    # Sclera with spherical shading and blood vessels hint
    r_eye = np.sqrt((tx / 0.55) ** 2 + (ty / 0.28) ** 2)
    sclera_shade = np.clip(1.0 - 0.42 * (r_eye ** 1.6), 0.25, 1.0)
    sclera = np.array([0.86, 0.83, 0.80], np.float32) * sclera_shade[..., None]

    # Caruncle (inner corner of the eye)
    cg = np.exp(-(((tx + 0.50) / 0.08) ** 2 + ((ty - 0.02) / 0.05) ** 2)) * (1.0 - eo * 0.3)
    sclera = lerp(sclera, np.array([0.62, 0.32, 0.28], np.float32), (cg * 0.75)[..., None])

    # Iris geometry & radial fibers
    ir_r = np.sqrt(gx ** 2 + gy ** 2)
    theta = np.arctan2(gy, gx)
    iris_radius = 0.235
    pupil_radius = 0.088

    rn = np.clip((ir_r - pupil_radius) / (iris_radius - pupil_radius + 1e-5), 0.0, 1.0)
    fibers = (
        0.50 * np.sin(theta * 42.0 + np.sin(rn * 10.0) * 1.5)
        + 0.30 * np.cos(theta * 78.0 - rn * 8.0)
        + 0.20 * np.sin(theta * 130.0)
    )

    inner_amber = np.array([0.78, 0.46, 0.20], np.float32)
    outer_brown = np.array([0.42, 0.23, 0.11], np.float32)
    iris_col = lerp(inner_amber, outer_brown, (rn ** 0.8)[..., None])
    iris_col += np.array([0.22, 0.14, 0.06], np.float32) * (fibers * (1.0 - rn * 0.5))[..., None]

    # Collarette ring & dark limbal ring
    collarette = np.exp(-((rn - 0.32) / 0.12) ** 2)
    iris_col += np.array([0.20, 0.11, 0.04], np.float32) * collarette[..., None]
    limbal = np.clip((rn - 0.76) / 0.24, 0.0, 1.0) ** 1.5
    iris_col *= (1.0 - 0.82 * limbal)[..., None]

    # Blend iris onto sclera
    iris_mask = np.clip((iris_radius - ir_r) / 0.012, 0.0, 1.0)
    eye_col = lerp(sclera, iris_col, iris_mask[..., None])

    # Pupil
    pupil_mask = np.clip((pupil_radius - ir_r) / 0.008, 0.0, 1.0)
    eye_col = lerp(eye_col, np.array([0.01, 0.01, 0.015], np.float32), pupil_mask[..., None])

    # Specular catchlights
    spec1 = np.exp(-(((gx + 0.055) / 0.028) ** 2 + ((gy + 0.050) / 0.020) ** 2))
    spec2 = np.exp(-(((gx - 0.065) / 0.014) ** 2 + ((gy - 0.045) / 0.011) ** 2)) * 0.55
    spec = np.clip(spec1 + spec2, 0.0, 1.0)
    eye_col = lerp(eye_col, np.array([0.98, 0.96, 0.94], np.float32), spec[..., None])

    return np.clip(eye_col, 0.0, 1.0), pupil_mask


def render_cosmos_and_heart(ux, uy, t, zoom_alpha):
    # Starfield & crosshair sparkles inside the zoomed pupil
    col = np.zeros(ux.shape + (3,), dtype=np.float32)
    if zoom_alpha <= 0.01:
        return col

    # Deterministic twinkling stars & crosshairs
    stars = [
        (-0.68, -0.52, 1.0, 0.0), (0.62, -0.45, 0.9, 1.2),
        (-0.55, 0.42, 0.85, 2.4), (0.58, 0.48, 1.0, 3.1),
        (-0.28, -0.68, 0.7, 0.7), (0.32, 0.65, 0.75, 1.9),
        (-0.82, 0.05, 0.9, 4.0),  (0.78, -0.08, 0.8, 2.8),
        (-0.38, -0.22, 0.5, 5.1), (0.42, -0.20, 0.5, 3.7),
    ]
    for sx, sy, size, phase in stars:
        twinkle = 0.55 + 0.45 * np.sin(t * 4.5 + phase)
        dx = np.abs(ux - sx)
        dy = np.abs(uy - sy)
        cross_h = np.exp(-(dy / 0.009) ** 2) * np.exp(-(dx / (0.055 * size * twinkle)) ** 2)
        cross_v = np.exp(-(dx / 0.014) ** 2) * np.exp(-(dy / (0.055 * size * twinkle)) ** 2)
        core = np.exp(-((dx ** 2 + dy ** 2) / (0.018 * size) ** 2))
        spark = np.clip(cross_h + cross_v + core, 0.0, 1.0) * twinkle
        col = col + (np.array([0.90, 0.92, 1.0], dtype=np.float32) * spark[..., None])

    # Faint background dust stars
    grid_hash = np.sin( np.floor(ux * 28.0) * 127.1 + np.floor(uy * 28.0) * 311.7 ) * 43758.5453
    dust_prob = grid_hash - np.floor(grid_hash)
    cell_x = (ux * 28.0) - np.floor(ux * 28.0) - 0.5
    cell_y = (uy * 28.0) - np.floor(uy * 28.0) - 0.5
    dust = (dust_prob > 0.965) * np.exp(-(cell_x ** 2 + cell_y ** 2) / 0.08)
    dust_twinkle = 0.5 + 0.5 * np.sin(t * 3.0 + dust_prob * 20.0)
    col += np.array([0.65, 0.70, 0.85], np.float32) * (dust * dust_twinkle * 0.55)[..., None]

    # Glowing beating heart in the center
    heart_appear = np.clip((zoom_alpha - 0.35) / 0.65, 0.0, 1.0)
    if heart_appear > 0.0:
        beat = 1.0 + 0.06 * np.sin(t * 6.5) ** 4 + 0.03 * np.sin(t * 6.5 + 0.4)
        scale = 0.36 * beat * (0.4 + 0.6 * heart_appear)
        hx = ux / (scale + 1e-5)
        hy = -uy / (scale + 1e-5) + 0.15

        # Implicit heart equation: (x^2 + y^2 - 1)^3 - x^2 * y^3 <= 0
        f = (hx ** 2 + hy ** 2 - 1.0) ** 3 - (hx ** 2) * (hy ** 3)
        inside = np.clip(-f * 3.5, 0.0, 1.0)

        # 3D-like volumetric shading on the heart
        depth = np.clip(1.0 - 0.38 * (hx ** 2 + (hy - 0.25) ** 2), 0.2, 1.0)
        scanline = 0.78 + 0.22 * np.sin(uy * 95.0 - t * 6.0)
        heart_rgb = (
            np.array([0.92, 0.24, 0.38], np.float32) * (depth * scanline)[..., None]
            + np.array([0.35, 0.05, 0.12], np.float32) * np.exp(-((hx + 0.3) ** 2 + (hy - 0.4) ** 2) / 0.25)[..., None]
        )

        # Soft outer aura around the heart
        glow = np.exp(-np.maximum(f, 0.0) * 1.8) * 0.35
        col += np.array([0.75, 0.14, 0.28], np.float32) * (glow * heart_appear)[..., None]
        col = lerp(col, heart_rgb, (inside * heart_appear)[..., None])

    return np.clip(col * zoom_alpha, 0.0, 1.0)


def main():
    # Read this script's own source code to populate the ASCII character matrix
    try:
        with open(__file__, "r", encoding="utf-8") as f:
            code_text = " ".join(line.strip() for line in f if line.strip())
    except Exception:
        code_text = "np.array([0.62, 0.40, 0.29], np.float32) * np.exp(-((rx / 0.90) ** 2)) "

    sys.stdout.write("\033[2J\033[?25l")
    sys.stdout.flush()

    t0 = time.perf_counter()
    try:
        while True:
            cols, rows = os.get_terminal_size()
            rows = max(24, rows - 1)
            cols = max(60, cols)

            t = (time.perf_counter() - t0) % 14.5

            # Timeline phases matching the video:
            # 0.0 - 1.2s: Eye blinks open
            # 1.2 - 5.2s: Eye looks around subtly
            # 5.2 - 9.5s: Smooth zoom deep into the pupil -> stars & heart
            # 9.5 - 14.5s: Heart beats in starry pupil
            if t < 1.2:
                eo = np.clip((t - 0.2) / 0.85, 0.0, 1.0) ** 1.5
            else:
                eo = 1.0 - 0.85 * np.exp(-((t - 3.1) / 0.11) ** 2)

            zoom_progress = np.clip((t - 5.0) / 4.2, 0.0, 1.0)
            zoom_smooth = zoom_progress * zoom_progress * (3.0 - 2.0 * zoom_progress)
            zoom = 1.0 * ((0.065 / 1.0) ** zoom_smooth)
            cosmos_alpha = np.clip((zoom_smooth - 0.28) / 0.55, 0.0, 1.0)

            # Gaze offset (settles to center as zoom begins)
            gaze_damp = 1.0 - zoom_smooth
            gaze_x = (0.045 * np.sin(t * 1.7) + 0.02 * np.cos(t * 3.1)) * gaze_damp
            gaze_y = (0.020 * np.cos(t * 1.3)) * gaze_damp

            # Screen coordinate grids
            aspect = (cols / rows) * 0.5
            ux = np.linspace(-aspect, aspect, cols, dtype=np.float32)[None, :]
            uy = np.linspace(-1.0, 1.0, rows, dtype=np.float32)[:, None]

            tx = ux * zoom + gaze_x * (1.0 - gaze_damp)
            ty = uy * zoom + gaze_y * (1.0 - gaze_damp)
            gx = tx - gaze_x
            gy = ty - gaze_y
            rx, ry = tx, ty

            # Upper and lower eyelid curves
            arch = np.clip(1.0 - (tx / 0.54) ** 2, 0.0, 1.0)
            y_upper = -0.23 * eo * (arch ** 0.85) + 0.03 * (1.0 - eo)
            y_lower = 0.16 * (0.30 + 0.70 * eo) * (arch ** 0.95) + 0.03 * (1.0 - eo)

            du = y_upper - ry
            dl = ry - y_lower
            upper = (ry < 0.5 * (y_upper + y_lower)).astype(np.float32)
            inside_eye = (ry > y_upper) & (ry < y_lower) & (np.abs(tx) < 0.54)

            # Compose skin, eyeball, and inner-pupil cosmos + heart
            skin_col = render_skin_and_lids(tx, ty, gx, gy, rx, ry, upper, du, dl, eo)
            eye_col, pupil_mask = render_eyeball(tx, ty, gx, gy, eo)

            # Eyelid shadow cast onto the top of the eyeball
            lid_shadow = np.clip((ry - y_upper) / 0.045, 0.0, 1.0)
            eye_col *= (0.35 + 0.65 * lid_shadow)[..., None]

            eye_blend = np.clip(
                np.minimum(ry - y_upper, y_lower - ry) / (0.015 * zoom + 1e-5),
                0.0,
                1.0,
            ) * (np.abs(tx) < 0.54)
            frame_col = lerp(skin_col, eye_col, eye_blend[..., None])

            if cosmos_alpha > 0.0:
                cosmos_col = render_cosmos_and_heart(ux, uy, t, cosmos_alpha)
                in_pupil = np.clip(pupil_mask * eye_blend, 0.0, 1.0)
                frame_col = lerp(
                    frame_col,
                     np.maximum(frame_col * (1.0 - cosmos_alpha), cosmos_col),
                    in_pupil[..., None],
                )

            # Convert float RGB [0, 1] to 0-255 uint8
            rgb = (np.clip(frame_col, 0.0, 1.0) * 255.0).astype(np.uint8)
            lum = 0.299 * frame_col[..., 0] + 0.587 * frame_col[..., 1] + 0.114 * frame_col[..., 2]

            # Build source-code character buffer for this terminal size
            total_chars = rows * cols
            repeats = (total_chars // len(code_text)) + 2
            char_pool = (code_text * repeats)[:total_chars]

            out_lines = ["\033[H"]
            idx = 0
            for r in range(rows):
                row_rgb = rgb[r]
                row_lum = lum[r]
                line_parts = []
                for c in range(cols):
                    if row_lum[c] < 0.025:
                        line_parts.append(" ")
                    else:
                        ch = char_pool[idx]
                        R, G, B = row_rgb[c]
                        line_parts.append(f"\033[38;2;{R};{G};{B}m{ch}")
                    idx += 1
                out_lines.append("".join(line_parts) + "\033[0m")

            sys.stdout.write("\n".join(out_lines))
            sys.stdout.flush()
            time.sleep(1.0 / 30.0)

    except KeyboardInterrupt:
        sys.stdout.write("\033[0m\033[?25h\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()