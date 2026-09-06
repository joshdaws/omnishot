from __future__ import annotations
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import copy
import hashlib
from PIL import Image
import numpy as np


def run(args, *, data=None, timeout=30):
    result = subprocess.run([str(a) for a in args], input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip() or result.stdout.decode(errors="replace").strip() or f"{args[0]} failed")
    return result.stdout


def hypr(query):
    return json.loads(run(["hyprctl", "-j", query]))


def move_to_trash(path):
    from PySide6.QtCore import QFile
    file=QFile(str(path))
    if not file.moveToTrash():raise OSError("The desktop could not move this capture to Trash: "+file.errorString())
    return file.fileName()


def move_cursor(x,y):
    run(["hyprctl","eval",f"hl.dispatch(hl.dsp.cursor.move({{ x = {int(x)}, y = {int(y)} }}))"])


def move_window(address,x,y):
    if not re.fullmatch(r"0x[0-9a-fA-F]+",address):raise ValueError("Invalid window address")
    client=next((c for c in hypr('clients') if c['address']==address),None)
    if client:
        from .clean_capture import monitor_bounds
        cx,cy=x+client['size'][0]/2,y+client['size'][1]/2
        for monitor in hypr('monitors'):
            mx,my,mw,mh=monitor_bounds(monitor)
            if mx<=cx<mx+mw and my<=cy<my+mh:
                if client['monitor']!=monitor['id']:
                    # Coordinates alone leave pinned windows on the old output.
                    # Transfer them without following, then apply exact position.
                    run(['hyprctl','eval',f'hl.dispatch(hl.dsp.window.move({{window="address:{address}",monitor="{int(monitor["id"])}",follow=false}}))'])
                break
    run(["hyprctl","eval",f'hl.dispatch(hl.dsp.window.move({{ window = "address:{address}", x = {int(x)}, y = {int(y)} }}))'])


def focus_window(address):
    if not re.fullmatch(r"0x[0-9a-fA-F]+",address):raise ValueError("Invalid window address")
    run(["hyprctl","eval",f'hl.dispatch(hl.dsp.focus({{ window = "address:{address}" }}))'])


def raise_window(address):
    if not re.fullmatch(r"0x[0-9a-fA-F]+",address):raise ValueError("Invalid window address")
    run(["hyprctl","eval",f'hl.dispatch(hl.dsp.window.alter_zorder({{ mode = "top", window = "address:{address}" }}))'])


def session_locked(monitors):
    # Hyprland reports null when nothing blocks a solitary fullscreen surface.
    return any('LOCK' in (m.get('solitaryBlockedBy') or []) for m in monitors)


def capture_monitors():
    monitors=hypr("monitors")
    if session_locked(monitors):
        raise RuntimeError("Unlock the desktop before capturing.")
    if not any(m.get("dpmsStatus",True) for m in monitors):
        raise RuntimeError("The display is asleep. Wake it before capturing.")
    return monitors


def grab_window(client,cursor=False):
    """Capture the selected surface independently of overlap and wallpaper."""
    capture_monitors()
    helper=Path(__file__).resolve().parent.parent/"native/window-helper"
    address=client.get('address','')
    if not isinstance(address,str) or not re.fullmatch(r'0x[0-9a-fA-F]+',address):raise RuntimeError('Invalid selected window')
    # The export protocol identifies a window by the low 32 bits of its address.
    # Titles are mutable and frequently shared by multiple windows.
    handle=int(address,16)&0xffffffff
    def resolve():
        matches=[c for c in hypr('clients') if int(c['address'],16)&0xffffffff==handle]
        if len(matches)!=1:raise RuntimeError('Window closed or has an ambiguous capture handle. Select it again.')
        return dict(matches[0])
    current=resolve()
    if int(current['address'],16)!=int(address,16) or (client.get('stableId') is not None and current.get('stableId')!=client['stableId']):
        raise RuntimeError('The selected window closed. Select a window again.')
    data=run([helper,handle,int(cursor)],timeout=12)
    after=resolve()
    if after['address']!=current['address'] or after.get('stableId')!=current.get('stableId'):
        raise RuntimeError('The selected window closed during capture. Select a window again.')
    header,separator,pixels=data.partition(b"ENDHDR\n")
    if not separator or not header.startswith(b"P7\n"):raise RuntimeError("Invalid window capture")
    fields=dict(line.split(b" ",1) for line in header.splitlines()[1:] if b" " in line)
    w,h=int(fields[b"WIDTH"]),int(fields[b"HEIGHT"])
    if len(pixels)!=w*h*4:raise RuntimeError("Incomplete window capture")
    return np.frombuffer(pixels,np.uint8).reshape(h,w,4).copy()


