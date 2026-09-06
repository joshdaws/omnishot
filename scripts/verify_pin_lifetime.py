"""Native Wayland backing-store teardown and pin reopening regression."""
import gc,json,os,sys,time
from pathlib import Path
from PySide6.QtCore import QEvent
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication
from shiboken6 import delete,isValid
from omnishot import backend,theme
from omnishot.widgets import Pin

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setQuitOnLastWindowClosed(False);manager=theme.ThemeManager(app)
store=backend.Store(out/'data');store.settings['pin_shadow']=True
image=QImage(240,160,QImage.Format.Format_RGB32);image.fill(QColor('#287ca4'));path=store.add(image=image)
def settle(predicate):
    end=time.monotonic()+3
    while time.monotonic()<end:
        app.processEvents();time.sleep(.02)
        if predicate():return
    assert predicate()
retained=[]
for index in range(6):
    pin=Pin(path,index,store);pin.show()
    settle(lambda:pin.shadow_window is not None and pin.shadow_window.isExposed())
    shadow=pin.shadow_window;old=shadow.backing;retained.append(old)
    pin.close();assert shadow.backing is None and not isValid(old)
    pin.show();settle(lambda:shadow.isExposed() and shadow.backing is not None)
    assert isValid(shadow.backing)
    backing=shadow.backing;retained.append(backing)
    # Deferred destruction may bypass closeEvent, as can direct native deletion.
    if index%2:
        pin.deleteLater();app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    else:delete(pin)
    assert not isValid(pin) and not isValid(backing)
    del pin,shadow,backing,old;gc.collect();app.processEvents()
assert not any(c['pid']==os.getpid() for c in backend.hypr('clients'))
report=dict(repeated_close_reopen=6,deferred_deletion=3,direct_deletion=3,backing_destroyed_before_window=True,all_native_windows_released=True)
(out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
