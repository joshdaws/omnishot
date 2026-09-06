"""Native restart/cancel recording using only a generated fullscreen pattern."""
import json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QApplication,QWidget,QPushButton
from PySide6.QtTest import QTest
from shiboken6 import isValid
from omnishot import backend,recording
from omnishot.app import Controller
from omnishot.widgets import JOBS
from omnishot.clean_capture import NATIVE
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False)
class Pattern(QWidget):
    color='#2468ac'
    def paintEvent(self,event):p=QPainter(self);p.fillRect(self.rect(),QColor(self.color))
source=Pattern();source.setWindowTitle('OmniShot Lifecycle Test Pattern');source.showFullScreen();QTest.qWait(500)
assert next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==source.windowTitle())['fullscreen']==2
state=Controller(app);completed=[];errors=[];state.finished_recording=completed.append;state.recovered_recording=lambda p,m:errors.append(m);recording.error=lambda parent,m:errors.append(str(m))
isolated='--isolated' in sys.argv
if isolated:
    assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
    original_command=recording.recorder_command
    def isolated_command(*args,**kwargs):
        command=original_command(*args,**kwargs)
        assert '-p' in command,'Isolated recording must use the test compositor capture plugin'
        command[command.index('-w')+1]='screen'
        return command
    recording.recorder_command=isolated_command
old_dnd=backend.run(['omarchy-shell','notifications','isDnd']).decode().strip() if not isolated else None
def wait(predicate,seconds=15):
    deadline=time.monotonic()+seconds
    while not predicate() and not errors and time.monotonic()<deadline:app.processEvents();QTest.qWait(1);time.sleep(.02)
    assert not errors,errors
    assert predicate(),'Condition not reached'
def press(rec,text):
    wait(lambda:any(c["pid"]==os.getpid() and c["title"]==rec.windowTitle() for c in backend.hypr("clients")));QTest.qWait(150)
    widget=next(b for b in rec.findChildren(QPushButton) if b.text()==text);client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==rec.windowTitle());point=widget.mapTo(rec,widget.rect().center());backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(100);command('click 272');QTest.qWait(100)

opts=dict(mode='Fullscreen',format='MP4',fps=15,quality='high',size='Native',system=False,mic=False,cursor=False,delay=0,studio=True,camera=False,dnd=not isolated,show_controls=True,show_time=True)
try:
    state.launch_recorder(None,{**opts,'delay':3});countdown=state.recorder;countdown_path=countdown.path;press(countdown,'Cancel');wait(lambda:state.recorder is None);assert not countdown_path.exists()
    state.launch_recorder(None,opts);first=state.recorder;first_path=first.path;wait(lambda:first.ready);QTest.qWait(650)
    source.color='#22cc66';source.update();QTest.qWait(80);press(first,'Restart');wait(lambda:state.recorder is not None and state.recorder is not first and state.recorder.ready)
    second=state.recorder;second_path=second.path;assert not first_path.exists() and not list(state.store.root.glob('tracks/'+first_path.stem+'*'))
    assert not completed;QTest.qWait(650);press(second,'Pause');assert second.paused;press(second,'Cancel');wait(lambda:state.recorder is None and not JOBS)
    assert not second_path.exists() and not list(state.store.root.glob('tracks/'+second_path.stem+'*')) and not state.store.history()
    assert isolated or backend.run(['omarchy-shell','notifications','isDnd']).decode().strip()==old_dnd
    state.launch_recorder(None,{**opts,'studio':False});third=state.recorder;wait(lambda:third.ready);QTest.qWait(1400);press(third,'Stop');wait(lambda:bool(completed) and state.recorder is None and not JOBS,30)
    final=Path(completed[0]);probe=json.loads(backend.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',final]));assert not any(s['codec_type']=='audio' for s in probe['streams'])
    frame=out/'final-frame.png';backend.run(['ffmpeg','-v','error','-y','-ss','0.5','-i',final,'-frames:v','1',frame]);pixels=np.array(Image.open(frame).convert('RGB'));h,w=pixels.shape[:2];assert np.max(abs(pixels[h//2,w//2].astype(int)-[34,204,102]))<8
    assert len(state.store.history())==1 and not any(p.get('name')=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
    assert isolated or backend.run(['omarchy-shell','notifications','isDnd']).decode().strip()==old_dnd
    report=dict(countdown_cancel=True,native_restart=True,discarded_take_and_tracks_removed=True,pause_then_cancel=True,subsequent_recording_valid=True,dnd_checked=not isolated,dnd_restored=None if isolated else True,clean_extension_released=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    if state.recorder and isValid(state.recorder):state.recorder.shutdown()
    state.cleanup();source.close();fixture.stdin.close();fixture.wait(timeout=3)
    for widget in app.topLevelWidgets():widget.close()