DEFAULTS = {
    "after_capture": "overlay", "after_recording": "edit", "output_dir": str(Path.home()/"Pictures"/"OmniShot"),
    "format": "png", "include_cursor": False, "freeze": True, "capture_ctrl_copy": True, "window_shadow": True, "window_wallpaper": True,
    "wallpaper_source": "desktop", "wallpaper_data": "", "wallpaper_follow_changes": True, "window_padding": 24,
    "scale_screenshots": False, "screenshot_border": False,
    "crosshair_mode": "always", "show_magnifier": True, "remember_selection": True,
    "delay": 3, "overlay_corner": "bottom-left", "overlay_size": 300,
    "overlay_timeout": 0, "history_days": 30, "ask_save_destination": False,
    "after_capture_extra": [], "after_recording_extra": [], "background_preset": "None",
    "clipboard_mode": "both", "url_api_enabled": True, "capture_shortcut_actions": True,
    "filename_format": "OmniShot %y-%m-%d at %H.%M.%S", "filename_utc": False,
    "pin_rounded": True, "pin_shadow": False, "pin_border": False, "convert_srgb": True, "filename_scale_suffix": True, "filename_remove_illegal": True, "filename_counter": 0, "ask_capture_name": False,
    "inverse_arrows": False, "smooth_drawing": True, "annotation_shadow": True, "auto_expand_canvas": False,
    "overlay_close_after_drag": True, "overlay_auto_action": "close", "overlay_active_screen": True,
    "scroll_interval": 550, "scroll_step": 3, "ocr_languages": "auto", "ocr_linebreaks": True, "ocr_detect_links": True,
    "record_dim_screen": True, "record_show_controls": True, "record_remember_selection": True, "record_show_time": True,
    "record_countdown": 3, "record_dnd": True, "record_clicks": False, "record_keys": False, "record_commands_only": True,
    "record_max_resolution": "Native", "record_scale_video": False,
    "gif_fps": 15, "gif_width": 800, "gif_optimize": True, "gif_quality": 80,
    "fps": 30, "quality": "very_high", "record_cursor": True,
    "record_system_audio": False, "record_microphone": False, "record_audio_tracks": "single", "record_audio_mono": False,
    "palette": ["#ff5b61", "#ffbc42", "#53d49b", "#60a5fa", "#b48bfa", "#ffffff", "#15171d"],
}


AREA_SHORTCUTS={f"area-{action}":action for action in ("copy","save","annotate","pin")}
OCR_SHORTCUTS={"ocr-lines":True,"ocr-single-line":False}


def capture_actions(settings,recording=False):
    key="after_recording" if recording else "after_capture"
    allowed={"copy","save","overlay","edit"} if recording else {"copy","save","overlay","annotate","pin"}
    return ({settings.get(key,""),*settings.get(key+"_extra",[])} & allowed)


def screenshot_actions(settings,action=None):
    if action in AREA_SHORTCUTS:
        actions=capture_actions(settings) if settings.get('capture_shortcut_actions',True) else set()
        return actions|{AREA_SHORTCUTS[action]}
    return {action} if action else capture_actions(settings)


def prepare_screenshot(frame,ratio,settings):
    """Apply capture-only presentation at final output resolution, preserving alpha."""
    if not settings.get("screenshot_border") and not (settings.get("scale_screenshots") and ratio and ratio>1):return frame,ratio
    image=Image.fromarray(frame)
    if settings.get("scale_screenshots") and ratio and ratio>1:
        image=image.resize((max(2,round(image.width/ratio)),max(2,round(image.height/ratio))),Image.Resampling.LANCZOS);ratio=1
    if settings.get("screenshot_border"):
        from PIL import ImageDraw
        ImageDraw.Draw(image).rectangle((0,0,image.width-1,image.height-1),outline=(0,0,0,255) if image.mode=="RGBA" else (0,0,0),width=1)
    return np.array(image),ratio


