import pytest
import numpy as np
from PySide6.QtCore import QPointF,Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from omnishot.backend import Store
from omnishot.editor import Editor


@pytest.mark.parametrize('delta',[(-130,-80),(-130,0),(-130,80),(0,-80),(0,80),(130,-80),(130,0),(130,80)])
def test_pencil_all_directions_are_visible_and_committed(tmp_path,delta):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data');store.settings.update(annotation_shadow=False,auto_expand_canvas=False)
    editor=Editor(store.add(image=np.full((350,500,3),255,np.uint8)),store);editor.show();QTest.qWait(10);editor.set_tool('pencil')
    a=editor.view.mapFromScene(QPointF(250,170));b=editor.view.mapFromScene(QPointF(250+delta[0],170+delta[1]))
    QTest.mousePress(editor.view.viewport(),Qt.MouseButton.LeftButton,pos=a)
    event=QMouseEvent(QMouseEvent.Type.MouseMove,QPointF(b),editor.view.viewport().mapToGlobal(b),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);app.sendEvent(editor.view.viewport(),event)
    draft=editor.view.draft
    for point in draft.props['points']:assert draft.boundingRect().contains(QPointF(*point))
    QTest.mouseRelease(editor.view.viewport(),Qt.MouseButton.LeftButton,pos=b)
    assert len(editor.objects)==1
    obj=editor.objects[0];points=obj.props['points']
    assert min(v[0] for v in points)>=0 and min(v[1] for v in points)>=0
    assert obj.props['w']==max(v[0] for v in points) and obj.props['h']==max(v[1] for v in points)
    rendered=editor.render();assert rendered!=editor.base
    editor.undo();assert not editor.objects;editor.redo();assert editor.render()==rendered
    project=tmp_path/'pencil.omnishot';editor.write_project(project);other=Editor(project,store)
    assert other.render()==rendered;other.close();editor.close()


def test_pencil_repeated_direction_changes_keep_every_scene_point(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data');store.settings.update(annotation_shadow=False,auto_expand_canvas=False)
    editor=Editor(store.add(image=np.full((350,500,3),255,np.uint8)),store);editor.show();QTest.qWait(10);editor.set_tool('pencil')
    path=[(250,170),(140,220),(320,260),(380,90),(110,80),(250,170)]
    positions=[editor.view.mapFromScene(QPointF(*point)) for point in path]
    expected=[editor.view.mapToScene(point) for point in positions]
    QTest.mousePress(editor.view.viewport(),Qt.MouseButton.LeftButton,pos=positions[0])
    for point in positions[1:]:
        event=QMouseEvent(QMouseEvent.Type.MouseMove,QPointF(point),editor.view.viewport().mapToGlobal(point),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);app.sendEvent(editor.view.viewport(),event)
    QTest.mouseRelease(editor.view.viewport(),Qt.MouseButton.LeftButton,pos=positions[-1])
    assert len(editor.objects)==1
    obj=editor.objects[0]
    for local,scene in zip(obj.props['points'],expected):assert (obj.pos()+QPointF(*local)-scene).manhattanLength()<.001
    assert len(obj.props['points'])==len(path)
    editor.close()
