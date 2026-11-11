#!/usr/bin/env bash
# Builds the Android app file (APK) you can install on a phone.
#
#   tools/build_apk.sh            ->  build/BattleWorld-<version>-debug.apk
#
# What it needs on the computer:
#   - Godot 4.7.2 (set GODOT=/path/to/godot if it is not called "godot")
#   - Godot's Android export templates for the same version
#   - The Android SDK and Java, with their folders set in Godot:
#       Editor -> Editor Settings -> Export -> Android
#
# The APK is signed with the test key in android/debug.keystore. Using the same
# key every time lets a new build install over the old one without uninstalling.
# This key is only for test builds: a Play Store release needs your own secret key.
set -euo pipefail
cd "$(dirname "$0")/.."
G="${GODOT:-godot}"
export GODOT_ANDROID_KEYSTORE_DEBUG_PATH="$PWD/android/debug.keystore"
export GODOT_ANDROID_KEYSTORE_DEBUG_USER="androiddebugkey"
export GODOT_ANDROID_KEYSTORE_DEBUG_PASSWORD="android"
version=$(grep -oE 'version/name="[^"]+"' export_presets.cfg | head -1 | cut -d'"' -f2)
out="build/BattleWorld-${version}-debug.apk"
mkdir -p build
echo "Importing assets ..."
"$G" --headless --path . --import >/dev/null 2>&1 || true
echo "Exporting $out ..."
"$G" --headless --path . --export-debug "Android" "$out"
ls -la "$out"
