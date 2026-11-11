extends Node3D
## Builds a fighter's body from code: a skeleton (bones) and one mesh that bends
## with the bones. No model file is needed, and every fighter can get its own
## colours. The fighter stands at the origin, is 1.8 m tall and faces -Z.

enum B {
	ROOT, HIPS, SPINE, CHEST, NECK, HEAD,
	CLAV_L, UARM_L, FARM_L, HAND_L,
	CLAV_R, UARM_R, FARM_R, HAND_R,
	THIGH_L, SHIN_L, FOOT_L,
	THIGH_R, SHIN_R, FOOT_R,
}

## Bone name, parent bone, and where the bone starts measured from its parent.
const BONES := [
	["root", -1, Vector3(0.0, 0.0, 0.0)],
	["hips", B.ROOT, Vector3(0.0, 0.98, 0.0)],
	["spine", B.HIPS, Vector3(0.0, 0.12, 0.0)],
	["chest", B.SPINE, Vector3(0.0, 0.16, 0.0)],
	["neck", B.CHEST, Vector3(0.0, 0.24, 0.0)],
	["head", B.NECK, Vector3(0.0, 0.09, 0.0)],
	["clavicle_l", B.CHEST, Vector3(-0.07, 0.17, 0.0)],
	["upper_arm_l", B.CLAV_L, Vector3(-0.13, 0.0, 0.0)],
	["forearm_l", B.UARM_L, Vector3(0.0, -0.29, 0.0)],
	["hand_l", B.FARM_L, Vector3(0.0, -0.27, 0.0)],
	["clavicle_r", B.CHEST, Vector3(0.07, 0.17, 0.0)],
	["upper_arm_r", B.CLAV_R, Vector3(0.13, 0.0, 0.0)],
	["forearm_r", B.UARM_R, Vector3(0.0, -0.29, 0.0)],
	["hand_r", B.FARM_R, Vector3(0.0, -0.27, 0.0)],
	["thigh_l", B.HIPS, Vector3(-0.10, -0.04, 0.0)],
	["shin_l", B.THIGH_L, Vector3(0.0, -0.45, 0.0)],
	["foot_l", B.SHIN_L, Vector3(0.0, -0.41, 0.0)],
	["thigh_r", B.HIPS, Vector3(0.10, -0.04, 0.0)],
	["shin_r", B.THIGH_R, Vector3(0.0, -0.45, 0.0)],
	["foot_r", B.SHIN_R, Vector3(0.0, -0.41, 0.0)],
]

const UPPER_LEG := 0.45
const LOWER_LEG := 0.41
const UPPER_ARM := 0.29
const LOWER_ARM := 0.27
const ANKLE_H := 0.08

# Colours. Alpha 1 = this part takes the fighter's suit colour.
const SUIT := Color(0.17, 0.19, 0.23, 0.0)       # dark under-suit
const PLATE := Color(0.92, 0.92, 0.92, 1.0)         # armour plates (tinted by the suit colour)
const TRIM := Color(0.05, 0.05, 0.06, 0.0)       # boots, gloves, straps
const VISOR := Color(0.02, 0.03, 0.04, 0.0)
const MAT_SUIT := Vector2(0.75, 0.0)             # (roughness, metallic)
const MAT_PLATE := Vector2(0.46, 0.3)
const MAT_TRIM := Vector2(0.6, 0.1)
const MAT_VISOR := Vector2(0.08, 0.7)

var skeleton: Skeleton3D
var body: MeshInstance3D
var material: ShaderMaterial

# Mesh data being collected.
var _verts := PackedVector3Array()
var _normals := PackedVector3Array()
var _uvs := PackedVector2Array()
var _uv2s := PackedVector2Array()
var _paint := PackedFloat32Array()
var _bones := PackedInt32Array()
var _weights := PackedFloat32Array()
var _indices := PackedInt32Array()


