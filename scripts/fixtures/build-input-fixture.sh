#!/usr/bin/env bash
set -euo pipefail
task_source=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
task_output=${1:?Pass a scratch output directory}
mkdir -p -- "$task_output"
wayland-scanner client-header "$task_source/virtual-keyboard.xml" "$task_output/virtual-keyboard.h"
wayland-scanner private-code "$task_source/virtual-keyboard.xml" "$task_output/virtual-keyboard.c"
wayland-scanner client-header "$task_source/../../native/wlr-virtual-pointer-unstable-v1.xml" "$task_output/virtual-pointer.h"
wayland-scanner private-code "$task_source/../../native/wlr-virtual-pointer-unstable-v1.xml" "$task_output/virtual-pointer.c"
gcc -O2 -I"$task_output" "$task_source/input-fixture.c" "$task_output/virtual-keyboard.c" "$task_output/virtual-pointer.c" \
    -o "$task_output/input-fixture" $(pkg-config --cflags --libs wayland-client xkbcommon)
