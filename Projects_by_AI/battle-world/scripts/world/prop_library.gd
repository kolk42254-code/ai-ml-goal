extends RefCounted
## Builds the small city objects (lamps, trees, cars ...) from code, so the game
## needs no model files for them. Every prop stands on y = 0 and its front is -Z.

const MeshBuilder := preload("res://scripts/util/mesh_builder.gd")

const DARK_METAL := Color(0.10, 0.11, 0.12, 0.0)
const MAT_METAL := Vector2(0.45, 0.7)       # (roughness, metallic)
const MAT_PAINT := Vector2(0.32, 0.45)
const MAT_RUBBER := Vector2(0.9, 0.0)
const MAT_GLASS := Vector2(0.08, 0.6)
const MAT_STONE := Vector2(0.85, 0.0)
const MAT_WOOD := Vector2(0.75, 0.0)
const MAT_LEAF := Vector2(0.9, 0.0)

## How far away each prop is still drawn (metres). Props not listed are always drawn.
const VIEW_DISTANCE := {
	"hydrant": 90.0, "bin": 90.0, "bench": 110.0, "bollard": 120.0, "bush": 140.0,
	"planter": 150.0, "park_lamp": 220.0, "traffic_light": 260.0, "lamp": 320.0,
	"car_sedan": 330.0, "car_suv": 330.0, "car_van": 330.0,
}
## Props that are too small or thin for their shadow to be worth drawing.
const NO_SHADOW := ["hydrant", "bin", "bollard", "pond", "bush", "lamp", "park_lamp",
	"traffic_light", "bench"]


## Shapes that block movement. Each entry: {shape: "box" | "cylinder", size or radius/height, offset}.
static func colliders(name: String) -> Array:
	match name:
		"lamp", "traffic_light":
			return [{"shape": "cylinder", "radius": 0.17, "height": 3.0, "offset": Vector3(0, 1.5, 0)}]
		"park_lamp":
			return [{"shape": "cylinder", "radius": 0.13, "height": 3.0, "offset": Vector3(0, 1.5, 0)}]
		"tree_a", "tree_b":
			return [{"shape": "cylinder", "radius": 0.28, "height": 3.2, "offset": Vector3(0, 1.6, 0)}]
		"hydrant":
			return [{"shape": "cylinder", "radius": 0.2, "height": 0.7, "offset": Vector3(0, 0.35, 0)}]
		"bin":
			return [{"shape": "cylinder", "radius": 0.3, "height": 0.95, "offset": Vector3(0, 0.47, 0)}]
		"bollard":
			return [{"shape": "cylinder", "radius": 0.24, "height": 0.7, "offset": Vector3(0, 0.35, 0)}]
		"bench":
			return [{"shape": "box", "size": Vector3(1.9, 0.9, 0.62), "offset": Vector3(0, 0.45, 0)}]
		"planter":
			return [{"shape": "box", "size": Vector3(2.2, 0.9, 2.2), "offset": Vector3(0, 0.45, 0)}]
		"car_sedan":
			return [{"shape": "box", "size": Vector3(1.86, 1.35, 4.5), "offset": Vector3(0, 0.72, 0)}]
		"car_suv":
			return [{"shape": "box", "size": Vector3(1.94, 1.68, 4.7), "offset": Vector3(0, 0.88, 0)}]
		"car_van":
			return [{"shape": "box", "size": Vector3(2.0, 2.05, 5.2), "offset": Vector3(0, 1.05, 0)}]
		"silo":
			return [{"shape": "cylinder", "radius": 2.3, "height": 11.0, "offset": Vector3(0, 5.5, 0)}]
		"fountain":
			return [{"shape": "cylinder", "radius": 4.2, "height": 0.6, "offset": Vector3(0, 0.3, 0)},
				{"shape": "cylinder", "radius": 0.6, "height": 2.2, "offset": Vector3(0, 1.1, 0)}]
		"pavilion":
			var out := []
			for i in 6:
				var a := TAU * i / 6.0
				out.append({"shape": "cylinder", "radius": 0.22, "height": 3.0,
					"offset": Vector3(cos(a) * 3.2, 1.5, sin(a) * 3.2)})
			return out
	return []


