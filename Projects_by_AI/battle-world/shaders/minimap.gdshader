shader_type canvas_item;
// Round minimap. The map picture turns so that "up" on the minimap is always
// the way the camera looks.

uniform sampler2D map_tex : filter_linear;
uniform vec2 center = vec2(0.5);       // where the player is on the map picture (0..1)
uniform float heading = 0.0;           // camera angle in radians
uniform float zoom = 0.17;             // share of the whole map shown across the circle

void fragment() {
	vec2 p = UV - 0.5;
	float r = length(p) * 2.0;
	float c = cos(heading);
	float s = sin(heading);
	vec2 q = center + zoom * vec2(p.x * c + p.y * s, -p.x * s + p.y * c);
	vec3 col = texture(map_tex, clamp(q, vec2(0.0), vec2(1.0))).rgb;
	if (q.x < 0.0 || q.x > 1.0 || q.y < 0.0 || q.y > 1.0) {
		col = vec3(0.07, 0.16, 0.22);
	}
	col = mix(col, vec3(0.02, 0.03, 0.05), 0.18);
	float inside = 1.0 - smoothstep(0.97, 1.0, r);
	float ring = smoothstep(0.90, 0.92, r);
	col = mix(col, vec3(0.92, 0.94, 0.97), ring);
	COLOR = vec4(col, inside * 0.94);
}
