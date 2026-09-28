# Shared by setup.sh and uninstall.sh. Source it; it defines paths and helpers.
omnishot_data="${XDG_DATA_HOME:-$HOME/.local/share}"
omnishot_config="${XDG_CONFIG_HOME:-$HOME/.config}"
# Built app files (venv, native helpers). Kept outside the plugin checkout:
# the Omarchy plugin validator rejects the symlinks a build creates.
omnishot_runtime="${OMNISHOT_INSTALL_DIR:-$omnishot_data/omnishot-app}"
# Records the plugin commit the runtime was built from; the widget compares it.
omnishot_stamp="$omnishot_runtime/.omnishot-source"
omnishot_launcher="$HOME/.local/bin/omnishot"

omnishot_running() {
  pgrep -u "$(id -u)" -f -- '-m omnishot\.app( |$)' >/dev/null 2>&1
}

# Quit a running OmniShot and wait for it, so files are not replaced under it.
# Returns 1 if it is still running (for example, finishing a recording).
omnishot_stop() {
  omnishot_running || return 0
  [[ -x $omnishot_launcher ]] && "$omnishot_launcher" quit >/dev/null 2>&1 || true
  local attempt
  for (( attempt = 0; attempt < ${OMNISHOT_QUIT_WAIT:-15} * 4; attempt++ )); do
    omnishot_running || return 0
    sleep 0.25
  done
  return 1
}

omnishot_require_session() {
  if (( EUID == 0 )); then
    printf 'Run this as your desktop user, without sudo.\n' >&2
    return 1
  fi
  if [[ ! -f "$omnishot_config/hypr/hyprland.lua" || ! -f "$omnishot_config/hypr/bindings.lua" || ! -f "$omnishot_config/omarchy/shell.json" ]]; then
    printf 'OmniShot requires Omarchy with Lua Hyprland configuration and the shell plugin API.\n' >&2
    return 1
  fi
  if [[ -z "${WAYLAND_DISPLAY:-}" || -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] || ! hyprctl -j version >/dev/null 2>&1; then
    printf 'Run this in a terminal inside your running Omarchy desktop session.\n' >&2
    return 1
  fi
}
