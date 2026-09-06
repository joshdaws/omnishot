import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import shutil
from pathlib import Path
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from omnishot.app import Controller
from omnishot.backend import Store
from omnishot.editor import Editor,Annotation
from omnishot.images import load_image
from omnishot.widgets import QuickOverlay


def test_preview_transforms_keep_original_and_editable_annotations(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/"data")
    frame=np.zeros((160,240,3),np.uint8);frame[20:50,30:60]=[255,0,0];path=store.add(image=frame);original=path.read_bytes()
    meta=store.metadata(path);meta["pixel_ratio"]=1.6;store.atomic_json(path.with_suffix(".json"),meta)
    editor=Editor(path,store);obj=Annotation({"kind":"text","text":"Editable","x":60,"y":80,"w":130,"h":50},editor);editor.objects.append(obj);editor.scene.addItem(obj);editor.commit()
    overlay=QuickOverlay(path,store);controller=Controller.__new__(Controller);controller.store=store;controller.windows=[editor];controller.overlays=[overlay];controller.pins=[]
    controller.transform_capture(path,"rotate");assert editor.base.width()==160 and editor.base.height()==240
    controller.transform_capture(path,"flip-vertical");assert len(editor.objects)==1
    controller.transform_capture(path,"scale");assert editor.base.width()==100 and editor.base.height()==150
    assert load_image(store.display_image(path)).size()==editor.base.size();assert path.read_bytes()==original
    controller.transform_capture(path,"scale");assert editor.base.width()==100
    editor.close();reopened=Editor(path,store);assert reopened.base.width()==100 and reopened.objects[0].props["text"]=="Editable"
    reopened.close();overlay.close()


def test_renamed_exports_do_not_overwrite_and_projects_reopen_latest_edits(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/"data");path=store.add(image=np.full((80,120,3),255,np.uint8))
    editor=Editor(path,store);project=tmp_path/"Imported project.omnishot";editor.write_project(project);editor.close()
    imported=store.import_file(project);edit=Editor(imported,store);edit.rotate();edit.close();edit=Editor(imported,store)
    assert edit.base.width()==80 and edit.base.height()==120;edit.close()
    assert store.rename(path,"Product overview")=="Product overview.png"
    overlay=QuickOverlay(path,store);folder=tmp_path/"exports";one=overlay.export_to(folder);before=one.read_bytes();two=overlay.export_to(folder)
    assert one.name=="Product overview.png" and two.name=="Product overview (2).png" and one.read_bytes()==before
    assert store.history(search="Product overview")[0]["path"]==str(path)
    with pytest.raises(ValueError):store.rename(path,"../wrong")
    overlay.close()


def test_trash_preserves_recoverable_edits_and_rolls_back_failure(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/"data");path=store.add(image=np.full((80,120,3),255,np.uint8))
    editor=Editor(path,store);editor.rotate();editor.close();before=path.read_bytes()
    def fail(path):raise OSError('Trash unavailable')
    monkeypatch.setattr('omnishot.backend.move_to_trash',fail)
    with pytest.raises(OSError):store.trash(path)
    assert path.read_bytes()==before and store.image_edit_path(path).exists()
    assert not list((store.root/"trash-staging").iterdir())
    recovered=tmp_path/"trash"
    def move(path):shutil.move(path,recovered);return str(recovered)
    monkeypatch.setattr('omnishot.backend.move_to_trash',move);store.trash(path)
    assert not path.exists() and not store.image_edit_path(path).exists()
    restored=Editor(next(recovered.glob("*.omnishot")),store);assert restored.base.width()==80 and restored.base.height()==120;restored.close()


def test_real_qt_trash_returns_recoverable_path(tmp_path):
    import subprocess,sys
    # Fresh Qt process avoids QStandardPaths caches; all data belongs to this test.
    subprocess.run([sys.executable,'-c','''
import os,sys,shutil
from pathlib import Path
root=Path(sys.argv[1]);data=root/'xdg';data.mkdir()
os.environ['XDG_DATA_HOME']=str(data)
from omnishot.backend import move_to_trash
source=root/'generated-capture';source.mkdir();(source/'pixels.txt').write_text('generated pixels')
trashed=Path(move_to_trash(source))
try:
    assert not source.exists() and (trashed/'pixels.txt').read_text()=='generated pixels'
    info=trashed.parent.parent/'info'/(trashed.name+'.trashinfo')
    assert info.is_file()
finally:
    shutil.move(trashed,source)
    (trashed.parent.parent/'info'/(trashed.name+'.trashinfo')).unlink(missing_ok=True)
''',str(tmp_path)],check=True,timeout=10)


@pytest.mark.parametrize('change',['unchanged','modified','replaced','symlink','missing'])
def test_trash_auto_save_tracks_owned_file_and_preserves_later_changes(tmp_path,monkeypatch,change):
    store=Store(tmp_path/'data');path=store.add(image=np.zeros((40,60,3),np.uint8))
    saved=tmp_path/'Saved screenshot.png';shutil.copy2(path,saved);store.remember_auto_save(path,saved)
    other=tmp_path/'Other file.png';other.write_bytes(b'unrelated external file')
    if change=='modified':saved.write_bytes(b'edited in another app')
    elif change=='replaced':other.replace(saved)
    elif change=='symlink':saved.unlink();saved.symlink_to(other)
    elif change=='missing':saved.unlink()
    moved=[];trash=tmp_path/'Trash';trash.mkdir()
    def move(source):
        destination=trash/Path(source).name;shutil.move(source,destination);moved.append(Path(source));return str(destination)
    monkeypatch.setattr('omnishot.backend.move_to_trash',move)
    result=Store(store.root).trash(path)
    assert not path.exists() and not store.history()
    assert (saved in moved)==(change=='unchanged')
    assert bool(result['kept_saved_files'])==(change in ('modified','replaced','symlink'))
    if change in ('modified','replaced','symlink'):assert saved.exists()
    if change=='symlink':assert other.read_bytes()==b'unrelated external file'


def test_auto_save_trash_failure_keeps_history_and_can_retry(tmp_path,monkeypatch):
    store=Store(tmp_path/'data');path=store.add(image=np.zeros((40,60,3),np.uint8))
    saved=tmp_path/'Saved screenshot.png';shutil.copy2(path,saved);store.remember_auto_save(path,saved)
    trash=tmp_path/'Trash';trash.mkdir();fail=True
    def move(source):
        if Path(source)==saved and fail:raise OSError('Destination is read-only')
        destination=trash/Path(source).name;shutil.move(source,destination);return str(destination)
    monkeypatch.setattr('omnishot.backend.move_to_trash',move)
    with pytest.raises(OSError,match='read-only'):store.trash(path)
    assert saved.exists() and path.exists() and len(store.history())==1 and list(trash.iterdir())
    fail=False;store.trash(path);assert not path.exists() and not saved.exists()
