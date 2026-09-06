import base64
import pytest
import numpy as np
from PySide6.QtCore import QRect,QPointF,Qt
from PySide6.QtGui import QImage,QColor,QPainter,QTransform
from PySide6.QtWidgets import QApplication
from omnishot.backend import Store
from omnishot.editor import Editor,Annotation,png_bytes
from omnishot.annotation_effects import rgba


def document(tmp_path):
    app=QApplication.instance() or QApplication([])
    source=QImage(400,260,QImage.Format.Format_ARGB32_Premultiplied);source.fill(Qt.GlobalColor.transparent)
    painter=QPainter(source);painter.fillRect(20,20,360,220,QColor('#e0e0e0'));painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);painter.fillRect(300,180,60,40,QColor(200,100,50,128));painter.end()
    path=tmp_path/'source.png';source.save(str(path));return app,Editor(path,Store(tmp_path/'data'))


def add(editor,props):
    obj=Annotation(props,editor);editor.objects.append(obj);editor.scene.addItem(obj);return obj


def test_spotlight_preserves_transparency_and_clips_to_image(tmp_path):
    app,editor=document(tmp_path)
    try:
        add(editor,dict(kind='spotlight',x=-25,y=40,w=170,h=120));editor.commit();result=editor.render()
        assert np.array_equal(rgba(result)[:,:,3],rgba(editor.base)[:,:,3])
        assert result.pixelColor(80,80)==editor.base.pixelColor(80,80)
        assert result.pixelColor(220,80).red()<editor.base.pixelColor(220,80).red()
        assert result.pixelColor(330,200).red()<editor.base.pixelColor(330,200).red()
        editor.background=dict(color='#aabbcc',padding=45,radius=0,shadow=False)
        framed=editor.render();assert framed.pixelColor(10,10)==QColor('#aabbcc')
    finally:editor.close()


@pytest.mark.parametrize('shape',['Rectangle','Ellipse','Rounded rectangle'])
@pytest.mark.parametrize('alpha',[0,64,255])
def test_spotlight_shape_and_opacity_preserve_source_alpha(tmp_path,shape,alpha):
    app,editor=document(tmp_path)
    try:
        add(editor,dict(kind='spotlight',x=50,y=50,w=200,h=160,spotlight_shape=shape,spotlight_radius=65,spotlight_alpha=alpha));editor.commit();result=editor.render()
        assert np.array_equal(rgba(result)[:,:,3],rgba(editor.base)[:,:,3])
        assert result.pixelColor(150,130)==editor.base.pixelColor(150,130)
        expected=round(224*(255-alpha)/255)
        assert abs(result.pixelColor(270,130).red()-expected)<=1
        assert abs(result.pixelColor(52,52).red()-(224 if shape=='Rectangle' else expected))<=1
        if alpha==0:assert np.array_equal(rgba(result),rgba(editor.base))
        project=tmp_path/'style.omnishot';editor.write_project(project);other=Editor(project,editor.store)
        assert other.render()==result;other.close()
    finally:editor.close()


def same_geometry(first,second):
    # Re-rasterizing transformed rounded corners differs by a few edge levels.
    diff=np.abs(rgba(first).astype(int)-rgba(second).astype(int))
    assert diff.max()<=4 and np.count_nonzero(diff.max(2))<100


def test_spotlight_transform_crop_and_inserted_image_round_trip(tmp_path):
    app,editor=document(tmp_path)
    try:
        inserted=QImage(240,150,QImage.Format.Format_RGB888);inserted.fill(QColor('#2474ab'))
        add(editor,dict(kind='image',x=70,y=60,w=240,h=150,image=base64.b64encode(png_bytes(inserted)).decode(),z=1))
        spot=add(editor,dict(kind='spotlight',x=90,y=85,w=110,h=75,z=2));editor.commit();initial=editor.render()
        assert initial.pixelColor(140,120)==QColor('#2474ab')
        assert initial.pixelColor(260,120).blue()<171
        editor.rotate();rotated=editor.render();expected=initial.transformed(QTransform().rotate(90));same_geometry(rotated,expected)
        editor.flip();same_geometry(editor.render(),rotated.flipped(Qt.Orientation.Horizontal))
        before=editor.render();editor.crop(QRect(15,25,220,330));assert editor.render()==before.copy(15,25,220,330)
        project=tmp_path/'spotlight.omnishot';editor.write_project(project);reopened=Editor(project,editor.store);assert reopened.render()==editor.render();reopened.close()
        editor.undo();assert editor.render()==before;editor.undo();editor.undo();assert editor.render()==initial
    finally:editor.close()


def test_zoomed_long_capture_uses_viewport_sized_buffer(tmp_path,monkeypatch):
    from omnishot.editor import AnnotationComposition
    app=QApplication.instance() or QApplication([])
    source=QImage(1000,3000,QImage.Format.Format_RGB888);source.fill(QColor('#d0e0f0'))
    painter=QPainter(source)
    for y in range(0,3000,200):painter.fillRect(0,y,1000,100,QColor('#c08040'))
    painter.end();path=tmp_path/'long.png';source.save(str(path));editor=Editor(path,Store(tmp_path/'data'))
    buffers=[];original=AnnotationComposition.sourcePixmap
    def observe(self,*args,**kwargs):
        result=original(self,*args,**kwargs);buffers.append((result.width(),result.height()));return result
    monkeypatch.setattr(AnnotationComposition,'sourcePixmap',observe)
    try:
        add(editor,dict(kind='spotlight',x=100,y=1100,w=250,h=250));editor.commit();expected=editor.render();editor.show();app.processEvents();buffers.clear()
        editor.view.resetTransform();editor.view.scale(2,2);editor.view.sync_composition_bounds()
        for y in (800,2200,3800):
            editor.view.verticalScrollBar().setValue(y);app.processEvents()
            preview=editor.view.viewport().grab().toImage();point=editor.view.viewport().rect().center();scene=editor.view.mapToScene(point)
            actual=preview.pixelColor(point);want=expected.pixelColor(round(scene.x()),round(scene.y()));assert actual==want
        assert buffers and all(w<=editor.view.viewport().width()+12 and h<=editor.view.viewport().height()+12 for w,h in buffers),buffers
        assert editor.render()==expected and editor.render().size()==source.size()
    finally:editor.close();editor.deleteLater();app.processEvents()
