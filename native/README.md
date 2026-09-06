# Native capture components

`scroll-helper` drives Wayland scrolling and `window-helper` captures an
individual Hyprland surface with alpha. Their protocol definitions retain the
upstream notices.

`clipboard-helper` owns PNG and file clipboard representations through Wayland
data-control. It forks only after the compositor acknowledges the selection,
serves immutable PNG bytes, and exits when replaced or the compositor disconnects.
Transfers use a bounded wait for stalled consumers. File URIs point to separate
snapshots retained by the application, including GNOME/KDE file-copy metadata.
`scripts/verify_clipboard_modes.py` exercises all three clipboard modes with
independent consumers and checks survival after history deletion.

`build-clean.sh` builds the recording libraries and a drag compatibility library:

- `clean-mirror.so` is a Hyprland extension. It checks the running compositor's
  exact ABI hash before installing render hooks. A Lua registration function
  accepts the recording application's PID and holds a Linux pidfd. Only that
  application's Recording Controls, Camera Preview and Recording Dim surfaces are omitted.
  A second live recording owner is rejected; an exited owner deactivates the
  hooks automatically. Passing 0 releases the registration normally.
  Independent selection and cursor-only registrations share the mirror without
  ending an active recording. Scrolling holds the cursor registration across
  frames so software pointers never repeat down the stitched image.
- `clean-capture.so` is a gpu-screen-recorder draw plugin. It requests the
  selected output or output-relative region using Wayland screencopy, then
  replaces GSR's frame with that clean image. GSR retains encoding, audio and
  pause/resume. Initial capture failure aborts startup; later source failure
  draws black and stops the recorder. Output removal also stops capture.
- `drag-status.so` is preloaded into the installed OmniShot launcher only. It
  observes the final Wayland `dnd_finished` event around OmniShot's file drags.
  Hyprland 0.56.2 can omit the source action event, causing Qt to return Ignore
  despite a completed transfer. This library observes completion without
  changing protocol events, the compositor, or the receiving app. Cancelled
  drags keep their previews. The preload environment is restored before starting
  child applications. Run through the installed launcher for this compatibility.

Hyprland's `no_screen_share` rule replaces windows with black rectangles. This
extension instead creates a mirror framebuffer while recording, keeps the
content behind controls rendering, and suppresses those control surfaces only
on the mirror's color attachment. Software cursor rendering is separated so
the screencopy request controls cursor inclusion. The ordinary display keeps
showing the controls. Their user-owned rules disable compositor blur, shadow,
border and rounding; the application paints its own appearance.

The extension is loaded on demand, never added to compositor startup config.
When inactive it delegates to the original rendering behavior. Builds replace
library files atomically rather than overwriting a mapped library. The mirror
extension uses a content-based path and `-fno-gnu-unique` so glibc cannot silently
reuse an older build after an update. The application unloads the extension after
recording if it loaded it; an extension that was already loaded is left in place. Rebuild after
Hyprland upgrades; the running compositor and installed headers must match.

Current capture buffers support 8-bit RGBA/BGRA and transfer through shared
memory. HDR formats need additional work. Clean regions spanning multiple outputs are
composed at logical coordinates, including black gaps between displays. Native
checks cover mixed scale, negative coordinates and control exclusion.

Verification: `scripts/verify_clean_recording.py` covers native fullscreen
capture at the desktop's scale, visible controls, a generated camera preview,
pause/resume, first-frame readiness and cleanup. Isolated-compositor experiments
also exercised moving controls over changing content, cursor on/off, regions,
hook unload and GSR H.264 encoding. No physical camera or microphone is needed.

`scripts/verify_overlay_workflows.py` exercises file dragging to a separate Qt
process using complete Wayland pointer events, including cancellation and Alt.
Its receiver verifies that the file contains the current annotated image.

`build-selector.sh` builds `live-selector`, a private MIT-licensed slurp 1.5.0
variant. It reports capture-time Shift/Ctrl along with the selected region,
including when the keys are released before capture processing finishes. It
uses the selection's existing Wayland keyboard focus and does not register
global key listeners. The system slurp binary is unchanged. The vendored source,
upstream revision and modifications are documented in `slurp/README.md`. Build
dependencies are a C compiler, pkg-config, Cairo, Wayland client/cursor and
protocols, libxkbcommon and wayland-scanner.
