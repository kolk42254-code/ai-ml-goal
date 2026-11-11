extends RefCounted
## Grows trees from code and turns them into 3D meshes.
##
## Only the tool `tools/bake_trees.gd` uses this file. Growing a tree takes a few
## seconds, so it is done once on a computer and the finished meshes are saved in
## `assets/models/trees/`. The game on the phone only loads those files.
##
## How a leafy tree is grown (a method called "space colonisation"):
##   1. Scatter many target points inside the shape the crown should have.
##   2. Start with a bare trunk. Every round, each target point pulls the nearest
##      branch tip a small step towards itself. A target that is reached is removed.
##   3. When no targets are left, the branches fill the crown shape.
## Thick branches become round tubes. Thin twigs are not modelled: flat cards
## with a picture of a leafy twig are put at the branch ends instead.

## Settings per tree kind. Sizes are metres.
const SPECS := {
	"cherry": {
		"seed": 11, "trunk_h": 1.6, "trunk_r": 0.31, "bark": Color(0.30, 0.21, 0.20),
		"crown_center": Vector3(0.0, 4.0, 0.0), "crown_radii": Vector3(4.7, 3.1, 4.7), "min_dir_y": -0.5,
		"limbs": 5, "limb_angle": 0.9, "limb_len": 1.5, "leader": false,
		"clumps": 40, "clump_r": 1.25, "clump_cards": 9, "inner_cards": 26, "fill": 60,
		"step": 0.32, "kill": 0.55, "tropism": Vector3(0.0, 0.03, 0.0),
		"wood_min_r": 0.03, "card": 1.55,
	},
	"maple": {
		"seed": 23, "trunk_h": 2.8, "trunk_r": 0.42, "bark": Color(0.36, 0.30, 0.27),
		"crown_center": Vector3(0.0, 8.4, 0.0), "crown_radii": Vector3(5.6, 5.7, 5.6), "min_dir_y": -0.72,
		"limbs": 4, "limb_angle": 0.6, "limb_len": 2.0, "leader": true,
		"clumps": 46, "clump_r": 1.75, "clump_cards": 8, "inner_cards": 30, "fill": 70,
		"step": 0.42, "kill": 0.7, "tropism": Vector3(0.0, 0.08, 0.0),
		"wood_min_r": 0.045, "card": 2.2,
	},
	"oak": {
		"seed": 37, "trunk_h": 2.1, "trunk_r": 0.82, "bark": Color(0.36, 0.32, 0.27),
		"crown_center": Vector3(0.0, 6.2, 0.0), "crown_radii": Vector3(10.2, 6.2, 9.4), "min_dir_y": -0.42,
		"limbs": 5, "limb_angle": 1.1, "limb_len": 3.0, "leader": false,
		"clumps": 56, "clump_r": 2.3, "clump_cards": 7, "inner_cards": 30, "fill": 90,
		"step": 0.5, "kill": 0.85, "tropism": Vector3(0.0, -0.03, 0.0),
		"wood_min_r": 0.06, "card": 2.9,
	},
	"oak_bare": {
		"seed": 51, "trunk_h": 1.9, "trunk_r": 0.66, "bark": Color(0.33, 0.28, 0.25),
		"crown_center": Vector3(0.0, 5.5, 0.0), "crown_radii": Vector3(8.0, 4.9, 8.0), "min_dir_y": -0.15,
		"limbs": 6, "limb_angle": 1.05, "limb_len": 2.4, "leader": false,
		"clumps": 64, "clump_r": 1.8, "clump_cards": 5, "inner_cards": 44, "fill": 90,
		"step": 0.45, "kill": 0.75, "tropism": Vector3(0.0, -0.015, 0.0),
		"wood_min_r": 0.05, "card": 2.4,
	},
}

const SPRUCE := {"seed": 5, "height": 14.5, "trunk_r": 0.28, "reach": 4.3, "bark": Color(0.40, 0.29, 0.24)}

var _rng := RandomNumberGenerator.new()

# Mesh being collected.
var _verts := PackedVector3Array()
var _normals := PackedVector3Array()
var _uvs := PackedVector2Array()
var _uv2s := PackedVector2Array()
var _colors := PackedColorArray()
var _indices := PackedInt32Array()