class Store:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("OMNISHOT_DATA_DIR") or
                         Path(os.environ.get("XDG_DATA_HOME", Path.home()/".local/share"))/"omnishot")
        self.root.mkdir(parents=True, exist_ok=True)
        self.captures = self.root/"captures"
        self.captures.mkdir(exist_ok=True)
        self.settings_path = self.root/"settings.json"
        self.settings = copy.deepcopy(DEFAULTS)
        if self.settings_path.exists():
            try: self.settings.update(json.loads(self.settings_path.read_text()))
            except (ValueError, OSError): pass
        self.settings.pop("theme",None)

    def atomic_json(self, path, value):
        from .storage import atomic_output
        with atomic_output(path) as temp:temp.write_text(json.dumps(value,indent=2))

    def save_settings(self): self.atomic_json(self.settings_path, self.settings)

    def metadata(self,path):
        try:return json.loads(Path(path).with_suffix(".json").read_text())
        except (ValueError,OSError):return {}

    def display_name(self,path):
        return Path(self.metadata(path).get("name") or Path(path).name).name

    def remember_auto_save(self,path,destination):
        destination=Path(destination).absolute();stat=destination.stat()
        metadata=self.metadata(path);outputs=metadata.setdefault('autosaved_files',[])
        outputs.append(dict(path=str(destination),identity=[stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]))
        self.atomic_json(Path(path).with_suffix('.json'),metadata)

    def trash_auto_saves(self,path):
        """Remove only the unchanged files created by this capture's auto-save."""
        kept=[]
        for output in self.metadata(path).get('autosaved_files',[]):
            destination=Path(output['path'])
            try:stat=destination.lstat()
            except FileNotFoundError:continue
            identity=[stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]
            if destination.is_symlink() or not destination.is_file() or identity!=output.get('identity'):
                kept.append(str(destination));continue
            move_to_trash(destination)
        return kept

    def name_capture(self,path,context=None):
        from .filenames import format_name,scale_suffix
        path=Path(path);metadata=self.metadata(path)
        sequence=int(self.settings.get("filename_counter",0))+1
        stem=format_name(self.settings.get("filename_format"),created=metadata.get("created"),utc=self.settings.get("filename_utc",False),remove_illegal=self.settings.get("filename_remove_illegal",True),sequence=sequence,context=context)
        suffix=scale_suffix(metadata.get("pixel_ratio")) if self.settings.get("filename_scale_suffix",True) and metadata.get("kind") in ("image","scroll") else ""
        metadata["filename_scale_suffix"]=suffix
        metadata["name"]=stem+suffix+path.suffix;metadata["capture_named"]=True;self.atomic_json(path.with_suffix(".json"),metadata)
        if "i" in re.findall(r"%(.)",self.settings.get("filename_format","")):
            self.settings["filename_counter"]=sequence;self.save_settings()
        return metadata["name"]

    def capture_name_context(self,client=None):
        pattern=self.settings.get("filename_format","")
        if "%t" not in pattern and "%a" not in pattern:return {}
        try:
            if client is None:
                client=hypr("activewindow")
                if client.get("pid")==os.getpid():
                    rows=[c for c in hypr("clients") if c.get("pid")!=os.getpid() and c.get("mapped") and c.get("visible",True)]
                    client=min(rows,key=lambda c:c.get("focusHistoryID",9999) if c.get("focusHistoryID",-1)>=0 else 9999) if rows else {}
            app=client.get("class","")
            if app and "/" not in app:
                import configparser
                for folder in (Path.home()/".local/share/applications",Path("/usr/share/applications")):
                    for key in dict.fromkeys((app,app.lower())):
                        desktop=folder/(key+".desktop")
                        if desktop.is_file():
                            try:
                                parser=configparser.ConfigParser(interpolation=None,strict=False);parser.read(desktop)
                                return dict(title=client.get("title",""),app=parser.get("Desktop Entry","Name",fallback=app))
                            except (configparser.Error,OSError):continue
            return dict(title=client.get("title",""),app=app)
        except (OSError,RuntimeError,ValueError):return {}

    def rename(self,path,name):
        path=Path(path).resolve();name=name.strip()
        if path.parent!=self.captures.resolve():raise ValueError("Import the capture before renaming it")
        if not name or name in (".","..") or any(c in name for c in ("/","\\","\0","\n","\r")):raise ValueError("Enter a filename without folders or line breaks")
        if not name.lower().endswith(path.suffix.lower()):name+=path.suffix
        metadata=self.metadata(path);metadata["name"]=name;metadata.pop("filename_scale_suffix",None);self.atomic_json(path.with_suffix(".json"),metadata)
        return name

    def set_pixel_ratio(self,path,ratio):
        metadata=self.metadata(path);metadata["pixel_ratio"]=ratio
        suffix=metadata.pop("filename_scale_suffix","")
        name=Path(metadata.get("name") or Path(path).name)
        if suffix and name.stem.endswith(suffix):
            from .filenames import scale_suffix
            replacement=scale_suffix(ratio) if self.settings.get("filename_scale_suffix",True) else ""
            metadata["name"]=name.stem[:-len(suffix)]+replacement+name.suffix
            metadata["filename_scale_suffix"]=replacement
        self.atomic_json(Path(path).with_suffix(".json"),metadata)

    def export_target(self,path,folder=None,extension=None):
        folder=Path(folder or self.settings["output_dir"]).expanduser();folder.mkdir(parents=True,exist_ok=True)
        name=Path(self.display_name(path))
        if extension:name=name.with_suffix("."+extension.lstrip("."))
        target=folder/name;number=2
        while target.exists():target=folder/(name.stem+f" ({number})"+name.suffix);number+=1
        return target

    def image_edit_path(self,path):
        return self.root/"image-edits"/(hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()[:24]+".omnishot")

    def video_edit_path(self,path):
        return self.root/"video-edits"/(hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()[:24]+".json")

    def display_image(self,path):
        path=Path(path)
        if path.resolve().parent==self.captures.resolve():
            preview=self.image_edit_path(path).with_suffix(".png")
            if preview.exists():return preview
        return path

    def add(self, image=None, source=None, kind="image"):
        ident = time.strftime("%Y-%m-%d_%H-%M-%S") + "_" + uuid.uuid4().hex[:8]
        ext = Path(source).suffix if source else ".png"
        path = self.captures/(ident+ext)
        from .storage import atomic_output
        with atomic_output(path) as temporary:
            if image is not None:
                from PySide6.QtGui import QImage
                if isinstance(image,QImage):
                    if not image.save(str(temporary),'PNG'):raise ValueError('Could not save clipboard image')
                else:Image.fromarray(image).save(temporary)
            elif source: shutil.copy2(source, temporary)
            else: raise ValueError("Missing capture")
        self.atomic_json(path.with_suffix(".json"), {"kind": kind, "created": time.time(), "name": path.name})
        return path

    def import_file(self,source):
        source=Path(source).resolve()
        if source.parent==self.captures.resolve():return source
        if source.suffix.lower() not in {".png",".jpg",".jpeg",".webp",".heic",".heif",".omnishot",".omnishot-video",".mp4",".gif",".webm",".mov",".mkv"}:raise ValueError("Unsupported image, recording or project format")
        stat=source.stat()
        if source.suffix.lower() in {".png",".jpg",".jpeg",".webp",".heic",".heif",".gif"}:
            from .images import validate_image
            validate_image(source)
        if source.suffix.lower()==".omnishot":
            from .image_project import read_project
            read_project(source)
        if source.suffix.lower() in {".mp4",".webm",".mov",".mkv"}:
            from .media_import import validate_video
            validate_video(source)
        for row in self.history():
            if row.get("source_path")==str(source) and row.get("source_mtime_ns")==stat.st_mtime_ns and row.get("source_size")==stat.st_size:return Path(row["path"])
        kind="gif" if source.suffix.lower()==".gif" else "video" if source.suffix.lower() in {".mp4",".webm",".mov",".mkv",".omnishot-video"} else "image"
        path=self.add(source=source,kind=kind)
        self.atomic_json(path.with_suffix(".json"),{"kind":kind,"created":time.time(),"name":source.name,"source_path":str(source),"source_mtime_ns":stat.st_mtime_ns,"source_size":stat.st_size})
        return path

    def history(self, kind="all", search=""):
        rows = []
        for p in self.captures.iterdir():
            if p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif", ".omnishot", ".omnishot-video", ".mp4", ".gif", ".webm", ".mov", ".mkv"}: continue
            if any(p.with_suffix(s).exists() for s in (".recording.json",".discarding.json",".failed-recording.json")):continue
            meta = p.with_suffix(".json")
            try: record = json.loads(meta.read_text()) if meta.exists() else {}
            except (ValueError, OSError): record = {}
            if p.suffix==".mp4" and record.get("kind")=="gif" and p.with_suffix(".gif").exists():continue
            record.setdefault("kind","video" if p.suffix.lower() in {".mp4",".webm",".mov",".mkv",".omnishot-video"} else "gif" if p.suffix.lower()==".gif" else "image")
            record.setdefault("name",p.name);record.update(path=str(p), created=record.get("created",p.stat().st_mtime))
            preview=self.image_edit_path(p).with_suffix(".png")
            if preview.exists():record["preview"]=str(preview)
            if kind != "all" and record.get("kind", "image") != kind: continue
            if search.lower() not in record["name"].lower(): continue
            rows.append(record)
        return sorted(rows, key=lambda r:r["created"], reverse=True)

    def expire(self):
        cutoff = time.time()-max(1,int(self.settings["history_days"]))*86400
        for row in self.history():
            if row["created"] < cutoff: self.remove(row["path"])
        for folder in ("exports","image-edits","video-edits"):
            for path in (self.root/folder).glob("*"):
                if path.is_file() and path.stat().st_mtime<cutoff:path.unlink()
        for folder in (self.root/"clipboard").glob("*"):
            if folder.is_dir() and not folder.is_symlink() and folder.stat().st_mtime<cutoff:shutil.rmtree(folder)

    def trash(self,path):
        """Trash a portable recovery bundle before removing the history copy."""
        path=Path(path).resolve()
        if path.parent!=self.captures.resolve():raise ValueError("Only history captures can be moved to Trash")
        staging=self.root/"trash-staging";staging.mkdir(exist_ok=True)
        bundle=staging/(Path(self.display_name(path)).stem+"-"+uuid.uuid4().hex[:8]);bundle.mkdir()
        try:
            if path.suffix.lower() in {".omnishot-video",".mp4",".gif",".webm",".mov",".mkv"} or path.with_suffix(".studio.json").exists():
                from .video_project import read_project,write_project
                if path.suffix.lower()==".omnishot-video":source,metadata,options=read_project(path,self)
                else:
                    studio=path.with_suffix(".studio.json")
                    metadata=json.loads(studio.read_text()) if studio.exists() else {}
                    source=Path(metadata.get("source_path") or (path.with_suffix(".mp4") if path.suffix.lower()==".gif" and metadata else path));options={}
                    # Match the editor's fallback when an old source track is
                    # unavailable; the visible recording is still recoverable.
                    if not source.is_file():source=path;metadata={}
                edits=self.video_edit_path(path)
                if edits.exists():options=json.loads(edits.read_text()).get("options",{})
                write_project(bundle/(Path(self.display_name(path)).stem+".omnishot-video"),source,metadata,options)
                if path.suffix.lower()!=".omnishot-video":shutil.copy2(path,bundle/self.display_name(path))
            else:
                preview=self.display_image(path);name=Path(self.display_name(path))
                if preview!=path:name=name.with_suffix(".png")
                shutil.copy2(preview,bundle/name)
                draft=self.image_edit_path(path)
                if draft.exists():shutil.copy2(draft,bundle/name.with_suffix(".omnishot"))
            (bundle/"Read me.txt").write_text("Restore this folder from Trash. Open the .omnishot or .omnishot-video file in OmniShot to recover editable annotations and recording tracks. Other files are the captured image or recording.\n")
            trashed=move_to_trash(bundle)
            kept=self.trash_auto_saves(path)
            self.remove(path)
            return dict(bundle=trashed,kept_saved_files=kept)
        finally:
            if bundle.exists():shutil.rmtree(bundle)

    def remove(self, path):
        p = Path(path).resolve()
        if p.parent==self.captures.resolve():
            edit=self.image_edit_path(p);edit.unlink(missing_ok=True);edit.with_suffix(".png").unlink(missing_ok=True)
            self.video_edit_path(p).unlink(missing_ok=True)
            identity=hashlib.sha256(str(p).encode()).hexdigest()[:24]
            for folder in (self.root/"video-projects").glob(identity+"-*"):
                if folder.is_dir():shutil.rmtree(folder)
        if p.parent != self.captures.resolve(): raise ValueError("Not a history capture")
        p.unlink(missing_ok=True)
        p.with_suffix(".json").unlink(missing_ok=True)
        studio=p.with_suffix(".studio.json")
        if studio.exists():
            try:
                record=json.loads(studio.read_text())
                for key in ("camera_path","source_path"):
                    track=Path(record.get(key,"")).resolve()
                    if track.parent==(self.root/"tracks").resolve():track.unlink(missing_ok=True);track.with_suffix(".camera-log").unlink(missing_ok=True)
            except (ValueError,OSError):pass
        if p.suffix==".gif":
            p.with_suffix(".mp4").unlink(missing_ok=True);self.video_edit_path(p.with_suffix(".mp4")).unlink(missing_ok=True)
        for extra in (studio,p.with_suffix(".studio.checkpoint"),p.with_suffix(".video-edit.json"),p.with_suffix(".log"),Path(str(p)+".ts")):extra.unlink(missing_ok=True)


