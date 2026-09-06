"""Native capture-time Shift/Ctrl across live, frozen, window and scrolling."""
import io,json,os,subprocess,sys,time
from pathlib import Path
from PIL import Image
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QPainter,QColor
from PySide6.QtWidgets import QApplication,QWidget,QCheckBox,QDialogButtonBox
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.app import Controller
from omnishot.widgets import Settings,JOBS,place_window
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def wait(predicate,seconds=10):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();QTest.qWait(1);time.sleep(.02)
    assert predicate(),dict(errors=errors,history=len(state.store.history()),overlays=len(state.overlays),busy=state.busy,jobs=len(JOBS))
def point(x,y):backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(80)
def click(widget,window):
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==window.windowTitle());p=widget.mapTo(window,QPoint(10,widget.height()//2) if isinstance(widget,QCheckBox) else widget.rect().center());point(client['at'][0]+p.x(),client['at'][1]+p.y());command('click 272');QTest.qWait(150)
class Pattern(QWidget):
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#4a8ddd'));p.setPen(QColor('white'))
        for y in range(30,self.height(),40):p.drawText(20,y,f'Generated capture row {y}')
window=Pattern();window.setWindowTitle('OmniShot Generated Modifier Fixture');window.resize(750,480);window.show();place_window(window,350,220);QTest.qWait(250)
state=Controller(app);state.store.settings.update(background_preset='Ocean',overlay_timeout=0,freeze=False);errors=[]
import omnishot.app as application
application.error=lambda parent,message:errors.append(str(message))
def finish_capture(before,copied=True):
    wait(lambda:len(state.store.history())==before+1 and bool(state.overlays) and not state.busy and not JOBS)
    assert not errors,errors
    path=Path(state.store.history()[0]['path']);assert state.store.metadata(path)['skip_background']
    assert Image.open(path).convert('RGB').getpixel((100,20))==(74,141,221)
    preview=Image.open(state.store.display_image(path)).convert('RGBA')
    if copied:
        data=subprocess.check_output(['wl-paste','--no-newline','--type','image/png']);clipboard=Image.open(io.BytesIO(data)).convert('RGBA');assert clipboard.size==preview.size and clipboard.tobytes()==preview.tobytes()
    for overlay in list(state.overlays):overlay.close()
    QTest.qWait(150);return path

def select_area(mode,freeze=False,copied=True):
    before=len(state.store.history());state.store.settings['freeze']=freeze;state.capture(mode,{'action':'overlay'})
    if freeze:wait(lambda:bool(state.selectors));QTest.qWait(250)
    else:
        wait(lambda:any(layer.get('namespace')=='selection' for monitor in backend.hypr('layers').values() for layers in monitor['levels'].values() for layer in layers));QTest.qWait(100)
    point(400,300);command('button 272 1');QTest.qWait(70);command('move 300 180');QTest.qWait(120);command('mods 5');QTest.qWait(80);command('button 272 0');command('mods 0')
    if mode=='scroll':
        wait(lambda:state.panel is not None and state.panel.isVisible());panel=state.panel;QTest.qWait(200);click(panel.start_btn,panel);wait(lambda:panel.stitcher.accepted>=1 and not panel.busy);click(panel.done_btn,panel)
    return finish_capture(before,copied)
try:
    select_area('area');select_area('area',True)
    before=len(state.store.history());state.capture('window',{'action':'overlay'});wait(lambda:bool(state.selectors));QTest.qWait(200);point(600,420);command('mods 5');QTest.qWait(70);command('click 272');command('mods 0');finish_capture(before)
    select_area('scroll')
    settings=Settings(state.store,'screenshots');settings.show();QTest.qWait(200)
    from PySide6.QtWidgets import QScrollArea
    field=settings.fields['capture_ctrl_copy'];scroll=field.parentWidget()
    while scroll and not isinstance(scroll,QScrollArea):scroll=scroll.parentWidget()
    if scroll:scroll.ensureWidgetVisible(field)
    QTest.qWait(150);click(field,settings);assert not field.isChecked();click(settings.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save),settings)
    assert not backend.Store(state.store.root).settings['capture_ctrl_copy']
    backend.copy_text('Keep this clipboard');select_area('area',True,False)
    assert subprocess.check_output(['wl-paste','--no-newline','--type','text/plain;charset=utf-8']).decode()=='Keep this clipboard'
    before=len(state.store.history());state.store.settings['freeze']=False;state.capture('area',{});wait(lambda:any(layer.get('namespace')=='selection' for monitor in backend.hypr('layers').values() for layers in monitor['levels'].values() for layer in layers));QTest.qWait(100);command('key 1 0');wait(lambda:not state.busy and not JOBS)
    assert len(state.store.history())==before and not errors,errors
    assert state.store.settings['background_preset']=='Ocean'
    report=dict(native_live_shift_ctrl=True,native_frozen_shift_ctrl=True,native_window_shift_ctrl=True,scrolling_initial_modifiers_preserved=True,clipboard_matches_export=True,copy_adds_to_overlay=True,ctrl_preference_persists=True,disabled_ctrl_preserves_clipboard=True,escape_silent=True,automatic_preset_unchanged=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cancel_selection();state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    command('mods 0');command('button 272 0');fixture.stdin.close();fixture.wait(timeout=3)
