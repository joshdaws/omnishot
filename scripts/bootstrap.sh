#!/usr/bin/env bash
# One-line installer: add OmniShot as an Omarchy plugin, then build it.
# Equivalent to `omarchy plugin add <repo> --enable` followed by the widget's
# "Finish setup". Keep execution at the end so an incomplete download cannot
# start installation.
omnishot_install() (
  set -euo pipefail
  trap 'printf "OmniShot installation failed. Fix the error above, then retry.\n" >&2' ERR

  if (( EUID == 0 )); then
    printf 'Run this installer as your desktop user, without sudo.\n' >&2
    exit 1
  fi
  local task_config="${XDG_CONFIG_HOME:-$HOME/.config}"
  local task_repository="${OMNISHOT_REPOSITORY:-https://github.com/joshdaws/omnishot.git}"
  local task_id="io.github.joshdaws.omnishot"
  local task_plugin="$task_config/omarchy/plugins/$task_id"
  for task_command in omarchy omarchy-shell hyprctl; do
    if ! command -v "$task_command" >/dev/null 2>&1; then
      printf 'OmniShot requires a supported Omarchy desktop (missing %s).\n' "$task_command" >&2
      exit 1
    fi
  done
  if [[ ! -f "$task_config/hypr/hyprland.lua" || ! -f "$task_config/hypr/bindings.lua" || ! -f "$task_config/omarchy/shell.json" ]]; then
    printf 'This release requires Omarchy with Lua Hyprland configuration and the shell plugin API.\n' >&2
    exit 1
  fi
  if [[ -z "${WAYLAND_DISPLAY:-}" || -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] || ! hyprctl -j version >/dev/null 2>&1; then
    printf 'Run this installer in a terminal inside your running Omarchy desktop session.\n' >&2
    exit 1
  fi
  if [[ -e "$task_plugin" || -L "$task_plugin" ]] && [[ ! -d "$task_plugin/.git" ]]; then
    printf 'A manually installed OmniShot widget exists at %s\nNothing was changed. Remove that folder, then retry.\n' "$task_plugin" >&2
    exit 1
  fi

  if [[ ! -d "$task_plugin/.git" ]]; then
    command -v git >/dev/null 2>&1 || omarchy pkg add git
    omarchy plugin add "$task_repository" --enable --yes
  else
    printf 'OmniShot is already added as a plugin; rebuilding it.\n'
  fi
  bash "$task_plugin/scripts/setup.sh"
)

omnishot_install
