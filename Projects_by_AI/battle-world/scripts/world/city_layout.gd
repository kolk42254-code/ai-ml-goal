extends RefCounted
## The city as plain data: roads, blocks, buildings, boxes and props.
##
## Nothing is drawn here. `city_builder.gd` turns this data into meshes and
## collision, the minimap draws from it, and the tests check it without a screen.
## The same seed always gives the same city.
##
## Directions: +X is east, +Z is south, +Y is up. All sizes are in metres.

enum Kind { DOWNTOWN, COMMERCIAL, RESIDENTIAL, INDUSTRIAL, HARBOR, PARK, PLAZA, PARKING }
enum Style { GLASS, OFFICE, BRICK, PLASTER, METAL, CONCRETE }

# --- Street grid ---------------------------------------------------------
# 7 x 7 blocks. Roads 0 and 7 on each axis form the ring road around the city.
const BLOCKS_X: Array[float] = [52.0, 60.0, 56.0, 64.0, 56.0, 60.0, 52.0]
const BLOCKS_Z: Array[float] = [54.0, 58.0, 60.0, 62.0, 60.0, 56.0, 50.0]
const STREET_W := 12.0
const AVENUE_W := 18.0
const AVENUES_X: Array[int] = [3, 5]
const AVENUES_Z: Array[int] = [2, 5]
const SIDEWALK := 3.5           # paved strip between the kerb and the buildings
const CURB_H := 0.12            # how high the pavement is above the road
const SHORE := 10.0             # promenade between the ring road and the sea wall

# One letter per block, one row per street row (north row first):
# R residential, C commercial, D downtown, K car park, P park, L landmark plaza,
# I industrial, H harbour.
const MAP: Array[String] = [
	"RRRCCCC",
	"RRCCDDC",
	"RKDDDDC",
	"RPPDLDC",
	"KDDDDCC",
	"IIKCCKI",
	"IHHHIII",
]
## Blocks joined into one big block (x, z, width, height in blocks).
const MERGES: Array[Rect2i] = [Rect2i(1, 3, 2, 1), Rect2i(1, 6, 3, 1)]

# --- Facade styles ---------------------------------------------------------
const FLOOR_H: Array[float] = [3.8, 3.6, 3.2, 3.0, 4.5, 3.4]     # metres per floor
const BAY_W: Array[float] = [2.4, 3.2, 3.0, 3.4, 4.0, 4.0]       # metres per window column

const GLASS_TINTS: Array[Color] = [
	Color(0.30, 0.46, 0.60), Color(0.26, 0.42, 0.45), Color(0.52, 0.46, 0.38),
	Color(0.22, 0.25, 0.30), Color(0.52, 0.62, 0.68), Color(0.20, 0.34, 0.50),
]
const OFFICE_TINTS: Array[Color] = [
	Color(0.72, 0.70, 0.66), Color(0.58, 0.58, 0.60), Color(0.80, 0.76, 0.68),
	Color(0.44, 0.45, 0.47), Color(0.66, 0.62, 0.56),
]
const BRICK_TINTS: Array[Color] = [
	Color(0.52, 0.25, 0.19), Color(0.60, 0.33, 0.24), Color(0.42, 0.23, 0.19),
	Color(0.68, 0.53, 0.39), Color(0.48, 0.30, 0.26),
]
const PLASTER_TINTS: Array[Color] = [
	Color(0.85, 0.80, 0.70), Color(0.80, 0.72, 0.62), Color(0.74, 0.79, 0.81),
	Color(0.87, 0.85, 0.81), Color(0.77, 0.61, 0.49), Color(0.70, 0.76, 0.66),
]
const METAL_TINTS: Array[Color] = [
	Color(0.55, 0.60, 0.65), Color(0.40, 0.48, 0.55), Color(0.60, 0.55, 0.48),
	Color(0.35, 0.42, 0.40), Color(0.62, 0.63, 0.62),
]
const CONTAINER_COLORS: Array[Color] = [
	Color(0.62, 0.16, 0.11), Color(0.11, 0.27, 0.50), Color(0.14, 0.38, 0.26),
	Color(0.80, 0.44, 0.09), Color(0.74, 0.74, 0.72), Color(0.18, 0.44, 0.50),
	Color(0.70, 0.60, 0.13), Color(0.36, 0.36, 0.38),
]
const CAR_COLORS: Array[Color] = [
	Color(0.90, 0.90, 0.90), Color(0.06, 0.06, 0.07), Color(0.55, 0.57, 0.60),
	Color(0.28, 0.29, 0.31), Color(0.55, 0.06, 0.06), Color(0.07, 0.17, 0.42),
	Color(0.10, 0.25, 0.17), Color(0.80, 0.62, 0.08), Color(0.42, 0.20, 0.10),
]

# --- Results ---------------------------------------------------------------
var seed_value := 0
## Roads running north-south: x = centre position on the X axis, y = width.
var roads_x: Array[Vector2] = []
## Roads running east-west: x = centre position on the Z axis, y = width.
var roads_z: Array[Vector2] = []
var block_x0: Array[float] = []
var block_x1: Array[float] = []
var block_z0: Array[float] = []
var block_z1: Array[float] = []
## Outer edge of the ring road (the city), and the whole island including the promenade.
var city_rect := Rect2()
var bounds := Rect2()

## {id, ix, iz, rect: Rect2 (x, z), kind: Kind, merged: bool}
var blocks: Array[Dictionary] = []
## Raised ground: {rect: Rect2, surface: "pavement" | "lot" | "park" | "plaza", block: int}
var slabs: Array[Dictionary] = []
## {rect, y0, y1, style, color, seed, shop, lit, floor0, block}
var buildings: Array[Dictionary] = []
## Plain coloured boxes: {pos (centre), size, yaw, color, rough, metal, emit, solid, block, ribs}
var boxes: Array[Dictionary] = []
## name -> Array of {pos, yaw, scale, tint, block}
var props: Dictionary = {}
## {rect, center, plaza_r, ring_inset, pond, pond_r, block}
var parks: Array[Dictionary] = []
## Safe places to put a fighter (street crossings).
var spawn_points: Array[Vector3] = []
var landmark_pos := Vector3.ZERO


