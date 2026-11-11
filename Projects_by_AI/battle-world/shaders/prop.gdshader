shader_type spatial;
render_mode world_vertex_coords;
// Painted objects without pictures: lamps, benches, cars, trees, containers ...
//   CUSTOM0.rgb = colour        CUSTOM0.a = 1 where the per-object tint applies
//   COLOR       = the per-object tint (filled in by the engine, white when none)
//   UV          = (roughness, metallic)
//   UV2         = (glow strength, wind sway amount)
// Glow below 3 is a street light and only shines at night. Glow of 3 or more
// (warning lights on towers) always shines.

uniform float night : hint_range(0.0, 1.0) = 0.0;
uniform float wind = 1.0;

varying vec3 v_color;
varying float v_glow;
varying float v_ribs;
varying vec3 v_world;
varying vec3 v_wnormal;

void vertex() {
	// Colours are written the way a paint program shows them (sRGB). The power of
	// 2.2 turns them into the linear values the lighting maths needs.
	v_color = pow(CUSTOM0.rgb, vec3(2.2)) * mix(vec3(1.0), pow(COLOR.rgb, vec3(2.2)), CUSTOM0.a);
	v_ribs = step(UV2.y, -0.5);          // UV2.y = -1 marks ribbed metal (shipping containers)
	v_world = VERTEX;
	v_wnormal = NORMAL;
	v_glow = UV2.x >= 3.0 ? UV2.x - 2.0 : UV2.x * night;
	if (UV2.y > 0.001) {
		// Leaves sway a little in the wind. VERTEX is a world position here.
		float t = TIME * 1.3 + VERTEX.x * 0.35 + VERTEX.z * 0.27;
		vec3 sway = vec3(sin(t) + 0.5 * sin(t * 2.3 + 1.7), 0.0, cos(t * 0.8) + 0.4 * sin(t * 1.9));
		VERTEX += sway * 0.05 * UV2.y * wind;
	}
}

void fragment() {
	vec3 c = v_color;
	if (v_ribs > 0.5) {
		// Upright ribs on container walls. They fade out far away so they do not flicker.
		float along = abs(v_wnormal.x) > 0.5 ? v_world.z : v_world.x;
		float rib = along / 0.3;
		float fade = (1.0 - smoothstep(0.15, 0.5, fwidth(rib))) * (1.0 - abs(v_wnormal.y));
		c *= 1.0 + 0.16 * sin(rib * 6.2832) * fade;
	}
	ALBEDO = c;
	ROUGHNESS = UV.x;
	METALLIC = UV.y;
	EMISSION = c * v_glow;
}