def parse_geometry(text):
    match = re.fullmatch(r"(-?\d+),(-?\d+)\s+(\d+)x(\d+)", text.strip())
    if not match: raise ValueError("Invalid capture geometry")
    x,y,w,h = map(int, match.groups())
    if w<2 or h<2: raise ValueError("Selection is too small")
    return x,y,w,h


def geometry_text(rect):
    x,y,w,h = map(int,rect)
    return f"{x},{y} {w}x{h}"


def grab(rect=None, cursor=False, output=None, scale=None):
    capture_monitors()
    args = ["grim"]
    if rect: args += ["-g",geometry_text(rect)]
    if cursor: args += ["-c"]
    if output: args += ["-o",output]
    if scale: args += ["-s",str(scale)]
    args += ["-t","png","-"]
    # Hyprland can bake a software pointer into the output even without grim's
    # -c. Use the clean mirror for both cursor modes so the protocol flag alone
    # determines inclusion. A scrolling session retains its outer lease.
    from .clean_capture import CursorMirror
    with CursorMirror():
        return np.array(Image.open(io.BytesIO(run(args, timeout=15))).convert("RGB"))


def window_background(client,frame,shadow=True,store=None,transparent=False):
    scale=frame.shape[1]/max(1,client["size"][0])
    def property_value(name,kind,default):
        address=client.get('address','')
        if re.fullmatch(r'0x[0-9a-fA-F]+',address):
            try:return float(json.loads(run(['hyprctl','-j','getprop',f'address:{address}',name]))[name])
            except (RuntimeError,ValueError,KeyError,TypeError):pass
        try:return float(json.loads(run(['hyprctl','-j','getoption',f'decoration:{name}']))[kind])
        except (RuntimeError,ValueError,KeyError,TypeError):return default
    rounding=property_value('rounding','int',0);power=property_value('rounding_power','float',2)
    padding=max(0,min(200,int(store.settings.get("window_padding",24)))) if store else (24 if shadow else 0)
    # Hyprland scales the radius by power/2 to retain perceived roundness.
    opts={"color":"#00000000","color2":"#00000000","padding":round(padding*scale),"radius":0 if client.get("fullscreen")==2 else round(rounding*power/2*scale),"radius_power":power,"shadow":shadow,"aspect":"Auto","align":"Center"}
    if store and store.settings["window_wallpaper"] and not transparent:
        from .wallpaper import capture_wallpaper
        data=capture_wallpaper(store)
        if data:opts.update(image_data=data)
    return opts


