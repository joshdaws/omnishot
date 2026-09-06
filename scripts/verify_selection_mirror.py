"""Native clean selection pixels and independent recording/selection leases."""
import json,os,sys,time
from pathlib import Path
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from omnishot import backend
from omnishot.clean_capture import SelectionMirror,CleanCapture
from omnishot.widgets import place_window
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False)
base=QWidget();base.setWindowTitle('OmniShot Generated Mirror Fixture');base.setStyleSheet('background:#4a8ddd');base.resize(500,350);base.show();place_window(base,300,200);QTest.qWait(200)
overlay=QWidget();overlay.setWindowTitle('OmniShot Selection — HEADLESS-1');overlay.setStyleSheet('background:#ee3344');overlay.resize(500,350);overlay.show();place_window(overlay,300,200);QTest.qWait(250)
backend.move_cursor(100,100)
rect=(400,300,100,80);selection=SelectionMirror();record=CleanCapture(backend.capture_monitors(),None)
def color():return tuple(backend.grab(rect)[20,20])
try:
    assert color()==(238,51,68),color()
    selection.start();QTest.qWait(250);assert color()==(74,141,221),color()
    record.start();record.stop();QTest.qWait(150);assert color()==(74,141,221),color()
    record.start();selection.stop();QTest.qWait(150);assert color()==(238,51,68),color()
    assert any(p['name']=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
    record.stop();assert not any(p['name']=='omnishot-clean-mirror' for p in backend.hypr('plugin list'))
    report=dict(selection_excluded_from_screencopy=True,visible_surface_retained=True,recording_stop_preserves_selection=True,selection_stop_preserves_recording=True,last_release_unloads_owned_plugin=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    selection.stop();record.stop();overlay.close();base.close()
