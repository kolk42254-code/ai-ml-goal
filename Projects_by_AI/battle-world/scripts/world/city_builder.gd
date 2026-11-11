extends Node3D
## Turns the city data from `city_layout.gd` into things you can see and bump into:
## meshes, collision shapes and props. One mesh per block keeps drawing fast.

const CityLayout := preload("res://scripts/world/city_layout.gd")
const MeshBuilder := preload("res://scripts/util/mesh_builder.gd")
const PropLibrary := preload("res://scripts/world/prop_library.gd")
const TreeLibrary := preload("res://scripts/world/tree_library.gd")

## Props are grouped into SECTORS x SECTORS squares, so far-away groups are skipped.
const SECTORS := 5
const WORLD_LAYER := 1
## Full tree models are grouped in squares of this size (metres). A whole square
## is skipped when it is too far away to show full models.
const TREE_CELL := 40.0

var layout: CityLayout
var materials := {}
var ao_texture: ImageTexture
var minimap_image: Image

var _prop_nodes: Array[MultiMeshInstance3D] = []
var _prop_names: Array[String] = []
var _shape_cache := {}
var _tree_groups: Array[MultiMeshInstance3D] = []


func build(p_layout: CityLayout) -> void:
	layout = p_layout
	_make_maps()
	_make_materials()
	_build_roads()
	_build_water()
	_build_chunks()
	_build_props()
	_build_trees()


# ---------------------------------------------------------------------------
# Pictures made from the layout: soft shadow map for the ground, and the minimap
# ---------------------------------------------------------------------------

func _make_maps() -> void:
	var size := 512
	var b := layout.bounds
	var scale := float(size) / b.size.x
	var ao := Image.create(size, size, false, Image.FORMAT_L8)
	ao.fill(Color.WHITE)
	minimap_image = Image.create(size, size, false, Image.FORMAT_RGBA8)
	minimap_image.fill(Color(0.07, 0.16, 0.22))
	minimap_image.fill_rect(_to_pixels(layout.bounds, scale), Color(0.36, 0.37, 0.39))
	minimap_image.fill_rect(_to_pixels(layout.city_rect, scale), Color(0.13, 0.14, 0.16))
	for slab in layout.slabs:
		var col := Color(0.36, 0.37, 0.39)
		match slab.surface:
			"park": col = Color(0.20, 0.38, 0.20)
			"lot": col = Color(0.22, 0.23, 0.25)
			"plaza": col = Color(0.46, 0.44, 0.40)
		minimap_image.fill_rect(_to_pixels(slab.rect, scale), col)
	for bd in layout.buildings:
		var r: Rect2 = bd.rect
		ao.fill_rect(_to_pixels(r, scale), Color(0.3, 0.3, 0.3))
		minimap_image.fill_rect(_to_pixels(r, scale), Color(0.60, 0.63, 0.68))
	for bx in layout.boxes:
		var s: Vector3 = bx.size
		if bx.solid and s.x > 2.0 and s.z > 2.0 and bx.pos.y < 3.0:
			var r := Rect2(bx.pos.x - s.x * 0.5, bx.pos.z - s.z * 0.5, s.x, s.z)
			ao.fill_rect(_to_pixels(r, scale), Color(0.45, 0.45, 0.45))
			minimap_image.fill_rect(_to_pixels(r, scale), Color(0.52, 0.42, 0.34))
	ao.generate_mipmaps()
	ao_texture = ImageTexture.create_from_image(ao)


func _to_pixels(r: Rect2, scale: float) -> Rect2i:
	var o := layout.bounds.position
	var p := ((r.position - o) * scale).round()
	var e := ((r.end - o) * scale).round()
	return Rect2i(int(p.x), int(p.y), maxi(1, int(e.x - p.x)), maxi(1, int(e.y - p.y)))


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

func _shader_material(shader_path: String, params: Dictionary) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = load(shader_path)
	for key in params:
		m.set_shader_parameter(key, params[key])
	return m


func _tex(name: String) -> Texture2D:
	return load("res://assets/textures/%s" % name)


