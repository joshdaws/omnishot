"""Portable local Studio projects, with bounded extraction and atomic saves."""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import uuid
import zipfile

EXTENSION=".omnishot-video"
MAX_MEDIA_BYTES=50*1024**3
MAX_MANIFEST_BYTES=20*1024**2


def validate_manifest(manifest):
    if not isinstance(manifest,dict) or manifest.get("format")!="omnishot-video" or manifest.get("version")!=1:raise ValueError("Unsupported OmniShot video project")
    source=manifest.get("source","");camera=manifest.get("camera")
    if not isinstance(source,str) or not re.fullmatch(r"source\.(mp4|mov|mkv|webm|gif)",source):raise ValueError("Invalid source track")
    if camera not in (None,"camera.mp4"):raise ValueError("Invalid camera track")
    meta=manifest.get("metadata",{});opts=manifest.get("options",{})
    if not isinstance(meta,dict) or not isinstance(opts,dict):raise ValueError("Invalid project settings")
    if 'motion_blur' in opts and (type(opts['motion_blur']) is not int or not 0<=opts['motion_blur']<=3):raise ValueError('Invalid motion blur intensity')
    if 'key_commands_only' in opts and not isinstance(opts['key_commands_only'],bool):raise ValueError('Invalid keystroke filter')
    if 'key_style' in opts and opts['key_style'] not in ('Dark','Light','Custom'):raise ValueError('Invalid keystroke style')
    def number(value):return isinstance(value,(int,float)) and math.isfinite(value)
    framing=meta.get('camera_framing',[])
    if not isinstance(framing,list) or len(framing)>100000:raise ValueError('Invalid camera framing changes')
    previous=-1
    for event in framing:
        if not isinstance(event,dict) or not number(event.get('t')) or isinstance(event['t'],bool) or event['t']<previous or event['t']<0 or not isinstance(event.get('fullscreen'),bool):raise ValueError('Invalid camera framing changes')
        if 'shape' in event and event['shape'] not in ('Circle','Square','Rounded','Rectangle'):raise ValueError('Invalid camera framing shape')
        if 'placement' in event:
            value=event['placement']
            if not isinstance(value,list) or len(value)!=3 or not all(number(v) and not isinstance(v,bool) for v in value) or not all(-1<=v<=1 for v in value[:2]) or not .001<=value[2]<=1:raise ValueError('Invalid camera framing placement')
        previous=event['t']
    if 'camera_recorded_framing' in opts and not isinstance(opts['camera_recorded_framing'],bool):raise ValueError('Invalid camera framing preference')
    for key in ("cursor","events"):
        rows=meta.get(key,[])
        if not isinstance(rows,list) or len(rows)>2_000_000:raise ValueError("Invalid input track")
        for row in rows:
            if not isinstance(row,dict) or not number(row.get("t")):raise ValueError("Invalid input timestamp")
            if key=="cursor" or row.get("kind")=="click":
                if not all(number(row.get(axis)) for axis in ("x","y")):raise ValueError("Invalid cursor position")
            if row.get("kind")=="key" and (not isinstance(row.get("label",""),str) or len(row.get("label",""))>4096):raise ValueError("Invalid keystroke label")
            if row.get('kind')=='key' and 'command' in row and not isinstance(row['command'],bool):raise ValueError('Invalid command classification')
    for zoom in opts.get("zooms",[]):
        if not isinstance(zoom,dict) or not all(number(zoom.get(k)) for k in ("start","end","scale")) or zoom["start"]<0 or zoom["end"]<=zoom["start"] or not 1<=zoom["scale"]<=5:raise ValueError("Invalid zoom region")
        if not all(number(zoom.get(k,.5)) and 0<=zoom.get(k,.5)<=1 for k in ("x","y")):raise ValueError("Invalid zoom focus")
    for cut in opts.get("cuts",[]):
        if not isinstance(cut,(list,tuple)) or len(cut)!=2 or not all(number(v) for v in cut) or not 0<=cut[0]<cut[1]:raise ValueError("Invalid cut region")
    splits=opts.get('splits',[])
    if not isinstance(splits,list) or any(not number(v) or isinstance(v,bool) or not 0<v<86400 for v in splits):raise ValueError('Invalid clip boundary')
    tracks=opts.get('audio_tracks')
    if tracks is not None:
        if not isinstance(tracks,list) or len(tracks)>256:raise ValueError('Invalid audio edits')
        for track in tracks:
            if not isinstance(track,dict) or not isinstance(track.get('enabled',True),bool) or not number(track.get('volume',100)) or isinstance(track.get('volume'),bool) or not 0<=track.get('volume',100)<=200:raise ValueError('Invalid audio edits')
    edits=opts.get("event_edits",{})
    if not isinstance(edits,dict):raise ValueError("Invalid input edits")
    for key,edit in edits.items():
        if not str(key).isdigit() or int(key)>=len(meta.get("events",[])) or not isinstance(edit,dict):raise ValueError("Invalid input edit")
        if "t" in edit and (not number(edit["t"]) or edit["t"]<0):raise ValueError("Invalid edited timestamp")
        if "label" in edit and (not isinstance(edit["label"],str) or len(edit["label"])>4096):raise ValueError("Invalid edited label")
        if "hidden" in edit and not isinstance(edit["hidden"],bool):raise ValueError("Invalid event visibility")
    return source,camera