static func build(name: String, material: Material) -> ArrayMesh:
	var mb := MeshBuilder.new()
	mb.paint_mode = true
	match name:
		"lamp": _lamp(mb)
		"park_lamp": _park_lamp(mb)
		"traffic_light": _traffic_light(mb)
		"tree_a": _tree_round(mb)
		"tree_b": _tree_tall(mb)
		"bush": _bush(mb)
		"hydrant": _hydrant(mb)
		"bin": _bin(mb)
		"bench": _bench(mb)
		"bollard": _bollard(mb)
		"planter": _planter(mb)
		"car_sedan": _car(mb, 0)
		"car_suv": _car(mb, 1)
		"car_van": _van(mb)
		"silo": _silo(mb)
		"fountain": _fountain(mb)
		"pond": _pond(mb)
		"pavilion": _pavilion(mb)
		_:
			mb.box(Vector3(0, 0.5, 0), Vector3.ONE, Color(1, 0, 1, 0))
	return mb.build(material)


static func _lamp(mb: MeshBuilder) -> void:
	mb.cylinder(Vector3.ZERO, 0.17, 0.13, 0.6, 8, DARK_METAL, MAT_METAL)
	mb.cylinder(Vector3(0, 0.6, 0), 0.085, 0.06, 7.2, 8, DARK_METAL, MAT_METAL)
	mb.box(Vector3(0, 7.75, -0.95), Vector3(0.09, 0.09, 2.0), DARK_METAL, MAT_METAL)
	mb.box(Vector3(0, 7.73, -1.95), Vector3(0.34, 0.12, 0.78), DARK_METAL, MAT_METAL)
	# The glowing panel under the head (UV2.x = 2: shines at night).
	mb.box(Vector3(0, 7.655, -1.95), Vector3(0.26, 0.03, 0.64), Color(1.0, 0.92, 0.75, 0.0),
		Vector2(0.4, 0.0), Vector2(2.0, 0.0))


static func _park_lamp(mb: MeshBuilder) -> void:
	mb.cylinder(Vector3.ZERO, 0.12, 0.09, 0.4, 8, DARK_METAL, MAT_METAL)
	mb.cylinder(Vector3(0, 0.4, 0), 0.055, 0.045, 3.1, 8, DARK_METAL, MAT_METAL)
	mb.cylinder(Vector3(0, 3.5, 0), 0.07, 0.2, 0.12, 8, DARK_METAL, MAT_METAL)
	mb.blob(Vector3(0, 3.82, 0), Vector3(0.2, 0.22, 0.2), 5, 8, Color(1.0, 0.93, 0.78, 0.0),
		Vector2(0.3, 0.0), Vector2(2.0, 0.0), Vector2(2.0, 0.0))
	mb.cylinder(Vector3(0, 4.02, 0), 0.22, 0.05, 0.1, 8, DARK_METAL, MAT_METAL)


static func _traffic_light(mb: MeshBuilder) -> void:
	mb.cylinder(Vector3.ZERO, 0.16, 0.12, 0.5, 8, DARK_METAL, MAT_METAL)
	mb.cylinder(Vector3(0, 0.5, 0), 0.09, 0.075, 5.4, 8, DARK_METAL, MAT_METAL)
	mb.box(Vector3(0, 5.75, -2.1), Vector3(0.1, 0.1, 4.2), DARK_METAL, MAT_METAL)
	for head in [Vector3(0, 5.2, -3.9), Vector3(0, 5.2, -1.6)]:
		var h: Vector3 = head
		mb.box(h, Vector3(0.3, 0.95, 0.34), Color(0.06, 0.06, 0.06, 0.0), Vector2(0.6, 0.2))
		var lens: Array[Color] = [Color(1.0, 0.08, 0.05, 0.0), Color(0.25, 0.18, 0.02, 0.0), Color(0.02, 0.2, 0.06, 0.0)]
		for i in 3:
			# Red is lit (glow 3.6 = always on), amber and green are dark.
			var glow := Vector2(3.6, 0.0) if i == 0 else Vector2.ZERO
			var m := Vector2(0.3, 0.0)
			for side: float in [-1.0, 1.0]:
				var c := h + Vector3(side * 0.153, 0.3 - i * 0.3, 0.0)
				mb.quad(c + Vector3(0, -0.1, -0.1), c + Vector3(0, 0.1, -0.1), c + Vector3(0, 0.1, 0.1),
					c + Vector3(0, -0.1, 0.1), Vector3(side, 0, 0), m, m, m, m, lens[i], glow)


