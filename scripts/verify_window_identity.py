"""Native duplicate-title window capture, occlusion, renaming and annotation."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QApplication,QWidget
from omnishot import backend
import omnishot.app as application
from omnishot.app import Controller
from omnishot.editor import Editor
from omnishot.widgets import JOBS,place_window
from omnishot.theme import ThemeManager
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=8):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert predicate()
def delay(seconds=.15):start=time.monotonic();wait(lambda:time.monotonic()-start>=seconds,seconds+1)
def client(widget):return next((c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==widget.windowTitle()),None)
def pointer(widget,point=None):
    top=widget.window();wait(lambda:client(top) is not None);native=client(top);point=widget.mapTo(top,point or widget.rect().center());backend.move_cursor(native['at'][0]+point.x()-2,native['at'][1]+point.y());command('move 2 0');delay(.06)
def click(widget):pointer(widget);command('click 272');delay()
class Pattern(QWidget):
    def __init__(self,color):super().__init__();self.color=QColor(color)
    def paintEvent(self,event):p=QPainter(self);p.fillRect(self.rect(),self.color)
windows=[];targets=[]
for index,color in enumerate(['#4a8ddd','#35b87a']):
    window=Pattern(color);window.setWindowTitle(f'OmniShot Identity {index}');window.resize(500,340);window.show();place_window(window,120+index*600,180);delay(.25)
    targets.append(client(window));windows.append(window);window.setWindowTitle('OmniShot Duplicate Title');delay(.1)
state=Controller(app);state.store.settings.update(window_wallpaper=False,window_shadow=False,window_padding=0,background_preset='None');errors=[];application.error=lambda parent,message:errors.append(str(message));records=[]
try:
    if len(sys.argv)>3:
        old=subprocess.run([sys.argv[3],targets[0]['class'],'OmniShot Duplicate Title','0'],capture_output=True,timeout=12)
        assert old.returncode and b'Multiple windows' in old.stderr
        (out/'before-failure.txt').write_bytes(old.stderr)
    for index,target_index in enumerate([0,1,0,1]):
        target=targets[target_index]
        if index==2:
            backend.move_window(targets[1]['address'],220,230);delay(.2);backend.focus_window(targets[1]['address']);backend.raise_window(targets[1]['address']);delay(.15)
        before=len(state.store.history());state.capture('window',dict(action='overlay'));wait(lambda:bool(state.selectors));delay(.2)
        x,y=(320,300) if index==2 else (target['at'][0]+250,target['at'][1]+170)
        if index==3:x,y=470,400
        backend.move_cursor(x-2,y);command('move 2 0');delay(.12)
        selector=state.selectors[0]
        if index==2:
            assert selector.current['address']==targets[1]['address'],selector.current;command('key 15 0');delay(.1)
        assert selector.current['address']==target['address'],selector.current
        if index==3:
            windows[1].setWindowTitle('OmniShot Renamed During Selection');delay(.12)
        command('key 28 0' if index==2 else 'click 272')
        wait(lambda:len(state.store.history())==before+1 and bool(state.overlays) and not JOBS and not state.busy);assert not errors,errors
        path=Path(state.store.history()[0]['path']);digest=hashlib.sha256(path.read_bytes()).hexdigest();pixels=np.array(Image.open(path).convert('RGBA'))
        expected=(74,141,221,255) if target_index==0 else (53,184,122,255)
        assert pixels.shape==(544,800,4) and np.all(pixels==expected)
        overlay=state.overlays[-1];click(overlay.preview);wait(lambda:any(isinstance(w,Editor) and w.isVisible() for w in state.windows))
        editor=next(w for w in state.windows if isinstance(w,Editor) and w.isVisible());delay(.15)
        click(editor.toolbar.widgetForAction(editor.tools['rect']))
        a=editor.view.mapFromScene(QPointF(50,50));b=editor.view.mapFromScene(QPointF(200,180))
        pointer(editor.view.viewport(),a);command('button 272 1');delay(.04);pointer(editor.view.viewport(),b);command('button 272 0');delay(.1)
        assert len(editor.objects)==1
        rendered=editor.render();project=out/f'window-{index}.omnishot';editor.write_project(project)
        if index==2:editor.grab().save(str(out/'duplicate-window-editor.png'))
        editor.close();other=Editor(project,state.store);assert other.render()==rendered and len(other.objects)==1;other.close()
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
        for overlay in list(state.overlays):overlay.close()
        delay(.08);records.append(dict(target=target_index,occluded=index==2,renamed_after_selection=index==3,isolated_pixels_exact=True,native_annotation=True,project_reopen=True,source_unchanged=True))
    # Closed selection must fail even though another same-title window remains.
    windows[0].close();delay(.15)
    try:backend.grab_window(targets[0])
    except RuntimeError:pass
    else:raise AssertionError('Closed window unexpectedly captured another surface')
    report=dict(native_picker=True,duplicate_class_and_title=True,closed_window_rejected=True,theme_applied=bool(theme.applied),cases=records)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cancel_selection();state.cleanup();command('button 272 0');command('mods 0')
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