func generate(p_seed: int = 7) -> void:
	seed_value = p_seed
	_build_grid()
	_build_blocks()
	for b: Dictionary in blocks:
		_fill_block(b)
	_parked_cars()
	_shore()
	for rx in roads_x:
		for rz in roads_z:
			spawn_points.append(Vector3(rx.x, 0.0, rz.x))


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------

func _build_grid() -> void:
	roads_x = _axis(BLOCKS_X, AVENUES_X, block_x0, block_x1)
	roads_z = _axis(BLOCKS_Z, AVENUES_Z, block_z0, block_z1)
	var x0 := roads_x[0].x - roads_x[0].y * 0.5
	var x1 := roads_x[-1].x + roads_x[-1].y * 0.5
	var z0 := roads_z[0].x - roads_z[0].y * 0.5
	var z1 := roads_z[-1].x + roads_z[-1].y * 0.5
	city_rect = Rect2(x0, z0, x1 - x0, z1 - z0)
	bounds = city_rect.grow(SHORE)


func _axis(sizes: Array[float], avenues: Array[int], lo: Array[float], hi: Array[float]) -> Array[Vector2]:
	var total := 0.0
	for i in sizes.size() + 1:
		total += AVENUE_W if avenues.has(i) else STREET_W
	for s in sizes:
		total += s
	var roads: Array[Vector2] = []
	var pos := -total * 0.5
	for i in sizes.size() + 1:
		var w := AVENUE_W if avenues.has(i) else STREET_W
		roads.append(Vector2(pos + w * 0.5, w))
		pos += w
		if i < sizes.size():
			lo.append(pos)
			pos += sizes[i]
			hi.append(pos)
	return roads


func _build_blocks() -> void:
	var used := {}
	for m in MERGES:
		var rect := Rect2(block_x0[m.position.x], block_z0[m.position.y], 0.0, 0.0)
		rect.end = Vector2(block_x1[m.end.x - 1], block_z1[m.end.y - 1])
		var letter := MAP[m.position.y][m.position.x]
		blocks.append({"id": blocks.size(), "ix": m.position.x, "iz": m.position.y, "rect": rect,
			"kind": _kind_of(letter), "merged": true})
		for iz in range(m.position.y, m.end.y):
			for ix in range(m.position.x, m.end.x):
				used[Vector2i(ix, iz)] = true
	for iz in BLOCKS_Z.size():
		for ix in BLOCKS_X.size():
			if used.has(Vector2i(ix, iz)):
				continue
			var rect := Rect2(block_x0[ix], block_z0[iz], BLOCKS_X[ix], BLOCKS_Z[iz])
			blocks.append({"id": blocks.size(), "ix": ix, "iz": iz, "rect": rect,
				"kind": _kind_of(MAP[iz][ix]), "merged": false})


func _kind_of(letter: String) -> int:
	match letter:
		"D": return Kind.DOWNTOWN
		"C": return Kind.COMMERCIAL
		"R": return Kind.RESIDENTIAL
		"I": return Kind.INDUSTRIAL
		"H": return Kind.HARBOR
		"P": return Kind.PARK
		"L": return Kind.PLAZA
		"K": return Kind.PARKING
	return Kind.COMMERCIAL


func _rng_for(ix: int, iz: int) -> RandomNumberGenerator:
	var r := RandomNumberGenerator.new()
	r.seed = (seed_value * 73856093) ^ (ix * 19349663) ^ (iz * 83492791) ^ 0x5bd1e995
	return r


func _pick(list: Array[Color], r: RandomNumberGenerator) -> Color:
	var c: Color = list[r.randi() % list.size()]
	var k := r.randf_range(0.9, 1.08)
	return Color(c.r * k, c.g * k, c.b * k)


# ---------------------------------------------------------------------------
# Block contents
# ---------------------------------------------------------------------------

func _fill_block(b: Dictionary) -> void:
	var r := _rng_for(b.ix, b.iz)
	match b.kind:
		Kind.DOWNTOWN:
			slabs.append({"rect": b.rect, "surface": "pavement", "block": b.id})
			_fill_downtown(b, r)
			_furnish_edges(b, r, true)
		Kind.COMMERCIAL:
			slabs.append({"rect": b.rect, "surface": "pavement", "block": b.id})
			_fill_commercial(b, r)
			_furnish_edges(b, r, true)
		Kind.RESIDENTIAL:
			slabs.append({"rect": b.rect, "surface": "pavement", "block": b.id})
			_fill_residential(b, r)
			_furnish_edges(b, r, true)
		Kind.INDUSTRIAL:
			slabs.append({"rect": b.rect, "surface": "pavement", "block": b.id})
			_fill_industrial(b, r)
			_furnish_edges(b, r, false)
		Kind.HARBOR:
			slabs.append({"rect": b.rect, "surface": "pavement", "block": b.id})
			_fill_harbor(b, r)
			_furnish_edges(b, r, false)
		Kind.PARK:
			slabs.append({"rect": b.rect, "surface": "park", "block": b.id})
			_fill_park(b, r)
			_furnish_edges(b, r, false)
		Kind.PLAZA:
			slabs.append({"rect": b.rect, "surface": "plaza", "block": b.id})
			_fill_plaza(b, r)
			_furnish_edges(b, r, true)
		Kind.PARKING:
			slabs.append({"rect": b.rect, "surface": "lot", "block": b.id})
			_fill_parking(b, r)
			_furnish_edges(b, r, false)