static func _tree_round(mb: MeshBuilder) -> void:
	var bark := Color(0.19, 0.13, 0.09, 0.0)
	mb.cylinder(Vector3.ZERO, 0.22, 0.13, 3.3, 6, bark, Vector2(0.95, 0.0), Vector2.ZERO, Vector2(0.0, 0.15), false)
	var leaf := Color(0.17, 0.31, 0.10, 1.0)
	var parts := [
		[Vector3(0.0, 4.5, 0.0), Vector3(2.1, 1.7, 2.1), 0.0],
		[Vector3(1.1, 4.0, 0.6), Vector3(1.45, 1.15, 1.45), 1.7],
		[Vector3(-0.95, 4.2, -0.7), Vector3(1.5, 1.2, 1.5), 3.1],
		[Vector3(0.2, 5.6, -0.3), Vector3(1.3, 1.05, 1.3), 4.4],
	]
	for part in parts:
		mb.blob(part[0], part[1], 4, 7, leaf, MAT_LEAF, Vector2(0.0, 0.35), Vector2(0.0, 1.0), 0.1, 0.5, part[2])


static func _tree_tall(mb: MeshBuilder) -> void:
	var bark := Color(0.16, 0.12, 0.09, 0.0)
	mb.cylinder(Vector3.ZERO, 0.2, 0.1, 3.0, 7, bark, Vector2(0.95, 0.0), Vector2.ZERO, Vector2(0.0, 0.15), false)
	var leaf := Color(0.11, 0.25, 0.11, 1.0)
	mb.blob(Vector3(0.0, 5.0, 0.0), Vector3(1.25, 3.3, 1.25), 6, 7, leaf, MAT_LEAF, Vector2(0.0, 0.3), Vector2(0.0, 1.0), 0.08, 0.5, 0.6)
	mb.blob(Vector3(0.25, 7.6, 0.1), Vector3(0.85, 2.0, 0.85), 5, 7, leaf, MAT_LEAF, Vector2(0.0, 0.6), Vector2(0.0, 1.2), 0.08, 0.4, 2.2)


static func _bush(mb: MeshBuilder) -> void:
	var leaf := Color(0.15, 0.29, 0.10, 1.0)
	mb.blob(Vector3(0.0, 0.5, 0.0), Vector3(0.85, 0.62, 0.85), 4, 7, leaf, MAT_LEAF, Vector2.ZERO, Vector2(0.0, 0.4), 0.12, 0.5, 0.3)
	mb.blob(Vector3(0.6, 0.38, 0.3), Vector3(0.55, 0.45, 0.55), 4, 6, leaf, MAT_LEAF, Vector2.ZERO, Vector2(0.0, 0.3), 0.12, 0.5, 1.9)


static func _hydrant(mb: MeshBuilder) -> void:
	var red := Color(0.62, 0.07, 0.05, 0.0)
	mb.cylinder(Vector3.ZERO, 0.16, 0.16, 0.08, 8, red, MAT_PAINT)
	mb.cylinder(Vector3(0, 0.08, 0), 0.11, 0.1, 0.5, 8, red, MAT_PAINT)
	mb.blob(Vector3(0, 0.6, 0), Vector3(0.12, 0.1, 0.12), 4, 8, red, MAT_PAINT)
	mb.box(Vector3(0, 0.42, 0), Vector3(0.36, 0.1, 0.1), red, MAT_PAINT)


static func _bin(mb: MeshBuilder) -> void:
	var green := Color(0.07, 0.16, 0.11, 0.0)
	mb.cylinder(Vector3.ZERO, 0.25, 0.29, 0.85, 10, green, Vector2(0.5, 0.4))
	mb.cylinder(Vector3(0, 0.85, 0), 0.31, 0.27, 0.1, 10, Color(0.05, 0.05, 0.05, 0.0), Vector2(0.5, 0.4))


