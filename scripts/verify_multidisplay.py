"""Mixed-scale native selection and preview placement on two isolated outputs."""
import json,os,subprocess,sys,time
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from PIL import Image
from omnishot.theme import ThemeManager
from omnishot import backend
import omnishot.app as application
from omnishot.app import Controller
from omnishot.widgets import JOBS
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
monitors=backend.hypr('monitors');assert monitors and all(m['name'].startswith('HEADLESS-') for m in monitors),'Only run in the isolated compositor'
backend.run(['hyprctl','output','create','headless','HEADLESS-2'])
# Loading a compositor plugin reloads its config. Persist the generated output's
# scale in this disposable harness so the reload does not reset it to autodetect.
config=Path(os.environ['XDG_RUNTIME_DIR'])/'hyprland.lua'
assert config.parent.name.startswith('os-') and config.parent.parent==Path('/tmp') and config.is_file()
with config.open('a') as f:f.write('\nhl.monitor({output="HEADLESS-2",mode="1920x1080@60",position="1800x0",scale=1})\n')
backend.run(['hyprctl','reload'])
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False);QTest.qWait(300)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=8):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert predicate()
class Pattern(QWidget):
    def __init__(self,color):super().__init__();self.color=color
    def paintEvent(self,event):p=QPainter(self);p.fillRect(self.rect(),QColor(self.color))
sources=[]
for name,color in [('HEADLESS-1','#468ac0'),('HEADLESS-2','#ce9850')]:
    screen=next(s for s in app.screens() if s.name()==name);window=Pattern(color);window.setWindowTitle('OmniShot '+name+' Pattern');window.winId();window.windowHandle().setScreen(screen);window.showFullScreen();sources.append(window);QTest.qWait(150)
state=Controller(app);errors=[];application.error=lambda parent,message:errors.append(str(message))
live='--live' in sys.argv
state.store.settings.update(previous_area=[120,160,640,400],window_wallpaper=False,freeze=not live)
original_done=state.selection_done
def selection_done(*args,**kwargs):
    with (out/'selection-diagnostics.jsonl').open('a') as log:
        log.write(json.dumps(dict(source_scale=args[-1],selectors=[dict(monitor=s.monitor,geometry=s.geometry().getRect(),frame=[s.image.width(),s.image.height()],selection=s.selection.getRect()) for s in state.selectors]))+'\n')
    return original_done(*args,**kwargs)
state.selection_done=selection_done
try:
    backend.move_cursor(98,100);command('move 2 0');QTest.qWait(150)
    state.capture('select',dict(action='overlay'));wait(lambda:len(state.selectors)==2);QTest.qWait(250)
    active=backend.hypr('activewindow');first=next(m for m in backend.hypr('monitors') if m['name']=='HEADLESS-1')
    assert active['monitor']==first['id'],('Selection activated wrong display',active['monitor'],first['id'])
    assert {m['name']:m['scale'] for m in backend.hypr('monitors')}=={'HEADLESS-1':1.6,'HEADLESS-2':1}
    assert all(selector.live==live for selector in state.selectors)
    command('key 28 0');wait(lambda:bool(state.overlays) and not JOBS and not state.busy)
    first_path=Path(state.store.history()[0]['path']);image=Image.open(first_path);assert image.size==(1024,640) and image.getpixel((500,300))==(70,138,192)
    assert backend.hypr('cursorpos')==dict(x=100,y=100)
    preview=state.overlays[0];assert preview.target_screen.name()=='HEADLESS-1'
    backend.move_cursor(2098,200);command('move 2 0');QTest.qWait(150);state.overlay(first_path);QTest.qWait(300)
    assert all(o.target_screen.name()=='HEADLESS-2' for o in state.overlays)
    clients=backend.hypr('clients')
    second=next(m for m in backend.hypr('monitors') if m['name']=='HEADLESS-2')
    for overlay in state.overlays:
        c=next(c for c in clients if c['pid']==os.getpid() and c['title']==overlay.windowTitle());assert c['at'][0]>=1800 and c['at'][0]+c['size'][0]<=3720 and c['monitor']==second['id'],c
    overlay=state.overlays[-1];c=next(c for c in clients if c['pid']==os.getpid() and c['title']==overlay.windowTitle());point=overlay.preview.mapTo(overlay,overlay.preview.rect().center())
    backend.move_cursor(c['at'][0]+point.x()-2,c['at'][1]+point.y());command('move 2 0');QTest.qWait(100);command('click 272')
    from omnishot.editor import Editor
    wait(lambda:any(isinstance(w,Editor) and w.isVisible() for w in state.windows));editor=next(w for w in state.windows if isinstance(w,Editor))
    assert (editor.base.width(),editor.base.height())==(1024,640);QTest.qWait(150);editor.grab().save(str(out/'secondary-preview-editor.png'));editor.close();QTest.qWait(100)
    for overlay in list(state.overlays):overlay.close()
    QTest.qWait(100);state.capture('select',dict(geometry='1900,150 500x300',action='copy'));wait(lambda:len(state.selectors)==2);QTest.qWait(200);command('key 28 0');wait(lambda:not state.busy and not JOBS and len(state.store.history())==2)
    image=Image.open(state.store.history()[0]['path']);assert image.size==(500,300) and image.getpixel((200,100))==(206,152,80),(image.size,image.getpixel((200,100)))
    state.capture('select',{});wait(lambda:len(state.selectors)==2);QTest.qWait(150);command('key 1 0');wait(lambda:not state.selectors and not state.busy)
    wait(lambda:not JOBS)
    assert not any(p['name']=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
    assert not errors,errors
    report=dict(live_selection=live,mixed_scales=[1.6,1],first_display_keyboard_focus=True,first_capture_pixels=[1024,640],second_capture_pixels=[500,300],previews_follow_active_display=True,preview_native_monitor_assignment=True,native_secondary_preview_to_annotate=True,all_selectors_cancel=True,mirror_released=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cancel_selection();state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3);backend.run(['wl-copy','--clear'])
