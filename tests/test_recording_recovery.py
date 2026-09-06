from pathlib import Path
from omnishot.backend import Store
from omnishot import recording_recovery


def test_recovers_moved_source_when_metadata_still_points_at_failed_output(tmp_path,monkeypatch):
    store=Store(tmp_path/"data");path=store.captures/"capture.mp4";path.write_bytes(b"partial export")
    source=store.root/"tracks/capture-source.mp4";source.parent.mkdir();source.write_bytes(b"valid original")
    store.atomic_json(path.with_suffix(".studio.json"),{"source_path":str(path)})
    monkeypatch.setattr(recording_recovery,"valid_video",lambda p:Path(p).exists() and Path(p).read_bytes()==b"valid original")
    assert recording_recovery.recover(store,path,{"format":"GIF"},"export failed")==str(path)
    assert path.read_bytes()==source.read_bytes()==b"valid original"
    assert store.history()[0]["recovery_error"]=="export failed"


def test_full_disk_sidecar_failure_keeps_video_discoverable(tmp_path,monkeypatch):
    store=Store(tmp_path/"data");path=store.captures/"capture.mp4"
    source=store.root/"tracks/capture-source.mp4";source.parent.mkdir();source.write_bytes(b"valid original")
    monkeypatch.setattr(recording_recovery,"valid_video",lambda p:Path(p).exists())
    monkeypatch.setattr(store,"atomic_json",lambda *args:(_ for _ in ()).throw(OSError("No space left")))
    assert recording_recovery.recover(store,path,{},"disk full")==str(path)
    assert store.history()[0]["path"]==str(path) and path.read_bytes()==b"valid original"


def test_invalid_sources_remain_untouched(tmp_path,monkeypatch):
    store=Store(tmp_path/"data");path=store.captures/"capture.mp4";path.write_bytes(b"invalid source")
    monkeypatch.setattr(recording_recovery,"valid_video",lambda p:False)
    assert recording_recovery.recover(store,path,{},"encoder failed") is None
    assert path.read_bytes()==b"invalid source"
