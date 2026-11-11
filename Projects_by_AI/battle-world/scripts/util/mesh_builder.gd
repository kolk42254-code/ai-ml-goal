extends RefCounted
## Collects triangles and turns them into one mesh surface.
##
## Every add call uses the current `xform`, so a shape can be moved and rotated
## before it is added. Triangle winding is fixed automatically from the normal,
## so callers never have to think about clockwise / counter-clockwise order.
##
## Vertex data is used by the shaders like this:
##   colour.rgb = base colour       colour.a = tint mask (1 = use the per-object tint)
##   UV         = (roughness, metallic) for props, or real texture coordinates
##   UV2        = (emission strength, wind sway amount)
##   CUSTOM0    = 4 free numbers (only when `use_custom` is true)
##
## With `paint_mode` on, the colour is saved in CUSTOM0 instead of COLOR. The
## engine then fills COLOR with each object's own tint (white when it has none).

var xform := Transform3D.IDENTITY
var use_custom := false
var paint_mode := false

var verts := PackedVector3Array()
var normals := PackedVector3Array()
var uvs := PackedVector2Array()
var uv2s := PackedVector2Array()
var colors := PackedColorArray()
var customs := PackedFloat32Array()
var indices := PackedInt32Array()


func is_empty() -> bool:
	return indices.is_empty()


func vertex(p: Vector3, n: Vector3, uv: Vector2, color: Color,
		uv2 := Vector2.ZERO, custom := Vector4.ZERO) -> int:
	verts.append(xform * p)
	normals.append((xform.basis * n).normalized())
	uvs.append(uv)
	uv2s.append(uv2)
	colors.append(color)
	if use_custom:
		customs.append(custom.x)
		customs.append(custom.y)
		customs.append(custom.z)
		customs.append(custom.w)
	return verts.size() - 1


## Adds a triangle from three vertex numbers. The order is flipped when needed
## so the front of the triangle is on the side its normals point to.
func tri(a: int, b: int, c: int) -> void:
	var face := (verts[b] - verts[a]).cross(verts[c] - verts[a])
	var n := normals[a] + normals[b] + normals[c]
	# Godot draws the front of a triangle when its corners go clockwise.
	if face.dot(n) > 0.0:
		indices.append(a)
		indices.append(c)
		indices.append(b)
	else:
		indices.append(a)
		indices.append(b)
		indices.append(c)


## Flat four-corner face. Corners go around the face in order (either direction).
func quad(p0: Vector3, p1: Vector3, p2: Vector3, p3: Vector3, n: Vector3,
		uv0: Vector2, uv1: Vector2, uv2_: Vector2, uv3: Vector2, color: Color,
		extra := Vector2.ZERO, custom := Vector4.ZERO) -> void:
	var a := vertex(p0, n, uv0, color, extra, custom)
	var b := vertex(p1, n, uv1, color, extra, custom)
	var c := vertex(p2, n, uv2_, color, extra, custom)
	var d := vertex(p3, n, uv3, color, extra, custom)
	tri(a, b, c)
	tri(a, c, d)