## Cuts a rectangle into smaller ones until every side is at most `max_side`.
## Sometimes leaves a narrow alley between two pieces.
func _split(rect: Rect2, min_side: float, max_side: float, alley_chance: float,
		r: RandomNumberGenerator) -> Array[Rect2]:
	var out: Array[Rect2] = []
	var todo: Array[Rect2] = [rect]
	while not todo.is_empty():
		var c: Rect2 = todo.pop_back()
		var long_side := maxf(c.size.x, c.size.y)
		if long_side <= max_side or long_side < min_side * 2.0:
			out.append(c)
			continue
		var gap := 0.0
		if r.randf() < alley_chance and long_side > min_side * 2.0 + 5.0:
			gap = r.randf_range(3.2, 4.5)
		var t := r.randf_range(0.4, 0.6)
		if c.size.x >= c.size.y:
			var w := c.size.x - gap
			var a := clampf(w * t, min_side, w - min_side)
			todo.append(Rect2(c.position, Vector2(a, c.size.y)))
			todo.append(Rect2(c.position + Vector2(a + gap, 0.0), Vector2(w - a, c.size.y)))
		else:
			var d := c.size.y - gap
			var a := clampf(d * t, min_side, d - min_side)
			todo.append(Rect2(c.position, Vector2(c.size.x, a)))
			todo.append(Rect2(c.position + Vector2(0.0, a + gap), Vector2(c.size.x, d - a)))
	return out


func _building(rect: Rect2, y0: float, y1: float, style: int, color: Color, seed_f: float,
		shop: bool, lit: float, floor0: float, block: int) -> void:
	buildings.append({"rect": rect, "y0": y0, "y1": y1, "style": style, "color": color,
		"seed": seed_f, "shop": shop, "lit": lit, "floor0": floor0, "block": block})


func _box(pos: Vector3, size: Vector3, color: Color, block: int, solid := true,
		rough := 0.75, metal := 0.0, emit := 0.0, yaw := 0.0, ribs := false) -> void:
	boxes.append({"pos": pos, "size": size, "yaw": yaw, "color": color, "rough": rough,
		"metal": metal, "emit": emit, "solid": solid, "block": block, "ribs": ribs})


func _prop(name: String, pos: Vector3, yaw: float, block: int, tint := Color.WHITE, scale := 1.0) -> void:
	if not props.has(name):
		props[name] = []
	props[name].append({"pos": pos, "yaw": yaw, "scale": scale, "tint": tint, "block": block})


## A tower made of stacked boxes: optional wide base, main body, optional narrower top.
func _tower(fp: Rect2, height: float, style: int, color: Color, r: RandomNumberGenerator,
		block: int) -> float:
	var fh := FLOOR_H[style]
	var seed_f := r.randf()
	var lit := r.randf_range(0.25, 0.6)
	var floors := maxi(3, roundi(height / fh))
	var y := CURB_H
	var body := fp
	var floor0 := 0.0
	var shop := true
	if floors >= 10 and r.randf() < 0.75 and minf(fp.size.x, fp.size.y) > 19.0:
		var base_floors := r.randi_range(2, 4)
		_building(fp, y, y + base_floors * fh, style, color.darkened(0.15), seed_f, true, lit, 0.0, block)
		y += base_floors * fh
		floors -= base_floors
		floor0 = float(base_floors)
		shop = false
		body = fp.grow(-r.randf_range(2.0, 4.0))
	var top_floors := 0
	if floors > 14 and r.randf() < 0.6 and minf(body.size.x, body.size.y) > 14.0:
		top_floors = r.randi_range(2, 5)
		floors -= top_floors
	_building(body, y, y + floors * fh, style, color, seed_f, shop, lit, floor0, block)
	y += floors * fh
	var top_rect := body
	if top_floors > 0:
		top_rect = body.grow(-r.randf_range(1.5, 3.0))
		_building(top_rect, y, y + top_floors * fh, style, color, seed_f, false, lit,
			floor0 + floors, block)
		y += top_floors * fh
	_roof_details(top_rect, y, r, block)
	return y


## Small things on a roof: machine boxes, a stair hut, and a mast on tall towers.
func _roof_details(rect: Rect2, y: float, r: RandomNumberGenerator, block: int) -> void:
	if minf(rect.size.x, rect.size.y) < 7.0:
		return
	var inner := rect.grow(-2.2)
	var grey := Color(0.56, 0.57, 0.58)
	for i in r.randi_range(1, 3):
		var p := Vector2(r.randf_range(inner.position.x, inner.end.x), r.randf_range(inner.position.y, inner.end.y))
		_box(Vector3(p.x, y + 0.75, p.y), Vector3(2.2, 1.5, 1.5), grey, block, true, 0.55, 0.5)
	if r.randf() < 0.6:
		var p := Vector2(r.randf_range(inner.position.x, inner.end.x), r.randf_range(inner.position.y, inner.end.y))
		_box(Vector3(p.x, y + 1.4, p.y), Vector3(3.6, 2.8, 4.2), Color(0.42, 0.42, 0.43), block, true, 0.9)
	if y > 62.0 and r.randf() < 0.7:
		var mast := r.randf_range(8.0, 18.0)
		var c := rect.get_center()
		_box(Vector3(c.x, y + mast * 0.5, c.y), Vector3(0.35, mast, 0.35), Color(0.75, 0.75, 0.76), block, false, 0.4, 0.8)
		_box(Vector3(c.x, y + mast + 0.2, c.y), Vector3(0.5, 0.4, 0.5), Color(1.0, 0.12, 0.08), block, false, 0.4, 0.0, 4.0)


