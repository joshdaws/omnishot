#!/usr/bin/env bash
# Build and install OmniShot from its Omarchy plugin checkout
# (~/.config/omarchy/plugins/io.github.joshdaws.omnishot). The bar widget runs
# this for first-time setup and after `omarchy plugin update`; rerunning it is safe.
set -euo pipefail
task_source=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
source "$task_source/scripts/runtime.sh"

fail() {
  printf 'OmniShot setup: %s\n' "$*" >&2
  exit 1
}

omnishot_require_session || exit 1
[[ -d $task_source/.git ]] ||
  fail "run this from the Omarchy plugin checkout. For a development checkout, use: bash install.sh"
task_commit=$(git -C "$task_source" rev-parse HEAD) || fail "could not read the plugin revision"

# Check the app folder before changing anything.
task_legacy=0
if [[ -e $omnishot_runtime || -L $omnishot_runtime ]] && [[ ! -f $omnishot_stamp ]]; then
  if [[ -d $omnishot_runtime/.git ]]; then
    task_legacy=1
  elif [[ -L $omnishot_runtime || ! -d $omnishot_runtime || -n $(find "$omnishot_runtime" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null) ]]; then
    fail "$omnishot_runtime exists and was not created by OmniShot setup. Move it aside, then retry."
  fi
fi

if [[ -z ${OMNISHOT_SKIP_PACKAGES:-} ]]; then
  printf 'Installing missing system dependencies through Omarchy. You may be asked for your password.\n'
  omarchy pkg add git rsync python python-pip gcc pkgconf wayland wayland-protocols \
    cairo libxkbcommon libglvnd lua54 grim slurp wl-clipboard ffmpeg \
    tesseract tesseract-data-eng tesseract-data-osd gpu-screen-recorder libpulse \
    desktop-file-utils shared-mime-info xdg-utils libnotify
fi

task_was_running=0
if omnishot_running; then
  task_was_running=1
  printf 'Quitting OmniShot so it can be updated.\n'
  omnishot_stop || fail "OmniShot is still running. Finish or stop any recording, quit OmniShot, then retry."
fi

if (( task_legacy )); then
  # An install from before plugin support: keep it, including its config
  # backups, but move it out of the way. Captures live elsewhere.
  task_previous="$omnishot_runtime.pre-plugin-$(date +%Y%m%d-%H%M%S)"
  mv -- "$omnishot_runtime" "$task_previous"
  printf 'Moved the previous OmniShot checkout to %s\nDelete it once you are happy with this installation.\n' "$task_previous"
fi

task_previous_build=""
[[ -f $omnishot_stamp ]] && task_previous_build=$(<"$omnishot_stamp")

mkdir -p -- "$omnishot_runtime"
# Remove the stamp first so an interrupted setup reads as unfinished.
rm -f -- "$omnishot_stamp"
# .gitignore protects build outputs, the venv and config backups from --delete.
rsync -a --delete --exclude=/.git --filter=':- .gitignore' -- "$task_source/" "$omnishot_runtime/"
(cd -- "$omnishot_runtime" && bash install.sh)
printf '%s\n' "$task_commit" >"$omnishot_stamp"

# The shell hot-reloads a changed plugin but can keep serving the previous
# widget component from its cache, so restart it when the widget changed
# since the last build. An unknown previous commit counts as changed.
if [[ -n $task_previous_build && $task_previous_build != "$task_commit" ]] &&
  ! git -C "$task_source" diff --quiet "$task_previous_build" "$task_commit" -- manifest.json plugin 2>/dev/null; then
  printf 'Restarting the Omarchy shell to load the updated bar widget.\n'
  omarchy restart shell || true
fi

if (( task_was_running )); then
  setsid -f "$omnishot_launcher" >/dev/null 2>&1 </dev/null || true
fi
printf '\nOmniShot is ready. Use the bar icon, press Print, or run: omnishot menu\n'