## Box for props: every corner of a face gets the same `mat` (roughness, metallic).
## `skip_bottom` leaves out the face nobody can see.
func box(center: Vector3, size: Vector3, color: Color, mat := Vector2(0.8, 0.0),
		extra := Vector2.ZERO, skip_bottom := false) -> void:
	var h := size * 0.5
	var c := center
	# +X and -X
	quad(c + Vector3(h.x, -h.y, -h.z), c + Vector3(h.x, h.y, -h.z), c + Vector3(h.x, h.y, h.z),
		c + Vector3(h.x, -h.y, h.z), Vector3.RIGHT, mat, mat, mat, mat, color, extra)
	quad(c + Vector3(-h.x, -h.y, -h.z), c + Vector3(-h.x, h.y, -h.z), c + Vector3(-h.x, h.y, h.z),
		c + Vector3(-h.x, -h.y, h.z), Vector3.LEFT, mat, mat, mat, mat, color, extra)
	# +Z and -Z
	quad(c + Vector3(-h.x, -h.y, h.z), c + Vector3(-h.x, h.y, h.z), c + Vector3(h.x, h.y, h.z),
		c + Vector3(h.x, -h.y, h.z), Vector3.BACK, mat, mat, mat, mat, color, extra)
	quad(c + Vector3(-h.x, -h.y, -h.z), c + Vector3(-h.x, h.y, -h.z), c + Vector3(h.x, h.y, -h.z),
		c + Vector3(h.x, -h.y, -h.z), Vector3.FORWARD, mat, mat, mat, mat, color, extra)
	# top and bottom
	quad(c + Vector3(-h.x, h.y, -h.z), c + Vector3(h.x, h.y, -h.z), c + Vector3(h.x, h.y, h.z),
		c + Vector3(-h.x, h.y, h.z), Vector3.UP, mat, mat, mat, mat, color, extra)
	if not skip_bottom:
		quad(c + Vector3(-h.x, -h.y, -h.z), c + Vector3(h.x, -h.y, -h.z), c + Vector3(h.x, -h.y, h.z),
			c + Vector3(-h.x, -h.y, h.z), Vector3.DOWN, mat, mat, mat, mat, color, extra)


## Upright cylinder or cone. `base` is the centre of the bottom circle.
## `extra_bottom` / `extra_top` let UV2 change along the height (used for tree sway).
func cylinder(base: Vector3, r_bottom: float, r_top: float, height: float, segs: int,
		color: Color, mat := Vector2(0.8, 0.0), extra_bottom := Vector2.ZERO,
		extra_top := Vector2.ZERO, cap_top := true, cap_bottom := false) -> void:
	var slope := (r_bottom - r_top) / maxf(height, 0.0001)
	var first := verts.size()
	for i in segs + 1:
		var a := TAU * float(i) / float(segs)
		var dir := Vector3(cos(a), 0.0, sin(a))
		var n := Vector3(dir.x, slope, dir.z).normalized()
		vertex(base + dir * r_bottom, n, mat, color, extra_bottom)
		vertex(base + dir * r_top + Vector3(0.0, height, 0.0), n, mat, color, extra_top)
	for i in segs:
		var b := first + i * 2
		tri(b, b + 1, b + 3)
		tri(b, b + 3, b + 2)
	if cap_top and r_top > 0.0005:
		_disc(base + Vector3(0.0, height, 0.0), r_top, segs, Vector3.UP, color, mat, extra_top)
	if cap_bottom and r_bottom > 0.0005:
		_disc(base, r_bottom, segs, Vector3.DOWN, color, mat, extra_bottom)


func _disc(center: Vector3, radius: float, segs: int, n: Vector3, color: Color,
		mat: Vector2, extra: Vector2) -> void:
	var mid := vertex(center, n, mat, color, extra)
	var first := verts.size()
	for i in segs + 1:
		var a := TAU * float(i) / float(segs)
		vertex(center + Vector3(cos(a), 0.0, sin(a)) * radius, n, mat, color, extra)
	for i in segs:
		tri(mid, first + i, first + i + 1)


## Flat disc lying on the ground plane (facing up).
func disc(center: Vector3, radius: float, segs: int, color: Color, mat := Vector2(0.8, 0.0),
		extra := Vector2.ZERO) -> void:
	_disc(center, radius, segs, Vector3.UP, color, mat, extra)


