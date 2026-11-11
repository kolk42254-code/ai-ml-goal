shader_type spatial;
// Facade shader. Buildings are plain boxes; this shader paints windows, frames,
// shop fronts and fake rooms on them, so one box looks like a real building.
//
// Data the mesh gives us:
//   UV       = (window column, floor number)
//   COLOR    = wall tint (rgb) and a random number for this building (a)
//   CUSTOM0  = (style, has shop front, chance a window is lit, top floor number)

uniform sampler2D noise_tex : filter_linear_mipmap, repeat_enable;
// 0 = day, 1 = night. More windows light up at night.
uniform float night : hint_range(0.0, 1.0) = 0.0;
// 1 = draw fake rooms behind the glass, 0 = flat windows (faster).
uniform float rooms : hint_range(0.0, 1.0) = 1.0;

varying vec4 v_style;
varying vec3 v_world_pos;
varying vec3 v_world_normal;

float hash21(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}

// 1 inside the rectangle lo..hi of a 0..1 cell, with soft edges `aa` wide.
float rect_mask(vec2 f, vec2 lo, vec2 hi, vec2 aa) {
	vec2 a = smoothstep(lo - aa, lo + aa, f);
	vec2 b = 1.0 - smoothstep(hi - aa, hi + aa, f);
	return a.x * a.y * b.x * b.y;
}