func _fill_downtown(b: Dictionary, r: RandomNumberGenerator) -> void:
	var lot: Rect2 = b.rect.grow(-SIDEWALK)
	var parcels := _split(lot, 19.0, 34.0, 0.35, r)
	for p in parcels:
		if parcels.size() > 2 and r.randf() < 0.12:
			_pocket_plaza(p, r, b.id)
			continue
		var fp := p.grow(-r.randf_range(0.4, 1.6))
		var d := fp.get_center().length()
		var h_max := lerpf(125.0, 44.0, clampf(d / 185.0, 0.0, 1.0))
		var h := clampf(h_max * r.randf_range(0.5, 1.08), 24.0, 135.0)
		var style := Style.GLASS if r.randf() < 0.72 else Style.OFFICE
		var color := _pick(GLASS_TINTS, r) if style == Style.GLASS else _pick(OFFICE_TINTS, r)
		_tower(fp, h, style, color, r, b.id)


## A small open square between towers: trees, benches and planters to hide behind.
func _pocket_plaza(p: Rect2, r: RandomNumberGenerator, block: int) -> void:
	var c := p.get_center()
	for i in 4:
		var corner := Vector2(p.position.x + (2.5 if i % 2 == 0 else p.size.x - 2.5),
			p.position.y + (2.5 if i < 2 else p.size.y - 2.5))
		_prop("tree_a", Vector3(corner.x, CURB_H, corner.y), r.randf() * TAU, block, _leaf_tint(r), r.randf_range(0.85, 1.1))
	_prop("planter", Vector3(c.x, CURB_H, c.y), 0.0, block)
	_prop("bench", Vector3(c.x, CURB_H, c.y + 2.6), 0.0, block)
	_prop("bench", Vector3(c.x, CURB_H, c.y - 2.6), PI, block)


func _fill_commercial(b: Dictionary, r: RandomNumberGenerator) -> void:
	var lot: Rect2 = b.rect.grow(-SIDEWALK)
	var parcels := _split(lot, 13.0, 27.0, 0.3, r)
	for p in parcels:
		var fp := p.grow(-r.randf_range(0.0, 0.8))
		var h := r.randf_range(13.0, 40.0)
		var pick := r.randf()
		var style := Style.OFFICE
		var color := _pick(OFFICE_TINTS, r)
		if pick < 0.38:
			style = Style.BRICK
			color = _pick(BRICK_TINTS, r)
		elif pick > 0.82:
			style = Style.GLASS
			color = _pick(GLASS_TINTS, r)
		_tower(fp, h, style, color, r, b.id)


func _fill_residential(b: Dictionary, r: RandomNumberGenerator) -> void:
	var lot: Rect2 = b.rect.grow(-SIDEWALK)
	var depth := r.randf_range(10.5, 12.5)
	var gap := 4.0
	_house_row(Rect2(lot.position, Vector2(lot.size.x, depth)), true, r, b.id)
	_house_row(Rect2(Vector2(lot.position.x, lot.end.y - depth), Vector2(lot.size.x, depth)), true, r, b.id)
	var inner_len := lot.size.y - 2.0 * (depth + gap)
	if inner_len > 10.0:
		var z := lot.position.y + depth + gap
		_house_row(Rect2(Vector2(lot.position.x, z), Vector2(depth, inner_len)), false, r, b.id)
		_house_row(Rect2(Vector2(lot.end.x - depth, z), Vector2(depth, inner_len)), false, r, b.id)
	# Courtyard
	var yard := lot.grow(-(depth + 3.0))
	if yard.size.x > 6.0 and yard.size.y > 6.0:
		for i in r.randi_range(3, 6):
			var p := Vector2(r.randf_range(yard.position.x, yard.end.x), r.randf_range(yard.position.y, yard.end.y))
			_prop("tree_a", Vector3(p.x, CURB_H, p.y), r.randf() * TAU, b.id, _leaf_tint(r), r.randf_range(0.8, 1.05))
		var c := yard.get_center()
		_prop("bench", Vector3(c.x - 3.0, CURB_H, c.y), PI * 0.5, b.id)
		_prop("planter", Vector3(c.x + 2.0, CURB_H, c.y), 0.0, b.id)


## A row of joined houses along one side of a block. Each house has its own height and colour.
func _house_row(rect: Rect2, along_x: bool, r: RandomNumberGenerator, block: int) -> void:
	var length := rect.size.x if along_x else rect.size.y
	var pos := 0.0
	var passage_at := r.randi_range(1, 2) if length > 40.0 else -1
	var index := 0
	while pos < length - 1.0:
		var w := minf(r.randf_range(13.0, 21.0), length - pos)
		if length - pos - w < 9.0:
			w = length - pos
		var piece := Rect2(rect.position + Vector2(pos, 0.0), Vector2(w, rect.size.y)) if along_x \
				else Rect2(rect.position + Vector2(0.0, pos), Vector2(rect.size.x, w))
		var style := Style.BRICK if r.randf() < 0.45 else Style.PLASTER
		var color := _pick(BRICK_TINTS, r) if style == Style.BRICK else _pick(PLASTER_TINTS, r)
		var floors := r.randi_range(4, 7)
		var y1 := CURB_H + floors * FLOOR_H[style]
		_building(piece, CURB_H, y1, style, color, r.randf(), r.randf() < 0.25, r.randf_range(0.3, 0.65), 0.0, block)
		if r.randf() < 0.5:
			_roof_details(piece, y1, r, block)
		pos += w
		if index == passage_at and pos < length - 12.0:
			pos += 3.6                      # walk-through passage into the courtyard
		index += 1