def selection_style_args():
    from .theme import color
    return ['-b',color('background').name()+'55','-c',color('accent').name()+'ff','-w','2']


def select_region(window=False,with_modifiers=False):
    executable=Path(__file__).resolve().parent.parent/"native"/"live-selector" if with_modifiers else "slurp"
    args = [executable, *selection_style_args()]
    if with_modifiers:args += ["-f","%x,%y %wx%h|%M\n"]
    data = None
    if window:
        rows = []
        visible = {m["activeWorkspace"]["id"] for m in hypr("monitors")}
        for c in hypr("clients"):
            if c.get("mapped") and c.get("workspace",{}).get("id") in visible and not c.get("hidden"):
                rows.append(f'{c["at"][0]},{c["at"][1]} {c["size"][0]}x{c["size"][1]}')
        args += ["-r"]
        data = ("\n".join(rows)+"\n").encode()
    result=run(args,data=data,timeout=180).decode().strip()
    if with_modifiers:
        geometry,modifiers=result.rsplit("|",1);return parse_geometry(geometry),int(modifiers)
    return parse_geometry(result)


def select_window():
    visible={m["activeWorkspace"]["id"] for m in capture_monitors()}
    clients=[c for c in hypr("clients") if c.get("mapped") and not c.get("hidden") and (c.get("workspace",{}).get("id") in visible or c.get("pinned"))]
    if not clients:raise RuntimeError("There are no windows to capture")
    rows=[f'{c["at"][0]},{c["at"][1]} {c["size"][0]}x{c["size"][1]} {c["address"]}' for c in clients]
    address=run(["slurp","-r","-f","%l",*selection_style_args()],data=("\n".join(rows)+"\n").encode(),timeout=180).decode().strip()
    return next(c for c in clients if c["address"]==address)


