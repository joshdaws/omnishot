"""Native selection gestures over a generated frozen frame, without reading the desktop."""
import argparse,json,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import QPoint,Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.selection import Selector

parser=argparse.ArgumentParser();parser.add_argument("output",type=Path);args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");theme=ThemeManager(app)
monitor=next(m for m in backend.capture_monitors() if m.get("focused"))
frame=np.zeros((monitor["height"],monitor["width"],3),np.uint8);frame[:]=[34,45,64];frame[::40]=[90,120,170];frame[:,::40]=[90,120,170]
selector=Selector(monitor,frame,"select");result=[];cancelled=[];selector.selected.connect(lambda *args:result.append(args));selector.cancelled.connect(lambda:cancelled.append(True))
def wait(n):
    end=time.monotonic()+n
    while time.monotonic()<end:app.processEvents();time.sleep(.01)
def drag(a,b):
    QTest.mousePress(selector,Qt.MouseButton.LeftButton,pos=QPoint(*a));QTest.mouseMove(selector,QPoint(*b));QTest.mouseRelease(selector,Qt.MouseButton.LeftButton,pos=QPoint(*b));wait(.08)
try:
    selector.showFullScreen();wait(.4)
    drag((120,120),(520,420));r=selector.selection;assert r.width()==401 and r.height()==301,r
    drag((300,250),(350,280));r=selector.selection;assert r.x()==170 and r.y()==150,r
    drag((r.right(),r.bottom()),(r.right()+60,r.bottom()+40));r=selector.selection;assert r.width()==461 and r.height()==341,r
    selector.width_box.setValue(640);selector.height_box.setValue(400);wait(.1)
    QTest.keyClick(selector,Qt.Key.Key_Right,Qt.KeyboardModifier.ShiftModifier);QTest.keyClick(selector,Qt.Key.Key_Down)
    assert selector.selection.x()==180 and selector.selection.y()==151
    selector.grab().save(str(out/"selection.png"));QTest.keyClick(selector,Qt.Key.Key_Return);assert len(result)==1
    rect,image,kind=result[0];scale=monitor["width"]/selector.width()
    assert rect==(monitor["x"]+180,monitor["y"]+151,640,400),rect
    assert image.width()==round(640*scale) and image.height()==round(400*scale),(image.width(),image.height(),scale)
    image.save(str(out/"capture.png"));selector.close();selector=Selector(monitor,frame,"select");selector.cancelled.connect(lambda:cancelled.append(True));selector.showFullScreen();wait(.15);QTest.keyClick(selector,Qt.Key.Key_Escape);assert cancelled==[True]
    report={"logical_rect":rect,"pixels":[image.width(),image.height()],"draw_move_resize_exact_keyboard_enter_escape":True};(out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
finally:selector.close();app.processEvents()