func _make_materials() -> void:
	var noise := _tex("noise_rgb.png")
	var b := layout.bounds
	var map_rect := Vector4(b.position.x, b.position.y, b.size.x, b.size.y)
	materials["building"] = _shader_material("res://shaders/building.gdshader", {"noise_tex": noise})
	var rx := PackedVector2Array()
	var rz := PackedVector2Array()
	for r in layout.roads_x:
		rx.append(Vector2(r.x, r.y * 0.5))
	for r in layout.roads_z:
		rz.append(Vector2(r.x, r.y * 0.5))
	var count_x := rx.size()
	var count_z := rz.size()
	rx.resize(10)
	rz.resize(10)
	materials["road"] = _shader_material("res://shaders/road.gdshader", {
		"albedo_tex": _tex("asphalt_color.jpg"), "normal_tex": _tex("asphalt_normal.jpg"),
		"rough_tex": _tex("asphalt_rough.jpg"), "noise_tex": noise, "ao_tex": ao_texture,
		"map_rect": map_rect, "count_x": count_x, "roads_x": rx, "count_z": count_z, "roads_z": rz,
	})
	materials["pavement"] = _shader_material("res://shaders/surface.gdshader", {
		"albedo_tex": _tex("concrete_color.jpg"), "normal_tex": _tex("concrete_normal.jpg"),
		"rough_tex": _tex("concrete_rough.jpg"), "noise_tex": noise, "ao_tex": ao_texture,
		"map_rect": map_rect, "tile": Vector2(4.0, 2.0), "tint": Color(0.60, 0.59, 0.57), "joint_size": 1.5,
	})
	materials["plaza"] = _shader_material("res://shaders/surface.gdshader", {
		"albedo_tex": _tex("cobble_color.jpg"), "normal_tex": _tex("cobble_normal.jpg"),
		"rough_tex": _tex("cobble_rough.jpg"), "noise_tex": noise, "ao_tex": ao_texture,
		"map_rect": map_rect, "tile": Vector2(3.0, 3.0), "tint": Color(0.95, 0.93, 0.9),
	})
	materials["lot"] = _shader_material("res://shaders/surface.gdshader", {
		"albedo_tex": _tex("asphalt_color.jpg"), "normal_tex": _tex("asphalt_normal.jpg"),
		"rough_tex": _tex("asphalt_rough.jpg"), "noise_tex": noise, "ao_tex": ao_texture,
		"map_rect": map_rect, "tile": Vector2(5.0, 5.0), "tint": Color(0.5, 0.5, 0.52), "bay_lines": 1.0,
	})
	materials["park"] = _shader_material("res://shaders/park.gdshader", {
		"grass_albedo": _tex("grass_color.jpg"), "grass_normal": _tex("grass_normal.jpg"),
		"path_albedo": _tex("cobble_color.jpg"), "path_normal": _tex("cobble_normal.jpg"),
		"path_rough": _tex("cobble_rough.jpg"), "noise_tex": noise,
	})
	materials["prop"] = _shader_material("res://shaders/prop.gdshader", {})
	materials["water"] = _shader_material("res://shaders/water.gdshader", {"noise_tex": noise})


# ---------------------------------------------------------------------------
# Roads and sea
# ---------------------------------------------------------------------------

func _build_roads() -> void:
	var mb := MeshBuilder.new()
	var c := layout.city_rect
	# North-south roads run the whole length; east-west roads fill the gaps between them.
	for r in layout.roads_x:
		_flat_quad(mb, Rect2(r.x - r.y * 0.5, c.position.y, r.y, c.size.y), 0.0)
	for r in layout.roads_z:
		for i in layout.block_x0.size():
			_flat_quad(mb, Rect2(layout.block_x0[i], r.x - r.y * 0.5, layout.block_x1[i] - layout.block_x0[i], r.y), 0.0)
	var mi := MeshInstance3D.new()
	mi.name = "Roads"
	mi.mesh = mb.build(materials.road)
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	# One thick floor under the whole island.
	var body := StaticBody3D.new()
	body.name = "Ground"
	body.collision_layer = WORLD_LAYER
	body.collision_mask = 0
	add_child(body)
	var b := layout.bounds
	var shape := BoxShape3D.new()
	shape.size = Vector3(b.size.x, 4.0, b.size.y)
	_add_shape(body, shape, Transform3D(Basis.IDENTITY, Vector3(b.get_center().x, -2.0, b.get_center().y)))
	# Invisible walls at the shore so nobody walks into the sea.
	for side in 4:
		var wall := BoxShape3D.new()
		var along_x := side < 2
		wall.size = Vector3(b.size.x + 4.0, 12.0, 1.0) if along_x else Vector3(1.0, 12.0, b.size.y + 4.0)
		var pos := Vector3(b.get_center().x, 6.0, b.get_center().y)
		match side:
			0: pos.z = b.position.y - 0.5
			1: pos.z = b.end.y + 0.5
			2: pos.x = b.position.x - 0.5
			3: pos.x = b.end.x + 0.5
		_add_shape(body, wall, Transform3D(Basis.IDENTITY, pos))


