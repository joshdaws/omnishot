# OmniShot for Omarchy

Screen capture, scrolling screenshots, annotation, and screen recording for Omarchy. OmniShot follows your active Omarchy theme automatically and keeps captures on your machine.

**Early community release — v0.2.0.** Inspired by the CleanShot X workflow, with broad local functionality implemented. Exact feature and UI/UX parity is still being worked on. This is an independent project, with no affiliation with CleanShot.

[User guide](docs/USAGE.md) · [Known limitations](docs/KNOWN_LIMITATIONS.md) · [Roadmap](https://github.com/joshdaws/omnishot/issues/13) · [Issues](https://github.com/joshdaws/omnishot/issues) · [Contributing](CONTRIBUTING.md)

[Watch the 45-second launch video](https://github.com/joshdaws/omnishot/releases/download/v0.2.0/omnishot-launch.mp4) · [Download the community preview](https://github.com/joshdaws/omnishot/releases/tag/v0.2.0)

## What it does

- Area, window, display, full-desktop, timed, and previous-area screenshots.
- Vertical and horizontal scrolling capture, manually or with Auto-Scroll.
- Corner previews with copy, save, annotate, drag, pin, and history actions.
- Arrows, text, shapes, counters, pencil, smart highlighter, blur, pixelation, and spotlight.
- Crop, resize, rotate, combine images, and add backgrounds. Save editable `.omnishot` projects.
- Local OCR and QR recognition; PNG, JPEG, WebP, and HEIC image exports.
- H.264/GIF recording, pause/resume, audio, camera overlays, and an editable video timeline with cuts and zooms.
- An Omarchy bar widget, configurable shortcuts, and a local CLI/URL API.

No accounts, telemetry, uploads, or cloud syncing. The interface follows Omarchy's palette; there is no separate light/dark switch.

## Compatibility

Developed and tested on **Omarchy 4.0.2 with Hyprland 0.56.2**, including fractional scale 1.6 and mixed-scale displays. This release requires Omarchy's Lua-based Hyprland configuration and shell plugin API. Other Hyprland versions and distributions are not currently supported.

A native capture extension is built against the installed Hyprland headers and checks the running compositor ABI before loading. After upgrading Hyprland, restart your desktop session and rebuild OmniShot. GPU recording requires a working `gpu-screen-recorder` setup. Physical camera/microphone coverage and HDR capture are still open work.

## Install

OmniShot is a **desktop application with a companion Omarchy shell bar widget**. Install the application from this checkout using `install.sh`; it also installs and enables the widget. `omarchy plugin add` only installs standalone shell plugin repositories and does not build this application's Python environment or native capture helpers.

Run these commands as your normal desktop user in a terminal inside an unlocked, supported Omarchy session. `omarchy pkg add` handles elevation for system packages; run `bash install.sh` **without sudo**.

```sh
# Install missing build and runtime dependencies.
omarchy pkg add git python python-pip gcc pkgconf wayland wayland-protocols \
  cairo libxkbcommon libglvnd lua54 grim slurp wl-clipboard ffmpeg \
  tesseract tesseract-data-eng tesseract-data-osd gpu-screen-recorder libpulse \
  desktop-file-utils shared-mime-info xdg-utils

mkdir -p ~/projects
git clone https://github.com/joshdaws/omnishot.git ~/projects/omnishot
cd ~/projects/omnishot
bash install.sh
omnishot menu
```

Omarchy supplies `omarchy-shell`, Hyprland, and its headers (in the `hyprland` package); their versions must match the running desktop. Use `omarchy version` and `hyprctl version` to check against the compatibility section above. Do not install a different compositor just to satisfy the build. Additional OCR languages require the corresponding `tesseract-data-*` packages. Python dependencies are installed into a local `.venv`; `pip install` alone is not a complete installation.

Keep the checkout and its `.venv` at this location: the launcher uses them directly. To relocate it later, finish your captures, quit OmniShot, clone it at the new location, and run the installer there to create a fresh `.venv` and repoint the launcher.

The installer adds user-owned launchers, file associations, a bar widget, and Hyprland bindings/rules. It backs up existing files under `backups/<timestamp>/` and does not edit `/usr/share/omarchy/`. It replaces the default Print, Alt+Print, and Super+Ctrl+Print actions; other capture bindings are listed below. Existing image/video default applications are preserved.

The launcher is `~/.local/bin/omnishot`. The companion widget lives in `$XDG_CONFIG_HOME/omarchy/plugins/local.omnishot` (normally `~/.config/omarchy/plugins/local.omnishot`); desktop and MIME entries use `$XDG_DATA_HOME` (normally `~/.local/share`). Capture history is separate from the checkout. The widget uses Omarchy's shell API, and the application reads the active Omarchy theme automatically.

The installer validates the plugin manifest, builds the native helpers, reloads Hyprland and checks for configuration errors. Verify the widget with `omarchy plugin list` and try **Ctrl+Print** followed by clicking the capture preview. If you change widget placement later, reinstalling preserves it. Changed widget code may restart the shell; layout-only changes hot-reload.

## Capture → annotate

1. Press **Super+Shift+Print** and select the scrolling content.
2. Click **Start Capture**. Scroll manually or choose **Auto-Scroll**.
3. Click **Done**, then click the corner preview to annotate.
4. Draw, crop, or conceal information, then copy/save/drag the result.

If alignment fails, scroll back slightly or slow down. Captures are limited to 120 megapixels. Save a `.omnishot` project to keep editing later. Projects contain the source image; share a flattened PNG/JPEG/WebP when concealing information.

![A scrolling capture open in Annotate with the Omarchy theme](docs/screenshots/annotation.png)

| Shortcut | Action |
|---|---|
| Print | Capture menu |
| Ctrl+Print | Area capture |
| Shift+Print | Focused display |
| Super+Shift+Print | Scrolling capture |
| Alt+Print | Screen recording |
| Super+Ctrl+Print | Capture text |

Super+Print retains Omarchy's color picker. Change shortcuts in Settings. See the [user guide](docs/USAGE.md) for horizontal capture, editor gestures, recording, history, and CLI commands.

## Update and remove

To update, finish any capture/recording and save/close editable windows, then:

```sh
omnishot quit
cd ~/projects/omnishot
git pull --ff-only
bash install.sh
omnishot menu
```

Use your actual checkout path if different. After a Hyprland upgrade, restart your desktop session before rebuilding so the running compositor and installed headers match. `omarchy plugin update` does not update OmniShot: the widget is installed by the application's installer. Your history and settings live in `$XDG_DATA_HOME/omnishot` (normally `~/.local/share/omnishot`) and are separate from the checkout.

Removal is currently manual; see [the removal guide](docs/REMOVE.md). Do not delete your history folder unless you also intend to delete your captures and editable projects.

## Development status

The latest local suite passes **438 automated tests**. Native Wayland checks cover scrolling → preview → annotation → project reopening, cross-display captures, control exclusion, and image/file dragging. Headed Chromium tests captured 60 vertical rows and 30 horizontal columns at 1.6× with fixed edges intact.

These checks do not establish exact CleanShot parity or exhaustive hardware compatibility. See the [feature ledger](docs/PARITY.md) and [known limitations](docs/KNOWN_LIMITATIONS.md). GitHub issues are the working backlog; reproducible bugs, device reports, and focused pull requests are welcome.

## License

MIT, with bundled third-party notices retained. Nunito is licensed under SIL OFL 1.1; vendored slurp and Wayland protocols retain their own notices. See [LICENSE](LICENSE) and [THIRD_PARTY.md](THIRD_PARTY.md).
