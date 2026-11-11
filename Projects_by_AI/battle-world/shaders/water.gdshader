shader_type spatial;
// The sea around the city: dark water with small moving ripples that catch the sky.

uniform sampler2D noise_tex : filter_linear_mipmap, repeat_enable;
uniform vec3 deep : source_color = vec3(0.012, 0.055, 0.085);

varying vec3 v_pos;

void vertex() {
	v_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 p = v_pos.xz;
	vec2 a = texture(noise_tex, p * 0.031 + TIME * vec2(0.011, 0.006)).rg;
	vec2 b = texture(noise_tex, p * 0.083 - TIME * vec2(0.009, 0.015)).gb;
	vec2 w = a + b - 1.0;
	// Ripples fade out far away so the horizon stays calm.
	float calm = 1.0 - smoothstep(60.0, 420.0, length(p - CAMERA_POSITION_WORLD.xz));
	vec3 n = normalize(vec3(w.x * 0.55 * calm, 1.0, w.y * 0.55 * calm));
	NORMAL = normalize((VIEW_MATRIX * vec4(n, 0.0)).xyz);
	ALBEDO = deep;
	ROUGHNESS = 0.06;
	METALLIC = 0.0;
	SPECULAR = 0.9;
}
