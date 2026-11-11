extends SceneTree
## Checks the city data (city_layout.gd) without drawing anything.
## Run:  godot --headless --path . -s tests/test_city.gd
## Ends with exit code 0 when every check passed, 1 when one failed.

const CityLayout := preload("res://scripts/world/city_layout.gd")

var passed := 0
var failed := 0


func _init() -> void:
	var city := CityLayout.new()
	city.generate(7)
	var again := CityLayout.new()
	again.generate(7)
	var other := CityLayout.new()
	other.generate(8)

	_check("the grid has 8 x 8 roads", city.roads_x.size() == 8 and city.roads_z.size() == 8)
	_check("the city has buildings and props", city.buildings.size() > 150 and city.props.size() > 10,
		"%d buildings, %d kinds of props" % [city.buildings.size(), city.props.size()])

	# Same seed -> same city. Different seed -> a different city.
	var same := city.buildings.size() == again.buildings.size() and city.boxes.size() == again.boxes.size()
	if same:
		for i in city.buildings.size():
			if city.buildings[i].rect != again.buildings[i].rect or city.buildings[i].y1 != again.buildings[i].y1:
				same = false
				break
	_check("the same seed always builds the same city", same)
	var differs := city.buildings.size() != other.buildings.size()
	if not differs:
		for i in city.buildings.size():
			if city.buildings[i].rect != other.buildings[i].rect:
				differs = true
				break
	_check("another seed builds a different city", differs)

	# Every block lies inside the city, and every building inside its own block's pavement.
	var blocks_ok := true
	for b: Dictionary in city.blocks:
		if not city.city_rect.encloses(b.rect):
			blocks_ok = false
	_check("all blocks are inside the ring road", blocks_ok)
	var inside := 0
	for b: Dictionary in city.buildings:
		var block: Dictionary = city.blocks[b.block]
		var lot: Rect2 = (block.rect as Rect2).grow(-CityLayout.SIDEWALK + 0.01)
		if lot.encloses(b.rect):
			inside += 1
	_check("every building keeps the pavement free", inside == city.buildings.size(),
		"%d of %d" % [inside, city.buildings.size()])

	# Buildings standing on the ground must not overlap each other.
	var ground: Array[Rect2] = []
	for b: Dictionary in city.buildings:
		if is_equal_approx(b.y0, CityLayout.CURB_H):
			ground.append(b.rect)
	var overlaps := 0
	for i in ground.size():
		for j in range(i + 1, ground.size()):
			var both := ground[i].intersection(ground[j])
			if both.size.x > 0.01 and both.size.y > 0.01:
				overlaps += 1
	_check("no two buildings overlap", overlaps == 0, "%d overlaps among %d footprints" % [overlaps, ground.size()])

	# Upper parts of a tower must sit on the part below (never hang in the air).
	var floating := 0
	for b: Dictionary in city.buildings:
		if b.y0 > CityLayout.CURB_H + 0.01:
			var held := false
			for below: Dictionary in city.buildings:
				if is_equal_approx(below.y1, b.y0) and (below.rect as Rect2).grow(0.01).encloses(b.rect):
					held = true
					break
			if not held:
				floating += 1
	_check("upper tower parts rest on the part below", floating == 0, "%d floating" % floating)

	# Street props must not be inside buildings, and nothing may be outside the island.
	var buried := 0
	var outside := 0
	var total := 0
	for name: String in city.props:
		for item: Dictionary in city.props[name]:
			total += 1
			var p := Vector2(item.pos.x, item.pos.z)
			if city.inside_building(p):
				buried += 1
			if not city.bounds.has_point(p):
				outside += 1
	_check("no prop is inside a building", buried == 0, "%d of %d" % [buried, total])
	_check("no prop is outside the island", outside == 0, "%d of %d" % [outside, total])

	# Start places must be free.
	var blocked := 0
	for s in city.spawn_points:
		if city.inside_building(Vector2(s.x, s.z), 0.5):
			blocked += 1
	_check("all start places are on open road", blocked == 0 and city.spawn_points.size() == 64,
		"%d places, %d blocked" % [city.spawn_points.size(), blocked])

	# The landmark is the tallest building.
	var tallest := 0.0
	var tallest_at := Vector2.ZERO
	for b: Dictionary in city.buildings:
		if b.y1 > tallest:
			tallest = b.y1
			tallest_at = (b.rect as Rect2).get_center()
	_check("the landmark tower is the tallest building",
		tallest > 140.0 and tallest_at.distance_to(Vector2(city.landmark_pos.x, city.landmark_pos.z)) < 1.0,
		"%.0f m tall" % tallest)

	# Park paths: the value is always between 0 and 1, the fountain square is paved, the lawn is not.
	var park: Dictionary = city.parks[0]
	var in_range := true
	for i in 400:
		var p := Vector2((park.rect as Rect2).position.x + (park.rect as Rect2).size.x * (i % 20) / 19.0,
			(park.rect as Rect2).position.y + (park.rect as Rect2).size.y * (i / 20) / 19.0)
		var v := CityLayout.park_path(park, p)
		if v < 0.0 or v > 1.0:
			in_range = false
	_check("park path values stay between 0 and 1", in_range)
	_check("the park's fountain square is paved", CityLayout.park_path(park, park.center) > 0.99)
	var lawn: Vector2 = park.center + Vector2(20.0, 12.0)
	_check("the park's lawn is grass", CityLayout.park_path(park, lawn) < 0.01, "%.3f" % CityLayout.park_path(park, lawn))

	print("CITY TESTS: %d passed, %d failed" % [passed, failed])
	quit(1 if failed > 0 else 0)


func _check(what: String, ok: bool, detail := "") -> void:
	if ok:
		passed += 1
		print("  PASS  ", what, ("  (" + detail + ")") if detail != "" else "")
	else:
		failed += 1
		print("  FAIL  ", what, ("  (" + detail + ")") if detail != "" else "")
