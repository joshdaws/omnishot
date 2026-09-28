#!/usr/bin/env bash
# Remove OmniShot: shortcuts, window rules, launcher, desktop integration, the
# built app files and the bar widget. Captures, projects and settings are kept.
set -euo pipefail
task_source=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
source "$task_source/scripts/runtime.sh"
task_plugin_id=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["id"])' "$task_source/manifest.json")

fail() {
  printf 'OmniShot uninstall: %s\n' "$*" >&2
  exit 1
}

if (( EUID == 0 )); then fail "run this as your desktop user, without sudo"; fi
if [[ -z ${OMNISHOT_ASSUME_YES:-} ]]; then
  [[ -t 0 ]] || fail "refusing to continue without confirmation; set OMNISHOT_ASSUME_YES=1"
  printf 'This removes OmniShot, its shortcuts and its bar widget.\nCaptures and settings in %s are kept.\n' "$omnishot_data/omnishot"
  read -r -p 'Remove OmniShot? [y/N] ' task_answer
  [[ $task_answer == [yY]* ]] || fail "cancelled"
fi

omnishot_stop || fail "OmniShot is still running. Finish or stop any recording, quit OmniShot, then retry."
python3 "$task_source/scripts/uninstall_user.py"
if command -v hyprctl >/dev/null 2>&1 && hyprctl -j version >/dev/null 2>&1; then hyprctl reload >/dev/null; fi

# Only delete app files that setup created; never a git (development) checkout.
if [[ -f $omnishot_stamp && ! -d $omnishot_runtime/.git ]]; then
  rm -rf -- "$omnishot_runtime"
  printf 'Removed %s\n' "$omnishot_runtime"
fi

task_plugin="$omnishot_config/omarchy/plugins/$task_plugin_id"
if [[ -d $task_plugin/.git ]]; then
  # Last: this may delete the folder holding this script (bash keeps it open).
  omarchy plugin remove "$task_plugin_id" --yes
fi
printf 'OmniShot has been removed. Captures and settings remain in %s\n' "$omnishot_data/omnishot"
