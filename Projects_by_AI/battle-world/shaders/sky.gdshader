shader_type sky;
// Shows the sky photo. Very bright pixels (the sun) are limited, because the
// real sunlight comes from the game's sun light. Below the horizon we repeat
// the colour of the horizon, so the far sea melts into the sky without a line.

uniform sampler2D panorama : filter_linear, source_color, hint_default_black;
uniform float max_light = 16.0;
uniform float energy = 1.0;

void sky() {
	vec3 c = min(texture(panorama, SKY_COORDS).rgb, vec3(max_light));
	vec3 horizon = min(texture(panorama, vec2(SKY_COORDS.x, 0.49)).rgb, vec3(max_light));
	float below = smoothstep(0.01, -0.03, EYEDIR.y);
	COLOR = mix(c, horizon * 0.8, below) * energy;
}
