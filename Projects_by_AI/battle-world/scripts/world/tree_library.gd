extends RefCounted
## The five kinds of trees: where their models and pictures are, and how they are drawn.
##
## The models in `assets/models/trees/` are made by `tools/bake_trees.gd`.
## Each tree is drawn in one of two ways:
##   near - the full model: bark tubes and leaf cards   (shaders/tree.gdshader)
##   far  - two crossed flat pictures of the model       (shaders/tree_far.gdshader)

const KINDS := {
	"cherry": {"leaves": "leaves_cherry", "backlight": 0.5},
	"spruce": {"leaves": "leaves_spruce", "backlight": 0.15},
	"maple": {"leaves": "leaves_maple", "backlight": 0.55},
	"oak_bare": {"leaves": "leaves_oak_bare", "backlight": 0.3},
	"oak": {"leaves": "leaves_oak", "backlight": 0.22},
}
## Rough size of each kind at scale 1: crown radius and trunk radius in metres.
## The city planner uses it to keep trees apart, the builder for collision.
const CROWN_RADIUS := {"cherry": 5.5, "spruce": 5.0, "maple": 7.2, "oak_bare": 10.0, "oak": 12.5}
const TRUNK_RADIUS := {"cherry": 0.31, "spruce": 0.28, "maple": 0.42, "oak_bare": 0.66, "oak": 0.82}
const TEXTURES := "res://assets/textures/trees/"
const MODELS := "res://assets/models/trees/"


static func kind_of(prop_name: String) -> String:
	return prop_name.trim_prefix("tree_")


static func model(kind: String) -> ArrayMesh:
	return load(MODELS + kind + ".res")


static func near_material(kind: String) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = load("res://shaders/tree.gdshader")
	m.set_shader_parameter("leaf_tex", load(TEXTURES + KINDS[kind].leaves + ".png"))
	m.set_shader_parameter("bark_tex", load(TEXTURES + "bark_color.jpg"))
	m.set_shader_parameter("backlight", KINDS[kind].backlight)
	return m


static func far_material(kind: String, tree: ArrayMesh) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = load("res://shaders/tree_far.gdshader")
	m.set_shader_parameter("picture", load(TEXTURES + "far_" + kind + ".png"))
	m.set_shader_parameter("crown_height", float(tree.get_meta("height")) * 0.6)
	return m


## Two upright crossed rectangles as wide and tall as the tree.
static func far_mesh(tree: ArrayMesh) -> ArrayMesh:
	var w: float = tree.get_meta("width") * 0.5
	var h: float = tree.get_meta("height")
	var verts := PackedVector3Array()
	var uvs := PackedVector2Array()
	var normals := PackedVector3Array()
	var colors := PackedColorArray()
	var indices := PackedInt32Array()
	for axis: Vector3 in [Vector3.RIGHT, Vector3.BACK]:
		var first := verts.size()
		for corner: Vector2 in [Vector2(-1, 0), Vector2(1, 0), Vector2(1, 1), Vector2(-1, 1)]:
			verts.append(axis * corner.x * w + Vector3.UP * corner.y * h)
			uvs.append(Vector2(corner.x * 0.5 + 0.5, 1.0 - corner.y))
			normals.append(Vector3.UP)
			colors.append(Color.WHITE)
		indices.append_array([first, first + 1, first + 2, first, first + 2, first + 3])
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh
