#!/usr/bin/env bash
# Keep execution at the end so an incomplete download cannot start installation.
omnishot_install() (
  set -euo pipefail
  trap 'printf "OmniShot installation failed. Fix the error above, then retry. If the checkout was created, run bash install.sh from that folder.\n" >&2' ERR

  if (( EUID == 0 )); then
    printf 'Run this installer as your desktop user, without sudo.\n' >&2
    exit 1
  fi
  local task_root="${OMNISHOT_INSTALL_DIR:-$HOME/projects/omnishot}"
  local task_config="${XDG_CONFIG_HOME:-$HOME/.config}"
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
  if [[ -e "$task_root" || -L "$task_root" ]]; then
    printf 'Destination already exists: %s\nNothing was changed. For an existing OmniShot installation, follow the Update and remove section at https://github.com/joshdaws/omnishot#update-and-remove\n' "$task_root" >&2
    exit 1
  fi

  printf 'Installing missing system dependencies through Omarchy. You may be asked for your password.\n'
  omarchy pkg add git python python-pip gcc pkgconf wayland wayland-protocols \
    cairo libxkbcommon libglvnd lua54 grim slurp wl-clipboard ffmpeg \
    tesseract tesseract-data-eng tesseract-data-osd gpu-screen-recorder libpulse \
    desktop-file-utils shared-mime-info xdg-utils
  mkdir -p -- "$(dirname -- "$task_root")"
  GIT_TERMINAL_PROMPT=0 git clone --branch main --single-branch -- https://github.com/joshdaws/omnishot.git "$task_root"
  (cd -- "$task_root" && bash install.sh)
  printf '\nOmniShot installed in %s\nOpen it from the app launcher or run: ~/.local/bin/omnishot menu\n' "$task_root"
)

omnishot_install
