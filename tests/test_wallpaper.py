import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PIL import Image
from PySide6.QtWidgets import QApplication
from omnishot import backend,wallpaper
from omnishot.widgets import Settings


def test_desktop_wallpaper_can_follow_changes_or_keep_snapshot(tmp_path,monkeypatch):
    store=backend.Store(tmp_path/'data');path=tmp_path/'desktop.png';Image.new('RGB',(40,30),'red').save(path)
    monkeypatch.setattr(wallpaper,'desktop_path',lambda:path)
    first=wallpaper.capture_wallpaper(store);store.settings['wallpaper_follow_changes']=False
    Image.new('RGB',(40,30),'blue').save(path)
    assert wallpaper.capture_wallpaper(store)==first
    store.settings['wallpaper_follow_changes']=True;assert wallpaper.capture_wallpaper(store)!=first


def test_custom_wallpaper_cancel_and_portable_save(tmp_path):
    app=QApplication.instance() or QApplication([]);store=backend.Store(tmp_path/'data');path=tmp_path/'custom.png';Image.new('RGB',(40,30),'green').save(path)
    data=wallpaper.image_data(path);dialog=Settings(store,'wallpaper');dialog.wallpaper_data=data;dialog.fields['wallpaper_source'].setCurrentIndex(1);dialog.reject()
    assert store.settings['wallpaper_source']=='desktop' and not store.settings['wallpaper_data']
    dialog=Settings(store,'wallpaper');dialog.wallpaper_data=data;dialog.fields['wallpaper_source'].setCurrentIndex(1);dialog.save();path.unlink()
    reopened=backend.Store(store.root);assert wallpaper.capture_wallpaper(reopened)==data
