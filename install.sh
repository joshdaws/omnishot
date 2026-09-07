#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
task_root="$PWD"
task_venv="${OMNISHOT_VENV:-$task_root/.venv}"
if (( EUID == 0 )); then
  printf 'Run bash install.sh as your desktop user, without sudo. Use omarchy pkg add for system dependencies.\n' >&2
  exit 1
fi
# Fail before changing user configuration when prerequisites are missing.
task_missing=()
for task_command in python gcc c++ pkg-config wayland-scanner hyprctl omarchy omarchy-shell grim slurp wl-copy ffmpeg ffprobe tesseract gpu-screen-recorder parec update-desktop-database update-mime-database xdg-mime; do
  command -v "$task_command" >/dev/null 2>&1 || task_missing+=("$task_command")
done
if (( ${#task_missing[@]} )); then
  printf 'Missing dependencies: %s\nSee README.md for installation instructions.\n' "${task_missing[*]}" >&2
  exit 1
fi
pkg-config --exists hyprland lua5.4 wayland-client wayland-cursor wayland-protocols cairo xkbcommon glesv2 egl || {
  printf 'Missing development headers. See README.md; Hyprland headers must match the running compositor.\n' >&2
  exit 1
}
task_config="${XDG_CONFIG_HOME:-$HOME/.config}"
if [[ ! -f "$task_config/hypr/hyprland.lua" || ! -f "$task_config/hypr/bindings.lua" || ! -f "$task_config/omarchy/shell.json" ]]; then
  printf 'This release requires Omarchy with Lua Hyprland configuration and the shell plugin API.\n' >&2
  exit 1
fi
if [[ -z "${WAYLAND_DISPLAY:-}" || -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] || ! hyprctl -j version >/dev/null 2>&1; then
  printf 'Run the installer inside your running Omarchy desktop session.\n' >&2
  exit 1
fi
omarchy plugin validate "$task_root/plugin"
"$(command -v python)" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11 or newer is required")'
if [[ ! -x "$task_venv/bin/python" ]]; then python -m venv "$task_venv"; fi
"$task_venv/bin/pip" install -e "$task_root"
wayland-scanner client-header native/wlr-virtual-pointer-unstable-v1.xml native/virtual-pointer.h
wayland-scanner private-code native/wlr-virtual-pointer-unstable-v1.xml native/virtual-pointer.c
gcc -Wall -Wextra -O2 native/scroll-helper.c native/virtual-pointer.c -o native/scroll-helper $(pkg-config --cflags --libs wayland-client)
wayland-scanner client-header native/hyprland-toplevel-export-v1.xml native/toplevel-export.h
wayland-scanner private-code native/hyprland-toplevel-export-v1.xml native/toplevel-export.c
wayland-scanner client-header native/wlr-foreign-toplevel-management-unstable-v1.xml native/foreign-toplevel.h
wayland-scanner private-code native/wlr-foreign-toplevel-management-unstable-v1.xml native/foreign-toplevel.c
gcc -Wall -Wextra -O2 native/window-helper.c native/toplevel-export.c native/foreign-toplevel.c -o native/window-helper $(pkg-config --cflags --libs wayland-client)
bash native/build-clean.sh
bash native/build-selector.sh
OMNISHOT_SOURCE="$task_root" OMNISHOT_PYTHON="$task_venv/bin/python" "$task_venv/bin/python" scripts/install_user.py
hyprctl reload
task_config_errors="$(hyprctl configerrors)"
if [[ -n "${task_config_errors//[[:space:]]/}" ]]; then
  printf 'Hyprland reported configuration errors after installation:\n%s\nReview your config and the backup path printed above.\n' "$task_config_errors" >&2
  exit 1
fi
printf 'Hyprland configuration is valid. Launch OmniShot with: omnishot menu\n'
