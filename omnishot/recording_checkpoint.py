"""Incremental, local Studio recovery without rewriting a growing event history."""
import json
import os
from pathlib import Path
import threading


def frame_origin(path):
    try:return float(Path(str(path)+".ts").read_text().strip().splitlines()[-1].split()[0])/1_000_000
    except (OSError,ValueError,IndexError):return None


class StudioCheckpoint:
    def __init__(self,path,options,trace=None,camera=None):
        self.source=Path(path);self.path=self.source.with_suffix(".studio.checkpoint")
        self.trace=trace;self.camera=camera;self.offsets=(0,0);self.error=None
        self.stop_event=threading.Event();self.thread=None
        self.fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_CLOEXEC,0o600)
        try:self.append(dict(version=1,source_path=str(self.source.resolve()),capture_options=options))
        except Exception:os.close(self.fd);raise
        self.thread=threading.Thread(target=self.run,name="omnishot-studio-checkpoint",daemon=True);self.thread.start()

    def append(self,record):
        data=memoryview((json.dumps(record,separators=(",",":"))+"\n").encode());offset=os.lseek(self.fd,0,os.SEEK_END)
        try:
            while data:
                written=os.write(self.fd,data)
                if written<=0:raise OSError("Could not write recovery checkpoint")
                data=data[written:]
            os.fsync(self.fd)
        except OSError:
            # Preserve complete earlier batches if a write stops halfway.
            try:os.ftruncate(self.fd,offset)
            except OSError:pass
            raise

    def run(self):
        try:
            while not self.stop_event.wait(1):
                origin=frame_origin(self.source)
                if origin is None:continue
                metadata,offsets=self.trace.snapshot(origin,self.offsets) if self.trace else ({"cursor":[],"events":[]},self.offsets)
                camera=self.camera
                if camera and camera.first_time is not None:
                    metadata.update(camera_path=str(camera.path.resolve()),camera_offset=camera.first_time-origin)
                    if hasattr(camera,'framing'):metadata['camera_framing']=camera.framing.snapshot(origin)
                    if camera.error:metadata["camera_error"]=camera.error
                self.append(metadata);self.offsets=offsets
        except (OSError,ValueError) as exc:self.error=str(exc)
        finally:os.close(self.fd)

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=3)

    def discard(self):
        self.stop();self.path.unlink(missing_ok=True)


def read_checkpoint(path):
    """Read committed batches, tolerating an incomplete last write after SIGKILL."""
    metadata={"version":1,"cursor":[],"events":[]}
    with Path(path).open("rb") as stream:
        while True:
            line=stream.readline(8*1024*1024)
            if not line or not line.endswith(b"\n"):break
            try:record=json.loads(line)
            except (ValueError,UnicodeDecodeError):break
            if not isinstance(record,dict):break
            for key in ("cursor","events"):
                rows=record.pop(key,[])
                if isinstance(rows,list):metadata[key].extend(rows)
            metadata.update(record)
    return metadata


def restore_checkpoint(store,path):
    path=Path(path);checkpoint=path.with_suffix(".studio.checkpoint");sidecar=path.with_suffix(".studio.json")
    if not checkpoint.is_file():return False
    try:
        existing=json.loads(sidecar.read_text())
        if isinstance(existing,dict) and existing.get("version")==1:return True
    except (OSError,ValueError):pass
    metadata=read_checkpoint(checkpoint)
    # Only app-owned camera tracks are recovered from a checkpoint.
    if metadata.get("camera_path"):
        camera=Path(metadata["camera_path"]).resolve()
        from .recording_recovery import valid_video
        if camera.parent!=(store.root/"tracks").resolve() or not camera.is_file() or not valid_video(camera):
            metadata.pop("camera_path",None);metadata["camera_error"]="The interrupted camera track could not be recovered."
    store.atomic_json(sidecar,metadata)
    return True
