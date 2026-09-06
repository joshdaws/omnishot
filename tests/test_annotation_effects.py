import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QPainter,QColor,QTransform,QImage
from PySide6.QtWidgets import QApplication
from omnishot.annotation_effects import render_effect,rgba
from omnishot.backend import Store
from omnishot.editor import Editor,Annotation,qimage


def test_secure_blur_is_independent_of_covered_pixels_even_when_transformed():
    app=QApplication.instance() or QApplication([])
    for transform in (QTransform.fromTranslate(35,40),QTransform().translate(100.4,90.7).rotate(28).scale(1.3,.85)):
        originals=[]
        for color in ('#ff0000','#0000ff'):
            base=QImage(400,260,QImage.Format.Format_ARGB32);base.fill(QColor('#e8edf4'))
            painter=QPainter(base);painter.setWorldTransform(transform);painter.fillRect(QRectF(0,0,120.3,70.2),QColor(color));painter.end();originals.append(base)
        props=dict(kind='blur',w=120.3,h=70.2,strength=18,blur_mode='Secure',effect_seed=123)
        first=render_effect(originals[0],transform,props);second=render_effect(originals[1],transform,props)
        assert first==second
        assert np.all(rgba(first)[:,:,3]==255)
        assert render_effect(originals[0],transform,{**props,'blur_mode':'Smooth'})!=render_effect(originals[1],transform,{**props,'blur_mode':'Smooth'})


def test_secure_blur_at_image_edge_and_transparent_source_is_opaque():
    app=QApplication.instance() or QApplication([])
    source=qimage(np.zeros((40,80,4),np.uint8));props=dict(kind='blur',w=80,h=40,blur_mode='Secure',effect_seed=8)
    result=render_effect(source,QTransform(),props)
    assert np.all(rgba(result)[:,:,3]==255)
    changed=qimage(np.full((40,80,4),255,np.uint8))
    assert result==render_effect(changed,QTransform(),props)


def test_randomized_pixelation_is_stable_and_preserves_legacy_mode():
    app=QApplication.instance() or QApplication([]);rng=np.random.default_rng(54);source=qimage(rng.integers(0,256,(80,160,3),np.uint8));props=dict(kind='pixelate',w=160,h=80,strength=10,effect_seed=123,pixelate_mode='Randomized')
    first=render_effect(source,QTransform(),props)
    assert first==render_effect(source,QTransform(),props)
    assert first!=render_effect(source,QTransform(),{**props,'effect_seed':124})
    legacy={k:v for k,v in props.items() if k!='pixelate_mode'}
    assert render_effect(source,QTransform(),legacy)==source.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied).scaled(16,8).scaled(160,80)


def test_effect_modes_survive_selection_undo_and_project_reopening(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data');source=np.random.default_rng(3).integers(0,256,(180,300,3),np.uint8);path=store.add(image=source);editor=Editor(path,store)
    for kind,x in (('blur',20),('pixelate',160)):
        obj=Annotation(dict(kind=kind,x=x,y=30,w=110,h=90,blur_mode='Secure',pixelate_mode='Randomized'),editor);editor.objects.append(obj);editor.scene.addItem(obj)
    editor.commit();initial=editor.render();obj=editor.objects[0];obj.setSelected(True)
    assert editor.blur_mode.currentText()=='Secure'
    editor.blur_mode.setCurrentText('Smooth');assert obj.props['blur_mode']=='Smooth' and editor.render()!=initial
    editor.undo();assert editor.render()==initial
    project=tmp_path/'effects.omnishot';editor.write_project(project);other=Editor(project,store)
    assert other.render()==initial and other.objects[0].props['effect_seed']==editor.objects[0].props['effect_seed']
    other.close();editor.close()


def test_secure_mask_covers_previously_added_text(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data');path=store.add(image=np.full((180,300,3),255,np.uint8));editor=Editor(path,store)
    text=Annotation(dict(kind='text',x=80,y=60,w=45,h=45,text='9',color='#ff0000',z=1),editor)
    mask=Annotation(dict(kind='blur',x=60,y=40,w=95,h=85,blur_mode='Secure',effect_seed=100,z=2),editor)
    for obj in (text,mask):editor.scene.addItem(obj);editor.objects.append(obj)
    first=editor.render();text.props.update(text='5',color='#0000ff');text.update()
    assert editor.render()==first
    editor.close()
