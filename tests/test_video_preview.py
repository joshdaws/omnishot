import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import time
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from omnishot import backend
from omnishot.recording import VideoEditor
from omnishot.video_preview import toggle_fullscreen


def test_fullscreen_keeps_composition_player_and_edits(tmp_path):
    app=QApplication.instance() or QApplication([]);source=tmp_path/"source.mp4"
    backend.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc2=size=320x240:rate=15:duration=2","-c:v","libx264","-threads","1",source])
    e=VideoEditor(source,backend.Store(tmp_path/"data"));e.show();e.player.pause()
    deadline=time.monotonic()+3
    while e.last_frame is None and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert e.last_frame is not None
    e.padding.setValue(24);e.styles.update(background2="#4869bc",camera=False);e.refresh_preview()
    expected=e.edit_options();image=e.preview_image.copy();player=e.player;geometry=e.geometry()
    toggle_fullscreen(e);p=e.fullscreen_preview;app.processEvents()
    assert p.isFullScreen() and p.image==image and e.player is player
    rect=p.image_rect();assert abs(rect.width()/rect.height()-image.width()/image.height())<.005
    QTest.keyClick(p,Qt.Key.Key_Right);assert 40<=e.player.position()<=80
    QTest.keyClick(p,Qt.Key.Key_Left);assert e.player.position()==0
    QTest.keyClick(p,Qt.Key.Key_Escape);app.processEvents()
    assert e.fullscreen_preview is None and e.geometry()==geometry and e.edit_options()==expected
    toggle_fullscreen(e);p=e.fullscreen_preview
    from shiboken6 import isValid
    e.close();app.processEvents();assert e.fullscreen_preview is None and e.player is player and not isValid(p)


def test_fullscreen_shortcuts_do_not_duplicate_playback(tmp_path):
    app=QApplication.instance() or QApplication([]);source=tmp_path/"source.mp4"
    backend.run(["ffmpeg","-v","error","-f","lavfi","-i","color=c=blue:size=160x120:rate=15:duration=3","-c:v","libx264","-threads","1",source])
    e=VideoEditor(source,backend.Store(tmp_path/"data"));e.show();e.player.pause();toggle_fullscreen(e);p=e.fullscreen_preview;app.processEvents()
    QTest.keyClick(p,Qt.Key.Key_Space);assert e.player.isPlaying()
    QTest.keyClick(p,Qt.Key.Key_Space);assert not e.player.isPlaying()
    e.start.setValue(.3);e.end.setValue(2)
    QTest.keyClick(p,Qt.Key.Key_Home);assert e.player.position()==300
    QTest.keyClick(p,Qt.Key.Key_End);assert e.player.position()==2000
    QTest.keyClick(p,Qt.Key.Key_Left,Qt.KeyboardModifier.ShiftModifier);assert e.player.position()==1000
    assert not p.volume.isEnabled() and not p.mute.isEnabled()
    QTest.keyClick(p,Qt.Key.Key_F11);assert e.fullscreen_preview is None
    e.close();app.processEvents()
    class ExpiredFrame:
        def isValid(self):raise AssertionError("Closed editor inspected a stale decoder frame")
        def toImage(self):raise AssertionError("Closed editor mapped a stale decoder surface")
    e.frame_changed(ExpiredFrame())
