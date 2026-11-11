shader_type spatial;
render_mode cull_disabled;
// A whole tree in one mesh: bark tubes and flat leaf cards.
//   COLOR.rgb = tint and shading stored in the mesh      COLOR.a = 1 for a leaf card, 0 for bark
//   UV        = picture coordinates
//   UV2       = (how much this point sways in the wind, a random number per card)
// Far from the player the tree is not drawn by this shader at all: a flat
// picture of it (tree_far.gdshader) takes over, which is much cheaper.

global uniform vec3 viewer_pos;          // where the player's camera is
global uniform float tree_lod;           // distance where the flat picture takes over
uniform sampler2D leaf_tex : source_color, filter_linear_mipmap, repeat_disable;
uniform sampler2D bark_tex : source_color, filter_linear_mipmap, repeat_enable;
uniform float wind = 1.0;
uniform float backlight = 0.35;          // how much sunlight shines through the leaves

varying float v_leaf;
varying vec3 v_tint;
varying float v_distance;                // metres from the camera to this point

void vertex() {
	v_leaf = COLOR.a;
	v_tint = COLOR.rgb;
	vec3 origin = MODEL_MATRIX[3].xyz;
	// Wind: the whole crown sways slowly, single leaf cards flutter fast.
	float t = TIME * 1.1 + origin.x * 0.13 + origin.z * 0.11;
	float sway = UV2.x * UV2.x;
	vec3 push = vec3(sin(t) + 0.4 * sin(t * 2.7 + 1.3), 0.0, cos(t * 0.83) * 0.7) * 0.07 * sway;
	push += vec3(sin(TIME * 4.3 + UV2.y * 40.0), cos(TIME * 3.7 + UV2.y * 33.0), sin(TIME * 5.1 + UV2.y * 21.0))
			* 0.014 * COLOR.a * UV2.x;
	VERTEX += push * wind;
	v_distance = distance((MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz, viewer_pos);
	if (distance(origin, viewer_pos) > tree_lod) {
		VERTEX = vec3(0.0);              // shrink to a point: nothing is drawn
	}
}

void fragment() {
	vec4 leaf = texture(leaf_tex, UV);
	vec3 bark = texture(bark_tex, UV).rgb;
	float is_leaf = step(0.5, v_leaf);
	ALBEDO = mix(bark * 1.5, leaf.rgb, is_leaf) * v_tint;
	// Far away the picture gets blurrier, so thin twigs would vanish. Making the
	// leaves a bit more solid with distance keeps them. (The cut-off itself must be
	// a fixed number: a changing one made the tree render black in Godot 4.7.)
	float keep = mix(1.0, 2.6, smoothstep(10.0, 45.0, v_distance));
	ALPHA = mix(1.0, leaf.a * keep, is_leaf);
	ALPHA_SCISSOR_THRESHOLD = 0.4;
	ROUGHNESS = mix(0.92, 0.7, is_leaf);
	SPECULAR = 0.25;
	BACKLIGHT = leaf.rgb * backlight * is_leaf;
	// The mesh stores light directions that point out of the crown. Keep them
	// the same on both sides of a card.
	NORMAL = FRONT_FACING ? NORMAL : -NORMAL;
}
