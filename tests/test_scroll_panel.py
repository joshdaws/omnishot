import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from omnishot.backend import Store
from omnishot.widgets import ScrollPanel
from omnishot import widgets


def test_finish_waits_for_current_frame_without_starting_another(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);panel=ScrollPanel((10,10,200,100),Store(tmp_path/'data'))
    jobs=[];monkeypatch.setattr(widgets,'background',lambda work,done,fail:jobs.append((work,done)))
    monkeypatch.setattr(panel.visuals,'before_grab',lambda:False);monkeypatch.setattr(panel.visuals,'after_grab',lambda:None);monkeypatch.setattr(panel.visuals,'update',lambda frame:None)
    panel.running=True;panel.timer.start(10);panel.tick();assert panel.busy and len(jobs)==1
    results=[];panel.completed.connect(results.append);panel.finish()
    assert not panel.running and not panel.timer.isActive()
    panel.tick();assert len(jobs)==1
    frame=np.full((100,200,3),125,np.uint8);panel.stitcher.push(frame);jobs[0][1]((True,'Ready',frame));QTest.qWait(100)
    assert panel.closed and len(results)==1 and np.array_equal(results[0],frame)


def test_completion_releases_capture_controls_before_opening_the_next_step(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);panel=ScrollPanel((10,10,200,100),Store(tmp_path/'data'))
    calls=[];panel.mirror.enabled=True
    monkeypatch.setattr(panel.keys,'stop',lambda:calls.append('keys stopped'))
    monkeypatch.setattr(panel.visuals,'close',lambda:calls.append('visuals closed'))
    monkeypatch.setattr(panel.mirror,'start',lambda:calls.append('unexpected restart'))
    def release():panel.mirror.enabled=False;calls.append('mirror released')
    monkeypatch.setattr(panel.mirror,'stop',release)
    frame=np.full((100,200,3),125,np.uint8);panel.stitcher.push(frame);observed=[];cancelled=[]
    panel.cancelled.connect(lambda:cancelled.append(True))
    def completed(image):
        observed.append((panel.closed,panel.mirror.enabled,list(calls),image.copy()))
        # Nested modal event loops must not restart this completed capture.
        panel.keyboard_action('accept')
    panel.completed.connect(completed);panel.finish()
    assert observed[0][0] and not observed[0][1]
    assert observed[0][2]==['keys stopped','visuals closed','mirror released']
    assert np.array_equal(observed[0][3],frame) and not panel.running and not cancelled


def test_end_message_survives_unchanged_frames(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);panel=ScrollPanel((10,10,200,100),Store(tmp_path/'data'));frame=np.full((100,200,3),125,np.uint8)
    monkeypatch.setattr(widgets.backend,'grab',lambda rect:frame)
    monkeypatch.setattr(widgets,'background',lambda work,done,fail:done(work()))
    monkeypatch.setattr(panel.visuals,'before_grab',lambda:False);monkeypatch.setattr(panel.visuals,'after_grab',lambda:None);monkeypatch.setattr(panel.visuals,'update',lambda frame:None)
    panel.running=True;panel.stitcher.push(frame);panel.auto=True;panel.scrolled_last=True;panel.no_change=3;panel.tick()
    assert panel.reached_end and not panel.auto and 'Reached the end' in panel.status.text()
    panel.tick();assert 'Reached the end' in panel.status.text();panel.close()


def test_cursor_mirror_failure_retry_and_cancel_during_frame(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    panel=ScrollPanel((10,10,200,100),Store(tmp_path/'data'))
    events=[];jobs=[]
    def start():
        if not events:
            events.append('rejected');raise RuntimeError('Capture components need rebuilding')
        panel.mirror.enabled=True;events.append('start')
    def stop():
        if panel.mirror.enabled:events.append('stop');panel.mirror.enabled=False
    monkeypatch.setattr(panel.mirror,'start',start);monkeypatch.setattr(panel.mirror,'stop',stop)
    monkeypatch.setattr(widgets,'background',lambda work,done,fail:jobs.append((done,fail)))
    monkeypatch.setattr(panel.visuals,'before_grab',lambda:False)
    monkeypatch.setattr(panel.visuals,'after_grab',lambda:None)
    monkeypatch.setattr(panel.visuals,'update',lambda frame:events.append('preview'))
    panel.start();assert not panel.running and not panel.timer.isActive() and 'rebuilding' in panel.status.text()
    panel.start();assert panel.running and panel.mirror.enabled
    panel.tick();jobs[0][1]('Display disconnected')
    assert not panel.running and not panel.mirror.enabled and not panel.timer.isActive()
    assert 'Display disconnected' in panel.status.text()
    panel.start();panel.tick();assert panel.busy and panel.mirror.enabled
    result=[];panel.completed.connect(result.append);panel.close()
    assert not panel.mirror.enabled
    jobs[1][0]((True,'Ready',np.zeros((100,200,3),np.uint8)))
    assert not panel.busy and not result and events==['rejected','start','stop','start','stop']
