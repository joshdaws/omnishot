# Remove OmniShot

Finish recording and close editable windows first. Quit from the tray menu or run `omnishot quit`.

1. Remove `local.omnishot` from the bar layout in `~/.config/omarchy/shell.json`.
2. Remove the OmniShot managed bindings from `~/.config/hypr/bindings.lua`. Restore any replaced Print bindings from your installation backup, keeping later unrelated edits.
3. Remove `require("hypr.omnishot")` and its comment from `~/.config/hypr/hyprland.lua`, then remove `~/.config/hypr/omnishot.lua`.
4. Remove `~/.config/omarchy/plugins/local.omnishot`, `~/.local/bin/omnishot`, `~/.local/share/applications/org.omarchy.OmniShot.desktop`, and `~/.local/share/mime/packages/omnishot.xml`.
5. Remove OmniShot entries for its project types and URL scheme from `~/.config/mimeapps.list`, or restore the corresponding entries from your backup. Refresh the desktop and MIME databases with `update-desktop-database ~/.local/share/applications` and `update-mime-database ~/.local/share/mime`.
6. Run `hyprctl reload` and `hyprctl configerrors`; resolve any reported configuration errors. The bar configuration reloads automatically.

Paths above use the default XDG directories; use your configured directories if different. Backups are in the source checkout's `backups/<timestamp>/`. Review differences before restoring a whole file so later customizations are retained.

You can then remove the installed checkout at `~/.local/share/omnishot-app` and its `.venv` (or your custom installation path). Earlier installations may use `~/projects/omnishot`; keep that directory if you still use it for development. Captures, projects, settings, and history remain in `~/.local/share/omnishot`; exported images normally remain in `~/Pictures/OmniShot`.
