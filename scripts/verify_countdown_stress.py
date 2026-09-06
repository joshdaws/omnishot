"""Repeated native All-In-One timer cancellation across shortcut lease reuse."""
import json,os,subprocess,sys,time
from pathlib import Path
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from omnishot import backend
from omnishot.app import Controller
from omnishot.theme import ThemeManager
from omnishot.capture_countdown import CaptureCountdown
from omnishot.widgets import JOBS,place_window
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');manager=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=4):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();QTest.qWait(1);time.sleep(.02)
    assert predicate(),'Countdown stress timeout'
def click(widget):
    top=widget.window();c=next(c for c in backend.hypr('clients') if c['title']==top.windowTitle());p=widget.mapTo(top,widget.rect().center());backend.move_cursor(c['at'][0]+p.x()-2,c['at'][1]+p.y());command('move 2 0');QTest.qWait(70);command('click 272');QTest.qWait(120)
window=QWidget();window.setWindowTitle('OmniShot Countdown Stress Source');window.resize(800,500);window.show();place_window(window,350,250);QTest.qWait(250)
state=Controller(app);state.store.settings.update(freeze=False,previous_area=[450,350,300,180],delay=5,capture_actions=['overlay'],overlay_timeout=0);count=0
try:
    for iteration in range(10):
        state.capture('select',{'action':'overlay'});wait(lambda:bool(state.selectors));QTest.qWait(250);click(state.selectors[0].controls.buttons['Self timer'])
        wait(lambda:any(isinstance(w,CaptureCountdown) and w.isVisible() for w in state.windows));timer=next(w for w in state.windows if isinstance(w,CaptureCountdown) and w.isVisible());wait(lambda:timer.keys.active)
        source=next(c for c in backend.hypr('clients') if c['title']==window.windowTitle());backend.focus_window(source['address']);QTest.qWait(100);command('key 1 0')
        end=time.monotonic()+1.5
        while state.busy and time.monotonic()<end:app.processEvents();QTest.qWait(1);time.sleep(.02)
        if state.busy:
            details=dict(iteration=iteration,keys_active=timer.keys.active,keys_error=timer.keys.error,remaining=timer.deadline-time.monotonic(),windows=[dict(title=c['title'],hidden=c.get('hidden'),mapped=c.get('mapped')) for c in backend.hypr('clients') if c['pid']==os.getpid()])
            (out/'failure.json').write_text(json.dumps(details,indent=2));raise AssertionError(details)
        assert not state.store.history() and not any('OmniShot screenshot countdown' in b.get('description','') for b in backend.hypr('binds'))
        count+=1;QTest.qWait(100)
    (out/'report.json').write_text(json.dumps(dict(native_timer_cancellations=count,history_empty=True,bindings_released=True),indent=2));print('Passed',count,'native timer cancellations')
finally:
    command('mods 0');command('button 272 0');state.cancel_selection();state.cleanup()
    for w in app.topLevelWidgets():w.close()
    fixture.stdin.close();fixture.wait(timeout=3)
