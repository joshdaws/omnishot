import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
import pytest
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication,QMessageBox
from omnishot.backend import Store
from omnishot.history import History,thumbnail_key


def test_filmstrip_groups_scrolls_and_preserves_multiple_selection(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data')
    paths=[store.add(image=np.zeros((20,30,3),np.uint8),kind=kind) for kind in ('image','scroll','gif')]
    monkeypatch.setattr(History,'request_thumbnails',lambda self:None)
    history=History(store)
    try:
        history.set_filter('image');assert {r['path'] for r in history.rows}==set(map(str,paths[:2]))
        for i in range(history.list.count()):history.list.item(i).setSelected(True)
        history.list.setCurrentItem(history.list.item(1),QItemSelectionModel.SelectionFlag.NoUpdate)
        history.refresh();assert len(history.selected())==2 and history.restore_button.text()=='↩ Restore 2'
        restored=[];history.restore_capture.connect(restored.append);history.emit_selected(history.restore_capture)
        assert set(restored)==set(map(str,paths[:2]))
        history.set_filter('gif');assert history.selected()==[str(paths[2])]
        history.search.setText('missing');assert history.list.count()==0 and not history.restore_button.isEnabled()
    finally:history.close()


def test_clear_all_ignores_filter_and_requires_confirmation(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data')
    paths=[store.add(image=np.zeros((20,30,3),np.uint8),kind=kind) for kind in ('image','scroll')]
    monkeypatch.setattr(History,'request_thumbnails',lambda self:None)
    history=History(store);history.search.setText(paths[0].name)
    try:
        assert history.list.count()==1
        monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Cancel);history.clear()
        assert all(p.exists() for p in paths)
        monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.StandardButton.Yes);history.clear()
        assert not any(p.exists() for p in paths) and history.list.count()==0
        history.reject();assert history.closed and history.cancel.is_set()
        history.thumbnail_done(('late',1,1),QImage(10,10,QImage.Format.Format_RGB32));assert not history.images
    finally:history.close()


def test_history_delete_respects_editor_cancel_and_active_export(tmp_path):
    from types import SimpleNamespace
    from omnishot.app import Controller
    store=Store(tmp_path/'data');path=store.add(image=np.zeros((20,30,3),np.uint8));controller=Controller.__new__(Controller)
    controller.store=store;controller.overlays=[];controller.pins=[];controller.last_closed=str(path)
    editor=SimpleNamespace(path=path,export_cancel=object(),close=lambda:False);controller.windows=[editor]
    with pytest.raises(ValueError,match='export'):controller.remove_history([path])
    assert path.exists()
    editor.export_cancel=None
    with pytest.raises(ValueError,match='preserve'):controller.remove_history([path])
    assert path.exists()
    editor.close=lambda:True;controller.remove_history([path]);assert not path.exists() and controller.last_closed is None