static func _bench(mb: MeshBuilder) -> void:
	var wood := Color(0.36, 0.22, 0.12, 0.0)
	mb.box(Vector3(0, 0.45, 0.0), Vector3(1.8, 0.06, 0.46), wood, MAT_WOOD)
	mb.xform = Transform3D(Basis(Vector3.RIGHT, deg_to_rad(-12.0)), Vector3(0, 0.74, 0.25))
	mb.box(Vector3.ZERO, Vector3(1.8, 0.42, 0.05), wood, MAT_WOOD)
	mb.xform = Transform3D.IDENTITY
	for x: float in [-0.78, 0.78]:
		mb.box(Vector3(x, 0.22, 0.0), Vector3(0.06, 0.44, 0.44), DARK_METAL, MAT_METAL)
		mb.box(Vector3(x, 0.66, 0.25), Vector3(0.06, 0.5, 0.05), DARK_METAL, MAT_METAL)


static func _bollard(mb: MeshBuilder) -> void:
	var iron := Color(0.07, 0.07, 0.08, 0.0)
	mb.cylinder(Vector3.ZERO, 0.2, 0.16, 0.5, 10, iron, MAT_METAL)
	mb.cylinder(Vector3(0, 0.5, 0), 0.26, 0.22, 0.16, 10, iron, MAT_METAL)


static func _planter(mb: MeshBuilder) -> void:
	var stone := Color(0.55, 0.54, 0.52, 0.0)
	mb.box(Vector3(0, 0.3, 0), Vector3(2.2, 0.6, 2.2), stone, MAT_STONE, Vector2.ZERO, true)
	mb.box(Vector3(0, 0.6, 0), Vector3(1.9, 0.04, 1.9), Color(0.12, 0.09, 0.06, 0.0), Vector2(0.95, 0.0), Vector2.ZERO, true)
	var leaf := Color(0.16, 0.30, 0.11, 1.0)
	mb.blob(Vector3(-0.35, 0.95, 0.2), Vector3(0.7, 0.5, 0.7), 4, 7, leaf, MAT_LEAF, Vector2.ZERO, Vector2(0.0, 0.3), 0.1, 0.5, 0.4)
	mb.blob(Vector3(0.45, 0.9, -0.3), Vector3(0.6, 0.45, 0.6), 4, 7, leaf, MAT_LEAF, Vector2.ZERO, Vector2(0.0, 0.3), 0.1, 0.5, 2.6)


## Wheel: a short cylinder lying on its side. `x_in` is the inner face, `x_out` the outer face.
## Kept simple (8 sides, no inner face): hundreds of cars are on screen at once.
static func _wheel(mb: MeshBuilder, x_in: float, x_out: float, y: float, z: float, radius: float) -> void:
	var outward := 1.0 if x_out > x_in else -1.0
	var width := absf(x_out - x_in)
	# The cylinder is built along +Y, then tipped over so +Y points out of the car's side.
	mb.xform = Transform3D(Basis(Vector3(0, 0, 1), -PI * 0.5 * outward), Vector3(x_in, y, z))
	mb.cylinder(Vector3.ZERO, radius, radius, width, 8, Color(0.03, 0.03, 0.035, 0.0), MAT_RUBBER)
	mb.disc(Vector3(0, width + 0.004, 0), radius * 0.58, 8, Color(0.55, 0.56, 0.58, 0.0), Vector2(0.3, 0.8))
	mb.xform = Transform3D.IDENTITY