static func kinds() -> Array[String]:
	return ["cherry", "spruce", "maple", "oak_bare", "oak"]


func make(kind: String) -> ArrayMesh:
	_verts = PackedVector3Array()
	_normals = PackedVector3Array()
	_uvs = PackedVector2Array()
	_uv2s = PackedVector2Array()
	_colors = PackedColorArray()
	_indices = PackedInt32Array()
	var trunk_r := 0.3
	if kind == "spruce":
		_make_spruce()
		trunk_r = SPRUCE.trunk_r
	else:
		_make_leafy(SPECS[kind])
		trunk_r = SPECS[kind].trunk_r
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = _verts
	arrays[Mesh.ARRAY_NORMAL] = _normals
	arrays[Mesh.ARRAY_TEX_UV] = _uvs
	arrays[Mesh.ARRAY_TEX_UV2] = _uv2s
	arrays[Mesh.ARRAY_COLOR] = _colors
	arrays[Mesh.ARRAY_INDEX] = _indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	# Remember the tree's size: the game needs it for the far-away picture and for collision.
	var half_width := 0.0
	var top := 0.0
	for v in _verts:
		half_width = maxf(half_width, maxf(absf(v.x), absf(v.z)))
		top = maxf(top, v.y)
	mesh.set_meta("width", half_width * 2.0)
	mesh.set_meta("height", top)
	mesh.set_meta("trunk_radius", trunk_r)
	return mesh


# ---------------------------------------------------------------------------
# Leafy trees
# ---------------------------------------------------------------------------

func _random_dir() -> Vector3:
	var y := _rng.randf_range(-1.0, 1.0)
	var a := _rng.randf() * TAU
	var r := sqrt(maxf(0.0, 1.0 - y * y))
	return Vector3(cos(a) * r, y, sin(a) * r)