func _fill_industrial(b: Dictionary, r: RandomNumberGenerator) -> void:
	var lot: Rect2 = b.rect.grow(-SIDEWALK)
	var parcels := _split(lot, 21.0, 40.0, 0.6, r)
	for p in parcels:
		if r.randf() < 0.62:
			var fp := p.grow(-r.randf_range(1.5, 4.0))
			var floors := r.randi_range(2, 3)
			var y1 := CURB_H + floors * FLOOR_H[Style.METAL]
			_building(fp, CURB_H, y1, Style.METAL, _pick(METAL_TINTS, r), r.randf(), false, 0.15, 0.0, b.id)
			_roof_details(fp, y1, r, b.id)
			if r.randf() < 0.4 and p.size.x - fp.size.x > 5.5:
				_prop("silo", Vector3(p.position.x + 2.6, CURB_H, p.get_center().y), 0.0, b.id)
		else:
			_container_yard(p.grow(-2.0), r, b.id, 2)


## Rows of shipping containers with walking lanes between them.
func _container_yard(area: Rect2, r: RandomNumberGenerator, block: int, max_levels: int) -> void:
	var c_len := 12.19
	var c_w := 2.44
	var c_h := 2.59
	var lane := 3.6
	var z := area.position.y + c_w * 0.5
	var row := 0
	while z + c_w * 0.5 <= area.end.y:
		var x := area.position.x + c_len * 0.5 + (r.randf_range(0.0, 3.0) if row % 2 == 1 else 0.0)
		while x + c_len * 0.5 <= area.end.x:
			if r.randf() < 0.74:
				var levels := 1 + int(r.randf() * r.randf() * float(max_levels) + 0.35)
				levels = clampi(levels, 1, max_levels)
				for level in levels:
					var col: Color = CONTAINER_COLORS[r.randi() % CONTAINER_COLORS.size()]
					_box(Vector3(x, CURB_H + c_h * (level + 0.5), z), Vector3(c_len, c_h, c_w), col, block, true, 0.55, 0.35, 0.0, 0.0, true)
			x += c_len + (0.5 if r.randf() < 0.7 else 4.5)
		z += c_w + lane
		row += 1


func _fill_harbor(b: Dictionary, r: RandomNumberGenerator) -> void:
	var lot: Rect2 = b.rect.grow(-SIDEWALK)
	# Warehouse at the west end, container yard in the rest.
	var shed := Rect2(lot.position, Vector2(38.0, lot.size.y)).grow(-1.5)
	var y1 := CURB_H + 3.0 * FLOOR_H[Style.METAL]
	_building(shed, CURB_H, y1, Style.METAL, _pick(METAL_TINTS, r), r.randf(), false, 0.15, 0.0, b.id)
	_roof_details(shed, y1, r, b.id)
	var yard := Rect2(lot.position + Vector2(44.0, 0.0), lot.size - Vector2(44.0, 0.0)).grow(-1.5)
	_container_yard(yard, r, b.id, 3)
	# Two big gantry cranes over the yard.
	for i in 2:
		var cx := yard.position.x + yard.size.x * (0.3 + 0.42 * i)
		_gantry_crane(Vector3(cx, CURB_H, yard.get_center().y), yard.size.y - 4.0, b.id,
			Color(0.82, 0.42, 0.08) if i == 0 else Color(0.78, 0.66, 0.10))


func _gantry_crane(center: Vector3, depth: float, block: int, color: Color) -> void:
	var span := 16.0
	var h := 21.0
	var leg := 1.0
	for sx: float in [-1.0, 1.0]:
		for sz: float in [-1.0, 1.0]:
			_box(center + Vector3(sx * span * 0.5, h * 0.5, sz * depth * 0.5), Vector3(leg, h, leg), color, block, true, 0.5, 0.4)
		# beams joining the two legs on each side
		_box(center + Vector3(sx * span * 0.5, h - 0.6, 0.0), Vector3(leg, 1.2, depth), color, block, false, 0.5, 0.4)
		_box(center + Vector3(sx * span * 0.5, 6.0, 0.0), Vector3(0.6, 0.6, depth), color, block, false, 0.5, 0.4)
	# top beam across, the long arm, the machine house and the hanging trolley
	_box(center + Vector3(0.0, h + 0.4, 0.0), Vector3(span + leg, 1.4, 2.0), color, block, false, 0.5, 0.4)
	_box(center + Vector3(0.0, h + 1.2, 8.0), Vector3(2.2, 1.6, depth + 30.0), color, block, false, 0.5, 0.4)
	_box(center + Vector3(0.0, h + 3.2, -depth * 0.3), Vector3(5.0, 3.0, 7.0), Color(0.85, 0.85, 0.83), block, false, 0.6, 0.2)
	_box(center + Vector3(0.0, h - 1.2, depth * 0.25), Vector3(3.0, 1.6, 3.0), Color(0.2, 0.2, 0.22), block, false, 0.6, 0.4)
	_box(center + Vector3(0.0, h + 4.9, -depth * 0.3), Vector3(0.5, 0.4, 0.5), Color(1.0, 0.12, 0.08), block, false, 0.4, 0.0, 4.0)


func _leaf_tint(r: RandomNumberGenerator) -> Color:
	return Color(r.randf_range(0.82, 1.1), r.randf_range(0.88, 1.12), r.randf_range(0.75, 1.0))


