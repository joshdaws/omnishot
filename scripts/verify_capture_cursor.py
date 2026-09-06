"""Native software-cursor inclusion, persistent leases and capture failure cleanup."""
import json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from omnishot import backend
from omnishot.clean_capture import CursorMirror,MirrorLease

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot')
class Pattern(QWidget):
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#dae8f7'));p.fillRect(0,self.height()//2,self.width(),self.height(),QColor('#2479ad'))
window=Pattern();window.showFullScreen();QTest.qWait(350)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def clear():return not any(p['name']=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
lease=CursorMirror();run=backend.run
try:
    assert all(m['name'].startswith('HEADLESS-') for m in backend.capture_monitors())
    # The isolated compositor's startup warning has an animated progress bar.
    backend.run(['hyprctl','dismissnotify']);QTest.qWait(200)
    backend.move_cursor(450,340);command('move 1 0');QTest.qWait(150)
    monitor=backend.capture_monitors()[0];cases=[('region',dict(rect=(300,200,500,350))),('output',dict(output=monitor['name'],scale=monitor['scale'])),('desktop',{})]
    results=[]
    for name,arguments in cases:
        lease.start();QTest.qWait(100);expected=backend.grab(**arguments);lease.stop();assert clear()
        actual=backend.grab(**arguments)
        if not np.array_equal(actual,expected):
            Image.fromarray(actual).save(out/(name+'-failure.png'));Image.fromarray(expected).save(out/(name+'-expected.png'))
            yy,xx=np.where(np.any(actual!=expected,axis=2));print('DIFFERENCE',name,len(yy),[int(xx.min()),int(yy.min()),int(xx.max()),int(yy.max())],flush=True)
        assert np.array_equal(actual,expected),(name,'Pointer leaked into cursor-disabled capture')
        assert clear()
        included=backend.grab(cursor=True,**arguments);assert clear()
        difference=np.any(included!=expected,axis=2);assert 10<int(difference.sum())<5000,(name,int(difference.sum()))
        results.append(dict(mode=name,pointer_excluded_exactly=True,explicit_cursor_pixels=int(difference.sum()),lease_released=True))
    lease.start();expected=backend.grab(cases[0][1]['rect']);assert lease.enabled and not clear()
    backend.grab(cases[0][1]['rect']);assert lease.enabled and MirrorLease.roles['cursor_capture']==1
    lease.stop();assert clear()
    def fail(args,**kwargs):
        if args[0]=='grim':raise RuntimeError('Generated screencopy failure')
        return run(args,**kwargs)
    backend.run=fail
    try:backend.grab(cases[0][1]['rect'])
    except RuntimeError as exc:assert str(exc)=='Generated screencopy failure'
    else:raise AssertionError('Capture failure was swallowed')
    assert clear() and not any(MirrorLease.roles.values())
    report=dict(display_scale=monitor['scale'],modes=results,persistent_lease_preserved=True,capture_failure_releases_lease=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    backend.run=run;lease.stop();window.close();fixture.stdin.close();fixture.wait(timeout=3)