func _make_leafy(spec: Dictionary) -> void:
	_rng.seed = spec.seed
	var center: Vector3 = spec.crown_center
	var radii: Vector3 = spec.crown_radii
	var step: float = spec.step

	# 1. Leaf clumps sit all over the outside of the crown. Their centres are also
	#    the target points the branches grow towards, plus some targets inside.
	var clumps: Array[Vector3] = []
	var targets := PackedVector3Array()
	var tries := 0
	var lump_a := _rng.randf() * TAU
	var lump_b := _rng.randf() * TAU
	while clumps.size() < int(spec.clumps) and tries < 4000:
		tries += 1
		var dir := _random_dir()
		if dir.y < spec.min_dir_y:
			continue
		# A wavy factor makes the crown bulge in some directions and dip in others.
		var ang := atan2(dir.z, dir.x)
		var lumpy := 1.0 + 0.14 * sin(ang * 3.0 + lump_a) * (1.0 - absf(dir.y)) + 0.10 * sin(ang * 5.0 + lump_b + dir.y * 3.0)
		var mid := center + dir * radii * _rng.randf_range(0.68, 0.9) * lumpy
		if mid.y < spec.trunk_h + 0.5:
			continue
		# Keep clumps apart so they cover the crown evenly.
		var crowded := false
		for other in clumps:
			if other.distance_to(mid) < float(spec.clump_r) * 0.95:
				crowded = true
				break
		if crowded and tries < 3000:
			continue
		clumps.append(mid)
		targets.append(mid)
		for j in 3:
			targets.append(mid + _random_dir() * float(spec.clump_r) * 0.6)
	for i in int(spec.fill):
		var dir := _random_dir()
		if dir.y < spec.min_dir_y:
			dir.y = -dir.y
		var inner := center + dir * radii * _rng.randf_range(0.2, 0.7)
		if inner.y > spec.trunk_h + 0.4:
			targets.append(inner)

	# 2. The trunk.
	var pos := PackedVector3Array()
	var parent := PackedInt32Array()
	pos.append(Vector3.ZERO)
	parent.append(-1)
	var p := Vector3.ZERO
	var lean := Vector3(_rng.randf_range(-0.06, 0.06), 1.0, _rng.randf_range(-0.06, 0.06))
	while p.y < spec.trunk_h:
		p += lean.normalized() * step
		pos.append(p)
		parent.append(pos.size() - 2)

	# 3. A few main limbs leave the top of the trunk, like the big arms of an oak.
	var top := pos.size() - 1
	var limb_turn := _rng.randf() * TAU
	for l in int(spec.limbs):
		var ang := limb_turn + TAU * (float(l) + _rng.randf_range(-0.2, 0.2)) / float(spec.limbs)
		var tilt: float = float(spec.limb_angle) * _rng.randf_range(0.85, 1.15)     # angle away from straight up
		var dir := Vector3(cos(ang) * sin(tilt), cos(tilt), sin(ang) * sin(tilt))
		var at := top
		var q := pos[top]
		for k in int(ceil(float(spec.limb_len) * _rng.randf_range(0.8, 1.2) / step)):
			dir = (dir + _random_dir() * 0.12 + Vector3.UP * 0.02).normalized()
			q += dir * step
			pos.append(q)
			parent.append(at)
			at = pos.size() - 1
	if spec.leader:
		# Some trees (maple) also keep a trunk that runs on upwards.
		var at := top
		var q := pos[top]
		for k in int(ceil(float(spec.limb_len) * 1.4 / step)):
			q += (Vector3.UP + _random_dir() * 0.1).normalized() * step
			pos.append(q)
			parent.append(at)
			at = pos.size() - 1

	# 4. Grow towards the targets: every target pulls on the node nearest to it.
	var kill2: float = float(spec.kill) * float(spec.kill)
	var tropism: Vector3 = spec.tropism
	for round_number in 260:
		if targets.is_empty():
			break
		var pull := {}
		for t in targets:
			var best := 0
			var best_d := 1e20
			for n in pos.size():
				var d := t.distance_squared_to(pos[n])
				if d < best_d:
					best_d = d
					best = n
			pull[best] = pull.get(best, Vector3.ZERO) + (t - pos[best]).normalized()
		var first_new := pos.size()
		for n: int in pull:
			var dir: Vector3 = (pull[n] as Vector3).normalized() + tropism
			if dir.length() < 0.05:
				dir = _random_dir()
			pos.append(pos[n] + dir.normalized() * step)
			parent.append(n)
		# Targets that a new node has reached are done.
		var left := PackedVector3Array()
		for t in targets:
			var hit := false
			for n in range(first_new, pos.size()):
				if t.distance_squared_to(pos[n]) < kill2:
					hit = true
					break
			if not hit:
				left.append(t)
		targets = left

	# 5. Branch thickness: a branch is as thick as all the twigs it carries together.
	var count := pos.size()
	var kids: Array[PackedInt32Array] = []
	kids.resize(count)
	for i in count:
		kids[i] = PackedInt32Array()
	for i in range(1, count):
		kids[parent[i]].append(i)
	var radius := PackedFloat32Array()
	radius.resize(count)
	var power := 2.35
	for i in range(count - 1, -1, -1):
		if kids[i].is_empty():
			radius[i] = 0.012
		else:
			var sum := 0.0
			for k in kids[i]:
				sum += pow(radius[k], power)
			radius[i] = pow(sum, 1.0 / power)
	var scale: float = float(spec.trunk_r) / radius[0]
	var length_from_root := PackedFloat32Array()
	length_from_root.resize(count)
	for i in count:
		radius[i] = maxf(radius[i] * scale, 0.012)
		length_from_root[i] = 0.0 if parent[i] < 0 else length_from_root[parent[i]] + pos[i].distance_to(pos[parent[i]])
	# The foot of the trunk spreads out a little.
	for i in count:
		if pos[i].y < 0.9 and length_from_root[i] < 1.1:
			radius[i] *= lerpf(1.7, 1.0, pos[i].y / 0.9)

	# 6. Wood: tubes for every branch that is thick enough. Every second node is
	#    skipped on straight runs to save triangles.
	var keep := PackedByteArray()
	keep.resize(count)
	for i in count:
		keep[i] = 1 if (i == 0 or kids[i].size() != 1 or i % 2 == 0) else 0
	var kept_parent := PackedInt32Array()
	kept_parent.resize(count)
	var thickest_kid := PackedInt32Array()          # for kept nodes: the kept child that carries on the branch
	thickest_kid.resize(count)
	thickest_kid.fill(-1)
	for i in count:
		kept_parent[i] = -1
		if i == 0 or keep[i] == 0:
			continue
		var a := parent[i]
		while keep[a] == 0:
			a = parent[a]
		kept_parent[i] = a
		if thickest_kid[a] == -1 or radius[i] > radius[thickest_kid[a]]:
			thickest_kid[a] = i
	var bark: Color = spec.bark
	var crown_h := radii.y * 2.0
	for i in range(1, count):
		if keep[i] == 0 or radius[i] < spec.wood_min_r:
			continue
		var a := kept_parent[i]
		var dir := (pos[i] - pos[a]).normalized()
		var carries_on := thickest_kid[a] == i
		# Where a branch carries on, both tubes share a slanted ring, so there is no gap at bends.
		var start_dir := dir
		var start_r := minf(radius[a], radius[i] * 1.3)
		if carries_on:
			start_r = radius[a]
			if kept_parent[a] >= 0:
				start_dir = (dir + (pos[a] - pos[kept_parent[a]]).normalized()).normalized()
		var end_dir := dir
		if thickest_kid[i] >= 0:
			end_dir = (dir + (pos[thickest_kid[i]] - pos[i]).normalized()).normalized()
		var shade_a := lerpf(1.0, 0.7, clampf((pos[a].y - spec.trunk_h) / crown_h, 0.0, 1.0))
		var shade_b := lerpf(1.0, 0.7, clampf((pos[i].y - spec.trunk_h) / crown_h, 0.0, 1.0))
		_tube(pos[a], pos[i], start_r, radius[i], length_from_root[a], length_from_root[i],
			Color(bark.r * shade_a, bark.g * shade_a, bark.b * shade_a, 0.0),
			Color(bark.r * shade_b, bark.g * shade_b, bark.b * shade_b, 0.0),
			_sway(pos[a], spec.trunk_h, crown_h, radii.x), _sway(pos[i], spec.trunk_h, crown_h, radii.x),
			start_dir, end_dir)

	# 7. Leaves. Every clump is a small ball of cards that face outwards, so the
	#    crown looks full from every side. A few more cards fill the inside.
	var card_size: float = spec.card
	for mid in clumps:
		var clump_r: float = float(spec.clump_r) * _rng.randf_range(0.65, 1.35)
		for c in int(spec.clump_cards):
			var dir := _random_dir()
			var away := (mid - center).normalized()
			# Most cards sit on the side of the clump that faces out of the crown.
			if dir.dot(away) < -0.3:
				dir = -dir
			var at := mid + Vector3(dir.x, dir.y * 0.75, dir.z) * clump_r * _rng.randf_range(0.45, 0.8)
			_leaf_card(at, card_size * _rng.randf_range(0.8, 1.2), dir, mid, center, radii)
	for c in int(spec.inner_cards):
		var dir := _random_dir()
		if dir.y < spec.min_dir_y:
			dir.y = -dir.y
		var at := center + dir * radii * _rng.randf_range(0.3, 0.62)
		_leaf_card(at, card_size * _rng.randf_range(0.9, 1.3), dir, at - dir, center, radii)