func _fill_park(b: Dictionary, r: RandomNumberGenerator) -> void:
	var rect: Rect2 = b.rect
	var c := rect.get_center()
	var pond := c + Vector2(rect.size.x * 0.27, rect.size.y * 0.06)
	var park := {"rect": rect, "center": c, "plaza_r": 9.0, "ring_inset": 9.5,
		"pond": pond, "pond_r": 8.0, "block": b.id}
	parks.append(park)
	_prop("fountain", Vector3(c.x, CURB_H, c.y), 0.0, b.id)
	_prop("pond", Vector3(pond.x, CURB_H, pond.y), 0.0, b.id, Color.WHITE, park.pond_r)
	var pav := c + Vector2(-rect.size.x * 0.27, -rect.size.y * 0.04)
	_prop("pavilion", Vector3(pav.x, CURB_H, pav.y), 0.0, b.id)
	# Trees: try many random spots, keep the ones on grass and not too close together.
	var placed: Array[Vector2] = []
	for i in 420:
		var p := Vector2(r.randf_range(rect.position.x + 5.0, rect.end.x - 5.0),
			r.randf_range(rect.position.y + 5.0, rect.end.y - 5.0))
		if park_path(park, p) > 0.02 or p.distance_to(pond) < park.pond_r + 2.5 or p.distance_to(pav) < 6.5:
			continue
		var ok := true
		for q in placed:
			if q.distance_to(p) < 5.2:
				ok = false
				break
		if not ok:
			continue
		placed.append(p)
		var kind := "tree_a" if r.randf() < 0.7 else "tree_b"
		_prop(kind, Vector3(p.x, CURB_H, p.y), r.randf() * TAU, b.id, _leaf_tint(r), r.randf_range(0.85, 1.25))
	for i in 46:
		var p := Vector2(r.randf_range(rect.position.x + 5.0, rect.end.x - 5.0),
			r.randf_range(rect.position.y + 5.0, rect.end.y - 5.0))
		if park_path(park, p) < 0.02 and p.distance_to(pond) > park.pond_r + 1.0:
			_prop("bush", Vector3(p.x, CURB_H, p.y), r.randf() * TAU, b.id, _leaf_tint(r), r.randf_range(0.8, 1.5))
	# Benches and lamps around the fountain square.
	var plaza_r: float = park.plaza_r
	for i in 8:
		var a := TAU * i / 8.0 + PI / 8.0
		var p := c + Vector2(cos(a), sin(a)) * (plaza_r - 1.2)
		if i % 2 == 0:
			_prop("bench", Vector3(p.x, CURB_H, p.y), atan2(-cos(a), -sin(a)) + PI, b.id)
		else:
			_prop("park_lamp", Vector3(p.x, CURB_H, p.y), 0.0, b.id)
	# Lamps along the ring path.
	var half := rect.size * 0.5 - Vector2(park.ring_inset, park.ring_inset)
	for i in 14:
		var t := float(i) / 14.0
		var a := TAU * t
		var p := c + Vector2(cos(a) * half.x, sin(a) * half.y) * 0.98
		if park_path(park, p) > 0.5:
			_prop("park_lamp", Vector3(p.x + 1.6, CURB_H, p.y + 1.6), 0.0, b.id)


## How much a point in a park is path or paving (1) instead of grass (0).
static func park_path(park: Dictionary, p: Vector2) -> float:
	var rect: Rect2 = park.rect
	var c: Vector2 = park.center
	var best := 0.0
	# Paved border next to the streets.
	var edge := minf(minf(p.x - rect.position.x, rect.end.x - p.x), minf(p.y - rect.position.y, rect.end.y - p.y))
	best = maxf(best, 1.0 - smoothstep(SIDEWALK - 0.6, SIDEWALK + 0.6, edge))
	# Fountain square in the middle.
	best = maxf(best, 1.0 - smoothstep(park.plaza_r - 0.6, park.plaza_r + 0.6, p.distance_to(c)))
	# Ring path: a rounded rectangle.
	var inset: float = park.ring_inset
	var half := rect.size * 0.5 - Vector2(inset, inset)
	var round_r := 9.0
	var q := (p - c).abs() - (half - Vector2(round_r, round_r))
	var sd := Vector2(maxf(q.x, 0.0), maxf(q.y, 0.0)).length() + minf(maxf(q.x, q.y), 0.0) - round_r
	best = maxf(best, 1.0 - smoothstep(1.2, 2.2, absf(sd)))
	# Straight paths through the middle, and to the four street corners.
	if sd < 0.0:
		best = maxf(best, 1.0 - smoothstep(1.1, 2.0, absf(p.x - c.x)))
		best = maxf(best, 1.0 - smoothstep(1.1, 2.0, absf(p.y - c.y)))
	for sx: float in [-1.0, 1.0]:
		for sz: float in [-1.0, 1.0]:
			var a := c + Vector2(half.x * sx, half.y * sz) * 0.93
			var e := c + rect.size * 0.5 * Vector2(sx, sz)
			var ab := e - a
			var t := clampf((p - a).dot(ab) / ab.length_squared(), 0.0, 1.0)
			best = maxf(best, 1.0 - smoothstep(1.1, 2.0, p.distance_to(a + ab * t)))
	return best


