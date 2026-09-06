import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from pathlib import Path
import zipfile
import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication,QMessageBox
from omnishot import backend,editor,images,recording


def application():return QApplication.instance() or QApplication([])


def test_partial_image_encoder_preserves_existing_destination(tmp_path,monkeypatch):
    application();destination=tmp_path/"saved.png";destination.write_bytes(b"previous export")
    frame=editor.qimage(np.zeros((40,60,3),np.uint8))
    def failing_encoder(self,path,*args,**kwargs):
        Path(path).write_bytes(b"partial image");raise OSError("Disk full")
    monkeypatch.setattr(Image.Image,"save",failing_encoder)
    with pytest.raises(OSError):images.save_image(frame,destination)
    assert destination.read_bytes()==b"previous export"
    assert not list(tmp_path.glob(".omnishot-*"))


def test_partial_project_preserves_previous_archive(tmp_path,monkeypatch):
    application();store=backend.Store(tmp_path/"data");path=store.add(image=np.zeros((40,60,3),np.uint8))
    e=editor.Editor(path,store);destination=tmp_path/"editable.omnishot";e.write_project(destination);original=destination.read_bytes()
    write=zipfile.ZipFile.writestr
    def failing_manifest(self,name,*args,**kwargs):
        if name=="project.json":raise OSError("Disk full")
        return write(self,name,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(zipfile.ZipFile,"writestr",failing_manifest)
        with pytest.raises(OSError):e.write_project(destination)
    assert destination.read_bytes()==original and not list(tmp_path.glob(".omnishot-*"));e.close()


def test_failed_annotation_draft_keeps_editor_open_then_retries(tmp_path,monkeypatch):
    app=application();store=backend.Store(tmp_path/"data");path=store.add(image=np.zeros((40,60,3),np.uint8))
    e=editor.Editor(path,store);e.show();app.processEvents();assert e.save_draft();previous=e.draft_path.read_bytes()
    e.rotate();expected=e.render()
    with monkeypatch.context() as patch:
        patch.setattr(e,"write_project",lambda *args:(_ for _ in ()).throw(OSError("Disk full")))
        patch.setattr(QMessageBox,"warning",lambda *args:QMessageBox.StandardButton.Cancel)
        assert not e.save_draft() and not e.close() and e.isVisible()
        assert e.draft_path.read_bytes()==previous and e.render()==expected
    assert e.close();reopened=editor.Editor(path,store);assert reopened.render()==expected;reopened.close()


def test_failed_thumbnail_does_not_discard_preserved_annotations(tmp_path,monkeypatch):
    application();store=backend.Store(tmp_path/"data");path=store.add(image=np.zeros((40,60,3),np.uint8))
    e=editor.Editor(path,store);e.rotate();expected=e.render()
    with monkeypatch.context() as patch:
        patch.setattr(editor,"export_image",lambda *args:(_ for _ in ()).throw(OSError("Disk full")))
        assert e.save_draft()
        reopened=editor.Editor(path,store);assert reopened.render()==expected;reopened.close()
    e.close()


def test_open_image_preserves_old_draft_and_rejects_corrupt_input(tmp_path,monkeypatch):
    application();store=backend.Store(tmp_path/"data");path=store.add(image=np.zeros((40,60,3),np.uint8))
    e=editor.Editor(path,store);e.rotate();expected=e.render();draft=e.draft_path
    corrupt=tmp_path/"corrupt.png";corrupt.write_bytes(b"not an image")
    monkeypatch.setattr(editor.QFileDialog,"getOpenFileName",lambda *args:(str(corrupt),""))
    monkeypatch.setattr(editor,"error",lambda *args:None);e.open_file()
    assert e.path==path and e.draft_path==draft and e.render()==expected
    incoming=tmp_path/"incoming.png";Image.new("RGB",(90,50),"blue").save(incoming)
    monkeypatch.setattr(editor.QFileDialog,"getOpenFileName",lambda *args:(str(incoming),""));e.open_file()
    assert e.path.parent==store.captures and e.path!=path and e.draft_path!=draft
    assert e.undo_index==0 and e.base.size().width()==90
    e.undo();assert e.base.width()==90;e.close()
    old=editor.Editor(path,store);assert old.render()==expected;old.close()


def test_failed_video_edits_keep_editor_available_for_recovery(tmp_path,monkeypatch):
    app=application();store=backend.Store(tmp_path/"data");source=store.captures/"recording.mp4"
    backend.run(["ffmpeg","-v","error","-f","lavfi","-i","color=c=blue:s=160x120:r=10:d=0.3","-c:v","libx264","-threads","1",source])
    e=recording.VideoEditor(source,store);e.show();app.processEvents();e.player.pause();e.padding.setValue(52)
    with monkeypatch.context() as patch:
        patch.setattr(store,"atomic_json",lambda *args:(_ for _ in ()).throw(OSError("Disk full")))
        patch.setattr(QMessageBox,"warning",lambda *args:QMessageBox.StandardButton.Cancel)
        assert not e.save_edits() and not e.close() and e.isVisible()
        assert e.padding.value()==52
    assert e.close();reopened=recording.VideoEditor(source,store);assert reopened.padding.value()==52;reopened.close()