## True when `i` continues the thickest line out of node `a` (trunk or main limb).
func _is_thickest_child(a: int, i: int, kids: Array[PackedInt32Array], radius: PackedFloat32Array,
		parent: PackedInt32Array) -> bool:
	# Walk up from i to the direct child of a.
	var first := i
	while parent[first] != a:
		first = parent[first]
	for k in kids[a]:
		if k != first and radius[k] > radius[first]:
			return false
	return true


## How much a point moves in the wind: nothing at the foot of the trunk, most at the crown's edge.
func _sway(p: Vector3, trunk_h: float, crown_h: float, crown_r: float) -> float:
	var up := clampf((p.y - trunk_h * 0.6) / (crown_h + trunk_h), 0.0, 1.0)
	var out := clampf(Vector2(p.x, p.z).length() / crown_r, 0.0, 1.0)
	return clampf(up * up * 0.7 + out * 0.5, 0.0, 1.0)


func _sides_for(r: float) -> int:
	if r > 0.3:
		return 9
	if r > 0.14:
		return 7
	if r > 0.07:
		return 5
	if r > 0.035:
		return 4
	return 3


## A tapered tube from `a` to `b`. `len_a` and `len_b` place the bark picture along
## the branch. `dir_a` and `dir_b` tilt the two end rings (used to join tubes at bends).
func _tube(a: Vector3, b: Vector3, ra: float, rb: float, len_a: float, len_b: float,
		col_a: Color, col_b: Color, sway_a: float, sway_b: float,
		dir_a := Vector3.ZERO, dir_b := Vector3.ZERO) -> void:
	var dir := (b - a)
	if dir.length() < 0.001:
		return
	dir = dir.normalized()
	if dir_a == Vector3.ZERO:
		dir_a = dir
	if dir_b == Vector3.ZERO:
		dir_b = dir
	# One sideways direction for the whole tube keeps it from twisting.
	var ref := Vector3.FORWARD if absf(dir.dot(Vector3.FORWARD)) < 0.9 else Vector3.RIGHT
	var x := dir.cross(ref).normalized()
	var z := x.cross(dir).normalized()
	var sides := _sides_for(maxf(ra, rb))
	var wraps := maxf(1.0, roundf(TAU * maxf(ra, rb) / 0.9))
	var first := _verts.size()
	for s in sides + 1:
		var ang := TAU * float(s) / float(sides)
		var n := x * cos(ang) + z * sin(ang)
		var u := float(s) / float(sides) * wraps
		# Slide each ring point along the tube so the ring lies in its tilted plane.
		var na := n - dir * (n.dot(dir_a) / maxf(dir.dot(dir_a), 0.3))
		var nb := n - dir * (n.dot(dir_b) / maxf(dir.dot(dir_b), 0.3))
		_verts.append(a + na * ra)
		_normals.append(n)
		_uvs.append(Vector2(u, len_a / 1.8))
		_uv2s.append(Vector2(sway_a, 0.0))
		_colors.append(col_a)
		_verts.append(b + nb * rb)
		_normals.append(n)
		_uvs.append(Vector2(u, len_b / 1.8))
		_uv2s.append(Vector2(sway_b, 0.0))
		_colors.append(col_b)
	for s in sides:
		var i := first + s * 2
		var outward := x * cos(TAU * (s + 0.5) / sides) + z * sin(TAU * (s + 0.5) / sides)
		_tri(i, i + 2, i + 1, outward)
		_tri(i + 1, i + 2, i + 3, outward)


