import signal,subprocess,sys
from omnishot.recording_process import stop_discarded_process


def test_cancel_stops_an_encoder_that_ignores_interrupt_and_terminate():
    process=subprocess.Popen([sys.executable,'-u','-c','import signal,time; signal.signal(signal.SIGINT,signal.SIG_IGN); signal.signal(signal.SIGTERM,signal.SIG_IGN); print("ready",flush=True); time.sleep(60)'],stdout=subprocess.PIPE,text=True)
    try:
        assert process.stdout.readline().strip()=='ready'
        stop_discarded_process(process,grace=.05,terminate_timeout=.05)
        assert process.poll()==-signal.SIGKILL
        stop_discarded_process(process)
    finally:
        if process.poll() is None:process.kill();process.wait()


def test_cancel_allows_graceful_encoder_exit():
    process=subprocess.Popen([sys.executable,'-u','-c','import signal,time,sys; signal.signal(signal.SIGINT,lambda *_:sys.exit(0)); print("ready",flush=True); time.sleep(60)'],stdout=subprocess.PIPE,text=True)
    try:
        assert process.stdout.readline().strip()=='ready'
        stop_discarded_process(process,grace=2)
        assert process.poll()==0
    finally:
        if process.poll() is None:process.kill();process.wait()


def test_discard_does_not_need_to_write_metadata_and_removes_camera_track(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication
    from omnishot.backend import Store
    from omnishot.recording import Recorder
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data')
    rec=Recorder(store,None,dict(delay=600));rec.timer.stop();rec.countdown.stop()
    camera=store.root/'tracks/cancelled-camera.mp4';camera.parent.mkdir();camera.write_bytes(b'partial video');camera.with_suffix('.camera-log').write_text('encoder log')
    from omnishot.camera_framing import CameraFraming
    rec.camera_track=SimpleNamespace(path=camera,stop=lambda:camera,first_time=None,error=None,framing=CameraFraming())
    rec.telemetry=SimpleNamespace(stop=lambda origin:dict(version=1,cursor=[],events=[]))
    monkeypatch.setattr(store,'atomic_json',lambda *args:(_ for _ in ()).throw(OSError('Disk full')))
    try:
        rec.stop_telemetry(discard=True)
        assert not camera.exists() and not camera.with_suffix('.camera-log').exists()
        assert rec.telemetry is None and rec.camera_track is None and not rec.path.with_suffix('.studio.json').exists()
    finally:rec.close()


def test_repeated_cancel_and_stop_share_one_discard_job(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication
    from omnishot.backend import Store
    from omnishot.recording import Recorder
    app=QApplication.instance() or QApplication([]);rec=Recorder(Store(tmp_path/'data'),None,dict(delay=600));rec.countdown.stop();rec.timer.stop()
    rec.process=SimpleNamespace(poll=lambda:None);jobs=[]
    monkeypatch.setattr('omnishot.recording.background',lambda work,done,failed:jobs.append((work,done,failed)))
    try:
        rec.cancel();rec.cancel();rec.stop()
        assert len(jobs)==1 and rec.discarding and rec.stopping
    finally:rec.process=None;rec.close()
