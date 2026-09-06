"""Keep a usable history entry when a recording's presentation export fails."""
import json
import os
from pathlib import Path
import shutil
import time
import uuid
from . import backend


def valid_video(path):
    try:
        result=json.loads(backend.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","json",path],timeout=10))
        return any(s.get("width",0)>0 and s.get("height",0)>0 for s in result.get("streams",[]))
    except (OSError,RuntimeError,ValueError):return False


def recover(store,path,options,message,prefer_source=False):
    path=Path(path);metadata_path=path.with_suffix(".studio.json")
    from .recording_checkpoint import restore_checkpoint
    restored=False
    try:restored=restore_checkpoint(store,path)
    except OSError:pass  # Preserve the video even if a full disk blocks metadata.
    try:metadata=json.loads(metadata_path.read_text())
    except (OSError,ValueError):metadata={}
    candidates=[Path(metadata["source_path"])] if metadata.get("source_path") else []
    candidates.append(store.root/"tracks"/(path.stem+"-source.mp4"))
    raw=next((p for p in candidates if p.resolve()!=path.resolve() and p.is_file() and valid_video(p)),None) if prefer_source else None
    if raw is not None or not valid_video(path):
        raw=raw or next((p for p in candidates if p.is_file() and valid_video(p)),None)
        if raw is None:return None
        temporary=path.with_name(path.stem+"-recover-"+uuid.uuid4().hex[:8]+".mp4")
        try:
            # The source is immutable and VideoEditor refuses to overwrite it.
            # A hard link also works when export failed because the disk filled.
            try:os.link(raw,temporary)
            except OSError:shutil.copy2(raw,temporary)
            temporary.replace(path)
        finally:temporary.unlink(missing_ok=True)
    record=store.metadata(path);record.update(kind="video",created=record.get("created",time.time()),options=options,recovery_error=str(message))
    try:store.atomic_json(path.with_suffix(".json"),record)
    except OSError:
        # History can discover the valid MP4 without its optional sidecar,
        # including when a full disk prevented saving the recovery message.
        pass
    if restored:
        try:path.with_suffix(".studio.checkpoint").unlink(missing_ok=True)
        except OSError:pass
    return str(path)
