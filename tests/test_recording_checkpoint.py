import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from omnishot.backend import Store
from omnishot.studio import Telemetry
from omnishot.recording_checkpoint import StudioCheckpoint,read_checkpoint,restore_checkpoint


def test_snapshot_deltas_normalize_closed_and_current_pauses(monkeypatch):
    trace=Telemetry((0,0,640,480),keys=True,clicks=True)
    trace.samples=[dict(t=t,x=.5,y=.5) for t in (99,100,102,103,104,105)]
    trace.events=[dict(t=t,kind='key',label=str(t)) for t in (101,103,105)]
    trace.pauses=[[102,104]];monkeypatch.setattr('omnishot.studio.time.monotonic',lambda:106)
    first,after=trace.snapshot(100)
    assert [r['t'] for r in first['cursor']]==[0,3]
    assert [r['t'] for r in first['events']]==[1,3]
    trace.samples.extend([dict(t=t,x=.2,y=.3) for t in (106,107,108)])
    trace.events.append(dict(t=108,kind='key',label='paused'))
    trace.pause_started=107;monkeypatch.setattr('omnishot.studio.time.monotonic',lambda:109)
    delta,end=trace.snapshot(100,after)
    assert [r['t'] for r in delta['cursor']]==[4] and not delta['events']
    trace.pauses.append([107,110]);trace.pause_started=None
    trace.samples.append(dict(t=111,x=.8,y=.8));monkeypatch.setattr('omnishot.studio.time.monotonic',lambda:112)
    last,_=trace.snapshot(100,end)
    assert last['cursor'][0]['t']==6 and trace.samples[-1]['t']==111


def test_checkpoint_commits_deltas_and_preserves_camera_offset(tmp_path,monkeypatch):
    store=Store(tmp_path);path=store.captures/'take.mp4';Path(str(path)+'.ts').write_text('100000000\n')
    trace=Telemetry((0,0,640,480));trace.samples=[dict(t=100.2,x=.3,y=.4)]
    camera=SimpleNamespace(path=store.root/'tracks/camera.mp4',first_time=99.8,error=None)
    from omnishot.camera_framing import CameraFraming
    camera.framing=CameraFraming();camera.framing.events=[dict(t=100.3,fullscreen=True)]
    checkpoint=StudioCheckpoint(path,dict(studio=True),trace,camera)
    try:
        deadline=time.monotonic()+3
        while checkpoint.offsets!=(1,0) and time.monotonic()<deadline:time.sleep(.02)
        assert checkpoint.offsets==(1,0)
        with trace.data_lock:trace.samples.append(dict(t=101.2,x=.5,y=.6));trace.events.append(dict(t=101.3,kind='key',label='Ctrl+K'))
        deadline=time.monotonic()+3
        while checkpoint.offsets!=(2,1) and time.monotonic()<deadline:time.sleep(.02)
        assert checkpoint.offsets==(2,1) and checkpoint.error is None
    finally:checkpoint.stop()
    result=read_checkpoint(checkpoint.path)
    assert len(result['cursor'])==2 and len(result['events'])==1
    assert abs(result['camera_offset']+.2)<.001 and result['capture_options']['studio']
    assert result['camera_framing'][0]['fullscreen'] and abs(result['camera_framing'][0]['t']-.3)<1e-6
    batches=[json.loads(line) for line in checkpoint.path.read_text().splitlines()]
    assert [len(row.get('cursor',[])) for row in batches]==[0,1,1]


def test_torn_last_batch_keeps_previous_checkpoint_and_final_sidecar_wins(tmp_path):
    store=Store(tmp_path);path=store.captures/'take.mp4';checkpoint=path.with_suffix('.studio.checkpoint')
    checkpoint.write_bytes(b'{"version":1,"source_path":"take.mp4","cursor":[{"t":1,"x":0.2,"y":0.3}]}\n{"cursor":[')
    assert restore_checkpoint(store,path)
    assert json.loads(path.with_suffix('.studio.json').read_text())['cursor'][0]['t']==1
    final=dict(version=1,cursor=[dict(t=2,x=.4,y=.5)],events=[])
    store.atomic_json(path.with_suffix('.studio.json'),final)
    assert restore_checkpoint(store,path) and json.loads(path.with_suffix('.studio.json').read_text())==final


