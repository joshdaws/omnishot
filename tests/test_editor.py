import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import json
import math
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPointF,QRect
from PySide6.QtGui import QColor,QFont,QPainter,QImage
from PySide6.QtTest import QTest
from PIL import Image
from omnishot.backend import Store
from omnishot.editor import Editor,Annotation


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(app,tmp_path):
    p=tmp_path/"source.png";Image.new("RGB",(800,500),"white").save(p)
    e=Editor(p,Store(tmp_path/"data"));e.show();app.processEvents();yield e;e.close()


def test_draw_undo_redo_export(editor,app):
    e=editor;e.set_tool("rect")
    a=e.view.mapFromScene(QPointF(70,60));b=e.view.mapFromScene(QPointF(270,200))
    QTest.mousePress(e.view.viewport(),Qt.MouseButton.LeftButton,pos=a)
    QTest.mouseMove(e.view.viewport(),b,20)
    QTest.mouseRelease(e.view.viewport(),Qt.MouseButton.LeftButton,pos=b)
    assert len(e.objects)==1
    before=e.render();assert before.pixelColor(70,100)!=QColor("white")
    e.undo();assert len(e.objects)==0
    e.redo();assert len(e.objects)==1
    assert e.render()==before


@pytest.mark.parametrize('style',['standard','open','double','curved'])
@pytest.mark.parametrize('reverse',[False,True])
def test_arrowhead_wings_are_selectable(editor,style,reverse):
    e=editor;obj=Annotation(dict(kind='arrow',x=80,y=100,w=220,h=60,ax=int(reverse),ay=int(reverse),bx=int(not reverse),by=int(not reverse),width=16,style=style,color='#ff0000'),e)
    e.objects.append(obj);e.scene.addItem(obj)
    a=obj.handles()['a'];b=obj.handles()['b'];direction=b-((a+b)/2+QPointF(0,-40)) if style=='curved' else b-a
    angle=math.atan2(direction.y(),direction.x())
    for tip,theta in [(b,angle)]+([(a,angle+math.pi)] if style=='double' else []):
        for sign in (-1,1):
            wing=tip-QPointF(math.cos(theta+sign*.5)*60,math.sin(theta+sign*.5)*60)
            assert obj.shape().contains(wing)
            assert e.scene.itemAt(obj.mapToScene(wing),e.view.transform()) is obj


def test_tapered_arrow_widens_toward_head_and_preserves_legacy(editor,tmp_path):
    e=editor;props=dict(kind='arrow',x=60,y=100,w=280,h=1,ax=0,ay=0,bx=1,by=0,width=16,style='standard',color='#ff0000',shadow=False)
    obj=Annotation(props,e);e.objects.append(obj);e.scene.addItem(obj);e.commit();legacy=e.render()
    obj.props['arrow_taper']=True;obj.update();e.commit();tapered=e.render()
    def thickness(image,x):return sum(image.pixelColor(x,y).green()<150 for y in range(70,130))
    assert thickness(tapered,80)<thickness(tapered,220)<thickness(legacy,220)
    assert thickness(legacy,80)==thickness(legacy,220)
    path=tmp_path/'taper.omnishot';e.write_project(path);reopened=Editor(path,e.store)
    assert reopened.render()==tapered and reopened.objects[0].props['arrow_taper'];reopened.close()
    e.undo();assert e.render()==legacy;e.redo();assert e.render()==tapered


def test_unmodified_pin_key_types_normally_in_inline_text(editor,app):
    from PySide6.QtGui import QKeySequence
    e=editor;e.store.settings['annotation_pin_shortcut']='J';e.apply_annotation_shortcuts();requests=[];e.pin_requested.connect(requests.append)
    e.set_tool('text');point=e.view.mapFromScene(QPointF(80,70));QTest.mouseClick(e.view.viewport(),Qt.MouseButton.LeftButton,pos=point)
    assert e.inline is not None and not e.pin_shortcut.isEnabled()
    QTest.keyClicks(e.view.viewport(),'j');assert e.inline.toPlainText()=='j' and not requests
    QTest.keyClick(e.view.viewport(),Qt.Key.Key_Return,Qt.KeyboardModifier.ControlModifier)
    assert e.inline is None and e.pin_shortcut.isEnabled() and e.pin_shortcut.key()==QKeySequence('J')
    QTest.keyClick(e.view.viewport(),Qt.Key.Key_J);app.processEvents();assert len(requests)==1


