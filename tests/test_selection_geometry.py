from PySide6.QtCore import QRect,Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
import numpy as np
from omnishot.selection_geometry import move_selection,resize_selection,size_selection


def test_aspect_resize_anchors_and_screen_edges_on_every_handle():
    bounds=QRect(-1800,-200,3720,1325);original=QRect(-300,100,640,400)
    for edge in ('lt','t','rt','r','rb','b','lb','l'):
        for dx,dy in ((130,80),(-130,-80),(5000,5000),(-5000,-5000),(130,-80)):
            result=resize_selection(original,edge,dx,dy,bounds,1.6,40)
            assert bounds.contains(result) and min(result.width(),result.height())>=40
            assert abs(result.width()-result.height()*1.6)<=1.6
            if 'l' in edge:assert result.x()+result.width()==original.x()+original.width()
            if 'r' in edge:assert result.x()==original.x()
            if 't' in edge:assert result.y()+result.height()==original.y()+original.height()
            if 'b' in edge:assert result.y()==original.y()


def test_typed_size_uses_changed_dimension_and_keeps_ratio_at_bounds():
    bounds=QRect(0,0,1800,1125);original=QRect(120,140,640,400)
    assert size_selection(original,800,400,bounds,16/9).size().toTuple()==(800,450)
    assert size_selection(original,800,360,bounds,16/9,'height').size().toTuple()==(640,360)
    result=size_selection(original,20000,360,bounds,16/9)
    assert result.getRect()==(120,140,1680,945)
    assert move_selection(result,5000,5000,bounds).getRect()==(120,180,1680,945)


def test_selector_fields_follow_constrained_size_and_ctrl_arrows():
    from omnishot.selection import Selector
    app=QApplication.instance() or QApplication([])
    screen=app.primaryScreen();monitor=dict(name=screen.name(),x=0,y=0,width=screen.size().width(),height=screen.size().height(),scale=1,focused=True)
    selector=Selector(monitor,np.zeros((monitor['height'],monitor['width'],3),np.uint8),'select',previous=[30,40,320,200])
    try:
        selector.aspect.setCurrentText('16:9');assert selector.selection.size().toTuple()==(320,180)
        selector.height_box.setValue(225);assert selector.selection.size().toTuple()==(400,225)
        selector.width_box.setValue(20000)
        assert selector.width_box.value()==selector.selection.width() and selector.height_box.value()==selector.selection.height()
        assert selector.rect().contains(selector.selection)
        selector.aspect.setCurrentText('Free');selector.width_box.setValue(320);selector.height_box.setValue(200)
        QTest.keyClick(selector,Qt.Key.Key_Right,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier)
        assert selector.selection.getRect()==(30,40,330,200) and selector.width_box.value()==330
        QTest.keyClick(selector,Qt.Key.Key_Down,Qt.KeyboardModifier.ShiftModifier)
        assert selector.selection.getRect()==(30,50,330,200)
    finally:selector.close()


def test_all_in_one_handles_do_not_cover_magnifier_pixels():
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QColor
    from omnishot.selection import Selector
    app=QApplication.instance() or QApplication([])
    screen=app.primaryScreen();monitor=dict(name=screen.name(),x=0,y=0,width=screen.size().width(),height=screen.size().height(),scale=1,focused=True)
    frame=np.full((monitor['height'],monitor['width'],3),[227,90,68],np.uint8)
    selector=Selector(monitor,frame,'select',previous=[30,40,320,200])
    try:
        selector.pointer=QPoint(100,100)
        rendered=selector.grab().toImage();ratio=rendered.devicePixelRatio()
        assert rendered.pixelColor(round(140*ratio),round(140*ratio))==QColor('#e35a44')
    finally:selector.close()