def copy_image(path,store=None,name=None):
    store=store or Store();mode=store.settings.get("clipboard_mode","both")
    if mode not in ("both","file","image"):raise ValueError("Unsupported clipboard mode")
    from .images import load_image,convert_image
    from PySide6.QtCore import QBuffer,QIODevice
    image=load_image(path)
    if store.settings.get("convert_srgb",True):image=convert_image(image)
    buf=QBuffer();buf.open(QIODevice.OpenModeFlag.WriteOnly)
    if image.isNull() or not image.save(buf,"PNG"):raise ValueError("Could not encode clipboard image")
    data=bytes(buf.data())
    if mode=="image":clipboard_write("image/png",data);return
    # File clipboard representations must survive edits, renames and history
    # deletion. Each copy owns a stable snapshot, never a mutable draft path.
    folder=store.root/"clipboard"/uuid.uuid4().hex;folder.mkdir(parents=True)
    target=folder/Path(name or Path(path).name).with_suffix(".png").name
    try:
        target.write_bytes(data)
        run([Path(__file__).resolve().parent.parent/"native/clipboard-helper",mode,target,target.resolve().as_uri()],timeout=10)
    except Exception:
        shutil.rmtree(folder);raise


def copy_file(path,store=None,name=None):
    """Offer an independent file snapshot, using copy-on-write when available."""
    store=store or Store();path=Path(path)
    folder=store.root/"clipboard"/uuid.uuid4().hex;folder.mkdir(parents=True)
    target=folder/Path(name or path.name).with_suffix(path.suffix).name
    try:
        # GNU cp clones extents on supporting filesystems and streams otherwise.
        # Neither path holds a whole recording in RAM or shares mutable inodes.
        run(["cp","--reflink=auto","--sparse=always","--",path,target],timeout=3600)
        run([Path(__file__).resolve().parent.parent/"native/clipboard-helper","file",target,target.resolve().as_uri()],timeout=10)
        return target
    except Exception:
        shutil.rmtree(folder);raise


