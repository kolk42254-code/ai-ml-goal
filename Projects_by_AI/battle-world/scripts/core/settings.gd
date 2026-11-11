extends Node
## Autoload "Settings": the player's saved choices (graphics level, look speed ...)
## and the code that applies them. Other scripts listen to `changed`.

signal changed

enum Quality { LOW, MEDIUM, HIGH }

const PATH := "user://settings.cfg"

## What each graphics level turns on. The world script reads the values it needs.
##   scale        how much of the screen resolution the 3D picture uses (lower = faster)
##   msaa         edge smoothing: 0 = off, 1 = 2x, 2 = 4x
##   shadow_size  sun shadow picture size in pixels (0 = no sun shadows)
##   shadow_dist  how far from the camera sun shadows are drawn (metres)
##   rooms        1 = draw fake rooms behind windows, 0 = flat windows
##   props        how many small street objects are kept (0..1)
##   view_dist    how far the camera can see (metres)
const PRESETS := {
	Quality.LOW: {
		"name": "Low", "scale": 0.6, "msaa": 0, "fxaa": false, "shadow_size": 0,
		"shadow_dist": 0.0, "glow": false, "rooms": 0.0, "props": 0.45, "view_dist": 420.0,
	},
	Quality.MEDIUM: {
		"name": "Medium", "scale": 0.8, "msaa": 0, "fxaa": true, "shadow_size": 2048,
		"shadow_dist": 70.0, "glow": true, "rooms": 1.0, "props": 0.8, "view_dist": 650.0,
	},
	Quality.HIGH: {
		"name": "High", "scale": 1.0, "msaa": 1, "fxaa": true, "shadow_size": 4096,
		"shadow_dist": 130.0, "glow": true, "rooms": 1.0, "props": 1.0, "view_dist": 900.0,
	},
}

var quality: int = Quality.MEDIUM
var look_sensitivity := 1.0        # 0.3 .. 2.5
var invert_y := false
var show_fps := true                 # on for now, so test builds show how fast the phone runs the game
var fps_cap := 60                  # 30 saves battery, 60 is smooth, 0 = no limit


func _ready() -> void:
	load_settings()
	apply()


func preset() -> Dictionary:
	return PRESETS[quality]


func set_quality(value: int) -> void:
	quality = clampi(value, Quality.LOW, Quality.HIGH)
	apply()
	save_settings()


## Pushes the current settings into the engine and tells everyone they changed.
func apply() -> void:
	var p := preset()
	var vp := get_viewport()
	vp.scaling_3d_scale = p.scale
	vp.msaa_3d = p.msaa as Viewport.MSAA
	# The simple OpenGL renderer has no FXAA, so only ask for it on the Vulkan renderers.
	if RenderingServer.get_current_rendering_method() != "gl_compatibility":
		vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_FXAA if p.fxaa else Viewport.SCREEN_SPACE_AA_DISABLED
	if p.shadow_size > 0:
		RenderingServer.directional_shadow_atlas_set_size(p.shadow_size, true)
	Engine.max_fps = fps_cap
	changed.emit()


func load_settings() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(PATH) != OK:
		return
	quality = clampi(int(cfg.get_value("graphics", "quality", quality)), Quality.LOW, Quality.HIGH)
	fps_cap = int(cfg.get_value("graphics", "fps_cap", fps_cap))
	show_fps = bool(cfg.get_value("graphics", "show_fps", show_fps))
	look_sensitivity = clampf(float(cfg.get_value("controls", "look_sensitivity", look_sensitivity)), 0.3, 2.5)
	invert_y = bool(cfg.get_value("controls", "invert_y", invert_y))


func save_settings() -> void:
	var cfg := ConfigFile.new()
	cfg.set_value("graphics", "quality", quality)
	cfg.set_value("graphics", "fps_cap", fps_cap)
	cfg.set_value("graphics", "show_fps", show_fps)
	cfg.set_value("controls", "look_sensitivity", look_sensitivity)
	cfg.set_value("controls", "invert_y", invert_y)
	cfg.save(PATH)