@pytest.mark.parametrize('light_text',[False,True])
def test_smart_highlighter_large_text_and_ctrl_override(editor,app,light_text):
    e=editor;e.base.fill(QColor('black' if light_text else 'white'))
    painter=QPainter(e.base);painter.setPen(QColor('white' if light_text else 'black'))
    font=QFont('DejaVu Sans');font.setPixelSize(96);painter.setFont(font);painter.drawText(65,180,'Big text')
    font.setPixelSize(20);painter.setFont(font);painter.drawText(65,235,'A neighboring smaller line');painter.end()
    sample=e.base.convertToFormat(QImage.Format.Format_Grayscale8)
    pixels=np.asarray(sample.bits(),dtype=np.uint8).reshape(sample.height(),sample.bytesPerLine())[:,:sample.width()]
    ys,xs=np.where(pixels[:210]>235 if light_text else pixels[:210]<20)
    next_rows,_=np.where(pixels[210:]>235 if light_text else pixels[210:]<20)
    top,bottom=ys.min(),ys.max()+1;assert bottom-top>65
    e.rebuild([]);e.commit();e.set_tool('highlight');app.processEvents()
    a=e.view.mapFromScene(QPointF(xs.min()-5,(top+bottom)/2-3));b=e.view.mapFromScene(QPointF(xs.max()+5,(top+bottom)/2+3))
    def draw(modifier):
        QTest.mousePress(e.view.viewport(),Qt.MouseButton.LeftButton,modifier,pos=a)
        QTest.mouseMove(e.view.viewport(),b,20)
        QTest.mouseRelease(e.view.viewport(),Qt.MouseButton.LeftButton,modifier,pos=b);app.processEvents()
        return e.objects[-1]
    snapped=draw(Qt.KeyboardModifier.NoModifier)
    assert snapped.y()<=top and snapped.y()+snapped.props['h']>=bottom
    assert snapped.y()+snapped.props['h']<210+next_rows.min() # Do not include the nearby line.
    expected=e.render();e.undo()
    manual=draw(Qt.KeyboardModifier.ControlModifier);assert manual.props['h']<10 and e.render()!=expected
    e.undo();draw(Qt.KeyboardModifier.NoModifier);assert e.render()==expected


def test_project_roundtrip_crop(editor,tmp_path):
    e=editor;obj=Annotation({"kind":"text","text":"Editable","x":100,"y":80,"w":250,"h":70,"color":"#222222"},e)
    e.objects.append(obj);e.scene.addItem(obj);e.commit();e.crop(QRect(50,40,600,400))
    p=tmp_path/"project.omnishot";e.write_project(p)
    other=Editor(p,e.store)
    assert other.base.width()==600 and other.objects[0].props["text"]=="Editable"
    assert other.objects[0].x()==50 and other.objects[0].y()==40
    assert other.render()==e.render();other.close()


@pytest.mark.parametrize('alpha',[0,64,128,255])
def test_highlighter_opacity_preserves_legacy_and_project_pixels(editor,tmp_path,alpha):
    e=editor;obj=Annotation(dict(kind='highlight',x=30,y=20,w=160,h=80,color='#00ff0000',shadow=False),e)
    e.objects.append(obj);e.scene.addItem(obj);e.commit();obj.setSelected(True)
    # Historical projects ignored the color's alpha: preserve their fixed 100.
    assert e.render().pixelColor(70,50)==QColor(255,155,155)
    assert QColor(e.picker_color()).alpha()==100
    e.set_color(QColor(255,0,0,alpha).name(QColor.NameFormat.HexArgb))
    assert obj.props['highlight_alpha']==alpha
    assert e.render().pixelColor(70,50)==QColor(255,255-alpha,255-alpha)
    expected=e.render();path=tmp_path/'opacity.omnishot';e.write_project(path);reopened=Editor(path,e.store)
    assert reopened.render()==expected;reopened.close()
    e.undo();assert e.render().pixelColor(70,50)==QColor(255,155,155)
    e.redo();assert e.render()==expected


def test_secure_redaction_export(editor):
    e=editor;obj=Annotation({"kind":"redact","x":30,"y":20,"w":120,"h":70,"color":"#000000"},e)
    e.objects.append(obj);e.scene.addItem(obj)
    image=e.render();assert image.pixelColor(60,50)==QColor("black")
    assert image.pixelColor(300,250)==QColor("white")


def test_counter_arrow_background(editor):
    e=editor
    for props in [{"kind":"counter","x":30,"y":20,"w":44,"h":44,"text":"1","color":"#ff5555"},
        {"kind":"arrow","x":150,"y":100,"w":200,"h":100,"style":"curved","color":"#ff5555"}]:
        obj=Annotation(props,e);e.objects.append(obj);e.scene.addItem(obj)
    e.background={"color":"#505588","color2":"#99ccff","padding":60,"aspect":"16:9","radius":14}
    rendered=e.render();assert rendered.width()>e.base.width();assert abs(rendered.width()/rendered.height()-16/9)<.005