func _fill_plaza(b: Dictionary, r: RandomNumberGenerator) -> void:
	var rect: Rect2 = b.rect
	var c := rect.get_center()
	landmark_pos = Vector3(c.x, 0.0, c.y)
	# The landmark tower: the tallest building, visible from the whole city.
	var style := Style.GLASS
	var fh := FLOOR_H[style]
	var color := Color(0.20, 0.36, 0.52)
	var seed_f := 0.37
	var fp := Rect2(c - Vector2(14.0, 14.0), Vector2(28.0, 28.0))
	var y := CURB_H
	var steps := [[fp, 3, true], [fp.grow(-2.5), 24, false], [fp.grow(-5.5), 9, false], [fp.grow(-8.5), 5, false]]
	var floor0 := 0.0
	for s: Array in steps:
		var floors: int = s[1]
		_building(s[0], y, y + floors * fh, style, color, seed_f, s[2], 0.5, floor0, b.id)
		y += floors * fh
		floor0 += floors
	_box(Vector3(c.x, y + 13.0, c.y), Vector3(1.2, 26.0, 1.2), Color(0.8, 0.82, 0.85), b.id, false, 0.3, 0.9)
	_box(Vector3(c.x, y + 26.3, c.y), Vector3(0.7, 0.6, 0.7), Color(1.0, 0.12, 0.08), b.id, false, 0.4, 0.0, 5.0)
	# Open square around it.
	for sx: float in [-1.0, 1.0]:
		for sz: float in [-1.0, 1.0]:
			var corner := c + Vector2(sx * (rect.size.x * 0.5 - 8.0), sz * (rect.size.y * 0.5 - 8.0))
			_prop("planter", Vector3(corner.x, CURB_H, corner.y), 0.0, b.id)
			_prop("tree_a", Vector3(corner.x + sx * 3.0, CURB_H, corner.y), r.randf() * TAU, b.id, _leaf_tint(r))
			_prop("tree_a", Vector3(corner.x, CURB_H, corner.y + sz * 3.0), r.randf() * TAU, b.id, _leaf_tint(r))
			_prop("bench", Vector3(corner.x - sx * 2.4, CURB_H, corner.y), PI * 0.5 * sx, b.id)
	# A small monument in front of the entrance.
	var m := Vector3(c.x, CURB_H, rect.end.y - 9.0)
	_box(m + Vector3(0.0, 0.5, 0.0), Vector3(3.0, 1.0, 3.0), Color(0.55, 0.55, 0.56), b.id, true, 0.6)
	_box(m + Vector3(0.0, 2.6, 0.0), Vector3(1.0, 3.2, 1.0), Color(0.78, 0.6, 0.22), b.id, true, 0.3, 0.9, 0.0, 0.5)
	_box(m + Vector3(0.0, 4.8, 0.0), Vector3(1.5, 1.5, 1.5), Color(0.78, 0.6, 0.22), b.id, false, 0.3, 0.9, 0.0, 0.9)


func _fill_parking(b: Dictionary, r: RandomNumberGenerator) -> void:
	var lot: Rect2 = b.rect.grow(-SIDEWALK)
	# Two rows of bays back to back, then a driving lane, and so on.
	var bay_w := 2.7
	var bay_d := 5.0
	var lane := 6.5
	var z := lot.position.y + 1.0
	var row := 0
	while z + bay_d <= lot.end.y - 0.5:
		var x := lot.position.x + 2.0
		while x + bay_w <= lot.end.x - 2.0:
			if r.randf() < 0.5:
				var yaw := (0.0 if row % 2 == 0 else PI) + r.randf_range(-0.04, 0.04)
				_car(Vector3(x + bay_w * 0.5, CURB_H, z + bay_d * 0.5), yaw, b.id, r)
			x += bay_w
		z += bay_d + (lane if row % 2 == 0 else 0.0)
		row += 1
	_building(Rect2(lot.position + Vector2(0.0, lot.size.y - 4.0), Vector2(4.0, 4.0)), CURB_H,
		CURB_H + FLOOR_H[Style.CONCRETE], Style.CONCRETE, Color(0.7, 0.7, 0.68), r.randf(), false, 0.5, 0.0, b.id)
	for sx: float in [0.25, 0.75]:
		for sz: float in [0.3, 0.75]:
			_prop("lamp", Vector3(lot.position.x + lot.size.x * sx, CURB_H, lot.position.y + lot.size.y * sz), 0.0, b.id)


func _car(pos: Vector3, yaw: float, block: int, r: RandomNumberGenerator) -> void:
	var pick := r.randf()
	var name := "car_sedan"
	if pick > 0.8:
		name = "car_van"
	elif pick > 0.5:
		name = "car_suv"
	_prop(name, pos, yaw, block, CAR_COLORS[r.randi() % CAR_COLORS.size()])


# ---------------------------------------------------------------------------
# Streets
# ---------------------------------------------------------------------------

## Lamps, trees, traffic lights and small objects along the four kerbs of a block.
func _furnish_edges(b: Dictionary, r: RandomNumberGenerator, trees: bool) -> void:
	var rect: Rect2 = b.rect
	var corners: Array[Vector2] = [rect.position, Vector2(rect.end.x, rect.position.y), rect.end,
		Vector2(rect.position.x, rect.end.y)]
	for e in 4:
		var a := corners[e]
		var c := corners[(e + 1) % 4]
		var dir := (c - a).normalized()
		var inward := Vector2(-dir.y, dir.x)               # corners go clockwise seen from above
		var length := a.distance_to(c)
		var lamp_yaw := atan2(inward.x, inward.y)          # lamp arm points out over the road
		var count := maxi(1, roundi(length / 24.0))
		for i in count:
			var t := (float(i) + 0.5) / float(count)
			var p := a + dir * (length * t) + inward * 0.75
			_prop("lamp", Vector3(p.x, CURB_H, p.y), lamp_yaw, b.id)
			if trees and b.kind != Kind.PLAZA:
				for side: float in [-0.25, 0.25]:
					var tp := a + dir * (length * (t + side / float(count))) + inward * 1.25
					if r.randf() < 0.8:
						_prop("tree_a", Vector3(tp.x, CURB_H, tp.y), r.randf() * TAU, b.id, _leaf_tint(r), r.randf_range(0.7, 0.95))
		if r.randf() < 0.55:
			var p := a + dir * r.randf_range(8.0, length - 8.0) + inward * 0.6
			_prop("hydrant", Vector3(p.x, CURB_H, p.y), 0.0, b.id)
		if r.randf() < 0.6:
			var p := a + dir * 6.5 + inward * 0.9
			_prop("bin", Vector3(p.x, CURB_H, p.y), 0.0, b.id)
		if trees and r.randf() < 0.4:
			var p := a + dir * r.randf_range(10.0, length - 10.0) + inward * 2.6
			_prop("bench", Vector3(p.x, CURB_H, p.y), atan2(inward.x, inward.y), b.id)
		# Traffic light at the start corner of every edge: 4 per crossing in total.
		var tl := a + dir * 0.9 + inward * 0.9
		_prop("traffic_light", Vector3(tl.x, CURB_H, tl.y), lamp_yaw, b.id)


