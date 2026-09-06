import io
import numpy as np
from PIL import Image,ImageCms
from PySide6.QtGui import QColor,QColorSpace,QImage
from PySide6.QtCore import QPointF,QRect,QSize
from PySide6.QtWidgets import QApplication
from omnishot.images import load_image,save_image,convert_image
from omnishot.editor import Editor,Annotation
from omnishot.backend import Store


def p3_image():
    image=QImage(96,64,QImage.Format.Format_RGBA8888);image.fill(QColor(160,100,40))
    image.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.DisplayP3));return image


def test_profiles_survive_all_export_codecs_and_real_srgb_conversion(tmp_path):
    original=p3_image()
    for suffix in ('png','jpg','webp','heic'):
        path=tmp_path/f'profile.{suffix}';save_image(original,path)
        decoded=load_image(path)
        assert decoded.colorSpace()==original.colorSpace(),suffix
        assert max(abs(a-b) for a,b in zip(decoded.pixelColor(40,30).getRgb(),original.pixelColor(40,30).getRgb()))<8
    expected=ImageCms.profileToProfile(Image.new('RGB',(1,1),(160,100,40)),ImageCms.ImageCmsProfile(io.BytesIO(bytes(original.colorSpace().iccProfile()))),ImageCms.createProfile('sRGB')).getpixel((0,0))
    thumbnail=load_image(tmp_path/"profile.png",QSize(24,24));assert thumbnail.size()==QSize(24,16) and thumbnail.colorSpace()==original.colorSpace()
    converted=convert_image(original)
    assert max(abs(a-b) for a,b in zip(converted.pixelColor(0,0).getRgb()[:3],expected))<=1
    assert converted.pixelColor(0,0)!=original.pixelColor(0,0)
    assert original.colorSpace()==QColorSpace(QColorSpace.NamedColorSpace.DisplayP3)
    path=tmp_path/'srgb.jpg';save_image(original,path,convert_srgb=True)
    assert load_image(path).colorSpace()==QColorSpace(QColorSpace.NamedColorSpace.SRgb)


def test_editing_preserves_source_profile_and_converts_inserted_images(tmp_path):
    app=QApplication.instance() or QApplication([])
    original=p3_image();path=tmp_path/'p3.png';save_image(original,path)
    store=Store(tmp_path/'data');store.settings['convert_srgb']=False
    owned=store.import_file(path);editor=Editor(owned,store)
    try:
        obj=Annotation(dict(kind='fill',x=8,y=8,w=20,h=20,color='#4080c0',width=1),editor);editor.objects.append(obj);editor.scene.addItem(obj)
        inserted=QImage(12,12,QImage.Format.Format_RGB32);inserted.fill(QColor('#80a040'));inserted.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb));editor.insert_qimage(inserted,QPointF(45,8))
        output=editor.render();assert output.colorSpace()==original.colorSpace()
        assert output.pixelColor(80,50)==original.pixelColor(80,50)
        color=convert_image(output).pixelColor(18,18);assert max(abs(a-b) for a,b in zip(color.getRgb(),QColor("#4080c0").getRgb()))<=1
        assert output.pixelColor(50,14)==convert_image(inserted,original.colorSpace()).pixelColor(0,0)
        expected=convert_image(output)
        store.settings['convert_srgb']=True;assert editor.render()==expected
        assert editor.save_draft();assert load_image(store.display_image(owned)).colorSpace()==original.colorSpace()
        project=tmp_path/'portable.omnishot';editor.write_project(project)
        reopened=Editor(project,store)
        try:assert reopened.base.colorSpace()==original.colorSpace() and reopened.render()==expected
        finally:reopened.close()
        editor.rotate();editor.crop(QRect(0,0,50,60));editor.combine(inserted,'Below')
        assert editor.base.colorSpace()==original.colorSpace()
        store.settings['convert_srgb']=False;assert editor.render().colorSpace()==original.colorSpace()
    finally:editor.close()


def test_clipboard_profile_preference(tmp_path,monkeypatch):
    from omnishot import backend
    path=tmp_path/'p3.png';save_image(p3_image(),path);store=Store(tmp_path/'data');store.settings['clipboard_mode']='image';values=[]
    monkeypatch.setattr(backend,'clipboard_write',lambda mime,data:values.append(QImage.fromData(data)))
    backend.copy_image(path,store)
    assert values[-1].colorSpace()==QColorSpace(QColorSpace.NamedColorSpace.SRgb)
    store.settings['convert_srgb']=False;backend.copy_image(path,store)
    assert values[-1].colorSpace()==QColorSpace(QColorSpace.NamedColorSpace.DisplayP3)