func _flat_quad(mb: MeshBuilder, r: Rect2, y: float, color := Color.WHITE, uv_origin := Vector2.INF) -> void:
	var o := uv_origin if uv_origin != Vector2.INF else Vector2.ZERO
	var p0 := Vector3(r.position.x, y, r.position.y)
	var p1 := Vector3(r.end.x, y, r.position.y)
	var p2 := Vector3(r.end.x, y, r.end.y)
	var p3 := Vector3(r.position.x, y, r.end.y)
	mb.quad(p0, p1, p2, p3, Vector3.UP,
		Vector2(p0.x, p0.z) - o, Vector2(p1.x, p1.z) - o, Vector2(p2.x, p2.z) - o, Vector2(p3.x, p3.z) - o, color)


func _build_water() -> void:
	var plane := PlaneMesh.new()
	plane.size = Vector2(12000.0, 12000.0)
	var mi := MeshInstance3D.new()
	mi.name = "Sea"
	mi.mesh = plane
	mi.material_override = materials.water
	mi.position = Vector3(0.0, -2.4, 0.0)
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------

func _build_chunks() -> void:
	# Sort everything by the block it belongs to (-1 = the promenade).
	var buckets := {}
	for id in range(-1, layout.blocks.size()):
		buckets[id] = {"buildings": [], "boxes": [], "slabs": []}
	for b in layout.buildings:
		buckets[b.block].buildings.append(b)
	for b in layout.boxes:
		buckets[b.block].boxes.append(b)
	for s in layout.slabs:
		buckets[s.block].slabs.append(s)
	for id: int in buckets:
		_build_chunk(id, buckets[id])


func _build_chunk(id: int, bucket: Dictionary) -> void:
	var walls := MeshBuilder.new()
	walls.use_custom = true
	var pavement := MeshBuilder.new()
	var plaza := MeshBuilder.new()
	var lot := MeshBuilder.new()
	var park := MeshBuilder.new()
	var misc := MeshBuilder.new()
	misc.paint_mode = true

	var body := StaticBody3D.new()
	body.name = "Block%dBody" % id
	body.collision_layer = WORLD_LAYER
	body.collision_mask = 0

	var top := CityLayout.CURB_H
	for slab: Dictionary in bucket.slabs:
		var r: Rect2 = slab.rect
		var bottom := -6.0 if id == -1 else -0.2
		_slab_sides(pavement, r, bottom, top)
		match slab.surface:
			"pavement":
				_flat_quad(pavement, r, top)
			"plaza":
				_flat_quad(plaza, r, top)
			"lot":
				var inner := r.grow(-CityLayout.SIDEWALK)
				_ring(pavement, r, inner, top)
				_flat_quad(lot, inner, top, Color.WHITE, inner.position + Vector2(2.0, 1.0))
			"park":
				_park_ground(park, r, top)
		_add_shape(body, _slab_shape(r, top), Transform3D(Basis.IDENTITY, Vector3(r.get_center().x, 0.0, r.get_center().y)))

	for b: Dictionary in bucket.buildings:
		_add_building(walls, b)
		var r: Rect2 = b.rect
		var h: float = b.y1 - b.y0
		_add_shape(body, _box_shape(Vector3(r.size.x, h, r.size.y)),
			Transform3D(Basis.IDENTITY, Vector3(r.get_center().x, b.y0 + h * 0.5, r.get_center().y)))

	for bx: Dictionary in bucket.boxes:
		var xf := Transform3D(Basis(Vector3.UP, bx.yaw), bx.pos)
		var c: Color = bx.color
		misc.xform = xf
		misc.box(Vector3.ZERO, bx.size, Color(c.r, c.g, c.b, 0.0), Vector2(bx.rough, bx.metal),
			Vector2(bx.emit, -1.0 if bx.ribs else 0.0))
		if bx.solid:
			_add_shape(body, _box_shape(bx.size), xf)
	misc.xform = Transform3D.IDENTITY

	var mesh := ArrayMesh.new()
	walls.commit(mesh, materials.building)
	pavement.commit(mesh, materials.pavement)
	plaza.commit(mesh, materials.plaza)
	lot.commit(mesh, materials.lot)
	park.commit(mesh, materials.park)
	misc.commit(mesh, materials.prop)
	if mesh.get_surface_count() > 0:
		var mi := MeshInstance3D.new()
		mi.name = "Block%d" % id
		mi.mesh = mesh
		add_child(mi)
	add_child(body)


