import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
import pytest
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QColor,QTransform
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from omnishot import backend
from omnishot.editor import Editor,Annotation


def test_counter_zero_layering_undo_and_portable_project(tmp_path):
    app=QApplication.instance() or QApplication([]);store=backend.Store(tmp_path/'data')
    editor=Editor(store.add(image=np.full((400,600,3),255,np.uint8)),store);editor.show();app.processEvents()
    assert editor.counter_number.value()==1
    editor.set_tool('counter');editor.counter_number.setValue(0)
    for x in (100,200):
        point=editor.view.mapFromScene(QPointF(x,100))
        QTest.mouseClick(editor.view.viewport(),Qt.MouseButton.LeftButton,pos=point)
    assert [o.props['text'] for o in editor.objects]==['0','1']
    editor.set_tool('fill');editor.color='#000000'
    start=editor.view.mapFromScene(QPointF(70,70));end=editor.view.mapFromScene(QPointF(270,180))
    QTest.mousePress(editor.view.viewport(),Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(editor.view.viewport(),end)
    assert editor.view.draft.zValue()<editor.objects[0].zValue()
    QTest.mouseRelease(editor.view.viewport(),Qt.MouseButton.LeftButton,pos=end)
    editor.objects[-1].props['z']=10**12;editor.commit()
    rendered=editor.render();counter=editor.objects[0]
    assert counter.zValue()>editor.objects[-1].zValue()
    assert editor.scene.itemAt(counter.pos()+QPointF(10,10),QTransform()) is counter
    assert rendered.pixelColor(80,80)==QColor('black')
    assert rendered.pixelColor(110,110)!=QColor('black')
    editor.undo();editor.redo();assert editor.render()==rendered
    project=tmp_path/'counters.omnishot';editor.write_project(project)
    reopened=Editor(project,store);assert reopened.render()==rendered
    assert [o.props['text'] for o in reopened.objects[:2]]==['0','1']
    # Undo with an in-progress draft must discard the deleted graphics item.
    editor.set_tool('rect');QTest.mousePress(editor.view.viewport(),Qt.MouseButton.LeftButton,pos=start)
    editor.undo();assert editor.view.draft is None
    editor.render();reopened.close();editor.close()


@pytest.mark.parametrize('padding,scale,shadow,transparent',[(0,1,True,False),(80,1.6,False,False),(200,1.6,True,True),(80,1,False,True)])
def test_window_padding_is_independent_and_scaled(tmp_path,monkeypatch,padding,scale,shadow,transparent):
    app=QApplication.instance() or QApplication([]);store=backend.Store(tmp_path/'data');store.settings.update(window_padding=padding,window_wallpaper=True)
    monkeypatch.setattr(backend,'run',lambda *a,**k:'{"int":0}')
    from omnishot import wallpaper
    monkeypatch.setattr(wallpaper,'capture_wallpaper',lambda store:'embedded-wallpaper')
    frame=np.full((round(180*scale),round(300*scale),4),255,np.uint8)
    opts=backend.window_background({'size':[300,180]},frame,shadow,store,transparent)
    assert opts['padding']==round(padding*scale) and opts['shadow']==shadow
    assert ('image_data' in opts)==(not transparent)
    opts.pop('image_data',None)
    editor=Editor(store.add(image=frame),store);editor.background=opts
    image=editor.render();assert image.width()==frame.shape[1]+2*round(padding*scale)
    assert image.height()==frame.shape[0]+2*round(padding*scale)
    if padding and not shadow:assert image.pixelColor(0,0).alpha()==0
    editor.close()