func _tri(a: int, b: int, c: int, outward: Vector3) -> void:
	var face := (_verts[b] - _verts[a]).cross(_verts[c] - _verts[a])
	if face.dot(outward) > 0.0:
		_indices.append(a)
		_indices.append(c)
		_indices.append(b)
	else:
		_indices.append(a)
		_indices.append(b)
		_indices.append(c)


## One flat card with a leafy-twig picture.
##   at        middle of the card            out      direction the card faces
##   clump_mid middle of the clump it belongs to (light seems to wrap around that ball)
func _leaf_card(at: Vector3, size: float, out: Vector3, clump_mid: Vector3, center: Vector3, radii: Vector3) -> void:
	var crown_out := (at - center) / radii
	var depth := clampf(crown_out.length(), 0.0, 1.2)       # 0 = middle of the crown, 1 = its surface
	var crown_dir := crown_out.normalized() if crown_out.length() > 0.01 else Vector3.UP
	var facing := (out + crown_dir * 0.35 + _random_dir() * 0.35).normalized()
	var ax := facing.cross(Vector3.UP)
	ax = ax.normalized() if ax.length() > 0.01 else Vector3.RIGHT
	var ay := ax.cross(facing).normalized()
	var turn := _rng.randf() * TAU
	var bx := ax * cos(turn) + ay * sin(turn)
	var by := ay * cos(turn) - ax * sin(turn)
	# The stored light direction mixes "out of the clump" and "out of the crown":
	# every clump is lit like a small ball, and the whole crown like a big one.
	var clump_dir := (at - clump_mid).normalized() if at.distance_to(clump_mid) > 0.01 else crown_dir
	var light := (clump_dir * 0.55 + crown_dir * 0.6 + Vector3.UP * 0.25).normalized()
	# Less light deep inside the crown and on the underside of a clump.
	var shade := lerpf(0.34, 1.0, smoothstep(0.3, 0.95, depth))
	shade *= lerpf(0.5, 1.0, clampf(clump_dir.y * 0.6 + 0.6, 0.0, 1.0))
	shade *= _rng.randf_range(0.9, 1.08)
	var tint := Color(shade * _rng.randf_range(0.94, 1.06), shade, shade * _rng.randf_range(0.92, 1.05), 1.0)
	var tile := Vector2(_rng.randi() % 2, _rng.randi() % 2)
	var sway := clampf(0.55 + 0.45 * depth, 0.0, 1.0)
	var phase := _rng.randf()
	var half := size * 0.5
	var first := _verts.size()
	var corners := [Vector2(-1, -1), Vector2(1, -1), Vector2(1, 1), Vector2(-1, 1)]
	for c: Vector2 in corners:
		_verts.append(at + bx * c.x * half + by * c.y * half)
		_normals.append((light + (bx * c.x + by * c.y) * 0.25).normalized())
		_uvs.append((tile + Vector2(c.x * 0.5 + 0.5, 0.5 - c.y * 0.5)) * 0.5)
		_uv2s.append(Vector2(sway, phase))
		_colors.append(tint)
	_indices.append_array([first, first + 1, first + 2, first, first + 2, first + 3])


