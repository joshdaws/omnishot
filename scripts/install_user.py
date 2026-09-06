"""Install only user-owned files; preserve package files and unrelated settings."""
import json
import os
from pathlib import Path
import shutil
import shlex
import time
import subprocess

source=Path(os.environ["OMNISHOT_SOURCE"]).resolve()
python=Path(os.environ["OMNISHOT_PYTHON"]).resolve()
# Do not resolve the interpreter symlink: invoking the venv path is essential.
python=Path(os.environ["OMNISHOT_PYTHON"])
home=Path.home();config=Path(os.environ.get("XDG_CONFIG_HOME",home/".config"))
stamp=time.strftime("%Y%m%d-%H%M%S")
backup=source/"backups"/stamp;backup.mkdir(parents=True,exist_ok=True)

def preserve(path):
    if path.exists():shutil.copy2(path,backup/path.name)

bin_dir=home/".local/bin";bin_dir.mkdir(parents=True,exist_ok=True)
launcher=bin_dir/"omnishot";preserve(launcher)
launcher.write_text("#!/bin/sh\nexport OMNISHOT_PREVIOUS_PRELOAD=\"${LD_PRELOAD-}\"\nexport LD_PRELOAD="+shlex.quote(str(source/"native/drag-status.so"))+"\"${LD_PRELOAD:+:$LD_PRELOAD}\"\nexec "+shlex.quote(str(python))+" -m omnishot.app \"$@\"\n");launcher.chmod(0o755)
applications=home/".local/share/applications";applications.mkdir(parents=True,exist_ok=True)
mime_dir=home/".local/share/mime";mime_packages=mime_dir/"packages";mime_packages.mkdir(parents=True,exist_ok=True)
preserve(mime_packages/"omnishot.xml");shutil.copy2(source/"packaging/omnishot.xml",mime_packages/"omnishot.xml")
desktop=applications/"org.omarchy.OmniShot.desktop";preserve(desktop)
desktop.write_text('[Desktop Entry]\nType=Application\nName=OmniShot\nComment=Capture, scroll, annotate and record\nExec="'+str(launcher)+'" %u\nIcon=camera-photo\nTerminal=false\nCategories=Graphics;Utility;\nMimeType=image/png;image/jpeg;image/webp;image/heic;image/heif;image/gif;video/mp4;video/webm;video/quicktime;video/x-matroska;application/x-omnishot;application/x-omnishot-video;x-scheme-handler/omnishot;\nActions=Capture;Scroll;History;\n\n[Desktop Action Capture]\nName=Capture\nExec="'+str(launcher)+'" menu\n\n[Desktop Action Scroll]\nName=Scrolling Capture\nExec="'+str(launcher)+'" scroll\n\n[Desktop Action History]\nName=Capture History\nExec="'+str(launcher)+'" history\n')
plugin=config/"omarchy/plugins/local.omnishot";plugin.mkdir(parents=True,exist_ok=True)
widget=(source/"plugin/BarWidget.qml").read_bytes()
installed_widget=plugin/"BarWidget.qml"
widget_changed=not installed_widget.exists() or installed_widget.read_bytes()!=widget
if (plugin/"manifest.json").exists():
    widget_changed=widget_changed or json.loads((plugin/"manifest.json").read_text()).get("entryPoints",{}).get("barWidget")!="BarWidget.qml"
