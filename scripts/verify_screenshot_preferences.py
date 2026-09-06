"""Fractional-scale selection preferences using generated pixels and Wayland keys."""
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from PySide6.QtCore import Qt,QPoint,QRect
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.app import Controller
from omnishot.editor import Editor
from omnishot.selection import Selector
from omnishot.widgets import cursor_position

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");app.setStyle("Fusion");theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=="ready"
def command(value):fixture.stdin.write(value+"\n");fixture.stdin.flush()
monitor=backend.capture_monitors()[0];frame=np.full((monitor["height"],monitor["width"],3),(32,100,180),np.uint8)
store=backend.Store(out/"data");store.settings.update(scale_screenshots=True,screenshot_border=True,background_preset="Ocean",crosshair_mode="disabled")
controller=Controller.__new__(Controller);controller.store=store;controller.restore_capture_windows=lambda:None;controller.busy=False;controller.selectors=[];paths=[];controller.overlay=paths.append
selector=Selector(monitor,frame,"select",settings=store.settings);controller.selectors=[selector]
selector.selected.connect(lambda rect,img,kind:controller.selection_done(rect,img,kind,None,selector.skip_background))
try:
    QTest.qWait(200);pointer=cursor_position();selector.showFullScreen();controller.activate_selection(pointer);QTest.qWait(300)
    selector.selection=QRect(110,90,200,120);selector.width_box.setValue(200);selector.height_box.setValue(120);selector.pointer=QPoint(350,230);selector.update();QTest.qWait(80)
    disabled=selector.grab().toImage();selector.settings["crosshair_mode"]="always";selector.settings["show_magnifier"]=False;selector.update();QTest.qWait(80)
    crosshair=selector.grab().toImage();ratio=disabled.devicePixelRatio()
    # This sample lies on the crosshair, outside the selected region and text.
    pos=QPoint(round(500*ratio),round(230*ratio));assert disabled.pixelColor(pos)!=crosshair.pixelColor(pos)
    selector.settings["show_magnifier"]=True;selector.update();QTest.qWait(80);magnifier=selector.grab().toImage()
    pos=QPoint(round(390*ratio),round(270*ratio));assert magnifier.pixelColor(pos)!=crosshair.pixelColor(pos)
    selector.settings["crosshair_mode"]="selecting";selector.start=None;selector.update();QTest.qWait(60)
    assert selector.grab().toImage().pixelColor(round(500*ratio),round(230*ratio))==disabled.pixelColor(round(500*ratio),round(230*ratio))
    selector.grab().save(str(out/"selection-preferences.png"))
    command("key 28 1");QTest.qWait(350)
    assert len(paths)==1 and selector.skip_background
    editor=Editor(paths[0],store)
    assert editor.base.width()==200 and editor.base.height()==120 and editor.background is None
    assert editor.base.pixelColor(0,0).name()=="#000000" and editor.base.pixelColor(1,1).name()=="#2064b4"
    editor.base.save(str(out/"scaled-bordered.png"));editor.close();editor.deleteLater()
    reopened=Editor(paths[0],store);assert reopened.background is None and reopened.base.width()==200;reopened.close()
    report=dict(display_scale=monitor["scale"],logical_selection=[200,120],saved_pixels=[200,120],one_pixel_border=True,shift_enter_skips_preset=True,history_preserves_bypass=True,crosshair_and_magnifier_preferences=True)
    (out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command("mods 0")
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