## kind 0 = saloon car, 1 = taller SUV.
static func _car(mb: MeshBuilder, kind: int) -> void:
	var paint := Color(1.0, 1.0, 1.0, 1.0)            # white with tint mask: takes the car colour
	var glass := Color(0.035, 0.045, 0.055, 0.0)
	var trim := Color(0.035, 0.035, 0.04, 0.0)
	var suv := kind == 1
	var half_w := 0.93 if suv else 0.9
	var clear := 0.33 if suv else 0.27
	var belt := 1.02 if suv else 0.88                  # height where the windows start
	var roof := 1.68 if suv else 1.40
	var front := -2.3 if suv else -2.25
	var back := 2.35 if suv else 2.25
	var wheel_r := 0.37 if suv else 0.33
	# Lower body: outline in (z, y), pushed across the car's width.
	var body := PackedVector2Array([
		Vector2(front, clear + 0.14), Vector2(front + 0.04, belt - 0.2), Vector2(front + 0.28, belt - 0.1),
		Vector2(-0.95, belt), Vector2(back - 0.5, belt + 0.03), Vector2(back - 0.04, belt - 0.05),
		Vector2(back, clear + 0.2), Vector2(back - 0.1, clear), Vector2(front + 0.12, clear),
	])
	mb.extrude_x(body, -half_w, half_w, paint, MAT_PAINT)
	# Cabin: windscreen, roof line and rear window. Its side caps are the side windows.
	var cabin_back := back - (0.25 if suv else 0.75)
	var cabin := PackedVector2Array([
		Vector2(-0.92, belt - 0.02), Vector2(-0.32 if not suv else -0.5, roof - 0.02),
		Vector2(cabin_back - (0.3 if suv else 0.62), roof), Vector2(cabin_back, belt + 0.01),
	])
	var cab_w := half_w - 0.12
	mb.extrude_x(cabin, -cab_w, cab_w, glass, MAT_GLASS)
	# Roof panel and window pillars in body colour.
	var roof_front := -0.32 if not suv else -0.5
	var roof_back := cabin_back - (0.3 if suv else 0.62)
	mb.box(Vector3(0, roof + 0.012, (roof_front + roof_back) * 0.5), Vector3(cab_w * 2.0 + 0.03, 0.035, roof_back - roof_front + 0.06), paint, MAT_PAINT)
	for z: float in [0.28, roof_back - 0.02]:
		mb.box(Vector3(0, (belt + roof) * 0.5, z), Vector3(cab_w * 2.0 + 0.03, roof - belt, 0.09), paint, MAT_PAINT)
	# Bumpers, lights and number plates.
	mb.box(Vector3(0, clear + 0.16, front - 0.01), Vector3(half_w * 1.9, 0.2, 0.06), trim, MAT_RUBBER)
	mb.box(Vector3(0, clear + 0.18, back + 0.01), Vector3(half_w * 1.9, 0.2, 0.06), trim, MAT_RUBBER)
	for sx: float in [-1.0, 1.0]:
		mb.box(Vector3(sx * (half_w - 0.28), belt - 0.23, front + 0.02), Vector3(0.38, 0.13, 0.08), Color(0.92, 0.92, 0.86, 0.0), Vector2(0.15, 0.3))
		mb.box(Vector3(sx * (half_w - 0.26), belt - 0.16, back - 0.01), Vector3(0.36, 0.12, 0.08), Color(0.55, 0.03, 0.03, 0.0), Vector2(0.2, 0.2))
	# Wheels
	for sx: float in [-1.0, 1.0]:
		for z: float in [front + 0.85, back - 0.88]:
			_wheel(mb, sx * (half_w - 0.2), sx * (half_w + 0.02), wheel_r, z, wheel_r)


static func _van(mb: MeshBuilder) -> void:
	var paint := Color(1.0, 1.0, 1.0, 1.0)
	var glass := Color(0.035, 0.045, 0.055, 0.0)
	var trim := Color(0.035, 0.035, 0.04, 0.0)
	var half_w := 0.98
	var body := PackedVector2Array([
		Vector2(-2.6, 0.48), Vector2(-2.55, 0.98), Vector2(-2.05, 1.14), Vector2(-1.5, 1.98),
		Vector2(2.6, 2.02), Vector2(2.6, 0.36), Vector2(-2.5, 0.36),
	])
	mb.extrude_x(body, -half_w, half_w, paint, MAT_PAINT)
	# Windscreen: a dark panel lying on the sloped front.
	var slope := Vector2(-1.5, 1.98) - Vector2(-2.05, 1.14)
	var n := Vector3(0.0, -slope.x, slope.y).normalized()
	var n_up := Vector3(0.0, absf(n.y), -absf(n.z)).normalized()
	var a := Vector3(-0.85, 1.22, -2.0) + n_up * 0.012
	var b := Vector3(0.85, 1.22, -2.0) + n_up * 0.012
	var c := Vector3(0.85, 1.9, -1.555) + n_up * 0.012
	var d := Vector3(-0.85, 1.9, -1.555) + n_up * 0.012
	mb.quad(a, b, c, d, n_up, MAT_GLASS, MAT_GLASS, MAT_GLASS, MAT_GLASS, glass)
	# Front door windows.
	for sx: float in [-1.0, 1.0]:
		mb.box(Vector3(sx * (half_w + 0.004), 1.6, -0.95), Vector3(0.01, 0.5, 0.8), glass, MAT_GLASS)
	mb.box(Vector3(0, 0.5, -2.6), Vector3(1.9, 0.24, 0.06), trim, MAT_RUBBER)
	mb.box(Vector3(0, 0.5, 2.61), Vector3(1.9, 0.24, 0.06), trim, MAT_RUBBER)
	for sx: float in [-1.0, 1.0]:
		mb.box(Vector3(sx * 0.7, 0.86, -2.57), Vector3(0.36, 0.15, 0.06), Color(0.92, 0.92, 0.86, 0.0), Vector2(0.15, 0.3))
		mb.box(Vector3(sx * 0.82, 1.2, 2.61), Vector3(0.16, 0.5, 0.05), Color(0.55, 0.03, 0.03, 0.0), Vector2(0.2, 0.2))
		for z: float in [-1.65, 1.6]:
			_wheel(mb, sx * (half_w - 0.2), sx * (half_w + 0.02), 0.37, z, 0.37)


