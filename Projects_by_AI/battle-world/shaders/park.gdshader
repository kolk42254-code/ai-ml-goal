shader_type spatial;
// Park ground: grass, with stone paths where the mesh says so.
// COLOR.r = how much path (1) or grass (0) each corner of the ground has.

uniform sampler2D grass_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D grass_normal : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D path_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D path_normal : hint_normal, filter_linear_mipmap, repeat_enable;
uniform sampler2D path_rough : hint_default_white, filter_linear_mipmap, repeat_enable;
uniform sampler2D noise_tex : filter_linear_mipmap, repeat_enable;
uniform vec3 grass_tint : source_color = vec3(0.80, 0.95, 0.62);

varying vec3 v_pos;

void vertex() {
	v_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	TANGENT = vec3(1.0, 0.0, 0.0);
	BINORMAL = vec3(0.0, 0.0, 1.0);
}

void fragment() {
	vec2 p = v_pos.xz;
	vec3 grass = texture(grass_albedo, p / 3.5).rgb * grass_tint;
	vec3 grass_n = texture(grass_normal, p / 3.5).rgb;
	vec3 path = texture(path_albedo, p / 2.6).rgb;
	vec3 path_n = texture(path_normal, p / 2.6).rgb;
	float path_r = texture(path_rough, p / 2.6).r;
	float big = texture(noise_tex, p / 38.0).r;
	float fine = texture(noise_tex, p / 4.0).g;
	// The noise makes the border between grass and path uneven, like in a real park.
	float k = smoothstep(0.38, 0.62, COLOR.r + (fine - 0.5) * 0.45);
	grass *= mix(0.72, 1.18, big);
	ALBEDO = mix(grass, path * 0.9, k);
	ROUGHNESS = mix(0.95, path_r, k);
	NORMAL_MAP = mix(grass_n, path_n, k);
	NORMAL_MAP_DEPTH = 1.0;
}
