shader_type spatial;
// Raised ground: pavements, the plaza, car parks and the promenade.
// The picture is placed by world position, so neighbouring slabs line up.

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rough_tex : hint_default_white, filter_linear_mipmap, repeat_enable;
uniform sampler2D noise_tex : filter_linear_mipmap, repeat_enable;
uniform sampler2D ao_tex : hint_default_white, filter_linear_mipmap, repeat_disable;
uniform vec4 map_rect = vec4(-264.0, -264.0, 528.0, 528.0);
uniform vec2 tile = vec2(3.0, 3.0);            // metres covered by one copy of the picture (wide, deep)
uniform vec3 tint : source_color = vec3(1.0);
uniform float joint_size = 0.0;              // paving slab size in metres (0 = no joints)
uniform float bay_lines = 0.0;               // 1 = paint car park bays (UV holds local metres)

varying vec3 v_pos;
varying vec3 v_normal;

float hash21(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}

void vertex() {
	v_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	v_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	// The top faces are flat, so the texture directions are simply +X and +Z.
	TANGENT = vec3(1.0, 0.0, 0.0);
	BINORMAL = vec3(0.0, 0.0, 1.0);
}

void fragment() {
	vec2 p = v_pos.xz;
	float top = step(0.5, v_normal.y);
	vec2 uv = mix(vec2(p.x + p.y, v_pos.y) / tile, p / tile, top);
	vec3 base = texture(albedo_tex, uv).rgb;
	vec3 nmap = texture(normal_tex, uv).rgb;
	float rough = texture(rough_tex, uv).r;
	float big = texture(noise_tex, p / 45.0).r;
	float ao = textureLod(ao_tex, (p - map_rect.xy) / map_rect.zw, 1.5).r;
	float aa = clamp((fwidth(p.x) + fwidth(p.y)) * 0.6, 0.003, 0.5);

	vec3 albedo = base * tint * mix(0.86, 1.08, big);
	if (joint_size > 0.01) {
		// Thin dark joints between paving slabs, and a slightly different tone per slab.
		vec2 g = p / joint_size;
		vec2 gf = abs(fract(g) - 0.5) * joint_size;       // distance to the slab centre in metres
		float edge = joint_size * 0.5 - max(gf.x, gf.y);
		float joint = 1.0 - smoothstep(0.012 - aa, 0.012 + aa, edge);
		float fade = 1.0 - smoothstep(0.1, 0.5, aa);
		albedo *= mix(1.0, 0.92 + 0.14 * hash21(floor(g)), top * fade);
		albedo *= 1.0 - 0.45 * joint * top * fade;
	}
	if (bay_lines > 0.5) {
		// Car park: white lines between the bays. UV = metres from the first bay.
		float row = mod(UV.y, 16.5);
		float in_bay = max(step(row, 5.0), step(11.5, row)) * step(0.0, UV.y) * step(-0.2, UV.x);
		float d = (fract(UV.x / 2.7 + 0.5) - 0.5) * 2.7;
		float line = (1.0 - smoothstep(0.06 - aa, 0.06 + aa, abs(d))) * in_bay;
		float back = 1.0 - smoothstep(0.06 - aa, 0.06 + aa, min(abs(row), abs(row - 16.5)));
		albedo = mix(albedo, vec3(0.72, 0.72, 0.68), max(line, back * step(0.0, UV.y)) * top * 0.85);
	}
	// Kerb sides are plain light stone.
	albedo = mix(vec3(0.50, 0.50, 0.49) * mix(0.8, 1.0, big), albedo, top);

	ALBEDO = albedo;
	ROUGHNESS = rough;
	NORMAL_MAP = nmap;
	NORMAL_MAP_DEPTH = 0.9 * top;
	AO = ao;
	AO_LIGHT_AFFECT = 0.4;
}
