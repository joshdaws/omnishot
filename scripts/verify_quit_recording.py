"""Quit waits for recording finalization and the resulting history entry."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from omnishot.theme import ThemeManager
from omnishot import backend,recording
from omnishot.app import Controller
from omnishot.recording_recovery import valid_video

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
source=out/'generated.mp4';backend.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=s=240x160:r=15:d=1','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',source])
store=backend.Store(out/'data');store.settings.update(after_recording='overlay',after_recording_extra=['edit'],ask_capture_name=False)
rec=recording.Recorder(store,None,dict(format='GIF',fps=15,cursor=False,studio=False,delay=99));shutil.copy2(source,rec.path);rec.log_path.write_text('Generated source for quit finalization check')
# An owned encoder stand-in stays alive until Stop sends SIGINT. The source and
# subsequent GIF encoder are real media; no physical device is opened.
encoder=subprocess.Popen([sys.executable,'-u','-c','import signal,sys,time; signal.signal(signal.SIGINT,lambda *args:sys.exit(0)); print("ready"); time.sleep(30)'],stdout=subprocess.PIPE,text=True);assert encoder.stdout.readline().strip()=='ready';rec.process=encoder
quit_calls=[];state=Controller.__new__(Controller);state.app=SimpleNamespace(quit=lambda:quit_calls.append(time.monotonic()));state.store=store;state.windows=[];state.overlays=[];state.pins=[];state.selectors=[];state.hidden_for_capture=[];state.busy=False;state.panel=None;state.recorder=rec;state.quit_after_recording=False
rec.completed.connect(state.finished_recording);rec.recovered.connect(state.recovered_recording);rec.destroyed.connect(state.recording_closed);completed=[];rec.completed.connect(completed.append);state.retain(rec)
try:
    assert state.request_quit() is False and not quit_calls
    deadline=time.monotonic()+18
    while not quit_calls and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert len(quit_calls)==1 and len(completed)==1 and state.recorder is None,(quit_calls,completed)
    path=Path(completed[0]);assert path.suffix=='.gif' and valid_video(path)
    assert any(row['path']==str(path) for row in store.history())
    assert not state.overlays and not state.windows
    report=dict(quit_waited_for_encoder=True,postprocessing_finished=True,history_preserved=True,quit_after_recording_destroyed=True,no_new_preview_during_quit=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    if encoder.poll() is None:encoder.terminate();encoder.wait(timeout=3)
    for widget in app.topLevelWidgets():widget.close()