func build(armor_color := Color(0.84, 0.86, 0.90), glow := Color(1.0, 0.55, 0.08)) -> void:
	skeleton = Skeleton3D.new()
	skeleton.name = "Skeleton"
	add_child(skeleton)
	for bone: Array in BONES:
		var index := skeleton.add_bone(bone[0])
		if bone[1] >= 0:
			skeleton.set_bone_parent(index, bone[1])
		skeleton.set_bone_rest(index, Transform3D(Basis.IDENTITY, bone[2]))
	skeleton.reset_bone_poses()

	_build_body()
	material = ShaderMaterial.new()
	material.shader = load("res://shaders/character.gdshader")
	material.set_shader_parameter("armor", armor_color)
	material.set_shader_parameter("glow_color", glow)

	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = _verts
	arrays[Mesh.ARRAY_NORMAL] = _normals
	arrays[Mesh.ARRAY_TEX_UV] = _uvs
	arrays[Mesh.ARRAY_TEX_UV2] = _uv2s
	arrays[Mesh.ARRAY_CUSTOM0] = _paint
	arrays[Mesh.ARRAY_BONES] = _bones
	arrays[Mesh.ARRAY_WEIGHTS] = _weights
	arrays[Mesh.ARRAY_INDEX] = _indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {},
		Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT)
	mesh.surface_set_material(0, material)
	# The mesh moves with the bones, so give it a box that always contains it.
	mesh.custom_aabb = AABB(Vector3(-1.2, -0.3, -1.2), Vector3(2.4, 2.6, 2.4))

	body = MeshInstance3D.new()
	body.name = "Body"
	body.mesh = mesh
	skeleton.add_child(body)
	body.skin = skeleton.create_skin_from_rest_transforms()
	body.skeleton = NodePath("..")
	_free_build_data()


func set_colors(armor_color: Color, glow: Color) -> void:
	material.set_shader_parameter("armor", armor_color)
	material.set_shader_parameter("glow_color", glow)


## Where a bone starts when the fighter stands in the rest pose.
static func rest_position(bone: int) -> Vector3:
	var p := Vector3.ZERO
	var i := bone
	while i >= 0:
		p += BONES[i][2]
		i = BONES[i][1]
	return p


func _free_build_data() -> void:
	_verts = PackedVector3Array()
	_normals = PackedVector3Array()
	_uvs = PackedVector2Array()
	_uv2s = PackedVector2Array()
	_paint = PackedFloat32Array()
	_bones = PackedInt32Array()
	_weights = PackedFloat32Array()
	_indices = PackedInt32Array()


# ---------------------------------------------------------------------------
# Body parts
# ---------------------------------------------------------------------------

func _build_body() -> void:
	_torso()
	_head()
	for side: float in [-1.0, 1.0]:
		_leg(side)
		_arm(side)


## One ring of a tube. `b1` and `w1` let a ring be shared between two bones,
## which is what makes knees and elbows bend smoothly.
func _ring(center: Vector3, rx: float, rz: float, b0: int, color: Color, mat: Vector2,
		b1 := -1, w1 := 0.0, power := 2.0) -> Dictionary:
	return {"c": center, "rx": rx, "rz": rz, "b0": b0, "b1": b1, "w1": w1, "color": color,
		"mat": mat, "power": power}


