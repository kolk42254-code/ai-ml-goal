import os
import sys
import time
import numpy as np


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(edge0, edge1, x):
    t = np.clip((x - edge0) / (edge1 - edge0 + 1e-6), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def asym_blink(t, blink_time):
    # Asymmetric physiological blink (rapid 55ms closure, slower 130ms opening)
    dt = t - blink_time
    close_part = np.exp(-((np.minimum(dt, 0.0)) / 0.055) ** 2) * (dt <= 0)
    open_part = np.exp(-((np.maximum(dt, 0.0)) / 0.130) ** 2) * (dt > 0)
    return close_part + open_part


def get_eye_state(t_raw):
    # Smoothly open the eye when launched, then run a seamless 10-second loop
    if t_raw < 1.0:
        eo = smoothstep(0.10, 0.90, t_raw) ** 1.3
        t = 0.0
    else:
        t = (t_raw - 1.0) % 10.0
        b1 = asym_blink(t, 2.1)
        b2 = asym_blink(t, 5.8)
        b3 = asym_blink(t, 8.6)
        blink = np.clip(b1 + b2 + b3, 0.0, 1.0)
        eo = 1.0 - 0.94 * blink

    # Fixed large close-up scale (no zoom-in transition)
    zoom = 0.40

    # Subtle saccadic glances that return to looking straight at you (0.0, 0.0)
    s1 = smoothstep(0.80, 0.96, t)
    s2 = smoothstep(1.75, 1.92, t)
    s3 = smoothstep(2.35, 2.52, t)
    s4 = smoothstep(3.40, 3.58, t)  # locks back straight at viewer
    s5 = smoothstep(6.20, 6.36, t)  # brief subtle glance
    s6 = smoothstep(7.20, 7.38, t)  # locks back straight at viewer

    gx_target = 0.060 * s1 - 0.115 * s2 + 0.080 * s3 - 0.025 * s4 - 0.040 * s5 + 0.040 * s6
    gy_target = -0.020 * s1 + 0.032 * s2 - 0.012 * s3 + 0.015 * s5 - 0.015 * s6

    # Subtle ocular micro-drift so direct eye contact feels alive
    drift_x = 0.0035 * np.sin(t_raw * 6.5) + 0.0020 * np.cos(t_raw * 11.3)
    drift_y = 0.0025 * np.cos(t_raw * 5.9)
    gaze_x = gx_target + drift_x
    gaze_y = gy_target + drift_y

    # Dynamic pupil reactivity (post-blink constriction + natural hippus oscillation)
    r1 = -0.011 * np.exp(-((t - 2.35) / 0.45) ** 2) * (t > 2.1)
    r2 = -0.011 * np.exp(-((t - 6.05) / 0.45) ** 2) * (t > 5.8)
    r3 = -0.011 * np.exp(-((t - 8.85) / 0.45) ** 2) * (t > 8.6)
    hippus = 0.004 * np.sin(t_raw * 2.8) + 0.002 * np.cos(t_raw * 5.1)
    pupil_r = 0.086 + r1 + r2 + r3 + hippus

    return eo, zoom, gaze_x, gaze_y, pupil_r


def render_skin_and_lids(tx, ty, gx, gy, rx, ry, upper, du, dl, eo):
    # Multi-frequency skin micro-texture
    n1 = np.sin(tx * 180.0 + ty * 120.0 + 100.0) * np.cos(tx * 95.0 - ty * 140.0)
    n2 = np.sin(tx * 340.0 - ty * 280.0) * 0.5
    n = 0.7 * n1 + 0.3 * n2

    # Warm human skin tone with reddish subsurface scattering (SSS) around the eyelids
    base_skin = np.array([0.64, 0.41, 0.30], np.float32)
    sss_tone = np.array([0.76, 0.36, 0.28], np.float32)
    sss_weight = np.exp(-((rx / 0.55) ** 2 + (ry / 0.35) ** 2)) * 0.25
    col = lerp(base_skin, sss_tone, sss_weight[..., None])
    col = col * (0.86 + 0.08 * tx)[..., None] + 0.022 * n[..., None]

    # Orbital socket depth & lower tear-trough contour
    socket = np.exp(-((rx / 0.88) ** 2 + ((ry + 0.04) / 0.60) ** 2))
    tear_trough = np.exp(-(((rx + 0.12) / 0.38) ** 2 + ((ry - 0.22) / 0.08) ** 2)) * 0.18
    col *= (0.54 + 0.46 * socket - tear_trough)[..., None]
    col *= (1.0 - 0.22 * np.exp(-((ry - 0.16) / 0.20) ** 2) * (1.0 - eo))[..., None]

    # Eyelid highlights & wet lower waterline (tear meniscus)
    hl_u = np.exp(-((du - 0.065) / 0.026) ** 2) * upper * np.exp(-((tx - 0.04) / 0.38) ** 2)
    hl_l = np.exp(-((dl - 0.042) / 0.035) ** 2) * (1.0 - upper) * np.exp(-(tx / 0.42) ** 2)
    waterline = np.exp(-((dl - 0.006) / 0.006) ** 2) * (dl >= 0) * (1.0 - upper) * np.exp(-(tx / 0.48) ** 2)

    lid_tone = hl_u * 0.24 + hl_l * 0.15
    col += np.array([0.94, 0.74, 0.58], np.float32) * lid_tone[..., None]
    col = lerp(col, np.array([0.88, 0.62, 0.56], np.float32), (waterline * 0.65 * eo)[..., None])

    # Dynamic supratarsal eyelid crease that folds deeper as the eye opens
    cr_pos = 0.105 + 0.095 * eo - 0.02 * (tx ** 2)
    cr = np.exp(-((du - cr_pos) / (0.016 + 0.008 * (1.0 - eo))) ** 2) * upper * np.exp(-(tx / 0.58) ** 2)
    col = lerp(col, np.array([0.15, 0.08, 0.05], np.float32), (cr * 0.72)[..., None])

    # Upper lash line & radially fanning curved eyelashes
    shb = np.exp(-(tx / 0.52) ** 2)
    du_pos = np.maximum(du, 0.0)
    lash_curve = tx * 195.0 + (du_pos * 380.0) ** 1.25 * np.sign(tx - 0.05)
    hair = 0.58 + 0.42 * np.sin(lash_curve) * np.cos(tx * 110.0 - ry * 40.0)
    lb = np.clip(1.0 - du / (0.052 + 0.016 * shb + 1e-5), 0.0, 1.0) * (du >= 0) * upper * shb
    col = lerp(col, np.array([0.04, 0.025, 0.02], np.float32), np.clip(lb * hair * 1.1, 0.0, 0.94)[..., None])

    # Lower lash line & fine lower lashes
    low_lashes = 0.65 + 0.35 * np.sin(tx * 240.0 - dl * 200.0)
    line = np.exp(-((dl - 0.014) / 0.015) ** 2) * (dl >= 0) * (1.0 - upper) * np.exp(-(tx / 0.50) ** 2)
    col = lerp(col, np.array([0.08, 0.05, 0.04], np.float32), np.clip(line * low_lashes * (1.0 - 0.25 * eo), 0.0, 0.78)[..., None])

    # Eyebrow with angled hair strokes
    brow_y = -0.28 + 0.14 * (tx ** 2) - 0.04 * tx - 0.015 * eo
    brow_env = np.exp(-((ry - brow_y) / 0.055) ** 2) * np.exp(-((tx - 0.02) / 0.62) ** 2)
    brow_strokes = 0.68 + 0.32 * np.sin((tx - (ry - brow_y) * 1.8) * 175.0) * np.cos(ty * 60.0)
    col = lerp(col, np.array([0.09, 0.06, 0.045], np.float32), np.clip(brow_env * brow_strokes * 0.88, 0.0, 0.92)[..., None])

    return np.clip(col, 0.0, 1.0)


def render_eyeball(tx, ty, gx, gy, eo, pupil_r):
    # Sclera with 3D spherical shading
    r_eye = np.sqrt((tx / 0.54) ** 2 + (ty / 0.28) ** 2)
    sclera_shade = np.clip(1.0 - 0.44 * (r_eye ** 1.65), 0.22, 1.0)
    sclera = np.array([0.90, 0.87, 0.85], np.float32) * sclera_shade[..., None]

    # Fine branching conjunctival capillaries near the medial & lateral corners
    corner_mask = np.clip((np.abs(tx) - 0.24) / 0.26, 0.0, 1.0) ** 1.5
    vein_wave = np.abs(np.sin(ty * 45.0 + np.sin(tx * 28.0) * 1.8 + tx * 8.0))
    capillaries = np.exp(-(vein_wave / 0.09) ** 2) * corner_mask * (1.0 - np.clip(r_eye - 0.95, 0.0, 1.0))
    sclera = lerp(sclera, np.array([0.78, 0.28, 0.26], np.float32), (capillaries * 0.28)[..., None])

    # Medial caruncle & plica semilunaris (inner tear-duct anatomy)
    cg = np.exp(-(((tx + 0.49) / 0.075) ** 2 + ((ty - 0.015) / 0.048) ** 2)) * (1.0 - eo * 0.25)
    plica = np.exp(-(((tx + 0.42) / 0.035) ** 2 + ((ty - 0.01) / 0.09) ** 2)) * 0.45
    caruncle_col = np.array([0.68, 0.32, 0.29], np.float32)
    sclera = lerp(sclera, caruncle_col, np.clip(cg * 0.82 + plica, 0.0, 0.88)[..., None])

    # Iris geometry & multi-layered stromal fibers + crypts of Fuchs
    ir_r = np.sqrt(gx ** 2 + gy ** 2)
    theta = np.arctan2(gy, gx)
    iris_radius = 0.238

    rn = np.clip((ir_r - pupil_r) / (iris_radius - pupil_r + 1e-5), 0.0, 1.0)
    wobbled_theta = theta + 0.06 * np.sin(rn * 12.0 + theta * 5.0)
    fibers_fine = np.sin(wobbled_theta * 56.0) * np.cos(theta * 92.0 - rn * 6.0)
    fibers_coarse = np.sin(wobbled_theta * 24.0 + 1.2) * np.exp(-((rn - 0.45) / 0.32) ** 2)
    crypts = np.clip(np.sin(theta * 19.0 + rn * 8.0) * np.cos(theta * 31.0 - rn * 10.0), -1.0, 1.0)

    # Three-zone iris pigment gradient (amber pupillary zone -> hazel ciliary zone -> dark limbal ring)
    inner_amber = np.array([0.82, 0.48, 0.18], np.float32)
    mid_hazel = np.array([0.55, 0.34, 0.15], np.float32)
    outer_umber = np.array([0.28, 0.16, 0.08], np.float32)

    iris_col = lerp(inner_amber, mid_hazel, smoothstep(0.0, 0.55, rn)[..., None])
    iris_col = lerp(iris_col, outer_umber, smoothstep(0.50, 1.0, rn)[..., None])

    iris_col += np.array([0.24, 0.15, 0.06], np.float32) * ((0.6 * fibers_fine + 0.4 * fibers_coarse) * (1.0 - rn * 0.45))[..., None]
    iris_col *= (1.0 - 0.18 * np.maximum(crypts, 0.0) * (1.0 - rn * 0.5))[..., None]

    # Irregular jagged collarette & dark limbal ring
    collarette_r = 0.28 + 0.03 * np.sin(theta * 16.0) + 0.02 * np.cos(theta * 27.0)
    collarette = np.exp(-((rn - collarette_r) / 0.09) ** 2)
    iris_col += np.array([0.26, 0.14, 0.04], np.float32) * collarette[..., None]

    limbal = smoothstep(0.72, 1.0, rn) ** 1.4
    iris_col *= (1.0 - 0.84 * limbal)[..., None]

    # Internal corneal refraction caustic on the opposite side of the light source
    caustic = np.exp(-(((gx - 0.06) / 0.12) ** 2 + ((gy - 0.05) / 0.12) ** 2)) * (1.0 - limbal)
    iris_col += np.array([0.14, 0.08, 0.02], np.float32) * caustic[..., None]
    iris_col *= (0.75 + 0.25 * np.clip((gx + gy + 0.25) / 0.5, 0.0, 1.0))[..., None]

    # Blend iris onto sclera
    iris_mask = np.clip((iris_radius - ir_r) / 0.011, 0.0, 1.0)
    eye_col = lerp(sclera, iris_col, iris_mask[..., None])

    # Pupil
    pupil_mask = np.clip((pupil_r - ir_r) / 0.007, 0.0, 1.0)
    eye_col = lerp(eye_col, np.array([0.01, 0.01, 0.015], np.float32), pupil_mask[..., None])

    # Dual corneal specular catchlights (parallax-damped across the curved cornea)
    cx = gx * 0.72 + 0.058
    cy = gy * 0.72 + 0.052
    spec_main = np.exp(-((cx / 0.029) ** 2 + (cy / 0.021) ** 2) ** 1.4)
    spec_sec = np.exp(-(((gx * 0.72 - 0.068) / 0.013) ** 2 + ((gy * 0.72 - 0.046) / 0.010) ** 2)) * 0.62
    spec = np.clip(spec_main + spec_sec, 0.0, 1.0)
    eye_col = lerp(eye_col, np.array([0.99, 0.98, 0.96], np.float32), spec[..., None])

    return np.clip(eye_col, 0.0, 1.0)


def main():
    try:
        with open(__file__, "r", encoding="utf-8") as f:
            code_text = " ".join(line.strip() for line in f if line.strip())
    except Exception:
        code_text = "np.array([0.64, 0.41, 0.30], np.float32) * np.exp(-((rx / 0.88) ** 2)) "

    sys.stdout.write("\033[2J\033[?25l")
    sys.stdout.flush()

    t0 = time.perf_counter()
    try:
        while True:
            frame_start = time.perf_counter()
            cols, rows = os.get_terminal_size()
            rows = max(24, rows - 1)
            cols = max(60, cols)

            t_raw = frame_start - t0
            eo, zoom, gaze_x, gaze_y, pupil_r = get_eye_state(t_raw)

            # 2D coordinate meshgrid
            aspect = (cols / rows) * 0.5
            x_1d = np.linspace(-aspect, aspect, cols, dtype=np.float32)
            y_1d = np.linspace(-1.0, 1.0, rows, dtype=np.float32)
            ux, uy = np.meshgrid(x_1d, y_1d)

            tx = ux * zoom
            ty = uy * zoom
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

            skin_col = render_skin_and_lids(tx, ty, gx, gy, rx, ry, upper, du, dl, eo)
            eye_col = render_eyeball(tx, ty, gx, gy, eo, pupil_r)

            # Ambient occlusion shadow cast by the upper eyelid and lashes onto the eyeball
            lid_shadow = smoothstep(0.0, 0.055, ry - y_upper)
            lower_occlusion = smoothstep(0.0, 0.025, y_lower - ry)
            eye_col *= (0.32 + 0.68 * lid_shadow * (0.85 + 0.15 * lower_occlusion))[..., None]

            eye_blend = np.clip(
                np.minimum(ry - y_upper, y_lower - ry) / (0.014 * zoom + 1e-5),
                0.0,
                1.0,
            ) * (np.abs(tx) < 0.54)
            frame_col = lerp(skin_col, eye_col, eye_blend[..., None])

            rgb = (np.clip(frame_col, 0.0, 1.0) * 255.0).astype(np.uint8)
            lum = 0.299 * frame_col[..., 0] + 0.587 * frame_col[..., 1] + 0.114 * frame_col[..., 2]

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
                    if row_lum[c] < 0.022:
                        line_parts.append(" ")
                    else:
                        ch = char_pool[idx]
                        R, G, B = row_rgb[c]
                        line_parts.append(f"\033[38;2;{R};{G};{B}m{ch}")
                    idx += 1
                out_lines.append("".join(line_parts) + "\033[0m")

            sys.stdout.write("\n".join(out_lines))
            sys.stdout.flush()

            elapsed = time.perf_counter() - frame_start
            time.sleep(max(0.0, (1.0 / 30.0) - elapsed))

    except KeyboardInterrupt:
        sys.stdout.write("\033[0m\033[?25h\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()