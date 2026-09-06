import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor,QTransform
from omnishot.editor import Editor,Annotation
from omnishot.backend import Store


def test_rotation_flip_keep_editable(tmp_path):
    app=QApplication.instance() or QApplication([])
    path=tmp_path/"base.png";Image.new("RGB",(500,300),"white").save(path)
    e=Editor(path,Store(tmp_path/"data"));obj=Annotation({"kind":"fill","x":50,"y":30,"w":100,"h":70,"color":"#ff5555"},e);e.objects.append(obj);e.scene.addItem(obj);e.commit()
    before=e.render();e.rotate()
    assert len(e.objects)==1 and e.objects[0].props["kind"]=="fill"
    assert e.base.size()==before.transformed(QTransform().rotate(90)).size()
    assert e.render().pixelColor(230,100)==QColor("#ff5555")
    e.flip();assert e.render().pixelColor(70,100)==QColor("#ff5555")
    p=tmp_path/"rotated.omnishot";e.write_project(p);other=Editor(p,e.store);assert other.render()==e.render();other.close();e.close()


def test_combine_preserves_annotations(tmp_path):
    app=QApplication.instance() or QApplication([])
    path=tmp_path/"base.png";Image.new("RGB",(300,200),"white").save(path)
    e=Editor(path,Store(tmp_path/"data"));obj=Annotation({"kind":"fill","x":20,"y":20,"w":50,"h":50,"color":"#ff5555"},e);e.objects.append(obj);e.scene.addItem(obj);e.commit()
    second=QImage(150,90,QImage.Format.Format_RGB888);second.fill(QColor("#3355ff"));e.combine(second,"Above")
    assert e.base.width()==300 and e.base.height()==290
    assert len(e.objects)==2 and e.objects[0].y()==110
    rendered=e.render();assert rendered.pixelColor(40,130)==QColor("#ff5555");assert rendered.pixelColor(40,30)==QColor("#3355ff")
    e.undo();assert e.base.height()==200 and len(e.objects)==1;e.close()