func _torso() -> void:
	var rings := [
		_ring(Vector3(0, 0.86, 0.0), 0.11, 0.095, B.HIPS, SUIT, MAT_SUIT),
		_ring(Vector3(0, 0.93, 0.0), 0.165, 0.118, B.HIPS, SUIT, MAT_SUIT),
		_ring(Vector3(0, 1.02, 0.0), 0.158, 0.112, B.HIPS, SUIT, MAT_SUIT, B.SPINE, 0.3),
		_ring(Vector3(0, 1.10, 0.0), 0.142, 0.102, B.SPINE, SUIT, MAT_SUIT),
		_ring(Vector3(0, 1.19, 0.0), 0.150, 0.106, B.SPINE, SUIT, MAT_SUIT, B.CHEST, 0.5),
		_ring(Vector3(0, 1.28, 0.0), 0.172, 0.120, B.CHEST, SUIT, MAT_SUIT),
		_ring(Vector3(0, 1.38, -0.005), 0.185, 0.126, B.CHEST, SUIT, MAT_SUIT),
		_ring(Vector3(0, 1.455, 0.0), 0.168, 0.108, B.CHEST, SUIT, MAT_SUIT),
		_ring(Vector3(0, 1.50, 0.005), 0.095, 0.08, B.CHEST, SUIT, MAT_SUIT, B.NECK, 0.4),
		_ring(Vector3(0, 1.54, 0.008), 0.064, 0.068, B.NECK, SUIT, MAT_SUIT),
		_ring(Vector3(0, 1.61, 0.008), 0.062, 0.066, B.NECK, SUIT, MAT_SUIT, B.HEAD, 0.6),
	]
	_loft(rings, 12, true, true)
	# Armour vest over the chest and back (a boxier shell around the body).
	var vest := [
		_ring(Vector3(0, 1.13, 0.0), 0.150, 0.118, B.SPINE, PLATE, MAT_PLATE, B.CHEST, 0.6, 3.0),
		_ring(Vector3(0, 1.16, 0.0), 0.172, 0.138, B.CHEST, PLATE, MAT_PLATE, -1, 0.0, 3.0),
		_ring(Vector3(0, 1.30, -0.004), 0.196, 0.152, B.CHEST, PLATE, MAT_PLATE, -1, 0.0, 3.2),
		_ring(Vector3(0, 1.42, -0.004), 0.200, 0.146, B.CHEST, PLATE, MAT_PLATE, -1, 0.0, 3.2),
		_ring(Vector3(0, 1.475, 0.0), 0.176, 0.118, B.CHEST, PLATE, MAT_PLATE, -1, 0.0, 3.0),
		_ring(Vector3(0, 1.49, 0.0), 0.11, 0.09, B.CHEST, PLATE, MAT_PLATE, -1, 0.0, 2.5),
	]
	_loft(vest, 14, true, true)
	# Belt, pouches, backpack and a small chest light.
	var belt := [
		_ring(Vector3(0, 0.985, 0.0), 0.172, 0.125, B.HIPS, TRIM, MAT_TRIM, -1, 0.0, 2.6),
		_ring(Vector3(0, 1.045, 0.0), 0.170, 0.123, B.HIPS, TRIM, MAT_TRIM, -1, 0.0, 2.6),
	]
	_loft(belt, 12, true, true)
	for side: float in [-1.0, 1.0]:
		_block(Vector3(side * 0.165, 0.99, 0.02), Vector3(0.05, 0.11, 0.10), B.HIPS, TRIM, MAT_TRIM)
	_block(Vector3(0.0, 1.30, 0.185), Vector3(0.25, 0.31, 0.11), B.CHEST, Color(0.5, 0.5, 0.5, 1.0), MAT_PLATE)
	_block(Vector3(0.0, 1.36, 0.243), Vector3(0.15, 0.022, 0.012), B.CHEST, Color(1, 1, 1, 0), Vector2(0.3, 0.0), 2.2)
	_block(Vector3(0.0, 1.47, 0.175), Vector3(0.20, 0.07, 0.09), B.CHEST, PLATE, MAT_PLATE)
	_block(Vector3(0.075, 1.40, -0.153), Vector3(0.05, 0.022, 0.012), B.CHEST, Color(1, 1, 1, 0), Vector2(0.3, 0.0), 2.5)
	for px: float in [-0.095, 0.0, 0.095]:
		_block(Vector3(px, 1.215, -0.158), Vector3(0.075, 0.11, 0.05), B.CHEST, TRIM, MAT_TRIM)


