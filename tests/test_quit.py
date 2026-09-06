import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
from PySide6.QtWidgets import QApplication,QMessageBox,QWidget
from PySide6.QtTest import QTest
from omnishot.app import Controller
from omnishot.backend import Store
from omnishot.editor import Editor


def controller():
    value=Controller.__new__(Controller);value.windows=[];value.selectors=[];value.busy=False;value.panel=None;value.recorder=None;value.quit_after_recording=False;value.hidden_for_capture=[];value.app=SimpleNamespace(quit=Mock());value.tray=SimpleNamespace(showMessage=Mock());return value


def test_quit_respects_cancel_from_failed_editor_save(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'data');path=store.add(image=np.full((100,200,3),255,np.uint8));editor=Editor(path,store);editor.show();state=controller();state.windows=[editor]
    original=editor.write_project;monkeypatch.setattr(editor,'write_project',lambda path:(_ for _ in ()).throw(OSError('disk full')))
    monkeypatch.setattr(QMessageBox,'warning',lambda *a,**k:QMessageBox.StandardButton.Cancel)
    assert not state.request_quit() and editor.isVisible();state.app.quit.assert_not_called()
    monkeypatch.setattr(editor,'write_project',original)
    assert state.request_quit() and editor.draft_path.is_file();state.app.quit.assert_called_once()


def test_quit_waits_for_recording_and_recovery_cancels_pending_quit(monkeypatch):
    app=QApplication.instance() or QApplication([]);state=controller();rec=QWidget();rec.stop=Mock();state.recorder=rec
    assert not state.request_quit() and state.quit_after_recording;rec.stop.assert_called_once();state.app.quit.assert_not_called()
    state.recording_closed();QTest.qWait(20);state.app.quit.assert_called_once()
    state=controller();state.store=SimpleNamespace(metadata=lambda path:{'capture_named':True});state.edit=Mock();state.quit_after_recording=True
    monkeypatch.setattr(QMessageBox,'warning',lambda *a,**k:None)
    state.recovered_recording('/tmp/generated-test.mp4','encoder ended')
    assert not state.quit_after_recording;state.edit.assert_called_once();state.app.quit.assert_not_called();rec.close()


def test_quit_waits_for_pending_clipboard_copy(monkeypatch):
    app=QApplication.instance() or QApplication([]);state=controller();pending={object()}
    monkeypatch.setattr('omnishot.widgets.JOBS',pending)
    assert not state.request_quit();state.app.quit.assert_not_called()
    pending.clear();QTest.qWait(200);state.app.quit.assert_called_once()