void vertex() {
	v_style = CUSTOM0;
	v_world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	v_world_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	vec3 tint = pow(COLOR.rgb, vec3(2.2));      // paint-program colour -> linear light
	float seed = COLOR.a;
	int style = int(v_style.x + 0.5);
	vec3 n = normalize(v_world_normal);
	bool is_roof = n.y > 0.5;

	vec2 cuv = UV;
	vec2 id = floor(cuv);
	vec2 f = fract(cuv);
	vec2 aa = clamp(fwidth(cuv) * 0.8, vec2(0.0005), vec2(0.5));
	// How many window cells one screen pixel covers. Above ~0.5 single windows
	// cannot be drawn cleanly any more, so we fade to an average colour.
	float far_fade = smoothstep(0.22, 0.6, max(aa.x, aa.y));

	// One noise lookup for everything (taken before any branching).
	vec2 noise_uv = is_roof ? v_world_pos.xz * 0.045 : vec2(cuv.x * 0.31 + seed * 7.0, cuv.y * 0.07);
	vec3 noise = texture(noise_tex, noise_uv).rgb;

	float rnd = hash21(id + seed * 91.7);
	float rnd2 = hash21(id * 1.7 + seed * 13.1 + 5.0);
	float col_rnd = hash21(vec2(id.x, seed * 31.0));

	// ---- Shape of the window inside one cell, per style ----
	vec2 w_lo = vec2(0.3, 0.3);
	vec2 w_hi = vec2(0.7, 0.8);
	vec3 wall = tint;
	float wall_rough = 0.85;
	float wall_metal = 0.0;
	float glass_metal = 0.25;
	float glass_rough = 0.07;
	vec3 glass_color = vec3(0.03, 0.04, 0.05);
	vec3 frame_color = vec3(0.10, 0.11, 0.12);
	float frame_w = 0.03;           // frame around the glass, in cell units
	float bay_m = 3.0;              // real size of one cell in metres (for the fake rooms)
	float floor_m = 3.2;
	bool has_windows = true;

	if (style == 0) {
		// Glass tower: glass from edge to edge, dark band at each floor line.
		w_lo = vec2(0.035, 0.24);
		w_hi = vec2(0.965, 0.985);
		wall = tint * 0.35;
		wall_rough = 0.25;
		wall_metal = 0.6;
		glass_metal = 0.85;
		glass_color = mix(vec3(0.30), tint * 1.5, 0.55);     // soften the tint so glass is not too blue
		glass_rough = 0.05;
		frame_w = 0.0;
		bay_m = 2.4;
		floor_m = 3.8;
	} else if (style == 1) {
		// Office: long bands of windows between concrete bands.
		w_lo = vec2(0.07, 0.36);
		w_hi = vec2(0.93, 0.86);
		glass_metal = 0.5;
		glass_color = vec3(0.10, 0.14, 0.17);
		bay_m = 3.2;
		floor_m = 3.6;
	} else if (style == 2) {
		// Brick building with single windows.
		w_lo = vec2(0.27, 0.28);
		w_hi = vec2(0.73, 0.80);
		frame_color = vec3(0.78, 0.76, 0.70);
		frame_w = 0.045;
		bay_m = 3.0;
		floor_m = 3.2;
		wall_rough = 0.92;
	} else if (style == 3) {
		// Plastered flats.
		w_lo = vec2(0.30, 0.26);
		w_hi = vec2(0.70, 0.78);
		frame_color = vec3(0.92, 0.92, 0.90);
		frame_w = 0.04;
		bay_m = 3.4;
		floor_m = 3.0;
		wall_rough = 0.9;
	} else if (style == 4) {
		// Metal shed: only a strip of small windows under the roof.
		w_lo = vec2(0.12, 0.55);
		w_hi = vec2(0.88, 0.82);
		has_windows = id.y > v_style.w - 1.5;
		wall_rough = 0.55;
		wall_metal = 0.55;
		bay_m = 4.0;
		floor_m = 4.5;
	} else {
		has_windows = false;
		bay_m = 4.0;
		floor_m = 3.4;
	}

	// ---- Wall look ----
	float streaks = mix(0.82, 1.0, noise.r);          // rain streaks and dirt
	vec3 wall_col = wall * streaks;
	if (style == 2) {
		// Brick rows. They fade out far away so they do not flicker.
		vec2 b = vec2(cuv.x * bay_m / 0.46, cuv.y * floor_m / 0.2);
		b.x += 0.5 * mod(floor(b.y), 2.0);
		vec2 bf = fract(b);
		float brick_far = 1.0 - smoothstep(0.12, 0.45, fwidth(b.y));
		float mortar = max(1.0 - smoothstep(0.0, 0.14, bf.y), 1.0 - smoothstep(0.0, 0.07, bf.x));
		float tone = 0.86 + 0.28 * hash21(floor(b) + seed);
		wall_col = mix(wall_col, wall_col * tone, brick_far);
		wall_col = mix(wall_col, vec3(0.62, 0.60, 0.56) * streaks, mortar * brick_far * 0.8);
	} else if (style == 4) {
		// Corrugated metal: thin upright ribs.
		float rib_x = cuv.x * bay_m / 0.22;
		float rib_far = 1.0 - smoothstep(0.15, 0.5, fwidth(rib_x));
		wall_col *= 1.0 + 0.16 * sin(rib_x * 6.2832) * rib_far;
	} else if (style == 5 || style == 1) {
		// Concrete panels: a thin joint line around each cell.
		float joint = 1.0 - rect_mask(f, vec2(0.012), vec2(0.988), aa);
		wall_col *= 1.0 - 0.22 * joint * (1.0 - far_fade);
	}

	// ---- Windows ----
	float glass = has_windows ? rect_mask(f, w_lo, w_hi, aa) : 0.0;
	float frame = has_windows ? rect_mask(f, w_lo - frame_w, w_hi + frame_w, aa) - glass : 0.0;
	float cover = (w_hi.x - w_lo.x) * (w_hi.y - w_lo.y);     // share of the cell that is glass

	// Big metal door on the ground floor of sheds.
	float door = 0.0;
	if (style == 4 && cuv.y < 1.0 && col_rnd < 0.34) {
		door = rect_mask(f, vec2(0.14, -0.1), vec2(0.86, 0.82), aa);
		float slats = 0.9 + 0.1 * sin(cuv.y * floor_m / 0.3 * 6.2832);
		wall_col = mix(wall_col, vec3(0.30, 0.31, 0.33) * slats, door);
	}

	// Shop front on the ground floor: large glass, coloured sign above it.
	bool shop = v_style.y > 0.5 && cuv.y < 1.0 && !is_roof;
	float sign_mask = 0.0;
	vec3 sign_col = vec3(0.0);
	if (shop) {
		w_lo = vec2(0.05, 0.03);
		w_hi = vec2(0.95, 0.70);
		glass = rect_mask(f, w_lo, w_hi, aa);
		frame = rect_mask(f, w_lo - 0.025, w_hi + 0.025, aa) - glass;
		frame_color = vec3(0.06, 0.06, 0.07);
		glass_metal = 0.1;
		glass_color = vec3(0.03, 0.04, 0.05);
		cover = 0.6;
		// One sign colour per pair of columns.
		float shop_id = floor(id.x * 0.5) + seed * 57.0;
		float hue = hash21(vec2(shop_id, 3.3));
		sign_col = clamp(abs(fract(hue + vec3(0.0, 0.667, 0.333)) * 6.0 - 3.0) - 1.0, 0.0, 1.0);
		sign_col = mix(vec3(0.35), sign_col, 0.5) * mix(0.12, 0.38, hash21(vec2(shop_id, 9.1)));
		sign_mask = rect_mask(f, vec2(-0.1, 0.76), vec2(1.1, 0.94), aa);
	}

	// ---- Fake room behind the glass (a cheap trick called interior mapping) ----
	float lit_chance = mix(v_style.z * 0.12, v_style.z, night);
	if (shop) {
		lit_chance = 0.9;
	}
	float lit = step(rnd, lit_chance);
	vec3 room = vec3(0.0);
	if (rooms > 0.5) {
		vec3 up = vec3(0.0, 1.0, 0.0);
		vec3 t = normalize(cross(up, n) + vec3(0.00001, 0.0, 0.0));
		vec3 eye = normalize(v_world_pos - CAMERA_POSITION_WORLD);
		float depth_m = shop ? 7.0 : 5.0;
		vec3 d = vec3(dot(eye, t) / bay_m, dot(eye, up) / floor_m, max(dot(eye, -n), 0.02) / depth_m);
		d += (step(0.0, d) * 2.0 - 1.0) * 0.00001;
		vec3 p = vec3(f, 0.0);
		vec3 hit_t = (step(0.0, d) - p) / d;          // distance to the far wall on each axis
		float tt = min(min(hit_t.x, hit_t.y), hit_t.z);
		vec3 hit = p + d * tt;
		float room_rnd = hash21(id * 3.1 + seed * 7.0);
		vec3 paint = mix(vec3(0.78, 0.74, 0.66), vec3(0.56, 0.63, 0.70), room_rnd);
		if (tt == hit_t.z) {
			// Back wall, with one darker shape (a door or a shelf).
			float shelf_x = 0.12 + room_rnd * 0.45;
			float shelf = rect_mask(hit.xy, vec2(shelf_x, -0.1), vec2(shelf_x + 0.3, 0.58), vec2(0.01));
			room = mix(paint * 0.9, paint * 0.4, shelf);
		} else if (tt == hit_t.y) {
			room = d.y > 0.0 ? vec3(0.92) : vec3(0.36, 0.31, 0.27);     // ceiling or floor
		} else {
			room = paint * 0.72;
		}
		room *= 1.0 - 0.5 * hit.z;                    // darker further inside
	} else {
		room = vec3(0.45, 0.43, 0.40);
	}
	// Blinds pulled part of the way down on some windows.
	float in_y = (f.y - w_lo.y) / max(w_hi.y - w_lo.y, 0.001);
	float blind = (!shop && rnd2 < 0.45) ? step(1.0 - rnd2 * 1.3, in_y) : 0.0;
	room = mix(room, vec3(0.80, 0.78, 0.72) * (0.55 + 0.45 * lit), blind);

	vec3 warm = mix(vec3(1.0, 0.82, 0.55), vec3(0.85, 0.92, 1.0), step(0.7, rnd2));
	float day = 1.0 - night;
	// Lit rooms glow; dark rooms only show a little daylight.
	vec3 room_light = room * mix(vec3(0.10) * day, warm * mix(0.55, 2.2, night), lit);
	if (shop) {
		room_light = room * vec3(1.0, 0.95, 0.85) * mix(0.9, 2.4, night);
	}
	// Mirror-like glass towers hide most of the room behind the reflection.
	float see_through = style == 0 ? mix(0.25, 0.9, lit * night) : 1.0;

	// ---- Put it together ----
	vec3 albedo = wall_col;
	float rough = wall_rough;
	float metal = wall_metal;
	vec3 emission = vec3(0.0);

	albedo = mix(albedo, frame_color, clamp(frame, 0.0, 1.0));
	albedo = mix(albedo, glass_color, glass);
	rough = mix(rough, glass_rough, glass);
	metal = mix(metal, glass_metal, glass);
	emission = room_light * see_through * glass;

	albedo = mix(albedo, sign_col, sign_mask);
	emission += sign_col * sign_mask * mix(0.35, 2.2, night);
	rough = mix(rough, 0.5, sign_mask);

	// Cap at the very top of the wall.
	float cap = smoothstep(v_style.w - 0.14, v_style.w - 0.12, cuv.y);
	albedo = mix(albedo, wall * 0.6, cap);
	emission *= 1.0 - cap;

	// Far away: blend to the average of wall and glass so nothing flickers.
	if (has_windows) {
		vec3 avg_albedo = mix(wall * streaks, glass_color, cover);
		vec3 avg_emission = room_light * see_through * cover * 0.8;
		albedo = mix(albedo, avg_albedo, far_fade);
		emission = mix(emission, avg_emission, far_fade * 0.7);
		rough = mix(rough, mix(wall_rough, glass_rough, cover), far_fade);
		metal = mix(metal, mix(wall_metal, glass_metal, cover), far_fade);
	}

	// Dirt near the street.
	albedo *= mix(0.72, 1.0, smoothstep(0.0, 3.0, v_world_pos.y));

	if (is_roof) {
		albedo = mix(vec3(0.17, 0.17, 0.18), vec3(0.29, 0.29, 0.30), noise.r);
		rough = 0.92;
		metal = 0.0;
		emission = vec3(0.0);
	}

	ALBEDO = albedo;
	ROUGHNESS = rough;
	METALLIC = metal;
	SPECULAR = 0.5;
	EMISSION = emission;
}
