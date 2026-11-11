shader_type spatial;
// Fighter body. The mesh has no pictures: every corner stores its own colour.
//   CUSTOM0.rgb = colour        CUSTOM0.a = 1 where the suit colour (armor) applies
//   UV          = (roughness, metallic)
//   UV2.x       = glow strength (visor strip, chest light)

uniform vec3 armor : source_color = vec3(0.85, 0.87, 0.90);    // main suit colour
uniform vec3 glow_color : source_color = vec3(0.1, 0.8, 1.0);  // colour of the glowing strips
uniform float rim = 0.35;                                       // thin light edge so the fighter stands out
uniform float hit_flash = 0.0;                                  // 1 = flash white (used when hit)

varying vec4 v_paint;

void vertex() {
	v_paint = CUSTOM0;
}

void fragment() {
	vec3 base = pow(v_paint.rgb, vec3(2.2));
	vec3 c = mix(base, base * armor, v_paint.a);
	float edge = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0);
	ALBEDO = mix(c, vec3(1.0), hit_flash * 0.7);
	ROUGHNESS = UV.x;
	METALLIC = UV.y;
	EMISSION = glow_color * UV2.x + vec3(0.55, 0.65, 0.8) * edge * rim + vec3(hit_flash * 0.6);
}