# ---------------------------------------------------------------------------
# Spruce
# ---------------------------------------------------------------------------

func _make_spruce() -> void:
	_rng.seed = SPRUCE.seed
	var height: float = SPRUCE.height
	var bark: Color = SPRUCE.bark
	# Trunk: a straight pole that gets thinner towards the top.
	var parts := 7
	for i in parts:
		var y0 := height * float(i) / parts
		var y1 := height * float(i + 1) / parts
		var r0 := lerpf(SPRUCE.trunk_r, 0.03, pow(float(i) / parts, 0.8)) * (1.4 if i == 0 else 1.0)
		var r1 := lerpf(SPRUCE.trunk_r, 0.03, pow(float(i + 1) / parts, 0.8))
		var c := Color(bark.r, bark.g, bark.b, 0.0)
		_tube(Vector3(0, y0, 0), Vector3(0, y1, 0), r0, r1, y0, y1, c, c, pow(y0 / height, 2.0) * 0.5, pow(y1 / height, 2.0) * 0.5)

	# A dark cone inside the branches. Without it you could see right through the tree.
	var core := Color(0.035, 0.075, 0.045, 0.0)
	_tube(Vector3(0, 1.5, 0), Vector3(0, height - 1.2, 0), float(SPRUCE.reach) * 0.45, 0.12, 0.0, 6.0, core, core, 0.1, 0.5)

	# Rings of branches. Low branches are long and hang down; high ones are short and point up.
	var y := 1.2
	var gap := 0.72
	while y < height - 0.7:
		var t := (y - 1.0) / (height - 1.0)                  # 0 at the lowest branches, 1 at the top
		var reach: float = float(SPRUCE.reach) * pow(1.0 - t, 0.82) + 0.3
		var branches := 9 if t < 0.35 else (7 if t < 0.7 else 5)
		var turn := _rng.randf() * TAU
		for b in branches:
			var ang := turn + TAU * (float(b) + _rng.randf_range(-0.25, 0.25)) / branches
			var dir := Vector3(cos(ang), 0.0, sin(ang))
			var length := reach * _rng.randf_range(0.72, 1.12)
			var droop := lerpf(0.42, -0.25, t) + _rng.randf_range(-0.06, 0.06)      # slope downwards at the trunk
			var lift := 0.22                                                       # tips curve up again
			var sprays := maxi(2, roundi(length / 0.8))
			for s in sprays:
				var u0 := float(s) / sprays
				var u1 := minf(1.0, (float(s) + 1.75) / sprays)
				var p0 := Vector3(0, y, 0) + dir * (length * u0) + Vector3.UP * length * (-droop * u0 + lift * u0 * u0)
				var p1 := Vector3(0, y, 0) + dir * (length * u1) + Vector3.UP * length * (-droop * u1 + lift * u1 * u1)
				var width := (p1 - p0).length() * _rng.randf_range(1.0, 1.25)
				_spruce_card(p0, p1, width, dir, _rng.randf_range(-0.75, 0.75), 1.0, u0, t, height, 0 if _rng.randf() < 0.5 else 1)
			# The tip of the branch hangs down: one more spray, tilted steeply.
			var tip := Vector3(0, y, 0) + dir * (length * 0.86) + Vector3.UP * length * (-droop * 0.86 + lift * 0.74)
			var hang := (dir * 0.75 + Vector3.DOWN * 0.66).normalized() * maxf(0.5, length * 0.3)
			_spruce_card(tip, tip + hang, hang.length() * 1.1, dir, _rng.randf_range(-0.3, 0.3), 1.0, 0.9, t, height, 3)
			if t < 0.72:
				# A curtain of small twigs hanging under the branch.
				var a := Vector3(0, y, 0) + dir * (length * 0.18) + Vector3.UP * length * (-droop * 0.18)
				var e := Vector3(0, y, 0) + dir * (length * 0.95) + Vector3.UP * length * (-droop * 0.95 + lift * 0.9)
				_spruce_curtain(a, e, lerpf(0.8, 0.35, t) * _rng.randf_range(0.8, 1.15), dir, t, height)
		y += gap
		gap = maxf(0.42, gap * 0.965)
	# The tip.
	for i in 3:
		var ang := TAU * i / 3.0 + 0.4
		var dir := Vector3(cos(ang), 0.0, sin(ang))
		_spruce_card(Vector3(0, height - 0.95, 0), Vector3(0, height - 0.95, 0) + dir * 0.55 + Vector3.UP * 0.75, 0.6, dir, 0.0, 1.0, 0.5, 1.0, height, 3)