def clipboard_write(mime,data):
    # wl-copy forks an owner process which can inherit stdout/stderr. PIPEs
    # would wait for that long-lived owner to close, freezing the calling UI.
    with tempfile.TemporaryFile() as errors:
        result=subprocess.run(["wl-copy","--type",mime],input=data,stdout=subprocess.DEVNULL,stderr=errors,timeout=10)
        if result.returncode:
            errors.seek(0);raise RuntimeError(errors.read().decode(errors="replace") or "Clipboard copy failed")


def copy_text(text): clipboard_write("text/plain;charset=utf-8",text.encode())


def ocr(path, languages="eng", linebreaks=True):
    from .ocr import recognize
    return recognize(path,languages,linebreaks)


def read_qr(path):
    import cv2
    image = cv2.imread(str(path))
    if image is None: raise ValueError("Could not open image")
    detector = cv2.QRCodeDetector()
    found, values, _, _ = detector.detectAndDecodeMulti(image)
    return "\n".join(v for v in values if v) if found else ""


def scroll_step(horizontal=False, amount=3):
    helper = Path(__file__).resolve().parent.parent/"native"/"scroll-helper"
    if not helper.exists(): raise RuntimeError("Scrolling helper is missing. Run install.sh.")
    run([helper,"horizontal" if horizontal else "vertical",str(amount)])
