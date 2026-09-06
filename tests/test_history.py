import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import time
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from omnishot.backend import Store
from omnishot.editor import Editor,Annotation


def test_history_restores_edits_and_deletion_cleans_them(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/"data")
    path=store.add(image=np.full((160,220,3),245,np.uint8));editor=Editor(path,store)
    obj=Annotation({"kind":"text","text":"Keep this edit","x":20,"y":20,"w":180,"h":60},editor);editor.objects.append(obj);editor.scene.addItem(obj);editor.commit();editor.close()
    other=Editor(path,store);assert other.objects[0].props["text"]=="Keep this edit";other.close()
    assert store.history()[0]["preview"]
    edit=store.image_edit_path(path);assert edit.exists()
    store.remove(path);assert not path.exists() and not edit.exists() and not edit.with_suffix(".png").exists()


def test_retention_and_delete_preserve_external_files(tmp_path):
    store=Store(tmp_path/"data");path=store.add(image=np.zeros((20,20,3),np.uint8));store.atomic_json(path.with_suffix(".json"),{"created":time.time()-32*86400,"kind":"image"})
    external=tmp_path/"keep.png";external.write_bytes(b"user file")
    with pytest.raises(ValueError):store.remove(external)
    store.expire();assert external.read_bytes()==b"user file" and not path.exists()


def test_recording_history_hides_legacy_raw_and_removes_owned_tracks(tmp_path):
    store=Store(tmp_path/"data");gif=store.captures/"record.gif";raw=gif.with_suffix(".mp4");gif.write_bytes(b"gif");raw.write_bytes(b"raw")
    tracks=store.root/"tracks";tracks.mkdir();camera=tracks/"camera.mp4";camera.write_bytes(b"camera")
    external=tmp_path/"external.mp4";external.write_bytes(b"keep")
    store.atomic_json(gif.with_suffix(".json"),{"kind":"gif"})
    store.atomic_json(gif.with_suffix(".studio.json"),{"camera_path":str(camera),"source_path":str(external)})
    edit=store.video_edit_path(gif);edit.parent.mkdir();edit.write_text("{}")
    assert [r["path"] for r in store.history("gif")]==[str(gif)]
    store.remove(gif)
    assert not gif.exists() and not raw.exists() and not camera.exists() and not edit.exists()
    assert external.read_bytes()==b"keep"


def test_external_import_is_searchable_deduplicated_and_keeps_original(tmp_path):
    from PIL import Image
    store=Store(tmp_path/"data");external=tmp_path/"Product overview.png";Image.new("RGB",(20,20),"white").save(external)
    imported=store.import_file(external);assert store.import_file(external)==imported
    assert store.history(search="product")[0]["path"]==str(imported)
    assert store.history()[0]["name"]==external.name
    store.remove(imported);assert external.exists() and store.history()==[]


def test_bad_image_import_does_not_leave_history_entry(tmp_path):
    import pytest
    from PIL import Image
    store=Store(tmp_path/'data');source=tmp_path/'broken.png'
    source.write_bytes(b'not an image')
    with pytest.raises(ValueError,match='Could not open image'):store.import_file(source)
    assert store.history()==[] and list(store.captures.iterdir())==[]
    Image.new('RGB',(40,30),'blue').save(source)
    source.write_bytes(source.read_bytes()[:50])
    with pytest.raises(ValueError,match='Could not open image'):store.import_file(source)
    assert store.history()==[] and list(store.captures.iterdir())==[]
    Image.new('RGB',(40,30),'blue').save(source)
    imported=store.import_file(source)
    assert imported.exists() and len(store.history())==1
    assert store.import_file(source)==imported


def test_bad_project_import_does_not_leave_history_entry(tmp_path):
    import json,zipfile
    from omnishot.editor import png_bytes
    from PySide6.QtGui import QImage,QTransform
    from omnishot.image_project import read_project
    store=Store(tmp_path/'data');source=tmp_path/'broken.omnishot'
    source.write_bytes(b'not a project')
    with pytest.raises(ValueError,match='Could not open image project'):store.import_file(source)
    assert store.history()==[] and list(store.captures.iterdir())==[]
    image=QImage(30,20,QImage.Format.Format_RGB32);image.fill(0xffabcdef)
    for data,bitmap in [({'version':2,'objects':[]},b'broken image'),({'version':2,'objects':[{}]},png_bytes(image)),({'version':2,'objects':[],'original_image':'original.png','source_transform':[0]*6},png_bytes(image))]:
        with zipfile.ZipFile(source,'w') as archive:
            archive.writestr('image.png',bitmap);archive.writestr('original.png',png_bytes(image));archive.writestr('project.json',json.dumps(data))
        with pytest.raises(ValueError,match='Could not open image project'):store.import_file(source)
        assert store.history()==[] and list(store.captures.iterdir())==[]
    with zipfile.ZipFile(source,'w') as archive:
        archive.writestr('image.png',png_bytes(image));archive.writestr('project.json',json.dumps({'version':1,'objects':[]}))
    imported=store.import_file(source);assert imported.exists() and len(store.history())==1
    decoded,data,original,transform=read_project(imported)
    assert decoded==image and original is None and transform==QTransform()
    assert store.import_file(source)==imported
