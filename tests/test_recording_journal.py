import json
import os
import subprocess
import sys
import time
from omnishot.backend import Store
from omnishot.recording_journal import RecordingJournal,recover_interrupted
from omnishot import recording_recovery


def test_inherited_lease_prevents_reading_or_expiring_active_take(tmp_path,monkeypatch):
    store=Store(tmp_path);path=store.captures/'take.mp4';journal=RecordingJournal(store,path,{})
    path.write_bytes(b'video');os.utime(path,(0,0))
    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],pass_fds=[journal.lock.fileno()])
    journal.close()
    try:
        assert recover_interrupted(store,[journal.marker])['pending']==[str(journal.marker)]
        store.expire();assert path.exists() and not store.history()
    finally:child.kill();child.wait()
    monkeypatch.setattr(recording_recovery,'valid_video',lambda path:True)
    result=recover_interrupted(store,[journal.marker])
    assert result['recovered'] and not result['pending']
    assert not journal.marker.exists() and not journal.lock_path.exists()
    assert len(store.history())==1 and store.history()[0]['created']>time.time()-5
    assert not recover_interrupted(store,[journal.marker])['recovered']


def test_cancel_intent_survives_crash_without_camera_metadata(tmp_path,monkeypatch):
    store=Store(tmp_path);path=store.captures/'take.mp4';path.write_bytes(b'partial')
    tracks=store.root/'tracks';tracks.mkdir();camera=tracks/'take-camera.mp4';camera.write_bytes(b'camera')
    log=camera.with_suffix('.camera-log');log.write_text('log')
    journal=RecordingJournal(store,path,{})
    monkeypatch.setattr(store,'atomic_json',lambda *args:(_ for _ in ()).throw(OSError('Disk full')))
    journal.discard();journal.close();assert journal.marker.name.endswith('.discarding.json')
    result=recover_interrupted(store,[journal.marker])
    assert not result['failed'] and not result['recovered'] and not result['pending']
    assert not path.exists() and not camera.exists() and not log.exists()


def test_unrecoverable_take_kept_and_hidden_from_retention(tmp_path,monkeypatch):
    store=Store(tmp_path);path=store.captures/'take.mp4';path.write_bytes(b'partial');os.utime(path,(0,0))
    journal=RecordingJournal(store,path,{});journal.close()
    monkeypatch.setattr(recording_recovery,'valid_video',lambda path:False)
    result=recover_interrupted(store,[journal.marker]);assert result['failed']==[str(path)]
    store.expire();assert path.read_bytes()==b'partial' and path.with_suffix('.failed-recording.json').exists()


def test_completed_gif_does_not_reappear_as_raw_video_after_crash(tmp_path):
    store=Store(tmp_path);path=store.captures/'take.mp4';gif=path.with_suffix('.gif');gif.write_bytes(b'gif')
    store.atomic_json(path.with_suffix('.json'),dict(kind='gif',created=time.time()))
    journal=RecordingJournal(store,path,{});journal.close()
    result=recover_interrupted(store,[journal.marker]);assert not any(result.values())
    assert [r['path'] for r in store.history()]==[str(gif)]


def test_interrupted_export_recovers_full_source_even_if_partial_is_playable(tmp_path,monkeypatch):
    store=Store(tmp_path);path=store.captures/'take.mp4';path.write_bytes(b'first few frames')
    source=store.root/'tracks/take-source.mp4';source.parent.mkdir();source.write_bytes(b'complete take')
    journal=RecordingJournal(store,path,dict(studio=True));journal.close()
    monkeypatch.setattr(recording_recovery,'valid_video',lambda path:True)
    result=recover_interrupted(store,[journal.marker])
    assert result['recovered'] and path.read_bytes()==b'complete take' and source.read_bytes()==b'complete take'