func _head() -> void:
	# Helmet, dark visor with a glowing strip, and a face guard.
	_ball(Vector3(0, 1.70, 0.01), Vector3(0.114, 0.118, 0.13), B.HEAD, PLATE, MAT_PLATE, 7, 12)
	_ball(Vector3(0, 1.69, -0.046), Vector3(0.102, 0.062, 0.1), B.HEAD, VISOR, MAT_VISOR, 6, 12)
	_ball(Vector3(0, 1.626, -0.034), Vector3(0.086, 0.06, 0.097), B.HEAD, TRIM, MAT_TRIM, 5, 10)
	_block(Vector3(0, 1.752, -0.105), Vector3(0.12, 0.014, 0.022), B.HEAD, Color(1, 1, 1, 0), Vector2(0.3, 0.0), 2.0)
	for side: float in [-1.0, 1.0]:
		_block(Vector3(side * 0.114, 1.68, 0.012), Vector3(0.024, 0.07, 0.07), B.HEAD, TRIM, MAT_TRIM)


func _leg(side: float) -> void:
	var left := side < 0.0
	var thigh := B.THIGH_L if left else B.THIGH_R
	var shin := B.SHIN_L if left else B.SHIN_R
	var foot := B.FOOT_L if left else B.FOOT_R
	var x := side * 0.10
	var knee_y := 0.49
	var rings := [
		_ring(Vector3(x, 0.955, 0.0), 0.096, 0.108, B.HIPS, SUIT, MAT_SUIT, thigh, 0.35),
		_ring(Vector3(x, 0.90, 0.0), 0.104, 0.116, thigh, SUIT, MAT_SUIT, B.HIPS, 0.2),
		_ring(Vector3(x, 0.78, 0.0), 0.099, 0.110, thigh, SUIT, MAT_SUIT),
		_ring(Vector3(x, 0.64, 0.0), 0.086, 0.094, thigh, SUIT, MAT_SUIT),
		_ring(Vector3(x, knee_y + 0.06, 0.0), 0.073, 0.080, thigh, SUIT, MAT_SUIT, shin, 0.2),
		_ring(Vector3(x, knee_y, 0.0), 0.069, 0.076, thigh, SUIT, MAT_SUIT, shin, 0.5),
		_ring(Vector3(x, knee_y - 0.06, 0.004), 0.068, 0.076, shin, SUIT, MAT_SUIT, thigh, 0.2),
		_ring(Vector3(x, 0.36, 0.014), 0.070, 0.082, shin, SUIT, MAT_SUIT),
		_ring(Vector3(x, 0.24, 0.006), 0.058, 0.066, shin, SUIT, MAT_SUIT),
		_ring(Vector3(x, 0.13, 0.0), 0.046, 0.050, shin, SUIT, MAT_SUIT, foot, 0.3),
	]
	_loft(rings, 10, true, true)
	# Armour: thigh plate on the outside, knee pad and shin guard on the front.
	_ball(Vector3(x + side * 0.07, 0.74, -0.012), Vector3(0.046, 0.15, 0.09), thigh, PLATE, MAT_PLATE, 5, 8)
	_ball(Vector3(x, knee_y + 0.005, -0.066), Vector3(0.064, 0.075, 0.04), shin, PLATE, MAT_PLATE, 5, 8)
	_ball(Vector3(x, 0.30, -0.05), Vector3(0.062, 0.15, 0.042), shin, PLATE, MAT_PLATE, 5, 8)
	# Boot: a short shaft around the ankle and a foot that points forward (-Z).
	var shaft := [
		_ring(Vector3(x, 0.27, 0.0), 0.068, 0.076, shin, TRIM, MAT_TRIM),
		_ring(Vector3(x, 0.12, 0.0), 0.064, 0.072, shin, TRIM, MAT_TRIM, foot, 0.5),
		_ring(Vector3(x, 0.03, 0.0), 0.062, 0.070, foot, TRIM, MAT_TRIM),
	]
	_loft(shaft, 10, true, true)
	var boot := [
		_ring(Vector3(x, 0.05, 0.095), 0.034, 0.038, foot, TRIM, MAT_TRIM, -1, 0.0, 2.6),
		_ring(Vector3(x, 0.06, 0.055), 0.060, 0.062, foot, TRIM, MAT_TRIM, -1, 0.0, 2.6),
		_ring(Vector3(x, 0.06, -0.05), 0.064, 0.062, foot, TRIM, MAT_TRIM, -1, 0.0, 2.6),
		_ring(Vector3(x, 0.05, -0.14), 0.064, 0.052, foot, TRIM, MAT_TRIM, -1, 0.0, 2.6),
		_ring(Vector3(x, 0.04, -0.20), 0.054, 0.042, foot, TRIM, MAT_TRIM, -1, 0.0, 2.6),
		_ring(Vector3(x, 0.032, -0.225), 0.03, 0.026, foot, TRIM, MAT_TRIM, -1, 0.0, 2.6),
	]
	_loft(boot, 10, true, true, Vector3.RIGHT, Vector3.UP, true)


