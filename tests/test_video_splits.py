import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from omnishot.timeline import Timeline
from omnishot.video_splits import clean_splits,clips


def test_split_frame_boundaries_and_clip_delete_restore():
    app=QApplication.instance() or QApplication([]);t=Timeline();t.resize(900,136);t.set_duration(12000);t.set_frame_rate(15);t.show();app.processEvents()
    assert not t.split_at(0) and not t.split_at(12)
    assert t.split_at(4.019) and t.splits==[4.0] and not t.split_at(4.01)
    t.set_position(8000);QTest.keyClick(t,Qt.Key.Key_B,Qt.KeyboardModifier.ControlModifier);assert t.splits==[4.,8.]
    assert t.clips()==[(0.,4.),(4.,8.),(8.,12.)]
    QTest.mouseClick(t,Qt.MouseButton.LeftButton,pos=QPoint(round(t.x(6)),88));assert t.selected==('clip',1)
    QTest.keyClick(t,Qt.Key.Key_Delete);assert t.cuts==[[4.,8.]] and t.clips()==[(0.,4.),(8.,12.)]
    assert not t.split_at(6)
    QTest.mouseClick(t,Qt.MouseButton.LeftButton,pos=QPoint(round(t.x(6)),88));QTest.keyClick(t,Qt.Key.Key_Delete);assert not t.cuts
    QTest.keyClick(t,Qt.Key.Key_B);assert t.cut_mode
    QTest.mouseClick(t,Qt.MouseButton.LeftButton,pos=QPoint(round(t.x(10)),88));assert abs(t.splits[-1]-10)<1/15
    QTest.keyClick(t,Qt.Key.Key_Escape);assert not t.cut_mode
    t.start=1;t.end=11;t.cuts=[[5,6]];assert not t.split_at(.5) and not t.split_at(11.5)
    assert t.split_at(2) and all(a>=1 and b<=11 for a,b in t.clips())
    t.set_duration(30000);t.splits=[i/15 for i in range(1,450)];assert len(t.thumbnail_tiles())<30;t.close()


def test_split_normalization_and_cut_intersections():
    assert clean_splits([3,2,2,True,'2',float('nan'),float('inf'),-1,90000])==[2.,3.]
    assert clean_splits(None)==[]
    assert clips(1,9,[[2,4],[3,5],[8,10]],[3,6,7])==[(1,2),(5,6),(6,7),(7,8)]
    import pytest
    from omnishot.video_project import validate_manifest
    manifest=dict(format='omnishot-video',version=1,source='source.mp4',metadata={})
    for invalid in ([True],[float('nan')],[-1],['3'],None):
        with pytest.raises(ValueError,match='clip boundary'):validate_manifest(dict(manifest,options=dict(splits=invalid)))
