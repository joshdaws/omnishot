"""Run in an isolated Hyprland session with the test virtual-keyboard helper."""
import json
import sys
import subprocess
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
from omnishot import backend
from omnishot.widgets import QuickOverlay

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);helper=Path(sys.argv[2]).resolve()
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([helper],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=="ready";QTest.qWait(250)
store=backend.Store(out/"data");path=store.add(image=np.full((100,200,3),(20,100,200),np.uint8))
class KeySink(QWidget):
    def __init__(self):super().__init__();self.keys=[];self.setWindowTitle("OmniShot Shortcut Receiver");self.resize(350,300)
    def keyPressEvent(self,event):
        if event.key()!=Qt.Key.Key_Control:self.keys.append(event.key())
sink=KeySink();sink.show();QTest.qWait(200)
def owned():return [b for b in backend.hypr("binds") if b.get("description","").startswith("OmniShot hovered preview:")]
def inject(code,mods=4):fixture.stdin.write(f"key {code} {mods}\n");fixture.stdin.flush();QTest.qWait(180)
def hover(overlay):
    backend.move_cursor(900,80);QTest.qWait(150)
    client=next(c for c in backend.hypr("clients") if c["title"]==overlay.windowTitle())
    backend.move_cursor(client["at"][0]+50,client["at"][1]+65);QTest.qWait(250)
    assert owned(),("Hover shortcuts were not registered",app.platformName(),overlay.underMouse(),overlay.hover_keys.active,overlay.hover_keys.error,client,backend.hypr("cursorpos"))
    assert backend.hypr("activewindow")["title"]==sink.windowTitle(),"Hover stole focus"
overlay=QuickOverlay(path,store);actions=[]
overlay.save=lambda:actions.append("save")
overlay.annotate.connect(lambda _:actions.append("annotate"));overlay.pin.connect(lambda _:actions.append("pin"))
try:
    overlay.show();QTest.qWait(350)
    hover(overlay)
    backend.run(["hyprctl","reload"]);QTest.qWait(400)
    assert owned(),"Hovered preview shortcuts did not recover after configuration reload"
    for code,action in ((31,"save"),(18,"annotate"),(25,"pin"),(25,"pin")):
        before=len(sink.keys);inject(code)
        assert actions[-1]==action and len(sink.keys)==before,(action,actions,sink.keys)
        assert owned(),"Visible hovered preview did not rearm after its action"
    hover(overlay);before=len(sink.keys);inject(46)
    assert not overlay.isVisible() and len(sink.keys)==before
    assert backend.run(["wl-paste","--list-types"]).decode().find("image/png")>=0
    assert not owned()
    overlay=QuickOverlay(path,store);overlay.show();QTest.qWait(250)
    hover(overlay);inject(57,0);assert overlay.quicklook and overlay.quicklook.isVisible()
    inject(57,0);assert overlay.quicklook is None
    # Exiting the overlay restores delivery to the previously active app.
    backend.move_cursor(900,80);QTest.qWait(250);assert not owned()
    sink.activateWindow();QTest.qWait(100);before=len(sink.keys);inject(46)
    assert len(sink.keys)>before and sink.keys[-1]==Qt.Key.Key_C
    hover(overlay);overlay.hover_keys.timer.stop();QTest.qWait(3300)
    assert not owned(),"Unresponsive app lease did not release the shortcuts"
    overlay.hover_keys.active=False
    # A user's pre-existing binding is preserved through enter/leave.
    backend.run(["hyprctl","eval",'omnishot_test_space=hl.bind("SPACE",function() end,{description="OmniShot test pre-existing Space"})'])
    hover(overlay);assert not any(b["key"].lower()=="space" for b in owned())
    backend.move_cursor(900,80);QTest.qWait(200)
    assert any(b.get("description")=="OmniShot test pre-existing Space" for b in backend.hypr("binds"))
    backend.run(["hyprctl","eval","omnishot_test_space:remove();omnishot_test_space=nil"])
    report=dict(copy=True,save=True,annotate=True,pin=True,space_preview=True,focus_preserved=True,
                keyboard_restored=True,lease_cleanup=True,existing_shortcut_preserved=True,repeated_actions_without_pointer_movement=True,configuration_reload_recovery=True)
    (out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    for window in app.topLevelWidgets():window.close()
    fixture.stdin.close();fixture.wait(timeout=3)
