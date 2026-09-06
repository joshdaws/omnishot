# Known limitations

This is an early community release. The GitHub issue tracker records actionable follow-up work; [PARITY.md](PARITY.md) records implemented behavior and the current verification scope.

- **Compatibility:** tested on Omarchy 4.0.2 / Hyprland 0.56.2. The native extension requires matching installed headers and running compositor ABI. Older Hyprland configurations are unsupported.
- **Scrolling:** highly repetitive content, large jumps, animations, changing overlays, and lazy-loaded layout changes can interrupt alignment. Auto-Scroll stops rather than silently claiming completion. The image limit is 120 megapixels.
- **Image dragging:** the native verifier sends motion after entering Annotate. A drop immediately on first entry can use Qt's initial centered position; this edge case needs further work. Edge-specific image attachment also needs comparison with CleanShot 4.8.
- **Exact reference behavior:** multiple spotlight regions, arrow contours/curve gestures, crop reversion details, preview gesture timing, and some menu interactions still need comparison with a running reference app. Linux fonts are substitutes for macOS fonts.
- **Displays:** mixed-scale and negative-coordinate captures are tested. Physical hot-plug, display-layout changes during selection, HDR capture, and exhaustive GPU combinations are not verified. Capture buffers currently support 8-bit RGB/RGBA.
- **Recording:** physical microphones/cameras, long-duration audio/video synchronization, camera timeline segments, and live camera resizing need more work. Generated media and isolated audio loopback are tested.
- **Video editing:** zoom heuristics, easing, motion blur, ripple/reorder behavior, and exact undo grouping have not been shown to match the reference.
- **Other hardware/apps:** physical touchpad gestures, printers, broader OCR accuracy, and cross-application clipboard/drag behavior need community testing.
- **Packaging:** install from source into the user account. There is no AUR package or automatic uninstaller yet.

Cloud uploads, syncing, accounts, collaboration, and cloud transcription are intentionally out of scope. OmniShot uses its own source, assets, and editable project formats; it does not read or write proprietary CleanShot projects.