## One building box: four walls and a roof. Wall UVs count window columns and floors.
func _add_building(mb: MeshBuilder, b: Dictionary) -> void:
	var r: Rect2 = b.rect
	var style: int = b.style
	var floor_h := CityLayout.FLOOR_H[style]
	var bay_w := CityLayout.BAY_W[style]
	var y0: float = b.y0
	var y1: float = b.y1
	var v0: float = b.floor0
	var v1 := v0 + (y1 - y0) / floor_h
	var tint: Color = b.color
	var color := Color(tint.r, tint.g, tint.b, b.seed)
	var custom := Vector4(float(style), 1.0 if b.shop else 0.0, b.lit, v1)
	var x0 := r.position.x
	var x1 := r.end.x
	var z0 := r.position.y
	var z1 := r.end.y
	# Each wall is listed left to right as seen from outside.
	var walls := [
		[Vector3(x0, y0, z1), Vector3(x1, y0, z1), Vector3.BACK],      # south
		[Vector3(x1, y0, z1), Vector3(x1, y0, z0), Vector3.RIGHT],     # east
		[Vector3(x1, y0, z0), Vector3(x0, y0, z0), Vector3.FORWARD],   # north
		[Vector3(x0, y0, z0), Vector3(x0, y0, z1), Vector3.LEFT],      # west
	]
	var face := 0
	for w: Array in walls:
		var a: Vector3 = w[0]
		var c: Vector3 = w[1]
		var bays := maxf(1.0, roundf(a.distance_to(c) / bay_w))
		var u0 := float(face * 64) + floorf(b.seed * 40.0) * 8.0
		var u1 := u0 + bays
		var up := Vector3(0.0, y1 - y0, 0.0)
		mb.quad(a, c, c + up, a + up, w[2], Vector2(u0, v0), Vector2(u1, v0), Vector2(u1, v1), Vector2(u0, v1),
			color, Vector2.ZERO, custom)
		face += 1
	mb.quad(Vector3(x0, y1, z0), Vector3(x1, y1, z0), Vector3(x1, y1, z1), Vector3(x0, y1, z1), Vector3.UP,
		Vector2(x0, z0), Vector2(x1, z0), Vector2(x1, z1), Vector2(x0, z1), color, Vector2.ZERO, custom)


func _slab_sides(mb: MeshBuilder, r: Rect2, y0: float, y1: float) -> void:
	var c := [Vector3(r.position.x, 0, r.position.y), Vector3(r.end.x, 0, r.position.y),
		Vector3(r.end.x, 0, r.end.y), Vector3(r.position.x, 0, r.end.y)]
	var normals := [Vector3.FORWARD, Vector3.RIGHT, Vector3.BACK, Vector3.LEFT]
	for i in 4:
		var a: Vector3 = c[i]
		var b: Vector3 = c[(i + 1) % 4]
		mb.quad(a + Vector3(0, y0, 0), b + Vector3(0, y0, 0), b + Vector3(0, y1, 0), a + Vector3(0, y1, 0),
			normals[i], Vector2.ZERO, Vector2.ZERO, Vector2.ZERO, Vector2.ZERO, Color.WHITE)


## The pavement strip between an outer and an inner rectangle (used around car parks).
func _ring(mb: MeshBuilder, outer: Rect2, inner: Rect2, y: float) -> void:
	_flat_quad(mb, Rect2(outer.position, Vector2(outer.size.x, inner.position.y - outer.position.y)), y)
	_flat_quad(mb, Rect2(Vector2(outer.position.x, inner.end.y), Vector2(outer.size.x, outer.end.y - inner.end.y)), y)
	_flat_quad(mb, Rect2(Vector2(outer.position.x, inner.position.y), Vector2(inner.position.x - outer.position.x, inner.size.y)), y)
	_flat_quad(mb, Rect2(Vector2(inner.end.x, inner.position.y), Vector2(outer.end.x - inner.end.x, inner.size.y)), y)


