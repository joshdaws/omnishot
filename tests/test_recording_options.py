import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from omnishot import backend,recording
from omnishot.recording_options import resolution_limit

MONITOR = dict(name='test',x=0,y=0,width=2880,height=1800,scale=1.6,focused=True)


def test_camera_size_setup_saves_only_when_options_accepted(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);store=backend.Store(tmp_path/'data');monkeypatch.setattr(backend,'run',lambda *a,**k:b'')
    dialog=recording.RecordSetup(store);assert dialog.camera_size.value()==22
    dialog.camera_size.setValue(35);options=dialog.options();assert options['camera_size']==.35
    dialog.close();other=recording.RecordSetup(backend.Store(store.root));assert other.camera_size.value()==35
    other.camera_size.setValue(70);other.reject()
    last=recording.RecordSetup(backend.Store(store.root));assert last.camera_size.value()==35;last.close()


def test_camera_flip_setup_persists_and_cancel_preserves_choice(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);store=backend.Store(tmp_path/'data');monkeypatch.setattr(backend,'run',lambda *a,**k:b'')
    dialog=recording.RecordSetup(store);assert not dialog.camera_mirror.isChecked()
    dialog.camera_mirror.setChecked(True);assert dialog.options()['camera_mirror'];dialog.close()
    other=recording.RecordSetup(backend.Store(store.root));assert other.camera_mirror.isChecked()
    other.camera_mirror.setChecked(False);other.reject()
    last=recording.RecordSetup(backend.Store(store.root));assert last.camera_mirror.isChecked()
    last.camera_mirror.setChecked(False);assert not last.options()['camera_mirror'];last.close()
    assert not backend.Store(store.root).settings['record_camera_mirror']


def test_resolution_limits_preserve_logical_bounds_and_rotation():
    assert resolution_limit('Native',False,[MONITOR]) is None
    assert resolution_limit('Native',True,[MONITOR]) == '1800x1125'
    assert resolution_limit('Native',True,[dict(MONITOR,transform=1)]) == '1125x1800'
    assert resolution_limit('1920x1080',True,[MONITOR]) == '1800x1080'
    assert resolution_limit('1280x720',True,[MONITOR],(-100,50,900,600)) == '900x600'
    assert resolution_limit('Native',True,[],(-200,10,2000,500)) == '2000x500'


def test_recording_resolution_preferences_survive_gif_switch(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);store=backend.Store(tmp_path/'data')
    store.settings.update(record_max_resolution='1920x1080',record_scale_video=True)
    monkeypatch.setattr(backend,'run',lambda *a,**k:b'')
    dialog=recording.RecordSetup(store)
    dialog.format.setCurrentText('GIF');options=dialog.options()
    assert options['size']=='Native' and not options['scale_video']
    dialog.format.setCurrentText('MP4');options=dialog.options()
    assert options['size']=='1920x1080' and options['scale_video']
    reopened=backend.Store(store.root)
    assert reopened.settings['record_max_resolution']=='1920x1080' and reopened.settings['record_scale_video']
    cmd=recording.recorder_command(tmp_path/'out.mp4',(0,0,900,600),options)
    assert cmd[cmd.index('-s')+1]=='900x600'
    dialog.close()
