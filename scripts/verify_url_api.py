"""Native URL-coordinate capture, copy action and URL-disable preference."""
import io,json,os,subprocess,sys,time
from pathlib import Path
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QApplication,QWidget,QDialogButtonBox,QScrollArea
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
import omnishot.app as application
from omnishot.app import Controller
from omnishot.api import parse_url
from omnishot.widgets import Settings,JOBS
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate):
    deadline=time.monotonic()+8
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert predicate()
def click(widget,window,checkbox=False):
    for scroll in window.findChildren(QScrollArea):
        if scroll.widget() and scroll.widget().isAncestorOf(widget):scroll.ensureWidgetVisible(widget);QTest.qWait(100)
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==window.windowTitle())
    point=widget.rect().center()
    if checkbox:point.setX(8)
    point=widget.mapTo(window,point);backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(100);command('click 272');QTest.qWait(100)
class Pattern(QWidget):
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#468ac0'))
base=Pattern();base.setWindowTitle('OmniShot Generated API Test');base.showFullScreen();QTest.qWait(300)
state=Controller.__new__(Controller);state.app=app;state.store=backend.Store(out/'data');state.windows=[];state.overlays=[];state.pins=[];state.selectors=[];state.busy=False;state.recorder=None;state.panel=None;state.hidden_for_capture=[];state.quit_after_recording=False;state.last_closed=None
errors=[];application.error=lambda parent,message:errors.append(str(message))
try:
    url='omnishot://capture-area?x=120&y=160&width=320&height=180&display=1&action=copy'
    state.dispatch(parse_url(url));wait(lambda:not state.busy and not JOBS and len(state.store.history())==1)
    assert not errors,errors
    pixels=Image.open(io.BytesIO(backend.run(['wl-paste','--type','image/png','--no-newline'])))
    assert pixels.size==(512,288) and pixels.convert('RGB').getpixel((200,100))==(70,138,192)
    assert state.store.settings['previous_area']==[120,785,320,180],state.store.settings['previous_area']
    settings=Settings(state.store,'advanced');settings.show();QTest.qWait(200);click(settings.fields['url_api_enabled'],settings,True)
    click(settings.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save),settings)
    assert not backend.Store(state.store.root).settings['url_api_enabled']
    state.dispatch(parse_url(url));QTest.qWait(200);assert len(state.store.history())==1 and errors and 'disabled' in errors[-1]
    state.dispatch(dict(command='fullscreen',action='copy'));wait(lambda:not state.busy and not JOBS and len(state.store.history())==2)
    pixels=Image.open(io.BytesIO(backend.run(['wl-paste','--type','image/png','--no-newline'])));assert pixels.size==(2880,1800)
    report=dict(native_url_capture=True,lower_left_coordinates=True,copy_action=True,native_disable_preference=True,disabled_url_does_not_capture=True,direct_cli_still_works=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cancel_selection()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3);backend.run(['wl-copy','--clear'])
