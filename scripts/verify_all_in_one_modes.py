"""Native All-In-One buttons: area, display, window, timer, OCR and setup."""
import io,json,os,subprocess,sys,time
from pathlib import Path
from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPainter,QColor,QFont
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.app import Controller
from omnishot.capture_countdown import CaptureCountdown
from omnishot.recording import RecordSetup
from omnishot.widgets import JOBS,place_window
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=8):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();QTest.qWait(1);time.sleep(.02)
    assert predicate(),errors
def point(x,y):backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(70)
def click(widget,window):
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==window.windowTitle());p=widget.mapTo(window,widget.rect().center());point(client['at'][0]+p.x(),client['at'][1]+p.y());command('click 272');QTest.qWait(120)
class Pattern(QWidget):
    color='#4a8ddd'
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor(self.color));p.setPen(QColor('white'));p.setFont(QFont('Inter',30));p.drawText(40,70,'OMNISHOT 2026')
window=Pattern();window.setWindowTitle('OmniShot All Modes Generated Source');window.resize(800,500);window.show();place_window(window,350,250);QTest.qWait(200)
state=Controller(app);state.store.settings.update(freeze=False,background_preset='None',window_padding=0,window_shadow=False,window_wallpaper=False,overlay_timeout=0,delay=1,ocr_detect_links=False,capture_ctrl_copy=False)
errors=[]
import omnishot.app as application
application.error=lambda parent,message:errors.append(str(message))
def begin(rect=(450,350,300,180)):
    for preview in list(state.overlays):preview.close()
    QTest.qWait(120);state.store.settings['previous_area']=list(rect);state.capture('select',{'action':'overlay'});wait(lambda:bool(state.selectors));QTest.qWait(250);return state.selectors[0]
def received(before):
    wait(lambda:len(state.store.history())==before+1 and not state.busy and not JOBS)
    return Image.open(state.store.history()[0]['path']).convert('RGB')
def clean():
    assert not state.selectors and not any(p['name']=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
try:
    before=len(state.store.history());selector=begin();selector.controls.grab().save(str(out/'all-in-one-toolbar.png'));click(selector.controls.buttons['Screenshot'],selector)
    image=received(before);assert image.size==(480,288) and image.getpixel((100,100))==(74,141,221);clean()
    before=len(state.store.history());selector=begin();selector.selection=selector.selection.__class__();click(selector.controls.buttons['Fullscreen'],selector)
    image=received(before);assert image.size==(2880,1800) and image.getpixel((850,700))==(74,141,221);clean()
    before=len(state.store.history());selector=begin();click(selector.controls.buttons['Window'],selector);assert selector.capture_mode.currentText()=='Window'
    point(650,450);wait(lambda:selector.window_client is not None);command('mods 1');command('click 272');QTest.qWait(120);command('mods 0')
    image=received(before);assert image.size==(1280,800) and image.getpixel((600,400))==(74,141,221);assert state.store.metadata(state.store.history()[0]['path'])['skip_background'];clean()
    before=len(state.store.history());selector=begin();command('key 46 4');image=received(before)
    clipboard=Image.open(io.BytesIO(subprocess.check_output(['wl-paste','--no-newline','--type','image/png']))).convert('RGB');assert clipboard.tobytes()==image.tobytes() and not state.overlays;clean()
    before=len(state.store.history());selector=begin();click(selector.controls.buttons['Self timer'],selector);wait(lambda:any(isinstance(w,CaptureCountdown) and w.isVisible() for w in state.windows))
    countdown=next(w for w in state.windows if isinstance(w,CaptureCountdown));countdown.grab().save(str(out/'timer.png'))
    assert backend.hypr('activewindow').get('title')!=countdown.windowTitle()
    window.color='#e35a44';window.update();image=received(before);assert image.getpixel((100,100))==(227,90,68);clean()
    state.store.settings['delay']=5;before=len(state.store.history());selector=begin();click(selector.controls.buttons['Self timer'],selector)
    wait(lambda:any(isinstance(w,CaptureCountdown) and w.isVisible() for w in state.windows));countdown=next(w for w in state.windows if isinstance(w,CaptureCountdown));wait(lambda:countdown.keys.active)
    source=next(c for c in backend.hypr('clients') if c['title']==window.windowTitle());backend.focus_window(source['address']);wait(lambda:backend.hypr('activewindow').get('address')==source['address']);QTest.qWait(150);command('key 1 0');QTest.qWait(200);wait(lambda:not state.busy)
    assert len(state.store.history())==before and not any('OmniShot screenshot countdown' in b.get('description','') for b in backend.hypr('binds')), (len(state.store.history()),before,[b for b in backend.hypr('binds') if 'OmniShot screenshot countdown' in b.get('description','')])
    before=len(state.store.history());selector=begin((350,250,800,130));click(selector.controls.buttons['Text (OCR)'],selector);received(before)
    wait(lambda:'OMNISHOT' in subprocess.check_output(['wl-paste','--no-newline'],text=True));clean()
    seen=[];poller=QTimer();poller.setInterval(80)
    def cancel_setup():
        setup=next((w for w in app.topLevelWidgets() if isinstance(w,RecordSetup) and w.isVisible()),None)
        if setup and backend.hypr('activewindow').get('title')==setup.windowTitle():
            seen.append(True);setup.grab().save(str(out/'record-setup.png'));command('key 1 0');poller.stop()
    poller.timeout.connect(cancel_setup);poller.start();selector=begin();click(selector.controls.buttons['Record video'],selector);wait(lambda:bool(seen) and not state.busy);assert state.recorder is None;clean()
    assert not errors,errors
    report=dict(native_area_button=True,fullscreen_without_region=True,isolated_window_button=True,shift_window_transparency=True,explicit_ctrl_c_ignores_hold_preference=True,timer_captures_latest_pixels=True,global_escape_cancels_timer=True,countdown_bindings_released=True,native_ocr_button=True,native_record_setup_button=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cancel_selection();state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    command('mods 0');command('button 272 0');fixture.stdin.close();fixture.wait(timeout=3)
