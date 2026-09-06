#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
# Replace, never overwrite, libraries that may be mapped by a running process.
task_build=$(mktemp -d .clean-build-XXXXXX)
trap 'rm -rf -- "$task_build"' EXIT
wayland-scanner client-header wlr-screencopy-unstable-v1.xml "$task_build/screencopy.h"
wayland-scanner private-code wlr-screencopy-unstable-v1.xml "$task_build/screencopy.c"
gcc -std=c11 -fPIC -shared -O2 -I"$task_build" clean-capture.c "$task_build/screencopy.c" \
    $(pkg-config --cflags --libs glesv2 egl wayland-client) -o "$task_build/clean-capture.so"
c++ -std=c++23 -fPIC -shared -fno-gnu-unique -O2 $(pkg-config --cflags hyprland lua5.4) \
    clean-mirror.cpp -o "$task_build/clean-mirror.so"
gcc -std=c11 -fPIC -shared -O2 drag-status.c $(pkg-config --cflags --libs wayland-client) -ldl -o "$task_build/drag-status.so"
gcc -std=c11 -fPIC -shared -O2 -Wall -Wextra -pthread recording-guard.c -o "$task_build/recording-guard.so"
wayland-scanner client-header wlr-data-control-unstable-v1.xml "$task_build/data-control.h"
wayland-scanner private-code wlr-data-control-unstable-v1.xml "$task_build/data-control.c"
gcc -std=c11 -O2 -Wall -Wextra -I"$task_build" clipboard-helper.c "$task_build/data-control.c" $(pkg-config --cflags --libs wayland-client) -o "$task_build/clipboard-helper"
mv -- "$task_build/clean-capture.so" clean-capture.so
# glibc can retain DSOs with GNU unique symbols after dlclose. A content-based
# path avoids loading a stale, already-mapped build during an in-session update.
mkdir -p .clean-mirrors
task_digest=$(sha256sum "$task_build/clean-mirror.so" | cut -d ' ' -f 1)
mv -- "$task_build/clean-mirror.so" ".clean-mirrors/$task_digest.so"
ln -s ".clean-mirrors/$task_digest.so" "$task_build/mirror-link"
mv -Tf -- "$task_build/mirror-link" clean-mirror.so
mv -- "$task_build/drag-status.so" drag-status.so
mv -- "$task_build/recording-guard.so" recording-guard.so
mv -- "$task_build/clipboard-helper" clipboard-helper