def test_failed_append_rolls_back_to_last_committed_batch(tmp_path,monkeypatch):
    path=tmp_path/'take.mp4';checkpoint=StudioCheckpoint(path,{})
    checkpoint.stop_event.set();checkpoint.thread.join()
    checkpoint.fd=os.open(checkpoint.path,os.O_WRONLY|os.O_APPEND)
    original=os.write;calls=[]
    def partial(fd,data):
        if calls:raise OSError('Disk full')
        calls.append(True);return original(fd,data[:9])
    monkeypatch.setattr('omnishot.recording_checkpoint.os.write',partial)
    try:
        import pytest
        with pytest.raises(OSError):checkpoint.append(dict(cursor=[dict(t=1,x=.2,y=.3)]))
    finally:os.close(checkpoint.fd)
    assert checkpoint.path.read_text().endswith('\n') and not read_checkpoint(checkpoint.path)['cursor']


def test_discard_removes_checkpoint_even_if_final_metadata_cannot_be_saved(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication
    from omnishot.recording import Recorder
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path)
    rec=Recorder(store,None,dict(delay=600));rec.timer.stop();rec.countdown.stop()
    rec.telemetry=Telemetry((0,0,640,480));rec.checkpoint=StudioCheckpoint(rec.path,{},rec.telemetry)
    checkpoint=rec.checkpoint.path
    monkeypatch.setattr(store,'atomic_json',lambda *args:(_ for _ in ()).throw(OSError('Disk full')))
    monkeypatch.setattr('omnishot.backend.run',lambda *args,**kwargs:b'')
    rec.stop_telemetry(discard=True);rec.close()
    assert not checkpoint.exists() and rec.checkpoint is None


def test_queued_paused_keys_are_filtered_even_when_polled_after_resume(monkeypatch):
    trace=Telemetry((0,0,640,480),keys=True)
    replies=iter([b'100,100\nkey,37,1,1',b'200,200\nkey,38,1,0'])
    polling=iter([False,False,True]);trace.stop_event=SimpleNamespace(wait=lambda _:next(polling))
    transitions=[]
    names=SimpleNamespace(label=lambda code,*args:transitions.append(code) or str(code),close=lambda:None)
    monkeypatch.setattr('omnishot.studio.KeyNames',lambda:names)
    monkeypatch.setattr('omnishot.backend.run',lambda *args,**kwargs:next(replies))
    monkeypatch.setattr('omnishot.backend.hypr',lambda *args:[])
    trace._poll()
    assert transitions==[37,38] and [e['label'] for e in trace.events]==['38']


def test_normal_stop_saves_final_memory_beyond_last_checkpoint(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication
    from omnishot.recording import Recorder
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path)
    rec=Recorder(store,None,dict(delay=600));rec.timer.stop();rec.countdown.stop()
    Path(str(rec.path)+'.ts').write_text('100000000\n')
    trace=Telemetry((0,0,640,480));trace.samples=[dict(t=100.2,x=.2,y=.3),dict(t=100.5,x=.5,y=.6)]
    rec.telemetry=trace;rec.checkpoint=StudioCheckpoint(rec.path,{},trace)
    checkpoint=rec.checkpoint.path
    monkeypatch.setattr('omnishot.backend.run',lambda *args,**kwargs:b'')
    rec.stop_telemetry();rec.close()
    assert len(json.loads(rec.path.with_suffix('.studio.json').read_text())['cursor'])==2
    assert not checkpoint.exists()


def test_metadata_write_failure_keeps_checkpoint_for_later_recovery(tmp_path,monkeypatch):
    from omnishot.recording_recovery import recover
    store=Store(tmp_path);path=store.captures/'take.mp4';path.write_bytes(b'video')
    checkpoint=path.with_suffix('.studio.checkpoint');checkpoint.write_text('{"version":1,"cursor":[{"t":0.2,"x":0.1,"y":0.3}]}\n')
    original=store.atomic_json
    monkeypatch.setattr('omnishot.recording_recovery.valid_video',lambda path:True)
    monkeypatch.setattr(store,'atomic_json',lambda *args:(_ for _ in ()).throw(OSError('Disk full')))
    assert recover(store,path,{},'interrupted')==str(path) and checkpoint.exists()
    monkeypatch.setattr(store,'atomic_json',original)
    assert restore_checkpoint(store,path)
    assert len(json.loads(path.with_suffix('.studio.json').read_text())['cursor'])==1