## Ball that can be squashed (`radii`) and made lumpy (`bumpy`), used for tree tops and bushes.
## `shade_bottom` darkens the lower half a little so it looks shaded.
func blob(center: Vector3, radii: Vector3, rings: int, segs: int, color: Color,
		mat := Vector2(0.9, 0.0), extra_bottom := Vector2.ZERO, extra_top := Vector2.ZERO,
		bumpy := 0.0, shade_bottom := 0.0, noise_seed := 0.0) -> void:
	var first := verts.size()
	for r in rings + 1:
		var v := float(r) / float(rings)
		var phi := PI * v                      # 0 = top, PI = bottom
		for s in segs + 1:
			var u := float(s) / float(segs)
			var theta := TAU * u
			var dir := Vector3(sin(phi) * cos(theta), cos(phi), sin(phi) * sin(theta))
			var k := 1.0
			if bumpy > 0.0:
				var wrap := theta if s < segs else 0.0   # keep the seam closed
				k += bumpy * (sin(wrap * 3.0 + noise_seed) * sin(phi * 4.0 + noise_seed * 1.7)
					+ 0.5 * sin(wrap * 5.0 + noise_seed * 2.3 + phi * 3.0))
			var p := Vector3(dir.x * radii.x, dir.y * radii.y, dir.z * radii.z) * k
			var n := Vector3(dir.x / radii.x, dir.y / radii.y, dir.z / radii.z).normalized()
			var t := 1.0 - v                    # 1 at the top, 0 at the bottom
			var col := color.darkened(shade_bottom * (1.0 - t))
			col.a = color.a
			vertex(center + p, n, mat, col, extra_bottom.lerp(extra_top, t))
	for r in rings:
		for s in segs:
			var a := first + r * (segs + 1) + s
			var b := a + segs + 1
			if r > 0:
				tri(a, a + 1, b)
			if r < rings - 1:
				tri(a + 1, b + 1, b)


## Pushes a flat outline (points in the Z-Y plane: x = z, y = y) along the X axis
## from `x0` to `x1`. Used for car bodies. Side walls get flat shading.
func extrude_x(outline: PackedVector2Array, x0: float, x1: float, color: Color,
		mat := Vector2(0.4, 0.2), extra := Vector2.ZERO, caps := true,
		cap_color := Color(-1, 0, 0)) -> void:
	var count := outline.size()
	# Work out which way round the outline goes, so the side walls face outwards.
	var area := 0.0
	for i in count:
		var p0 := outline[i]
		var q0 := outline[(i + 1) % count]
		area += p0.x * q0.y - q0.x * p0.y
	var outward := -1.0 if area > 0.0 else 1.0
	for i in count:
		var p := outline[i]
		var q := outline[(i + 1) % count]
		var edge := q - p
		if edge.length() < 0.0001:
			continue
		var n := Vector3(0.0, edge.x, -edge.y).normalized() * outward
		quad(Vector3(x0, p.y, p.x), Vector3(x1, p.y, p.x), Vector3(x1, q.y, q.x),
			Vector3(x0, q.y, q.x), n, mat, mat, mat, mat, color, extra)
	if caps:
		var cc := color if cap_color.r < 0.0 else cap_color
		var tris := Geometry2D.triangulate_polygon(outline)
		for side in 2:
			var x := x0 if side == 0 else x1
			var n := Vector3.LEFT if (x0 < x1) == (side == 0) else Vector3.RIGHT
			var first := verts.size()
			for p in outline:
				vertex(Vector3(x, p.y, p.x), n, mat, cc, extra)
			for t in range(0, tris.size(), 3):
				tri(first + tris[t], first + tris[t + 1], first + tris[t + 2])


## Adds everything collected so far to `mesh` as a new surface. Returns the surface number.
func commit(mesh: ArrayMesh, material: Material) -> int:
	if indices.is_empty():
		return -1
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_TEX_UV2] = uv2s
	arrays[Mesh.ARRAY_INDEX] = indices
	var flags := 0
	if paint_mode:
		var paint := PackedFloat32Array()
		paint.resize(colors.size() * 4)
		for i in colors.size():
			var c := colors[i]
			paint[i * 4] = c.r
			paint[i * 4 + 1] = c.g
			paint[i * 4 + 2] = c.b
			paint[i * 4 + 3] = c.a
		arrays[Mesh.ARRAY_CUSTOM0] = paint
		flags = Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT
	else:
		arrays[Mesh.ARRAY_COLOR] = colors
		if use_custom:
			arrays[Mesh.ARRAY_CUSTOM0] = customs
			flags = Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {}, flags)
	var surface := mesh.get_surface_count() - 1
	if material:
		mesh.surface_set_material(surface, material)
	return surface


func build(material: Material) -> ArrayMesh:
	var mesh := ArrayMesh.new()
	commit(mesh, material)
	return mesh
