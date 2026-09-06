"""Standalone self-timer: select first, countdown, latest pixels, action and cancel."""
import io,json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtGui import QPainter,QColor
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from omnishot import backend,theme
from omnishot.app import Controller,parse_args
from omnishot.api import parse_url
from omnishot.capture_countdown import CaptureCountdown
from omnishot.editor import Editor
from omnishot.widgets import JOBS,place_window
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data');freeze=sys.argv[3]=='frozen'
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');manager=theme.ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate(),errors

def point(x,y):backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(70)
def countdown():return next((w for w in state.windows if isinstance(w,CaptureCountdown) and w.isVisible()),None)
def selecting():
    if freeze:return bool(state.selectors)
    return any(row.get('namespace')=='selection' for monitor in backend.hypr('layers').values() for rows in monitor['levels'].values() for row in rows)
class Pattern(QWidget):
    color='#4a8ddd'
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor(self.color))
window=Pattern();window.setWindowTitle('OmniShot Generated Self Timer Source');window.resize(800,500);window.show();place_window(window,350,250);QTest.qWait(200)
state=Controller(app);state.store.settings.update(freeze=freeze,delay=2,background_preset='None',overlay_timeout=0,capture_ctrl_copy=False);errors=[]
import omnishot.app as application
application.error=lambda parent,message:errors.append(str(message))
def begin():
    started=time.monotonic();state.dispatch(parse_url('omnishot://self-timer?action=annotate'));wait(selecting,1.8)
    assert time.monotonic()-started<1.8 and countdown() is None
    if freeze:assert state.selectors[0].capture_mode.currentText()=='Self timer'
    point(450,350);command('button 272 1');QTest.qWait(70);command('move 300 180');QTest.qWait(150)
    if not freeze:
        frame=backend.grab();accent=theme.color('accent');rgb=np.array(accent.getRgb()[:3]);assert np.any(np.all(frame[:,:,:3]==rgb,axis=2))
        Image.fromarray(frame).save(out/'themed-live-selection.png')
    command('button 272 0');wait(lambda:countdown() is not None);return time.monotonic()
try:
    before=len(state.store.history());selected=begin();timer=countdown();timer.grab().save(str(out/'countdown.png'))
    assert not selecting() and not state.store.history();assert backend.hypr('activewindow').get('title')!=timer.windowTitle()
    window.color='#e35a44';window.update();wait(lambda:len(state.store.history())==before+1 and not state.busy and not JOBS)
    elapsed=time.monotonic()-selected;assert elapsed>=1.5,elapsed
    path=state.store.history()[0]['path'];image=Image.open(path).convert('RGB');assert image.size==(481,289) and image.getpixel((100,100))==(227,90,68)
    assert any(isinstance(w,Editor) for w in state.windows) and not state.overlays
    for w in list(state.windows):w.close()
    QTest.qWait(150);assert not any('OmniShot screenshot countdown' in b.get('description','') for b in backend.hypr('binds'))
    before=len(state.store.history());begin();timer=countdown();wait(lambda:timer.keys.active)
    client=next(c for c in backend.hypr('clients') if c['title']==window.windowTitle());backend.focus_window(client['address']);QTest.qWait(100);command('key 1 0')
    wait(lambda:not state.busy and countdown() is None);assert len(state.store.history())==before
    assert not any('OmniShot screenshot countdown' in b.get('description','') for b in backend.hypr('binds'))
    # Explicit native CLI delay bypasses the settings interval, with no selector.
    started=time.monotonic();state.dispatch(parse_args(['timer','--geometry','450,350 300x180','--delay','0','--action','copy']))
    wait(lambda:len(state.store.history())==before+1 and not state.busy and not JOBS);assert time.monotonic()-started<1.8
    copied=Image.open(io.BytesIO(backend.run(['wl-paste','--type','image/png','--no-newline']))).convert('RGB');assert copied.size==(480,288) and copied.getpixel((100,100))==(227,90,68)
    assert not selecting() and not any(isinstance(w,Editor) for w in state.windows) and not state.overlays
    assert not errors,errors
    report=dict(freeze=freeze,selection_before_delay=True,countdown_after_selection=True,capture_uses_latest_pixels=True,after_capture_annotate=True,global_escape_cancels=True,countdown_bindings_released=True,explicit_zero_delay_and_geometry=True,explicit_copy_action=True,theme_accent_verified=not freeze,elapsed_after_selection=round(elapsed,2),display_scale=backend.capture_monitors()[0]['scale'])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('mods 0');command('button 272 0');state.cancel_selection();state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
