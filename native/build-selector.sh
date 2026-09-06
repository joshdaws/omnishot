#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
selector_build=$(mktemp -d .selector-build-XXXXXX)
trap 'rm -rf -- "$selector_build"' EXIT
protocol_root=$(pkg-config --variable=pkgdatadir wayland-protocols)
protocols=("$protocol_root/stable/xdg-shell/xdg-shell.xml" "$protocol_root/staging/cursor-shape/cursor-shape-v1.xml" "$protocol_root/unstable/tablet/tablet-unstable-v2.xml" "$protocol_root/unstable/xdg-output/xdg-output-unstable-v1.xml" slurp/protocol/wlr-layer-shell-unstable-v1.xml)
for source in "${protocols[@]}"; do
    name=$(basename "$source" .xml)
    wayland-scanner client-header "$source" "$selector_build/$name-client-protocol.h"
    wayland-scanner private-code "$source" "$selector_build/$name-protocol.c"
done
cc -std=c11 -O2 -Wall -Wextra -Wno-unused-parameter -Islurp/include -I"$selector_build" slurp/main.c slurp/lock.c slurp/pool-buffer.c slurp/render.c slurp/box.c "$selector_build/"*-protocol.c $(pkg-config --cflags --libs cairo wayland-client wayland-cursor xkbcommon) -lrt -o "$selector_build/live-selector"
mv "$selector_build/live-selector" live-selector
