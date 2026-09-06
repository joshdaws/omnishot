import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import numpy as np
from PySide6.QtCore import QPointF,QRect,Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from omnishot.backend import Store
from omnishot.editor import Editor,Annotation


def test_canvas_expands_for_outside_arrow_and_preserves_undo_project(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/"data");store.settings["auto_expand_canvas"]=True
    path=store.add(image=np.full((100,200,3),255,np.uint8));editor=Editor(path,store)
    arrow=Annotation(dict(kind="arrow",x=-60,y=40,w=180,h=1,ax=0,ay=0,bx=1,by=0,color="#ff0000",width=4),editor)
    editor.objects.append(arrow);editor.scene.addItem(arrow);editor.commit()
    assert editor.base.width()>=264 and arrow.x()>=0
    rendered=editor.render();assert rendered.pixelColor(10,40).red()>200 and rendered.pixelColor(10,40).green()<100
    project=tmp_path/"expanded.omnishot";editor.write_project(project);other=Editor(project,store)
    assert other.expand_canvas and other.render()==rendered
    editor.undo();assert editor.base.width()==200 and not editor.objects
    editor.redo();assert editor.render()==rendered
    editor.crop(QRect(70,10,90,50));assert editor.base.width()==90 and editor.base.height()==50 and not editor.expand_canvas
    editor.undo();assert editor.expand_canvas and editor.render()==rendered
    other.close();editor.close()


def test_shadow_render_excludes_selection_and_smoothing_is_optional(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/"data")
    path=store.add(image=np.full((180,260,3),255,np.uint8));editor=Editor(path,store)
    obj=Annotation(dict(kind="fill",x=60,y=40,w=90,h=60,color="#ff0000",width=2,shadow=True),editor);editor.objects.append(obj);editor.scene.addItem(obj);editor.commit()
    before=editor.render();obj.setSelected(True);after=editor.render();assert before==after
    assert after.pixelColor(105,104)!=QColor("white")
    obj.setSelected(False);editor.scene.removeItem(obj);editor.objects=[]
    pencil=Annotation(dict(kind="pencil",x=30,y=30,w=150,h=100,color="#ff0000",width=4,points=[[0,0],[50,90],[100,0],[150,90]],smooth=True),editor);editor.objects.append(pencil);editor.scene.addItem(pencil)
    smooth=editor.render();pencil.props["smooth"]=False;pencil.update();assert editor.render()!=smooth;editor.close()


def test_inverse_arrow_preference_and_alt_override(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/"data");store.settings.update(inverse_arrows=True,annotation_shadow=False)
    path=store.add(image=np.full((300,500,3),255,np.uint8));editor=Editor(path,store);editor.show();QTest.qWait(20);editor.set_tool("arrow")
    for index,mods in enumerate((Qt.KeyboardModifier.NoModifier,Qt.KeyboardModifier.AltModifier)):
        a=editor.view.mapFromScene(QPointF(70,80+80*index));b=editor.view.mapFromScene(QPointF(270,100+80*index))
        QTest.mousePress(editor.view.viewport(),Qt.MouseButton.LeftButton,mods,pos=a)
        from PySide6.QtGui import QMouseEvent
        event=QMouseEvent(QMouseEvent.Type.MouseMove,QPointF(b),editor.view.viewport().mapToGlobal(b),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,mods);app.sendEvent(editor.view.viewport(),event)
        QTest.mouseRelease(editor.view.viewport(),Qt.MouseButton.LeftButton,mods,pos=b)
    assert editor.objects[0].props["ax"]==1 and editor.objects[0].props["bx"]==0
    assert editor.objects[1].props["ax"]==0 and editor.objects[1].props["bx"]==1
    editor.close()