static func _silo(mb: MeshBuilder) -> void:
	var steel := Color(0.62, 0.64, 0.66, 0.0)
	mb.cylinder(Vector3.ZERO, 2.3, 2.3, 9.6, 16, steel, Vector2(0.4, 0.75), Vector2.ZERO, Vector2.ZERO, false)
	mb.cylinder(Vector3(0, 9.6, 0), 2.3, 0.35, 1.5, 16, steel, Vector2(0.4, 0.75))
	for y: float in [3.2, 6.4]:
		mb.cylinder(Vector3(0, y, 0), 2.34, 2.34, 0.12, 16, Color(0.4, 0.42, 0.44, 0.0), Vector2(0.5, 0.7), Vector2.ZERO, Vector2.ZERO, false)


static func _fountain(mb: MeshBuilder) -> void:
	var stone := Color(0.58, 0.57, 0.54, 0.0)
	var water := Color(0.05, 0.22, 0.30, 0.0)
	mb.cylinder(Vector3.ZERO, 4.3, 4.2, 0.55, 24, stone, MAT_STONE)
	mb.disc(Vector3(0, 0.56, 0), 3.85, 24, water, Vector2(0.04, 0.0))
	mb.cylinder(Vector3(0, 0.55, 0), 0.5, 0.38, 1.3, 12, stone, MAT_STONE, Vector2.ZERO, Vector2.ZERO, false)
	mb.cylinder(Vector3(0, 1.85, 0), 0.45, 1.6, 0.4, 16, stone, MAT_STONE)
	mb.disc(Vector3(0, 2.26, 0), 1.45, 16, water, Vector2(0.04, 0.0))
	mb.cylinder(Vector3(0, 2.25, 0), 0.16, 0.1, 0.55, 8, stone, MAT_STONE)


static func _pond(mb: MeshBuilder) -> void:
	# Radius 1: the builder scales it to the pond's real size.
	mb.cylinder(Vector3.ZERO, 1.08, 1.06, 0.004, 28, Color(0.42, 0.41, 0.38, 0.0), MAT_STONE)
	mb.disc(Vector3(0, 0.006, 0), 1.0, 28, Color(0.04, 0.16, 0.20, 0.0), Vector2(0.04, 0.0))


static func _pavilion(mb: MeshBuilder) -> void:
	var stone := Color(0.72, 0.70, 0.66, 0.0)
	mb.cylinder(Vector3.ZERO, 4.0, 3.9, 0.16, 20, stone, MAT_STONE)
	for i in 6:
		var a := TAU * i / 6.0
		mb.cylinder(Vector3(cos(a) * 3.2, 0.16, sin(a) * 3.2), 0.2, 0.17, 2.9, 8, stone, MAT_STONE, Vector2.ZERO, Vector2.ZERO, false)
	mb.cylinder(Vector3(0, 3.05, 0), 4.2, 4.2, 0.18, 20, stone, MAT_STONE, Vector2.ZERO, Vector2.ZERO, true, true)
	mb.cylinder(Vector3(0, 3.23, 0), 4.0, 0.25, 1.5, 20, Color(0.30, 0.13, 0.10, 0.0), Vector2(0.6, 0.1))