## Park ground: a grid of 1 m squares. Each corner stores how much path it is (COLOR.r).
func _park_ground(mb: MeshBuilder, r: Rect2, y: float) -> void:
	var park := {}
	for p: Dictionary in layout.parks:
		if (p.rect as Rect2).is_equal_approx(r):
			park = p
	var nx := int(ceil(r.size.x))
	var nz := int(ceil(r.size.y))
	var first := mb.verts.size()
	for iz in nz + 1:
		for ix in nx + 1:
			var p := Vector2(r.position.x + r.size.x * ix / float(nx), r.position.y + r.size.y * iz / float(nz))
			var path := CityLayout.park_path(park, p) if not park.is_empty() else 0.0
			mb.vertex(Vector3(p.x, y, p.y), Vector3.UP, p, Color(path, 0.0, 0.0, 1.0))
	for iz in nz:
		for ix in nx:
			var a := first + iz * (nx + 1) + ix
			mb.tri(a, a + 1, a + nx + 2)
			mb.tri(a, a + nx + 2, a + nx + 1)


# ---------------------------------------------------------------------------
# Collision helpers
# ---------------------------------------------------------------------------

func _add_shape(body: CollisionObject3D, shape: Shape3D, xform: Transform3D) -> void:
	var owner_id := body.create_shape_owner(body)
	body.shape_owner_set_transform(owner_id, xform)
	body.shape_owner_add_shape(owner_id, shape)


func _box_shape(size: Vector3) -> BoxShape3D:
	var key := "box%s" % size.snappedf(0.01)
	if not _shape_cache.has(key):
		var s := BoxShape3D.new()
		s.size = size
		_shape_cache[key] = s
	return _shape_cache[key]


## Pavement collision with sloped edges, so feet slide up the kerb instead of stopping at it.
func _slab_shape(r: Rect2, top: float) -> ConvexPolygonShape3D:
	var h := r.size * 0.5
	var bevel := top
	var pts := PackedVector3Array()
	for sx: float in [-1.0, 1.0]:
		for sz: float in [-1.0, 1.0]:
			pts.append(Vector3(sx * h.x, -1.0, sz * h.y))
			pts.append(Vector3(sx * h.x, 0.0, sz * h.y))
			pts.append(Vector3(sx * (h.x - bevel), top, sz * (h.y - bevel)))
	var shape := ConvexPolygonShape3D.new()
	shape.points = pts
	return shape


# ---------------------------------------------------------------------------
# Props
# ---------------------------------------------------------------------------

func _sector_of(pos: Vector3) -> int:
	var b := layout.bounds
	var sx := clampi(int((pos.x - b.position.x) / b.size.x * SECTORS), 0, SECTORS - 1)
	var sz := clampi(int((pos.z - b.position.y) / b.size.y * SECTORS), 0, SECTORS - 1)
	return sz * SECTORS + sx


func _build_props() -> void:
	var bodies := {}
	for name: String in layout.props:
		if name.begins_with("tree_"):
			continue                      # trees have their own builder below
		var mesh := PropLibrary.build(name, materials.prop)
		var shapes := PropLibrary.colliders(name)
		var by_sector := {}
		for item: Dictionary in layout.props[name]:
			var sector := _sector_of(item.pos)
			if not by_sector.has(sector):
				by_sector[sector] = []
			by_sector[sector].append(item)
		for sector: int in by_sector:
			var items: Array = by_sector[sector]
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.use_colors = true
			mm.mesh = mesh
			mm.instance_count = items.size()
			if not bodies.has(sector):
				var body := StaticBody3D.new()
				body.name = "Props%dBody" % sector
				body.collision_layer = WORLD_LAYER
				body.collision_mask = 0
				add_child(body)
				bodies[sector] = body
			for i in items.size():
				var item: Dictionary = items[i]
				var basis := Basis(Vector3.UP, item.yaw)
				var xf := Transform3D(basis.scaled(Vector3.ONE * float(item.scale)), item.pos)
				mm.set_instance_transform(i, xf)
				mm.set_instance_color(i, item.tint)
				for s: Dictionary in shapes:
					_add_shape(bodies[sector], _prop_shape(name, s), Transform3D(basis, item.pos + basis * (s.offset as Vector3)))
			var mmi := MultiMeshInstance3D.new()
			mmi.name = "%s_%d" % [name, sector]
			mmi.multimesh = mm
			if PropLibrary.NO_SHADOW.has(name):
				mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			add_child(mmi)
			_prop_nodes.append(mmi)
			_prop_names.append(name)


# ---------------------------------------------------------------------------
# Trees
# ---------------------------------------------------------------------------