def test_inline_text_typing_and_commit(editor,app):
    e=editor;e.set_tool("text");position=e.view.mapFromScene(QPointF(80,70))
    QTest.mouseClick(e.view.viewport(),Qt.MouseButton.LeftButton,pos=position);app.processEvents()
    assert e.inline is not None
    QTest.keyClicks(e.view.viewport(),"Editable label")
    QTest.keyClick(e.view.viewport(),Qt.Key.Key_Return,Qt.KeyboardModifier.ControlModifier);app.processEvents()
    assert e.inline is None
    assert e.objects[0].props["text"]=="Editable label"
    e.edit_text(e.objects[0]);QTest.keyClicks(e.view.viewport(),"Changed");QTest.keyClick(e.view.viewport(),Qt.Key.Key_Escape);app.processEvents()
    assert e.objects[0].props["text"]=="Editable label"


def test_annotation_move_duplicate_and_resize(editor,app):
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent
    e=editor;obj=Annotation({"kind":"rect","x":100,"y":100,"w":180,"h":120},e);e.objects.append(obj);e.scene.addItem(obj);obj.setSelected(True);e.commit()
    def drag(a,b,mods=Qt.KeyboardModifier.NoModifier):
        view=e.view.viewport();a=e.view.mapFromScene(QPointF(*a));b=e.view.mapFromScene(QPointF(*b))
        for kind,pos,button,buttons in [(QEvent.Type.MouseButtonPress,a,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton),(QEvent.Type.MouseMove,b,Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton),(QEvent.Type.MouseButtonRelease,b,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)]:
            event=QMouseEvent(kind,QPointF(pos),QPointF(view.mapToGlobal(pos)),button,buttons,mods);app.sendEvent(view,event)
    drag((180,160),(240,190),Qt.KeyboardModifier.ShiftModifier)
    assert abs(obj.x()-160)<2 and abs(obj.y()-100)<2
    drag((240,160),(300,200),Qt.KeyboardModifier.AltModifier)
    assert len(e.objects)==2 and abs(obj.x()-220)<2 and abs(obj.y()-140)<2
    copy=e.objects[1];assert abs(copy.x()-160)<2 and abs(copy.y()-100)<2
    right=obj.x()+obj.props["w"]-1;bottom=obj.y()+obj.props["h"]-1
    drag((right,bottom),(right+50,bottom+30))
    assert abs(obj.props["w"]-230)<3 and abs(obj.props["h"]-150)<3
    e.undo();assert abs(e.objects[0].props["w"]-180)<2


def test_background_canvas_keeps_source_coordinates_and_uncropped_export(editor):
    e=editor;e.background={"color":"#a060e0","color2":"#a060e0","padding":50,"radius":30,"aspect":"16:9","shadow":False};e.commit()
    assert e.scene.sceneRect().left()<0 and e.scene.sceneRect().width()>e.base.width()
    raw=e.render(False);assert raw.size()==e.base.size() and raw.pixelColor(0,0)==QColor("white")
    rendered=e.render();w,h,r=e.background_layout()
    assert rendered.size().width()==w and rendered.pixelColor(0,0)==QColor("#a060e0")
    assert rendered.pixelColor(round(r.center().x()),round(r.center().y()))==QColor("white")
    e.undo();assert e.background is None and e.scene.sceneRect().left()==0


def test_rotated_arrow_endpoint_and_keyboard_nudge(editor,app):
    from PySide6.QtGui import QTransform
    e=editor;obj=Annotation({"kind":"arrow","x":220,"y":180,"w":150,"h":100,"ax":0,"ay":1,"bx":1,"by":0},e);obj.setTransform(QTransform().rotate(25));e.objects.append(obj);e.scene.addItem(obj);obj.setSelected(True);e.commit()
    a=obj.mapToScene(obj.handles()["a"]);b=obj.mapToScene(obj.handles()["b"]);target=b+QPointF(70,30)
    QTest.mousePress(e.view.viewport(),Qt.MouseButton.LeftButton,pos=e.view.mapFromScene(b));QTest.mouseMove(e.view.viewport(),e.view.mapFromScene(target));QTest.mouseRelease(e.view.viewport(),Qt.MouseButton.LeftButton,pos=e.view.mapFromScene(target))
    assert (obj.mapToScene(obj.handles()["a"])-a).manhattanLength()<2
    assert (obj.mapToScene(obj.handles()["b"])-target).manhattanLength()<2
    old=obj.pos();QTest.keyClick(e.view.viewport(),Qt.Key.Key_Right,Qt.KeyboardModifier.ShiftModifier);assert obj.pos()==old+QPointF(10,0)
    QTest.keyClick(e.view.viewport(),Qt.Key.Key_D,Qt.KeyboardModifier.ControlModifier);assert len(e.objects)==2
