"""Native recording selection: adjust remembered dimensions and restore on reopen."""
import json,os,subprocess,sys,time
from pathlib import Path
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend,recording
from omnishot.app import Controller
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False);theme=ThemeManager(app)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate):
    deadline=time.monotonic()+6
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert predicate()
class StandIn(QWidget):
    completed=Signal(str);recovered=Signal(str,str);restart_requested=Signal()
    def __init__(self,store,rect,opts):super().__init__();self.rect_capture=rect;self.opts=opts;self.setWindowTitle('OmniShot Recording Selection Result')
recording.Recorder=StandIn
state=Controller.__new__(Controller);state.app=app;state.store=backend.Store(out/'data');state.windows=[];state.overlays=[];state.pins=[];state.selectors=[];state.busy=False;state.recorder=None;state.panel=None;state.hidden_for_capture=[];state.quit_after_recording=False
state.store.settings['previous_recording_area']=[120,140,640,400]
try:
    state.recording_selection(dict(remember_selection=True));wait(lambda:bool(state.selectors));selector=state.selectors[0];QTest.qWait(300)
    assert selector.selection.getRect()==(120,140,640,400) and not selector.capture_mode.isVisible()
    selector.grab().save(str(out/'remembered-selection.png'))
    command('key 106 1');QTest.qWait(100);command('key 108 0');QTest.qWait(100);command('key 28 0')
    wait(lambda:state.recorder is not None)
    assert state.recorder.rect_capture==(130,141,640,400),state.recorder.rect_capture
    assert backend.Store(state.store.root).settings['previous_recording_area']==[130,141,640,400]
    state.recorder.close();QTest.qWait(100);state.recording_selection(dict(remember_selection=True));wait(lambda:bool(state.selectors));selector=state.selectors[0]
    assert selector.selection.getRect()==(130,141,640,400);QTest.qWait(200);command('key 1 0');wait(lambda:not state.selectors)
    state.recording_selection(dict(remember_selection=False));wait(lambda:bool(state.selectors));assert state.selectors[0].selection.isEmpty()
    QTest.qWait(200);command('key 1 0');wait(lambda:not state.selectors)
    report=dict(native_selection_confirmation=True,shift_arrow_nudge=True,dimensions_preserved=True,remembered_recording_area=True,remember_toggle=True,cancel_without_recording=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cancel_selection()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
