shader_type spatial;
render_mode unshaded, cull_disabled;
// Used only by tools/bake_trees.gd to photograph a tree without any lighting.
// The photo becomes the flat picture that stands in for the tree far away.

uniform sampler2D leaf_tex : source_color, filter_linear_mipmap, repeat_disable;
uniform sampler2D bark_tex : source_color, filter_linear_mipmap, repeat_enable;

void fragment() {
	vec4 leaf = texture(leaf_tex, UV);
	vec3 bark = texture(bark_tex, UV).rgb;
	float is_leaf = step(0.5, COLOR.a);
	ALBEDO = mix(bark * 1.5, leaf.rgb, is_leaf) * COLOR.rgb;
	ALPHA = mix(1.0, leaf.a, is_leaf);
	ALPHA_SCISSOR_THRESHOLD = 0.35;
}