## Every tree is added twice: as a full model (drawn only near the player) and
## as a flat picture (drawn only far away). The shaders decide per tree which
## of the two is visible, using the distance to the player's camera.
func _build_trees() -> void:
	var bodies := {}
	for name: String in layout.props:
		if not name.begins_with("tree_"):
			continue
		var kind := TreeLibrary.kind_of(name)
		var model := TreeLibrary.model(kind)
		var far_model := TreeLibrary.far_mesh(model)
		var near_material := TreeLibrary.near_material(kind)
		var far_material := TreeLibrary.far_material(kind, model)
		var cells := {}
		var sectors := {}
		for item: Dictionary in layout.props[name]:
			var cell := Vector2i(floori(item.pos.x / TREE_CELL), floori(item.pos.z / TREE_CELL))
			if not cells.has(cell):
				cells[cell] = []
			cells[cell].append(item)
			var sector := _sector_of(item.pos)
			if not sectors.has(sector):
				sectors[sector] = []
			sectors[sector].append(item)
			# The trunk blocks movement.
			if not bodies.has(sector):
				var body := StaticBody3D.new()
				body.name = "Trees%dBody" % sector
				body.collision_layer = WORLD_LAYER
				body.collision_mask = 0
				add_child(body)
				bodies[sector] = body
			var trunk := snappedf(float(TreeLibrary.TRUNK_RADIUS[kind]) * float(item.scale), 0.05)
			_add_shape(bodies[sector], _trunk_shape(trunk), Transform3D(Basis.IDENTITY, item.pos + Vector3(0.0, 1.5, 0.0)))
		for cell: Vector2i in cells:
			var group := _tree_group(model, near_material, cells[cell], "%s_near_%d_%d" % [name, cell.x, cell.y])
			_tree_groups.append(group)
		for sector: int in sectors:
			var group := _tree_group(far_model, far_material, sectors[sector], "%s_far_%d" % [name, sector])
			group.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF


func _tree_group(mesh: Mesh, material: Material, items: Array, node_name: String) -> MultiMeshInstance3D:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = mesh
	mm.instance_count = items.size()
	for i in items.size():
		var item: Dictionary = items[i]
		mm.set_instance_transform(i, Transform3D(Basis(Vector3.UP, item.yaw).scaled(Vector3.ONE * float(item.scale)), item.pos))
		mm.set_instance_color(i, item.tint)
	var group := MultiMeshInstance3D.new()
	group.name = node_name
	group.multimesh = mm
	group.material_override = material
	add_child(group)
	return group


func _trunk_shape(radius: float) -> CylinderShape3D:
	var key := "trunk%.2f" % radius
	if not _shape_cache.has(key):
		var cyl := CylinderShape3D.new()
		cyl.radius = radius
		cyl.height = 3.0
		_shape_cache[key] = cyl
	return _shape_cache[key]


func _prop_shape(name: String, s: Dictionary) -> Shape3D:
	var key := "%s%s" % [name, s]
	if not _shape_cache.has(key):
		if s.shape == "box":
			var box := BoxShape3D.new()
			box.size = s.size
			_shape_cache[key] = box
		else:
			var cyl := CylinderShape3D.new()
			cyl.radius = s.radius
			cyl.height = s.height
			_shape_cache[key] = cyl
	return _shape_cache[key]


# ---------------------------------------------------------------------------
# Graphics level
# ---------------------------------------------------------------------------

## Applies the parts of a graphics preset that belong to the city.
func apply_quality(preset: Dictionary) -> void:
	(materials.building as ShaderMaterial).set_shader_parameter("rooms", preset.rooms)
	# Full tree models are shown up to `tree_lod` metres, flat pictures beyond.
	RenderingServer.global_shader_parameter_set("tree_lod", float(preset.tree_lod))
	for group in _tree_groups:
		group.visibility_range_end = float(preset.tree_lod) + TREE_CELL + 14.0
	var sector_radius := layout.bounds.size.x / SECTORS * 0.75
	for i in _prop_nodes.size():
		var name := _prop_names[i]
		if PropLibrary.VIEW_DISTANCE.has(name):
			var d: float = PropLibrary.VIEW_DISTANCE[name] * float(preset.props)
			_prop_nodes[i].visibility_range_end = d + sector_radius
			_prop_nodes[i].visibility_range_end_margin = 10.0


func set_night(amount: float) -> void:
	for key: String in ["building", "prop"]:
		(materials[key] as ShaderMaterial).set_shader_parameter("night", amount)
