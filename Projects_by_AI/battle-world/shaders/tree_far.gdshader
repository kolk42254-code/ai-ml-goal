shader_type spatial;
render_mode cull_disabled;
// A far-away tree: just two crossed flat pictures of the real tree.
// Close to the player it shrinks to nothing, because there the full tree
// (tree.gdshader) is drawn instead.

global uniform vec3 viewer_pos;
global uniform float tree_lod;
uniform sampler2D picture : source_color, filter_linear_mipmap, repeat_disable;
uniform float crown_height = 5.0;        // height of the middle of the crown
uniform float brightness = 0.8;          // makes up for the shadows a real crown casts on itself

varying vec3 v_tint;

void vertex() {
	v_tint = COLOR.rgb * brightness;
	vec3 origin = MODEL_MATRIX[3].xyz;
	// Both pictures get nearly the same light direction (mostly up, a little
	// outwards). Otherwise one picture would look bright and the other dark.
	NORMAL = normalize(vec3(VERTEX.x * 0.35, crown_height, VERTEX.z * 0.35));
	if (distance(origin, viewer_pos) <= tree_lod) {
		VERTEX = vec3(0.0);
	}
}

void fragment() {
	vec4 t = texture(picture, UV);
	ALBEDO = t.rgb * v_tint;
	ALPHA = t.a;
	ALPHA_SCISSOR_THRESHOLD = 0.4;
	ROUGHNESS = 0.8;
	SPECULAR = 0.2;
	NORMAL = FRONT_FACING ? NORMAL : -NORMAL;
}