## One spruce spray: a card along the branch from `p0` to `p1`, rolled a little around the branch.
func _spruce_card(p0: Vector3, p1: Vector3, width: float, out_dir: Vector3, roll: float, light_k: float,
		along: float, t: float, height: float, tile_index: int) -> void:
	var axis := (p1 - p0).normalized()
	var side := axis.cross(Vector3.UP)
	side = side.normalized() if side.length() > 0.01 else out_dir.cross(Vector3.UP).normalized()
	var up := side.cross(axis).normalized()
	var across := (side * cos(roll) + up * sin(roll)) * width * 0.5
	var tile := Vector2(tile_index % 2, tile_index / 2)
	# Darker close to the trunk (deep inside the tree), lighter at the tips.
	var shade := lerpf(0.55, 1.0, clampf(along * 1.2 + 0.15, 0.0, 1.0)) * lerpf(0.8, 1.0, t) * light_k * _rng.randf_range(0.9, 1.08)
	var col := Color(shade, shade, shade, 1.0)
	var light := (out_dir * 0.6 + Vector3.UP * 0.7).normalized()
	var sway := clampf(0.25 + 0.5 * along + 0.25 * t, 0.0, 1.0)
	var phase := _rng.randf()
	var first := _verts.size()
	var corners := [[p0 - across, Vector2(0, 1)], [p1 - across, Vector2(1, 1)], [p1 + across, Vector2(1, 0)], [p0 + across, Vector2(0, 0)]]
	for c: Array in corners:
		_verts.append(c[0])
		_normals.append(light)
		_uvs.append((tile + (c[1] as Vector2)) * 0.5)
		_uv2s.append(Vector2(sway, phase))
		_colors.append(col)
	_indices.append_array([first, first + 1, first + 2, first, first + 2, first + 3])


## Hanging twigs under a spruce branch: an upright card from `a` to `e`, `drop` metres tall.
func _spruce_curtain(a: Vector3, e: Vector3, drop: float, out_dir: Vector3, t: float, _height: float) -> void:
	var tile := Vector2(0, 1)                                 # third picture: hanging strands
	var shade := lerpf(0.6, 0.85, t) * _rng.randf_range(0.9, 1.05)
	var col := Color(shade, shade, shade, 1.0)
	var light := (out_dir * 0.7 + Vector3.UP * 0.5).normalized()
	var down := Vector3.DOWN * drop
	var first := _verts.size()
	var corners := [[a, Vector2(0, 0)], [e, Vector2(1, 0)], [e + down, Vector2(1, 1)], [a + down, Vector2(0, 1)]]
	var phase := _rng.randf()
	for c: Array in corners:
		_verts.append(c[0])
		_normals.append(light)
		_uvs.append((tile + (c[1] as Vector2)) * 0.5)
		_uv2s.append(Vector2(0.6, phase))
		_colors.append(col)
	_indices.append_array([first, first + 1, first + 2, first, first + 2, first + 3])
