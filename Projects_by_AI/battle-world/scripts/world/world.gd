extends Node3D
## The game world: sky, sun, sea and the city.

const CityLayout := preload("res://scripts/world/city_layout.gd")
const CityBuilder := preload("res://scripts/world/city_builder.gd")

## Direction from the ground towards the sun. Measured from the sky picture with
## tools/find_sun.gd, so shadows match the sun you see in the sky.
const SUN_DIRECTION := Vector3(-0.3775, 0.7418, 0.5544)

var layout: CityLayout
var city: CityBuilder
var sun: DirectionalLight3D
var environment: Environment


func _ready() -> void:
	build(7)


func build(city_seed: int) -> void:
	layout = CityLayout.new()
	layout.generate(city_seed)
	_make_sky_and_sun()
	city = CityBuilder.new()
	city.name = "City"
	add_child(city)
	city.build(layout)
	Settings.changed.connect(_apply_quality)
	_apply_quality()


func _make_sky_and_sun() -> void:
	var sky_material := ShaderMaterial.new()
	sky_material.shader = load("res://shaders/sky.gdshader")
	sky_material.set_shader_parameter("panorama", load("res://assets/sky/sky_day_2k.hdr"))
	var sky := Sky.new()
	sky.sky_material = sky_material
	sky.radiance_size = Sky.RADIANCE_SIZE_128

	environment = Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	environment.ambient_light_energy = 1.0
	environment.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	environment.tonemap_mode = Environment.TONE_MAPPER_ACES
	environment.tonemap_exposure = 1.0
	environment.tonemap_white = 6.0
	# Haze: far buildings fade into the sky colour, which gives a feeling of distance.
	environment.fog_enabled = true
	environment.fog_mode = Environment.FOG_MODE_EXPONENTIAL
	environment.fog_density = 0.0009
	environment.fog_light_color = Color(0.62, 0.72, 0.84)
	environment.fog_aerial_perspective = 0.8
	environment.fog_sun_scatter = 0.15
	environment.fog_sky_affect = 0.0
	environment.glow_enabled = true
	environment.glow_intensity = 0.6
	environment.glow_bloom = 0.05
	environment.glow_hdr_threshold = 1.1
	environment.adjustment_enabled = true
	environment.adjustment_contrast = 1.06
	environment.adjustment_saturation = 1.12
	var world_env := WorldEnvironment.new()
	world_env.name = "Environment"
	world_env.environment = environment
	add_child(world_env)

	sun = DirectionalLight3D.new()
	sun.name = "Sun"
	sun.light_color = Color(1.0, 0.95, 0.86)
	sun.light_energy = 1.7
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS
	sun.directional_shadow_blend_splits = false
	sun.shadow_bias = 0.06
	sun.shadow_normal_bias = 1.6
	add_child(sun)
	sun.look_at_from_position(SUN_DIRECTION * 100.0, Vector3.ZERO, Vector3.UP)


func _apply_quality() -> void:
	var p := Settings.preset()
	sun.shadow_enabled = p.shadow_size > 0
	sun.directional_shadow_max_distance = maxf(p.shadow_dist, 10.0)
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS if p.shadow_dist > 100.0 \
			else DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS
	environment.glow_enabled = p.glow
	city.apply_quality(p)


## A street crossing near the middle of the city, used as the hero's start place.
func start_position() -> Vector3:
	return Vector3(layout.roads_x[4].x, 0.2, layout.roads_z[5].x)
