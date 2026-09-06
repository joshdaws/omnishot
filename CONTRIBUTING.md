# Contributing

Start with an open GitHub issue. Keep changes focused on one reproducible problem or documented interaction. For reference-parity work, link to a public reference or describe observations from a legally obtained running copy; distinguish observed behavior from assumptions.

## Test locally

```sh
python -m venv .venv
.venv/bin/pip install -e . pytest
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

FFmpeg and Qt's platform dependencies must be installed. Offscreen tests exercise image pixels, editable projects, geometry, settings, and media composition. Tests that mock compositor calls use temporary placeholder files; they do not load native capture code.

Build native components with `bash install.sh` in a supported Omarchy session. This also installs user configuration, so review the installer first. `native/build-clean.sh` and `native/build-selector.sh` can rebuild those components without installing user configuration.

Scripts under `scripts/verify_*.py` are development integration probes, not a single portable test runner. Many require a private compositor, generated media, or a Wayland input fixture supplied as arguments. They may move the pointer, show windows, and change isolated test configuration. Read the script before running it; do not run competing native verifiers simultaneously. Consolidating this harness is tracked in the issue backlog.

## Report a bug

Include OmniShot commit/version, Omarchy and Hyprland versions, GPU, display scale/layout, steps to reproduce, expected/actual behavior, and whether the issue affects a screenshot, editable project, or exported video. Use generated or non-sensitive sample content when possible. Do not attach your entire capture history or private recordings.

## Pull requests

Explain the user-visible problem and resulting behavior. Run relevant tests, add a regression for data loss or incorrect rendering, and show native evidence for UI/Wayland changes where practical. Preserve source images, editable projects, unrelated shortcuts, and the active Omarchy theme. Do not add cloud services or copy proprietary source/assets.
