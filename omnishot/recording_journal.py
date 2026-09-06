"""Persist unfinished takes and lease them until capture and export have ended."""
import fcntl
import json
from pathlib import Path
import time
from .recording_recovery import recover


class RecordingJournal:
    def __init__(self,store,path,options):
        self.store=store;self.path=Path(path);self.marker=self.path.with_suffix(".recording.json")
        self.lock_path=self.path.with_suffix(".recording.lock")
        self.lock=self.lock_path.open("a+b")
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.record=dict(version=1,options=options,created=time.time(),phase="recording",old_dnd=None)
        try:self.update()
        except Exception:self.close();self.lock_path.unlink(missing_ok=True);raise

    def update(self,**fields):
        self.record.update(fields);self.store.atomic_json(self.marker,self.record)

    def close(self):
        if self.lock:self.lock.close();self.lock=None

    def discard(self):
        # Rename the existing journal instead of allocating another JSON file:
        # cancelling a recording must still work when the disk is full.
        marker=self.path.with_suffix(".discarding.json")
        try:self.marker.replace(marker);self.marker=marker
        except OSError:
            try:self.update(phase="discarding")
            except OSError:pass

    def complete(self):
        try:self.marker.unlink(missing_ok=True);self.lock_path.unlink(missing_ok=True)
        except OSError:pass  # A committed sidecar is recognized on relaunch.
        finally:self.close()


def recover_interrupted(store,markers):
    """Never read or remove a take while its app or encoder still holds it.

    flock survives the app's death through the fd inherited by the encoder.
    It also covers the crash between launching that encoder and saving its PID.
    """
    result=dict(recovered=[],failed=[],pending=[])
    for marker in markers:
        marker=Path(marker)
        suffix=next((s for s in (".recording.json",".discarding.json") if marker.name.endswith(s)),None)
        if marker.parent.resolve()!=store.captures.resolve() or suffix is None:continue
        if not marker.exists():continue
        path=marker.with_name(marker.name.removesuffix(suffix)+".mp4")
        lock_path=path.with_suffix(".recording.lock")
        with lock_path.open("a+b") as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:result["pending"].append(str(marker));continue
            if not marker.exists():lock_path.unlink(missing_ok=True);continue
            try:
                record=json.loads(marker.read_text())
                if not isinstance(record,dict):raise ValueError("Invalid recording journal")
                old_dnd=record.get("old_dnd")
                if old_dnd in ("on","off","true","false"):
                    from . import backend
                    try:backend.run(["omarchy-shell","notifications","setDnd",old_dnd])
                    except RuntimeError:pass
                if suffix==".discarding.json" or record.get("phase")=="discarding":
                    store.remove(path)
                    # An abrupt exit can precede the camera sidecar write.
                    for suffix in ("-camera.mp4","-camera.camera-log"):
                        (store.root/"tracks"/(path.stem+suffix)).unlink(missing_ok=True)
                    path.with_suffix(".log").unlink(missing_ok=True)
                else:
                    metadata=store.metadata(path)
                    # A final sidecar may have committed just before app death.
                    if metadata.get("kind") in ("video","gif") and "created" in metadata:
                        completed=path.with_suffix(".gif") if metadata["kind"]=="gif" else path
                        if completed.is_file():
                            marker.unlink();lock_path.unlink(missing_ok=True);continue
                    message="OmniShot closed unexpectedly. The recorded video has been recovered."
                    saved=recover(store,path,record.get("options",{}),message,prefer_source=True)
                    if saved:
                        metadata=store.metadata(path);metadata["created"]=time.time()
                        try:store.atomic_json(path.with_suffix(".json"),metadata)
                        except OSError:pass
                        result["recovered"].append((saved,message))
                    elif not path.exists() and not (store.root/"tracks"/(path.stem+"-source.mp4")).exists():
                        pass  # App exited before the encoder wrote any video.
                    else:
                        result["failed"].append(str(path))
                        marker.replace(path.with_suffix(".failed-recording.json"));lock_path.unlink(missing_ok=True);continue
                marker.unlink(missing_ok=True);lock_path.unlink(missing_ok=True)
            except (OSError,ValueError,RuntimeError) as exc:
                result["failed"].append(f"{path}: {exc}")
                # Keep the marker for a later retry (e.g. after freeing space).
    return result
