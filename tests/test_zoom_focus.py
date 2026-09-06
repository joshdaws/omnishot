import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import numpy as np
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from omnishot.zoom_focus import ZoomFocus
from omnishot.studio import compose_frame


def test_visual_zoom_move_resize_and_bounds():
    app=QApplication.instance() or QApplication([])
    image=QImage(800,400,QImage.Format.Format_RGB32);image.fill(Qt.GlobalColor.white)
    widget=ZoomFocus(image);widget.resize(600,320);widget.show();app.processEvents()
    values=[];widget.changed.connect(lambda *value:values.append(value))
    center=widget.focus_rect().center().toPoint()
    QTest.mousePress(widget,Qt.MouseButton.LeftButton,pos=center)
    QTest.mouseMove(widget,center+QPoint(40,20));QTest.mouseRelease(widget,Qt.MouseButton.LeftButton)
    assert widget.cx>.55 and widget.cy>.55 and values
    corner=widget.corners()[2].toPoint();before=widget.scale
    QTest.mousePress(widget,Qt.MouseButton.LeftButton,pos=corner)
    QTest.mouseMove(widget,corner+QPoint(25,12));QTest.mouseRelease(widget,Qt.MouseButton.LeftButton)
    assert widget.scale<before
    widget.set_values(3,1,1)
    assert widget.image_rect().adjusted(-.001,-.001,.001,.001).contains(widget.focus_rect())
    old=widget.cx;QTest.keyClick(widget,Qt.Key.Key_Left,Qt.KeyboardModifier.ShiftModifier)
    assert abs(widget.cx-(old-.01))<1e-6
    widget.close()


def test_visual_frame_matches_export_focus():
    app=QApplication.instance() or QApplication([])
    source=np.zeros((200,400,3),np.uint8);source[:100,:200]=[255,0,0]
    source[100:,200:]=[0,255,0]
    widget=ZoomFocus();widget.set_values(2,.75,.75)
    zoom=dict(start=0,end=3,scale=widget.scale,x=widget.cx,y=widget.cy)
    result=compose_frame(source,1.5,{},dict(zooms=[zoom],cursor=False))
    assert result.pixelColor(200,100).getRgb()[:3]==(0,255,0)
    assert result.pixelColor(20,20).getRgb()[:3]==(0,255,0)
    widget.close()