def write_project(destination,source,metadata,options,progress=None,cancel=None):
    destination=Path(destination);source=Path(source)
    if source.resolve()==destination.resolve():raise ValueError("A project cannot replace its source recording")
    source_name="source"+source.suffix.lower();meta=copy.deepcopy(metadata);meta.pop("source_path",None);camera_path=meta.pop("camera_path",None)
    manifest={"format":"omnishot-video","version":1,"source":source_name,"camera":"camera.mp4" if camera_path else None,"metadata":meta,"options":copy.deepcopy(options)}
    validate_manifest(manifest);data=json.dumps(manifest).encode()
    if len(data)>MAX_MANIFEST_BYTES:raise ValueError("Project metadata is too large")
    files=[(source,source_name)]+([(Path(camera_path),"camera.mp4")] if camera_path else [])
    total=sum(path.stat().st_size for path,name in files)
    if total>MAX_MEDIA_BYTES:raise ValueError("Project media exceeds the 50 GB limit")
    destination.parent.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(destination.parent).free<total+len(data):raise OSError("Not enough disk space to save this project")
    temporary=destination.with_name(".omnishot-"+uuid.uuid4().hex+".partial");written=0
    try:
        with zipfile.ZipFile(temporary,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
            archive.writestr("manifest.json",data)
            for path,name in files:
                with path.open("rb") as reader,archive.open(name,"w",force_zip64=True) as writer:
                    while chunk:=reader.read(1024*1024):
                        if cancel and cancel.is_set():raise InterruptedError("Project save cancelled")
                        writer.write(chunk);written+=len(chunk)
                        if progress:progress(round(written/max(1,total)*100))
        if cancel and cancel.is_set():raise InterruptedError("Project save cancelled")
        temporary.replace(destination)
    finally:temporary.unlink(missing_ok=True)


def read_project(path,store):
    path=Path(path);stat=path.stat();identity=hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:24]
    parent=store.root/"video-projects";parent.mkdir(exist_ok=True);folder=parent/f"{identity}-{stat.st_mtime_ns}"
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist();names=[entry.filename for entry in entries]
        if len(names)!=len(set(names)) or len(entries)>3:raise ValueError("Unexpected project entries")
        info=archive.getinfo("manifest.json")
        if info.file_size>MAX_MANIFEST_BYTES:raise ValueError("Project metadata is too large")
        manifest=json.loads(archive.read(info));source,camera=validate_manifest(manifest)
        expected={"manifest.json",source}|({camera} if camera else set())
        if set(names)!=expected:raise ValueError("Unexpected or missing project tracks")
        total=sum(entry.file_size for entry in entries)
        if total>MAX_MEDIA_BYTES+MAX_MANIFEST_BYTES:raise ValueError("Project media exceeds the 50 GB limit")
        digest=hashlib.sha256(json.dumps([(entry.filename,entry.CRC,entry.file_size) for entry in entries]).encode()).hexdigest()[:12]
        folder=parent/f"{identity}-{stat.st_mtime_ns}-{digest}"
        if not (folder/"ready.json").exists():
            if shutil.disk_usage(parent).free<total:raise OSError("Not enough disk space to open this project")
            staging=parent/(".extract-"+uuid.uuid4().hex);staging.mkdir()
            try:
                for name in expected:
                    with archive.open(name) as reader,(staging/name).open("wb") as writer:shutil.copyfileobj(reader,writer,1024*1024)
                (staging/"ready.json").write_text("{}")
                try:staging.rename(folder)
                except FileExistsError:
                    if not (folder/"ready.json").exists():raise
            finally:
                if staging.exists():shutil.rmtree(staging)
    metadata=manifest["metadata"];metadata["source_path"]=str(folder/source)
    if camera:metadata["camera_path"]=str(folder/camera)
    else:metadata.pop("camera_path",None)
    return folder/source,metadata,manifest["options"]
