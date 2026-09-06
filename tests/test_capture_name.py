from pathlib import Path
import numpy as np
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QDialog
from omnishot.app import Controller
from omnishot.backend import Store
from omnishot.capture_name import CaptureNameDialog


def state(tmp_path):
    app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
    controller=Controller.__new__(Controller);controller.store=Store(tmp_path/'data')
    controller.store.settings.update(ask_capture_name=True,background_preset='Ocean')
    controller.restore_capture_windows=lambda:None;actions=[];controller.perform_capture_actions=lambda *args,**kwargs:actions.append(args)
    return app,controller,actions


@pytest.mark.parametrize('kind',['image','scroll'])
def test_discard_removes_new_capture_and_automatic_background_before_any_action(tmp_path,kind):
    app,controller,actions=state(tmp_path)
    QTimer.singleShot(0,lambda:app.activeModalWidget().discard())
    controller.finished_capture(np.zeros((40,60,3),np.uint8),action='area-annotate',kind=kind,force_copy=True)
    assert not actions and not controller.store.history()
    assert not list(controller.store.captures.iterdir()) and not list((controller.store.root/'image-edits').glob('*'))


@pytest.mark.parametrize('extension',['mp4','gif'])
def test_discard_recording_cleans_owned_tracks_but_preserves_external_files(tmp_path,extension):
    app,controller,actions=state(tmp_path);store=controller.store
    source=tmp_path/('original.'+extension);source.write_bytes(b'external recording')
    owned=store.add(source=source,kind='gif' if extension=='gif' else 'video')
    tracks=store.root/'tracks';tracks.mkdir();camera=tracks/'camera.mp4';camera.write_bytes(b'owned camera')
    store.atomic_json(owned.with_suffix('.studio.json'),dict(source_path=str(source),camera_path=str(camera)))
    if extension=='gif':owned.with_suffix('.mp4').write_bytes(b'owned raw recording')
    QTimer.singleShot(0,lambda:app.activeModalWidget().discard());controller.finished_recording(owned)
    assert not actions and not store.history() and not camera.exists()
    assert source.read_bytes()==b'external recording' and not list(store.captures.iterdir())


def test_cancel_keeps_automatic_name_and_accept_renames_before_actions(tmp_path):
    app,controller,actions=state(tmp_path);controller.store.settings['background_preset']='None'
    def cancel():
        dialog=app.activeModalWidget();dialog.name.setText('Do not use this name');dialog.reject()
    QTimer.singleShot(0,cancel);controller.finished_capture(np.zeros((40,60,3),np.uint8),action='save')
    first=actions[0][0];assert controller.store.display_name(first).startswith('OmniShot ')
    def accept():
        dialog=app.activeModalWidget();dialog.name.setText('Chosen name');dialog.accept()
    QTimer.singleShot(0,accept);controller.finished_capture(np.zeros((40,60,3),np.uint8),action='save')
    assert controller.store.display_name(actions[-1][0])=='Chosen name.png' and len(actions)==2


def test_invalid_name_and_failed_discard_keep_dialog_open_and_capture_owned(tmp_path,monkeypatch):
    app,controller,actions=state(tmp_path);store=controller.store;path=store.add(image=np.zeros((40,60,3),np.uint8))
    dialog=CaptureNameDialog(store,path);dialog.show();app.processEvents()
    try:
        original=store.display_name(path);dialog.name.setText('../bad');dialog.accept()
        assert dialog.isVisible() and dialog.message.isVisible() and store.display_name(path)==original
        with monkeypatch.context() as patch:
            patch.setattr(store,'remove',lambda path:(_ for _ in ()).throw(PermissionError('Read-only capture')))
            dialog.discard();assert dialog.isVisible() and path.exists() and dialog.message.text()=='Read-only capture'
        dialog.name.setText('Repaired');dialog.accept();assert dialog.result()==QDialog.DialogCode.Accepted and store.display_name(path)=='Repaired.png'
    finally:dialog.close()
