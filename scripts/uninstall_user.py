"""Remove what install_user.py added; keep captures, settings and unrelated config."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime

home=Path.home();config=Path(os.environ.get("XDG_CONFIG_HOME",home/".config"))
data_home=Path(os.environ.get("XDG_DATA_HOME",home/".local/share"))
plugin_ids=("io.github.joshdaws.omnishot","local.omnishot")
desktop_id="org.omarchy.OmniShot.desktop"
MARKER="-- OmniShot managed bindings";END="-- End OmniShot managed bindings"
REQUIRE='require("hypr.omnishot")'
# Parse everything first, so a broken file cannot leave a partial removal.
shell=config/"omarchy/shell.json";data=json.loads(shell.read_text()) if shell.exists() else None
backup=data_home/"omnishot/config-backups"/("uninstall-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f"))

def preserve(path):
    if not path.exists():return
    root,name=next(((r,n) for r,n in ((config,"config"),(data_home,"data"),(home,"home")) if path.is_relative_to(r)),(path.parent,"other"))
    target=backup/name/path.relative_to(root)
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)

def rewrite(path,text):
    if path.exists() and path.read_text()!=text:preserve(path);path.write_text(text)

def remove(path):
    if path.is_file() or path.is_symlink():preserve(path);path.unlink()

def without_bindings(text):
    lines=text.splitlines(keepends=True)
    try:start=next(i for i,line in enumerate(lines) if line.rstrip()==MARKER)
    except StopIteration:return text
    end=start+1
    while end<len(lines):
        if lines[end].rstrip()==END:end+=1;break
        if end+1<len(lines) and re.fullmatch(r'hl\.unbind\("[^"]+"\)\s*',lines[end]) and re.match(r'o\.bind\("[^"]+", "OmniShot ',lines[end+1]):end+=2
        else:break
    # The installer separated its block with one blank line.
    if start and not lines[start-1].strip():start-=1
    return "".join(lines[:start]+lines[end:])

def without_require(text):
    lines=text.splitlines(keepends=True);out=[]
    for line in lines:
        if line.strip()==REQUIRE:
            if out and out[-1].strip()=="-- OmniShot capture and annotation windows.":out.pop()
            if out and not out[-1].strip():out.pop()
            continue
        out.append(line)
    return "".join(out)

def without_desktop(text):
    out=[]
    for line in text.splitlines(keepends=True):
        key,sep,value=line.partition("=")
        if sep and not line.lstrip().startswith(("#","[")):
            entries=[v for v in value.strip().split(";") if v]
            if desktop_id in entries:
                kept=[v for v in entries if v!=desktop_id]
                if not kept:continue
                line=key+"="+";".join(kept)+";\n"
        out.append(line)
    return "".join(out)

launcher=home/".local/bin/omnishot"
if launcher.is_file() and "omnishot.app" in launcher.read_text(errors="replace"):remove(launcher)
remove(data_home/"applications"/desktop_id)
remove(data_home/"mime/packages/omnishot.xml")
mimeapps=config/"mimeapps.list"
if mimeapps.exists():rewrite(mimeapps,without_desktop(mimeapps.read_text()))
bindings=config/"hypr/bindings.lua"
if bindings.exists():rewrite(bindings,without_bindings(bindings.read_text()))
hypr=config/"hypr/hyprland.lua"
if hypr.exists():rewrite(hypr,without_require(hypr.read_text()))
remove(config/"hypr/omnishot.lua")
if data is not None:
    layout=data.get("bar",{}).get("layout",{})
    for section in ("left","center","right"):
        if section in layout:layout[section]=[v for v in layout[section] if v.get("id") not in plugin_ids]
    rewrite(shell,json.dumps(data,indent=2)+"\n")
for plugin_id in plugin_ids:
    plugin=config/"omarchy/plugins"/plugin_id
    # A git checkout belongs to `omarchy plugin remove`; plain copies are ours.
    if plugin.is_dir() and not (plugin/".git").exists():
        for path in plugin.rglob("*"):
            if path.is_file():preserve(path)
        shutil.rmtree(plugin)

for command,path in (("update-desktop-database",data_home/"applications"),("update-mime-database",data_home/"mime")):
    if shutil.which(command) and path.is_dir():subprocess.run([command,str(path)],check=False)
print("Removed OmniShot's launcher, shortcuts, window rules and desktop integration.")
if backup.exists():print(f"Previous configuration: {backup}")
