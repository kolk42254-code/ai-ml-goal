#!/usr/bin/env bash
# Runs a scene of the game on a computer without a screen or graphics card
# (software rendering inside a virtual screen). Used to take test pictures.
#
#   tools/render.sh vk res://tools/shots.tscn      Vulkan "Mobile" renderer (what phones use)
#   tools/render.sh gl res://tools/shots.tscn      OpenGL "Compatibility" renderer
#
# Extra words after the scene are passed to the game after "--".
set -euo pipefail
cd "$(dirname "$0")/.."
mode="$1"; scene="$2"; shift 2
size="${RENDER_SIZE:-1280x720}"
if [ "$mode" = "vk" ]; then
  export VK_ICD_FILENAMES="${VK_ICD_FILENAMES:-/usr/share/vulkan/icd.d/lvp_icd.json}"
  driver=(--rendering-driver vulkan --rendering-method mobile)
else
  driver=(--rendering-driver opengl3 --rendering-method gl_compatibility)
fi
# GODOT_ARGS can add engine options, for example GODOT_ARGS="--fixed-fps 15".
exec xvfb-run -a -s "-screen 0 ${size}x24" "${GODOT:-godot}" --path . --audio-driver Dummy \
  "${driver[@]}" --resolution "$size" ${GODOT_ARGS:-} "$scene" -- "$@"