func _arm(side: float) -> void:
	var left := side < 0.0
	var upper := B.UARM_L if left else B.UARM_R
	var fore := B.FARM_L if left else B.FARM_R
	var hand := B.HAND_L if left else B.HAND_R
	var x := side * 0.20
	var elbow_y := 1.14
	var rings := [
		_ring(Vector3(x - side * 0.02, 1.47, 0.0), 0.058, 0.064, B.CHEST, SUIT, MAT_SUIT, upper, 0.5),
		_ring(Vector3(x, 1.41, 0.0), 0.064, 0.068, upper, SUIT, MAT_SUIT, B.CHEST, 0.15),
		_ring(Vector3(x, 1.30, 0.0), 0.060, 0.064, upper, SUIT, MAT_SUIT),
		_ring(Vector3(x, elbow_y + 0.05, 0.0), 0.052, 0.055, upper, SUIT, MAT_SUIT, fore, 0.2),
		_ring(Vector3(x, elbow_y, 0.0), 0.050, 0.053, upper, SUIT, MAT_SUIT, fore, 0.5),
		_ring(Vector3(x, elbow_y - 0.05, 0.0), 0.051, 0.054, fore, SUIT, MAT_SUIT, upper, 0.2),
		_ring(Vector3(x, 1.0, 0.0), 0.050, 0.053, fore, SUIT, MAT_SUIT),
		_ring(Vector3(x, 0.89, 0.0), 0.040, 0.043, fore, SUIT, MAT_SUIT, hand, 0.3),
	]
	_loft(rings, 9, true, true)
	# Shoulder pad, forearm guard and a gloved hand.
	_ball(Vector3(x + side * 0.022, 1.455, 0.0), Vector3(0.09, 0.068, 0.095), upper, PLATE, MAT_PLATE, 5, 10)
	_ball(Vector3(x + side * 0.014, 1.01, 0.0), Vector3(0.058, 0.105, 0.062), fore, PLATE, MAT_PLATE, 5, 8)
	_ball(Vector3(x, 0.80, -0.008), Vector3(0.04, 0.082, 0.052), hand, TRIM, MAT_TRIM, 5, 8)


# ---------------------------------------------------------------------------
# Mesh building blocks
# ---------------------------------------------------------------------------

func _vert(p: Vector3, color: Color, mat: Vector2, glow: float, b0: int, b1: int, w1: float) -> int:
	_verts.append(p)
	_normals.append(Vector3.ZERO)
	_uvs.append(mat)
	_uv2s.append(Vector2(glow, 0.0))
	_paint.append(color.r)
	_paint.append(color.g)
	_paint.append(color.b)
	_paint.append(color.a)
	var second := b1 if b1 >= 0 else 0
	var w := w1 if b1 >= 0 else 0.0
	_bones.append(b0)
	_bones.append(second)
	_bones.append(0)
	_bones.append(0)
	_weights.append(1.0 - w)
	_weights.append(w)
	_weights.append(0.0)
	_weights.append(0.0)
	return _verts.size() - 1


## Adds a triangle. `inside` is any point inside the shape: it decides which side is the front.
func _tri(a: int, b: int, c: int, inside: Vector3) -> void:
	var face := (_verts[b] - _verts[a]).cross(_verts[c] - _verts[a])
	if face.length_squared() < 1e-14:
		return
	var center := (_verts[a] + _verts[b] + _verts[c]) / 3.0
	var outward := face.dot(center - inside) > 0.0
	# Godot shows the side where the corners go clockwise, which is the side `face` points away from.
	if outward:
		_indices.append(a)
		_indices.append(c)
		_indices.append(b)
	else:
		_indices.append(a)
		_indices.append(b)
		_indices.append(c)
		face = -face
	_normals[a] += face
	_normals[b] += face
	_normals[c] += face


