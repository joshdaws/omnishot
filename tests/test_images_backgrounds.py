import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PIL import Image
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtGui import QColor,QImage,QTransform
from omnishot.images import load_image,save_image
from omnishot.editor import Editor,Annotation
from omnishot.backend import Store
from omnishot.backgrounds import BackgroundDialog,PRESETS


def test_codecs_keep_alpha_and_jpeg_composites(tmp_path):
    image=QImage(96,64,QImage.Format.Format_RGBA8888);image.fill(QColor(255,0,0,0));image.setPixelColor(40,30,QColor("#0066ff"))
    for suffix in ("png","webp","heic","jpg"):
        path=tmp_path/f"image.{suffix}";save_image(image,path);decoded=load_image(path)
        assert decoded.size()==image.size()
        if suffix in ("png","webp","heic"):assert decoded.pixelColor(0,0).alpha()==0
        else:assert decoded.pixelColor(0,0).red()>245 and decoded.pixelColor(0,0).green()>245


def test_background_live_cancel_presets_and_portable_project(tmp_path):
    app=QApplication.instance() or QApplication([])
    path=tmp_path/"source.png";Image.new("RGB",(300,200),"white").save(path)
    e=Editor(path,Store(tmp_path/"data"));d=BackgroundDialog(e)
    assert len(PRESETS)>=20
    d.presets.setCurrentText("Ocean");d.pad.setValue(34)
    assert e.render().width()==368
    d.reject();assert e.background is None
    custom=tmp_path/"custom.png";Image.new("RGB",(200,200),"blue").save(custom)
    e.background={"image":str(custom),"color":"#000000","padding":40}
    expected=e.render();project=tmp_path/"editable.omnishot";e.write_project(project);custom.unlink()
    other=Editor(project,e.store);assert other.render()==expected
    other.close();e.close()


def test_blur_rotation_preserves_effect_region(tmp_path):
    app=QApplication.instance() or QApplication([])
    import numpy as np
    a=np.zeros((240,320,3),dtype=np.uint8);a[:,:160]=[250,10,30];a[:,160:]=[10,20,245]
    path=tmp_path/"source.png";Image.fromarray(a).save(path);e=Editor(path,Store(tmp_path/"data"))
    obj=Annotation({"kind":"blur","x":110,"y":60,"w":100,"h":120,"strength":12},e);e.objects.append(obj);e.scene.addItem(obj)
    before=e.render();e.rotate();after=e.render();expected=before.transformed(QTransform().rotate(90))
    # Exact color samples across the effect, including its transformed boundary.
    for x,y in [(70,120),(100,160),(150,190),(30,30)]:assert after.pixelColor(x,y)==expected.pixelColor(x,y)
    e.close()
