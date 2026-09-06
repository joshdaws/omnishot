import numpy as np
from PySide6.QtCore import QRect,QPoint,Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from omnishot.selection import Selector
from omnishot.selection_group import SelectionGroup


def selectors(previous=None):
    app=QApplication.instance() or QApplication([])
    monitors=[dict(name='left',x=-300,y=0,width=480,height=320,scale=1.6),dict(name='right',x=40,y=30,width=400,height=220,scale=1)]
    result=[]
    for monitor,color in zip(monitors,[(200,50,80),(20,150,210)]):
        frame=np.full((monitor['height'],monitor['width'],3),color,np.uint8)
        selector=Selector(monitor,frame,'select');selector.resize(round(monitor['width']/monitor['scale']),round(monitor['height']/monitor['scale']));result.append(selector)
    group=SelectionGroup(result,previous)
    return app,result,group


def test_shared_geometry_preserves_previous_region_and_exact_dimensions():
    app,items,group=selectors((-100,50,300,100))
    try:
        assert [group.region(s).getRect() for s in items]==[(-100,50,300,100)]*2
        assert items[1].selection.x()==-140
        items[1].width_box.setValue(400)
        assert [group.region(s).getRect() for s in items]==[(-100,50,400,100)]*2
        QTest.keyClick(items[0],Qt.Key.Key_Right,Qt.KeyboardModifier.ControlModifier)
        assert all(s.width_box.value()==401 for s in items)
        items[0].aspect.setCurrentText('4:3')
        assert items[1].aspect.currentText()=='4:3'
        assert abs(items[0].selection.width()/items[0].selection.height()-4/3)<.01
    finally:
        for s in items:s.close()


def test_frozen_composite_uses_full_resolution_and_preserves_gap():
    app,items,group=selectors((-100,0,300,150))
    try:
        image=group.image(items[1])
        assert image.size().toTuple()==(480,240) and items[1].capture_scale()==1.6
        assert image.pixelColor(40,100)==QColor(200,50,80)
        assert image.pixelColor(190,100)==QColor('black')
        assert image.pixelColor(300,20)==QColor('black')
        assert image.pixelColor(300,100)==QColor(20,150,210)
        results=[];items[1].selected.connect(lambda *args:results.append(args));items[1].finish()
        assert results[0][0]==(-100,0,300,150) and results[0][1]==image
    finally:
        for s in items:s.close()


def test_capture_modes_and_drag_pointer_follow_across_outputs():
    app,items,group=selectors()
    try:
        items[0].choose_mode('Record video')
        assert items[1].capture_mode.currentText()=='Record video'
        assert items[1].controls.buttons['Record video'].isChecked()
        group.active=items[0];items[0].pointer=QPoint(450,80);group.pointer(items[0])
        assert items[1].pointer==QPoint(110,50) and items[1].selecting()
        group.set_region(QRect(-100,50,300,100));results=[];items[1].selected.connect(lambda *args:results.append(args));items[1].finish()
        assert results[0]==((-100,50,300,100),None,'Record video')
    finally:
        for s in items:s.close()


def test_window_mode_restores_shared_area_without_auto_capturing_peers():
    app,items,group=selectors((-100,50,300,100))
    try:
        captures=[];items[1].selected.connect(lambda *args:captures.append(args))
        items[0].choose_mode('Window')
        assert items[1].capture_mode.currentText()=='Window' and not items[1].width_box.isEnabled()
        items[0].choose_mode('Screenshot')
        assert not captures and items[1].width_box.isEnabled()
        assert group.region(items[1]).getRect()==(-100,50,300,100)
    finally:
        for s in items:s.close()
