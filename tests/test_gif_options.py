import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from omnishot import backend,recording


def test_gif_switch_stops_audio_and_preserves_video_preferences(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([]);store=backend.Store(tmp_path/'data');store.settings.update(record_microphone=True,record_system_audio=True,fps=60,gif_fps=10)
    monkeypatch.setattr(backend,'run',lambda *a,**k:b'');events=[]
    monkeypatch.setattr(recording.AudioMeter,'start',lambda self,device:events.append('start'))
    monkeypatch.setattr(recording.AudioMeter,'stop',lambda self:events.append('stop'))
    dialog=recording.RecordSetup(store);dialog.format.setCurrentText('GIF')
    assert dialog.fps.currentText()=='10' and not dialog.mic.isEnabled() and events[-1]=='stop'
    options=dialog.options();assert not options['mic'] and not options['system']
    assert store.settings['record_microphone'] and store.settings['record_system_audio'] and store.settings['fps']==60
    dialog.format.setCurrentText('MP4');assert dialog.fps.currentText()=='60' and dialog.mic.isEnabled() and events[-1]=='start'
    dialog.close()
