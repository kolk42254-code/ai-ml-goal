shader_type spatial;
// The road surface: asphalt plus lane lines, zebra crossings and stop lines.
// The paint is worked out from the street grid numbers, so it stays sharp at
// any distance and needs no picture of road markings.

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rough_tex : hint_default_white, filter_linear_mipmap, repeat_enable;
uniform sampler2D noise_tex : filter_linear_mipmap, repeat_enable;
uniform sampler2D ao_tex : hint_default_white, filter_linear_mipmap, repeat_disable;
uniform vec4 map_rect = vec4(-264.0, -264.0, 528.0, 528.0);   // island corner (x, z) and size
uniform int count_x = 0;
uniform vec2 roads_x[10];        // north-south roads: (centre x, half width)
uniform int count_z = 0;
uniform vec2 roads_z[10];        // east-west roads: (centre z, half width)
uniform float tile = 5.0;        // metres covered by one copy of the asphalt picture
uniform vec3 tint : source_color = vec3(0.30, 0.30, 0.32);

varying vec3 v_pos;

void vertex() {
	v_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

// 1 on a line of half width `hw` at distance `d` from its centre, with soft edges.
float stripe(float d, float hw, float aa) {
	return 1.0 - smoothstep(hw - aa, hw + aa, abs(d));
}

// Paint for one road piece. Returns (white, yellow).
//   u    distance from the road's centre line     v    distance along the road
//   hw   half the road width                      edge distance to the nearest crossing road
//   side which side of that crossing we are on (+1 / -1)
vec2 road_paint(float u, float v, float hw, float edge, float side, float aa) {
	float white = 0.0;
	float yellow = 0.0;
	float open_road = smoothstep(5.5, 5.7, edge);
	float dash = step(fract(v / 9.0), 0.4);
	if (hw > 7.0) {
		// Avenue: double yellow in the middle, dashed white between the lanes.
		yellow = max(stripe(u - 0.16, 0.06, aa), stripe(u + 0.16, 0.06, aa)) * open_road;
		white = stripe(abs(u) - 3.4, 0.06, aa) * dash * open_road;
	} else {
		yellow = stripe(u, 0.07, aa) * dash * open_road;
	}
	// Thin line marking the parking lane beside each kerb.
	white = max(white, stripe(abs(u) - (hw - 2.4), 0.05, aa) * open_road);
	// Zebra crossing 1 to 4 metres before the crossing road.
	float zone = smoothstep(1.0 - aa, 1.0 + aa, edge) * (1.0 - smoothstep(4.0 - aa, 4.0 + aa, edge))
			* (1.0 - smoothstep(hw - 0.5 - aa, hw - 0.5 + aa, abs(u)));
	float bar = abs(fract(u / 1.1) - 0.5) * 2.0;
	float k = clamp(aa / 0.55, 0.01, 0.5);
	white = max(white, zone * smoothstep(0.5 - k, 0.5 + k, bar));
	// Stop line for the cars that drive towards the crossing.
	float stop = stripe(edge - 4.9, 0.2, aa) * step(0.0, u * side) * step(abs(u), hw - 2.4);
	white = max(white, stop);
	return vec2(white, yellow);
}

void fragment() {
	vec2 p = v_pos.xz;
	// Find the nearest north-south road and the nearest east-west road.
	float sdx = 100000.0;
	float cx = 0.0;
	float hwx = 6.0;
	for (int i = 0; i < count_x; i++) {
		float d = abs(p.x - roads_x[i].x) - roads_x[i].y;
		if (d < sdx) {
			sdx = d;
			cx = roads_x[i].x;
			hwx = roads_x[i].y;
		}
	}
	float sdz = 100000.0;
	float cz = 0.0;
	float hwz = 6.0;
	for (int i = 0; i < count_z; i++) {
		float d = abs(p.y - roads_z[i].x) - roads_z[i].y;
		if (d < sdz) {
			sdz = d;
			cz = roads_z[i].x;
			hwz = roads_z[i].y;
		}
	}

	vec2 uv = p / tile;
	vec3 base = texture(albedo_tex, uv).rgb;
	vec3 nmap = texture(normal_tex, uv).rgb;
	float rough = texture(rough_tex, uv).r;
	float big = texture(noise_tex, p / 70.0).r;          // large light and dark patches
	float fine = texture(noise_tex, p / 3.0).g;          // small wear in the paint
	float ao = textureLod(ao_tex, (p - map_rect.xy) / map_rect.zw, 1.5).r;

	float aa = clamp((fwidth(p.x) + fwidth(p.y)) * 0.6, 0.004, 0.6);
	vec2 paint = vec2(0.0);
	if (sdx < 0.0 && sdz > 0.0) {
		paint = road_paint(p.x - cx, p.y, hwx, sdz, sign(p.y - cz), aa);
	} else if (sdz < 0.0 && sdx > 0.0) {
		paint = road_paint(p.y - cz, p.x, hwz, sdx, -sign(p.x - cx), aa);
	}
	paint *= smoothstep(0.18, 0.42, fine) * 0.9;          // worn paint

	vec3 asphalt = base * tint * 2.2 * mix(0.82, 1.12, big);
	vec3 albedo = mix(asphalt, vec3(0.74, 0.74, 0.70), paint.x);
	albedo = mix(albedo, vec3(0.80, 0.58, 0.10), paint.y);

	ALBEDO = albedo;
	ROUGHNESS = mix(rough, 0.6, max(paint.x, paint.y));
	NORMAL_MAP = nmap;
	NORMAL_MAP_DEPTH = 0.8;
	AO = ao;
	AO_LIGHT_AFFECT = 0.35;
}
