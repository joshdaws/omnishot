# Remove OmniShot

The quickest way is **Uninstall OmniShot** in the bar icon's menu, or `bash scripts/uninstall.sh` from the plugin folder (`~/.config/omarchy/plugins/io.github.joshdaws.omnishot`) or a manual checkout. It performs the steps below and backs up each configuration file it edits under `~/.local/share/omnishot/config-backups/`. To remove OmniShot by hand instead:

Finish recording and close editable windows first. Quit from the tray menu or run `omnishot quit`.

1. Remove `io.github.joshdaws.omnishot` (or `local.omnishot` on installs from before plugin support) from the bar layout in `~/.config/omarchy/shell.json`.
2. Remove the OmniShot managed bindings from `~/.config/hypr/bindings.lua`. Restore any replaced Print bindings from your installation backup, keeping later unrelated edits.
3. Remove `require("hypr.omnishot")` and its comment from `~/.config/hypr/hyprland.lua`, then remove `~/.config/hypr/omnishot.lua`.
4. Remove the plugin with `omarchy plugin remove io.github.joshdaws.omnishot` (for a manual install, delete `~/.config/omarchy/plugins/io.github.joshdaws.omnishot` or `~/.config/omarchy/plugins/local.omnishot`), then remove `~/.local/bin/omnishot`, `~/.local/share/applications/org.omarchy.OmniShot.desktop`, and `~/.local/share/mime/packages/omnishot.xml`.
5. Remove OmniShot entries for its project types and URL scheme from `~/.config/mimeapps.list`, or restore the corresponding entries from your backup. Refresh the desktop and MIME databases with `update-desktop-database ~/.local/share/applications` and `update-mime-database ~/.local/share/mime`.
6. Run `hyprctl reload` and `hyprctl configerrors`; resolve any reported configuration errors. The bar configuration reloads automatically.

Paths above use the default XDG directories; use your configured directories if different. Installer backups are in the app folder's `backups/<timestamp>/` (normally `~/.local/share/omnishot-app/backups/`). Review differences before restoring a whole file so later customizations are retained.

You can then remove the built app files at `~/.local/share/omnishot-app`, including its `.venv` (or your custom installation path), and any `omnishot-app.pre-plugin-*` folder left from an earlier install. Earlier installations may use `~/projects/omnishot`; keep that directory if you still use it for development. Captures, projects, settings, and history remain in `~/.local/share/omnishot`; exported images normally remain in `~/Pictures/OmniShot`.