## Skin stretched over a row of rings (a tube). Rings lie in the plane of `axis_u`
## and `axis_v`. `flat_sole` keeps boot soles flat on the ground.
func _loft(rings: Array, segs: int, cap_start: bool, cap_end: bool, axis_u := Vector3.RIGHT,
		axis_v := Vector3.BACK, flat_sole := false, glow := 0.0) -> void:
	var first := _verts.size()
	for ring: Dictionary in rings:
		var e := 2.0 / float(ring.power)
		for s in segs:
			var a := TAU * float(s) / float(segs)
			var cu := cos(a)
			var sv := sin(a)
			var u: float = ring.rx * signf(cu) * pow(absf(cu), e)
			var v: float = ring.rz * signf(sv) * pow(absf(sv), e)
			var p: Vector3 = ring.c + axis_u * u + axis_v * v
			if flat_sole:
				p.y = maxf(p.y, 0.0)
			_vert(p, ring.color, ring.mat, glow, ring.b0, ring.b1, ring.w1)
	for r in rings.size() - 1:
		var inside: Vector3 = (rings[r].c + rings[r + 1].c) * 0.5
		for s in segs:
			var a := first + r * segs + s
			var b := first + r * segs + (s + 1) % segs
			var c := a + segs
			var d := b + segs
			_tri(a, b, d, inside)
			_tri(a, d, c, inside)
	if cap_start:
		_cap(rings[0], first, segs, rings[1].c, glow)
	if cap_end:
		_cap(rings[-1], first + (rings.size() - 1) * segs, segs, rings[-2].c, glow)
	for i in range(first, _verts.size()):
		_normals[i] = _normals[i].normalized()


func _cap(ring: Dictionary, ring_start: int, segs: int, inside: Vector3, glow: float) -> void:
	var mid := _vert(ring.c, ring.color, ring.mat, glow, ring.b0, ring.b1, ring.w1)
	for s in segs:
		_tri(mid, ring_start + s, ring_start + (s + 1) % segs, inside)


## Egg shape fixed to one bone (helmet, pads, hands).
func _ball(center: Vector3, radii: Vector3, bone: int, color: Color, mat: Vector2,
		ring_count := 6, segs := 10, glow := 0.0) -> void:
	var rings := []
	for i in ring_count + 1:
		var t := float(i) / float(ring_count)
		var phi := PI * (0.06 + 0.88 * t)
		var k := sin(phi)
		rings.append(_ring(center + Vector3(0.0, cos(phi) * radii.y, 0.0), radii.x * k, radii.z * k, bone, color, mat))
	_loft(rings, segs, true, true, Vector3.RIGHT, Vector3.BACK, false, glow)


## Box with rounded edges fixed to one bone (backpack, pouches, lights).
func _block(center: Vector3, size: Vector3, bone: int, color: Color, mat: Vector2, glow := 0.0) -> void:
	var h := size * 0.5
	var bevel := minf(h.y, minf(h.x, h.z)) * 0.35
	var rings := [
		_ring(center + Vector3(0, -h.y, 0), h.x - bevel, h.z - bevel, bone, color, mat, -1, 0.0, 4.0),
		_ring(center + Vector3(0, -h.y + bevel, 0), h.x, h.z, bone, color, mat, -1, 0.0, 4.0),
		_ring(center + Vector3(0, h.y - bevel, 0), h.x, h.z, bone, color, mat, -1, 0.0, 4.0),
		_ring(center + Vector3(0, h.y, 0), h.x - bevel, h.z - bevel, bone, color, mat, -1, 0.0, 4.0),
	]
	_loft(rings, 8, true, true, Vector3.RIGHT, Vector3.BACK, false, glow)
