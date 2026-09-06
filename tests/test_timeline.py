import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from omnishot.timeline import Timeline


def test_drag_resize_seek_and_delete():
    app=QApplication.instance() or QApplication([])
    timeline=Timeline();timeline.resize(800,136);timeline.set_duration(10000)
    timeline.zooms=[{"start":2.,"end":4.,"scale":1.8,"x":.5,"y":.5}]
    timeline.cuts=[[6.,7.]];timeline.show();app.processEvents()
    def drag(a,b):
        QTest.mousePress(timeline,Qt.MouseButton.LeftButton,pos=a)
        QTest.mouseMove(timeline,b)
        QTest.mouseRelease(timeline,Qt.MouseButton.LeftButton,pos=b)
    drag(QPoint(round(timeline.x(3)),44),QPoint(round(timeline.x(4)),44))
    assert abs(timeline.zooms[0]["start"]-3)<.03
    drag(QPoint(round(timeline.x(5)),44),QPoint(round(timeline.x(6)),44))
    assert abs(timeline.zooms[0]["end"]-6)<.03
    drag(QPoint(round(timeline.x(0)),88),QPoint(round(timeline.x(1)),88))
    assert abs(timeline.start-1)<.03
    seek=[];timeline.seek.connect(seek.append)
    QTest.mouseClick(timeline,Qt.MouseButton.LeftButton,pos=QPoint(round(timeline.x(8)),15))
    assert abs(seek[-1]-8000)<20
    QTest.mouseClick(timeline,Qt.MouseButton.LeftButton,pos=QPoint(round(timeline.x(6.5)),95))
    QTest.keyClick(timeline,Qt.Key.Key_Delete)
    assert timeline.cuts==[]
    timeline.close()


def test_zoom_pan_cancel_and_long_recording_bounds():
    import copy
    app=QApplication.instance() or QApplication([]);t=Timeline();t.resize(800,136);t.set_duration(60000);t.set_frame_rate(15);t.show();app.processEvents()
    t.set_position(20000);anchor=t.x(20);t.set_zoom(70,anchor)
    assert abs(t.time_at(anchor)-20)<.001 and t.scroll.maximum()>0
    t.scroll.setValue(22000)
    for seconds in (22,24,26):assert abs(t.time_at(t.x(seconds))-seconds)<.001
    t.zooms=[dict(start=23,end=25,scale=2)];before=copy.deepcopy(t.zooms)
    a=QPoint(round(t.x(24)),44);b=a+QPoint(45,0)
    QTest.mousePress(t,Qt.MouseButton.LeftButton,pos=a);QTest.mouseMove(t,b);assert t.zooms!=before
    QTest.keyClick(t,Qt.Key.Key_Escape);QTest.mouseRelease(t,Qt.MouseButton.LeftButton,pos=b);assert t.zooms==before and not t.auto_scroll.isActive()
    t.set_duration(86400000);t.set_frame_rate(60);t.set_zoom(100);t.scroll.setValue(40000000)
    assert t.visible_span()<2 and abs(t.pixels_per_second()-480)<.01
    assert len(t.thumbnail_tiles())<25 and t.grab().width()==800
    t.set_playing(True);t.manual_scroll_until=0;t.set_position(60000000)
    assert t.offset()<=60000<=t.offset()+t.visible_span()
    t.set_zoom(0);assert t.scroll.value()==0 and t.scroll.maximum()==0;t.close()


def test_thumbnail_pixels_cache_limit_and_close(tmp_path):
    import time
    from PySide6.QtGui import QImage,QColor
    from omnishot import backend
    from omnishot.timeline_thumbnails import ThumbnailCache
    from omnishot.widgets import JOBS
    app=QApplication.instance() or QApplication([]);source=tmp_path/'colors.mp4'
    backend.run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:size=160x90:rate=15:duration=1','-f','lavfi','-i','color=blue:size=160x90:rate=15:duration=1','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-c:v','libx264','-threads','1',source])
    cache=ThumbnailCache(source);cache.request([0,1500])
    end=time.monotonic()+4
    while cache.running and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert not cache.running and len(cache.images)==2
    assert cache.get(0).pixelColor(20,20).red()>240 and cache.get(1500).pixelColor(20,20).blue()>240
    image=QImage(32,20,QImage.Format.Format_RGB888);image.fill(QColor('green'))
    cache.complete({i+10000: image for i in range(300)})
    assert len(cache.images)<=cache.LIMIT
    cache.request(range(0,1900,25));cache.close()
    end=time.monotonic()+4
    while cache.running and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert not cache.running and not cache.images and cache.closed


def test_wheel_zoom_anchor_and_horizontal_scrolling():
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QWheelEvent
    app=QApplication.instance() or QApplication([]);t=Timeline();t.resize(800,136);t.set_duration(120000);t.show();app.processEvents()
    t.set_zoom(60);t.update_scroll(20);pointer=QPointF(400,80);anchor=t.time_at(pointer.x())
    def wheel(pixels,angle,mods=Qt.KeyboardModifier.NoModifier):
        event=QWheelEvent(pointer,pointer,pixels,angle,Qt.MouseButton.NoButton,mods,Qt.ScrollPhase.ScrollUpdate,False)
        app.sendEvent(t,event);assert event.isAccepted()
    wheel(QPoint(),QPoint(0,120),Qt.KeyboardModifier.ControlModifier)
    assert t.zoom_level==68 and abs(t.time_at(pointer.x())-anchor)<.001
    before=t.offset();pps=t.pixels_per_second();wheel(QPoint(-50,0),QPoint())
    assert abs(t.offset()-before-50/pps)<.001
    before=t.offset();wheel(QPoint(),QPoint(0,-120))
    assert abs(t.offset()-before-90/pps)<.001
    wheel(QPoint(0,-80),QPoint(),Qt.KeyboardModifier.ControlModifier)
    assert t.zoom_level==58;t.close()