preserve(installed_widget);installed_widget.write_bytes(widget)
manifest=json.loads((source/"plugin/manifest.json").read_text())
preserve(plugin/"manifest.json");(plugin/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
shell=config/"omarchy/shell.json";preserve(shell);data=json.loads(shell.read_text())
layout=data.setdefault("bar",{}).setdefault("layout",{}).setdefault("right",[])
if not any(v.get("id")=="local.omnishot" for v in layout):layout.insert(0,{"id":"local.omnishot"})
shell_text=json.dumps(data,indent=2)+"\n"
if shell.read_text()!=shell_text:shell.write_text(shell_text)
bindings=config/"hypr/bindings.lua";preserve(bindings)
marker="-- OmniShot managed bindings"
old=bindings.read_text()
if marker not in old:
    with bindings.open("a") as f:
        f.write('\n'+marker+'\n')
        for key,desc,cmd in [("PRINT","OmniShot capture","menu"),("CTRL + PRINT","OmniShot area","area"),
           ("SHIFT + PRINT","OmniShot fullscreen","fullscreen"),("ALT + PRINT","OmniShot recording","record"),
           ("SUPER + SHIFT + PRINT","OmniShot scrolling capture","scroll"),("SUPER + CTRL + PRINT","OmniShot text capture","ocr")]:
            f.write(f'hl.unbind("{key}")\no.bind("{key}", "{desc}", "{launcher} {cmd}")\n')
rules=config/"hypr/omnishot.lua";preserve(rules)
rules_text='''-- OmniShot user-owned window rules.
o.window("^(omnishot|org\\\\.omarchy\\\\.OmniShot)$", { float = true, opacity = "1 1", no_anim = true })
o.window({ class = "^(omnishot|org\\\\.omarchy\\\\.OmniShot)$", title = "^OmniShot Preview.*" }, { pin = true, no_initial_focus = true, no_follow_mouse = true })
o.window({ title = "^OmniShot Pin.*", class = "^(omnishot|org\\\\.omarchy\\\\.OmniShot)$" }, { pin = true, no_blur = true, no_shadow = true, border_size = 0, rounding = 0 })
o.window({ title = "^OmniShot Locked Pin.*", class = "^(omnishot|org\\\\.omarchy\\\\.OmniShot)$" }, { pin = true, no_focus = true, no_blur = true, no_shadow = true, border_size = 0, rounding = 0 })
o.window({ title = "^OmniShot (Recording Controls|Camera Preview|Self Timer)$", class = "^(omnishot|org\\\\.omarchy\\\\.OmniShot)$" }, { pin = true, no_initial_focus = true, no_follow_mouse = true, no_blur = true, no_shadow = true, border_size = 0, rounding = 0 })
o.window({ title = "^OmniShot Scrolling (Guide.*|Preview)$", class = "^(omnishot|org\\\\.omarchy\\\\.OmniShot)$" }, { no_focus = true, no_initial_focus = true, no_blur = true, no_shadow = true, no_dim = true, border_size = 0, rounding = 0 })
o.window({ title = "^OmniShot Recording Dim .*", class = "^(omnishot|org\\\\.omarchy\\\\.OmniShot)$" }, { pin = true, no_focus = true, no_initial_focus = true, no_blur = true, no_shadow = true, no_dim = true, border_size = 0, rounding = 0 })
o.window({ title = "^OmniShot Scrolling Capture$", class = "^(omnishot|org\\\\.omarchy\\\\.OmniShot)$" }, { no_initial_focus = true, no_follow_mouse = true, no_blur = true, no_shadow = true, border_size = 0, rounding = 10 })
o.window({ title = "^OmniShot Scrolling Selection$", class = "^(omnishot|org\\\\.omarchy\\\\.OmniShot)$" }, { no_initial_focus = true, no_follow_mouse = true, no_blur = true, no_shadow = true, border_size = 0, rounding = 0 })
o.window({ title = "^OmniShot (Window )?Selection.*$", class = "^(omnishot|org\\\\.omarchy\\\\.OmniShot)$" }, { no_initial_focus = true, no_blur = true, no_shadow = true, border_size = 0, rounding = 0 })
'''
if not rules.exists() or rules.read_text()!=rules_text:rules.write_text(rules_text)
hypr=config/"hypr/hyprland.lua";preserve(hypr)
if 'require("hypr.omnishot")' not in hypr.read_text():
    with hypr.open("a") as f:f.write('\n-- OmniShot capture and annotation windows.\nrequire("hypr.omnishot")\n')
print(f"Installed OmniShot. Configuration backups: {backup}")

if shutil.which("update-desktop-database"):
    subprocess.run(["update-desktop-database",str(applications)],check=True)
if shutil.which("update-mime-database"):
    subprocess.run(["update-mime-database",str(mime_dir)],check=True)
if shutil.which("xdg-mime"):
    preserve(config/"mimeapps.list")
    subprocess.run(["xdg-mime","default",desktop.name,"application/x-omnishot","application/x-omnishot-video","x-scheme-handler/omnishot"],check=True)
if widget_changed and subprocess.run(["omarchy-shell","shell","ping"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
    # Quickshell's live component/file cache can retain the prior widget after
    # rescanPlugins, including when a new entry-point filename is introduced.
    # The stock restart command refuses to interrupt an active lock screen.
    result=subprocess.run(["omarchy","restart","shell"])
    if result.returncode:print("Widget files are installed; reload the Omarchy shell after unlocking to activate the update.")
