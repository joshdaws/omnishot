import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy,json,time,hashlib
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint,Qt,QTimer
from PySide6.QtTest import QTest
from omnishot import backend
from omnishot.recording import VideoEditor
from omnishot.video_ui import apply_background
from test_video_audio import make_source


def wait(app,predicate):
    end=time.monotonic()+4
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert predicate()


def test_complete_edit_undo_redo_and_source_preservation(tmp_path):
    app=QApplication.instance() or QApplication([]);source=tmp_path/'source.mp4';make_source(source,4)
    source.with_suffix('.studio.json').write_text(json.dumps(dict(version=1,cursor=[],events=[],capture_options=dict(audio_sources=['system','microphone']))))
    digest=hashlib.sha256(source.read_bytes()).digest();e=VideoEditor(source,backend.Store(tmp_path/'data'));e.player.pause();e.show()
    wait(app,lambda:e.timeline.duration>=4 and len(e.audio_tracks_controls.rows)==2);app.processEvents();h=e.edit_history
    assert not h.past
    states=[h.snapshot()]
    actions=[lambda:e.timeline.add_zoom_at(.5),lambda:e.timeline.split_at(2),lambda:apply_background(e,'Ocean'),lambda:e.motion.setValue(3),lambda:e.effect_controls['Camera'].fields['camera_mirror'].setChecked(True),lambda:e.camera_size.setValue(33),lambda:e.audio_tracks_controls.rows[0][2].setValue(47),lambda:e.audio_tracks_controls.rows[1][1].setChecked(False),lambda:e.audio_mono.setChecked(True),lambda:e.speed.setCurrentText('1.5'),lambda:e.format.setCurrentText('GIF')]
    for action in actions:
        action();h.flush(True);states.append(h.snapshot())
    assert len(h.past)==len(actions)
    for expected in reversed(states[:-1]):
        h.undo();assert h.snapshot()==expected
    assert not h.past and e.redo_button.isEnabled()
    for expected in states[1:]:h.redo();assert h.snapshot()==expected
    h.undo();e.padding.setValue(90);h.flush(True);assert not h.future
    current=e.edit_options();e.close();assert h.closed and not h.timer.isActive()
    e=VideoEditor(source,e.store);e.player.pause();wait(app,lambda:len(e.audio_tracks_controls.rows)==2);assert e.edit_options()==current;e.close()
    assert hashlib.sha256(source.read_bytes()).digest()==digest


def test_timeline_drag_is_one_step_and_cancel_is_not_an_edit(tmp_path):
    app=QApplication.instance() or QApplication([]);source=tmp_path/'source.mp4';make_source(source,4)
    e=VideoEditor(source,backend.Store(tmp_path/'data'));e.player.pause();e.show();wait(app,lambda:e.timeline.duration>=4)
    h=e.edit_history;t=e.timeline;point=lambda seconds:QPoint(round(t.x(seconds)),44)
    before=h.snapshot();QTest.mousePress(t,Qt.MouseButton.LeftButton,pos=point(.3))
    for second in (.6,.9,1.2,1.5):QTest.mouseMove(t,point(second));app.processEvents()
    QTest.mouseRelease(t,Qt.MouseButton.LeftButton,pos=point(1.5));wait(app,lambda:bool(h.past));assert len(h.past)==1
    after=h.snapshot();h.undo();assert h.snapshot()==before;h.redo();assert h.snapshot()==after
    QTest.mousePress(t,Qt.MouseButton.LeftButton,pos=point(2));QTest.mouseMove(t,point(3));QTest.keyClick(t,Qt.Key.Key_Escape);QTest.mouseRelease(t,Qt.MouseButton.LeftButton,pos=point(3));app.processEvents();h.flush(True)
    assert h.snapshot()==after and len(h.past)==1
    e.close()


def test_cancelled_effects_dialog_does_not_enter_history(tmp_path):
    app=QApplication.instance() or QApplication([]);source=tmp_path/'source.mp4';make_source(source,1)
    source.with_suffix('.studio.json').write_text(json.dumps({'capture_options':{'commands_only':True}}))
    e=VideoEditor(source,backend.Store(tmp_path/'data'));e.player.pause();e.show();wait(app,lambda:e.last_frame is not None)
    h=e.edit_history;before=h.snapshot()
    def cancel():
        dialog=app.activeModalWidget();assert dialog.fields['key_commands_only'].isChecked();dialog.fields['key_commands_only'].setChecked(False);dialog.fields['camera_mirror'].setChecked(True);dialog.reject()
    QTimer.singleShot(10,cancel);e.edit_effects();app.processEvents();h.flush(True)
    assert h.snapshot()==before and not h.past
    assert e.effect_controls['Keystrokes'].fields['key_commands_only'].isChecked()
    e.close()
