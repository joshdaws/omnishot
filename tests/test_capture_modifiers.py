import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from omnishot import backend
from omnishot.app import Controller


def test_live_selector_reports_geometry_and_completion_modifiers(monkeypatch):
    seen=[]
    def run(args,**kwargs):seen.append(args);return b'-400,200 320x180|5\n'
    monkeypatch.setattr(backend,'run',run)
    assert backend.select_region(with_modifiers=True)==((-400,200,320,180),5)
    assert str(seen[0][0]).endswith('/native/live-selector') and '%M' in seen[0][-1]


@pytest.mark.parametrize('enabled,force,expected',[(True,True,{'overlay','copy'}),(False,True,{'overlay'}),(True,False,{'overlay'})])
def test_control_copy_adds_to_actions_without_changing_settings(tmp_path,enabled,force,expected):
    app=QApplication.instance() or QApplication([]);state=Controller.__new__(Controller);state.store=backend.Store(tmp_path/'data')
    state.store.settings.update(capture_ctrl_copy=enabled,background_preset='Ocean');state.restore_capture_windows=lambda:None;state.choose_capture_name=lambda path:True
    received=[];state.perform_capture_actions=lambda path,actions:received.append((path,actions))
    state.finished_capture(np.full((100,200,3),255,np.uint8),action='overlay',skip_background=True,force_copy=force)
    path,actions=received[0];assert actions==expected and state.store.settings['background_preset']=='Ocean'
    assert state.store.metadata(path)['skip_background'] and not state.store.image_edit_path(path).exists()