func _covered_by_big_block(p: Vector2) -> bool:
	for b in blocks:
		if b.merged and (b.rect as Rect2).has_point(p):
			return true
	return false


## Cars parked along the kerbs of every street.
func _parked_cars() -> void:
	var r := _rng_for(991, 17)
	for i in roads_x.size():
		var road := roads_x[i]
		for j in block_z0.size():
			for side: float in [-1.0, 1.0]:
				var x: float = road.x + side * (road.y * 0.5 - 1.25)
				var z := block_z0[j] + 9.0
				while z < block_z1[j] - 9.0:
					if r.randf() < 0.3 and not _covered_by_big_block(Vector2(road.x, z)):
						# Drive on the right: cars on the east side face north.
						var yaw := (0.0 if side > 0.0 else PI) + r.randf_range(-0.03, 0.03)
						_car(Vector3(x, 0.0, z), yaw, -1, r)
					z += 6.2
	for i in roads_z.size():
		var road := roads_z[i]
		for j in block_x0.size():
			for side: float in [-1.0, 1.0]:
				var z: float = road.x + side * (road.y * 0.5 - 1.25)
				var x := block_x0[j] + 9.0
				while x < block_x1[j] - 9.0:
					if r.randf() < 0.3 and not _covered_by_big_block(Vector2(x, road.x)):
						var yaw := (-PI * 0.5 if side > 0.0 else PI * 0.5) + r.randf_range(-0.03, 0.03)
						_car(Vector3(x, 0.0, z), yaw, -1, r)
					x += 6.2


## The promenade around the city, with a railing, lamps and benches.
func _shore() -> void:
	var r := _rng_for(555, 31)
	var c := city_rect
	var o := bounds
	slabs.append({"rect": Rect2(o.position.x, o.position.y, o.size.x, SHORE), "surface": "pavement", "block": -1})
	slabs.append({"rect": Rect2(o.position.x, c.end.y, o.size.x, SHORE), "surface": "pavement", "block": -1})
	slabs.append({"rect": Rect2(o.position.x, c.position.y, SHORE, c.size.y), "surface": "pavement", "block": -1})
	slabs.append({"rect": Rect2(c.end.x, c.position.y, SHORE, c.size.y), "surface": "pavement", "block": -1})
	var rail := Color(0.16, 0.17, 0.18)
	var inset := 0.4
	# Railing on the north, east and west sides. The south side is the harbour quay.
	var runs := [
		[Vector2(o.position.x + inset, o.position.y + inset), Vector2(o.end.x - inset, o.position.y + inset)],
		[Vector2(o.position.x + inset, o.position.y + inset), Vector2(o.position.x + inset, o.end.y - inset)],
		[Vector2(o.end.x - inset, o.position.y + inset), Vector2(o.end.x - inset, o.end.y - inset)],
	]
	for run: Array in runs:
		var a: Vector2 = run[0]
		var e: Vector2 = run[1]
		var length := a.distance_to(e)
		var mid := (a + e) * 0.5
		var along_x := absf(e.x - a.x) > absf(e.y - a.y)
		for h: float in [0.55, 1.05]:
			var size := Vector3(length, 0.06, 0.06) if along_x else Vector3(0.06, 0.06, length)
			_box(Vector3(mid.x, CURB_H + h, mid.y), size, rail, -1, false, 0.5, 0.7)
		var posts := int(length / 4.0)
		for i in posts + 1:
			var p := a.lerp(e, float(i) / float(posts))
			_box(Vector3(p.x, CURB_H + 0.55, p.y), Vector3(0.09, 1.1, 0.09), rail, -1, false, 0.5, 0.7)
	# Lamps and benches along all four sides.
	var sides := [
		[Vector2(o.position.x, o.position.y + 3.0), Vector2(1, 0), o.size.x, 0.0],
		[Vector2(o.position.x, o.end.y - 3.0), Vector2(1, 0), o.size.x, PI],
		[Vector2(o.position.x + 3.0, o.position.y), Vector2(0, 1), o.size.y, PI * 0.5],
		[Vector2(o.end.x - 3.0, o.position.y), Vector2(0, 1), o.size.y, -PI * 0.5],
	]
	for s: Array in sides:
		var start: Vector2 = s[0]
		var dir: Vector2 = s[1]
		var length: float = s[2]
		var t := 14.0
		while t < length - 10.0:
			var p := start + dir * t
			_prop("park_lamp", Vector3(p.x, CURB_H, p.y), 0.0, -1)
			var q := start + dir * (t + 13.0)
			if r.randf() < 0.7:
				_prop("bench", Vector3(q.x, CURB_H, q.y), s[3], -1)
			t += 26.0
	# Mooring posts on the harbour quay.
	var x := o.position.x + 8.0
	while x < o.end.x - 8.0:
		_prop("bollard", Vector3(x, CURB_H, o.end.y - 1.0), 0.0, -1)
		x += 12.0


# ---------------------------------------------------------------------------
# Questions other scripts ask
# ---------------------------------------------------------------------------

## True when the point is inside a building footprint (grown by `margin`).
func inside_building(p: Vector2, margin := 0.0) -> bool:
	for b in buildings:
		if (b.rect as Rect2).grow(margin).has_point(p):
			return true
	return false


func kind_name(kind: int) -> String:
	return ["Downtown", "Commercial", "Residential", "Industrial", "Harbour", "Park", "Plaza", "Car park"][kind]
