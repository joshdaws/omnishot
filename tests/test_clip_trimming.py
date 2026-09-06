import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from omnishot.timeline import Timeline
from omnishot.video_splits import trim_clip,clips


def test_clip_trim_restore_and_neighbor_limits():
    args=(0,12,[],[4,8],(4,8))
    cuts,bounds=trim_clip(*args,'start',5.02,15)
    assert cuts==[[4,5]] and bounds==(5,8)
    cuts,bounds=trim_clip(0,12,cuts,[4,8],bounds,'end',6,15)
    assert cuts==[[4,5],[6,8]] and bounds==(5,6)
    cuts,bounds=trim_clip(0,12,cuts,[4,8],bounds,'start',-100,15)
    assert cuts==[[6,8]] and bounds==(4,6)
    cuts,bounds=trim_clip(0,12,cuts,[4,8],bounds,'end',100,15)
    assert not cuts and bounds==(4,8)
    assert trim_clip(*args,'start',100,15)[1][1]-trim_clip(*args,'start',100,15)[1][0]==pytest.approx(1/15)
    # Existing gaps cannot consume an adjacent retained interval; restoring a
    # whole gap joins same-source intervals when no explicit split exists.
    cuts,bounds=trim_clip(1,11,[[2,5],[6,7]],[],(5,6),'start',0,30)
    assert cuts==[[6,7]] and bounds==(2,6)
    assert clips(1,11,cuts,[])==[(1,6),(7,11)]


def test_native_widget_edge_gesture_reverse_cancel_and_frame_snap():
    app=QApplication.instance() or QApplication([]);t=Timeline();t.resize(1232,136);t.set_duration(12000);t.set_frame_rate(15);t.splits=[4,8];t.show();app.processEvents()
    point=lambda s:QPoint(round(t.x(s)),88)
    QTest.mouseClick(t,Qt.MouseButton.LeftButton,pos=point(6));assert t.selected==('clip',1)
    QTest.mousePress(t,Qt.MouseButton.LeftButton,pos=point(4));assert t.drag[:3]==('clip',1,'start')
    QTest.mouseMove(t,point(5));assert t.cuts==[[4,5]]
    QTest.mouseMove(t,point(4));assert not t.cuts
    QTest.mouseMove(t,point(5.02));QTest.mouseRelease(t,Qt.MouseButton.LeftButton,pos=point(5.02));assert t.cuts==[[4,5]]
    QTest.mousePress(t,Qt.MouseButton.LeftButton,pos=point(8));QTest.mouseMove(t,point(6));assert t.cuts==[[4,5],[6,8]]
    QTest.keyClick(t,Qt.Key.Key_Escape);QTest.mouseRelease(t,Qt.MouseButton.LeftButton,pos=point(6));assert t.cuts==[[4,5]] and t.selected==('clip',1)
    QTest.mousePress(t,Qt.MouseButton.LeftButton,pos=point(5));QTest.mouseMove(t,point(0));QTest.mouseRelease(t,Qt.MouseButton.LeftButton,pos=point(0));assert not t.cuts and t.clips()==[(0,4),(4,8),(8,12)]
    t.close()
