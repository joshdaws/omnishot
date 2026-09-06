"""Native exact-size, aspect-lock and keyboard resizing over generated pixels."""
import json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import QPoint,QRect
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.app import Controller
from omnishot.selection import Selector

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');theme=ThemeManager(app)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def key(code,mods=0):command(f'key {code} {mods}');QTest.qWait(100)
monitor=next(m for m in backend.capture_monitors() if m.get('focused'))
frame=np.full((monitor['height'],monitor['width'],3),[36,104,172],np.uint8);frame[::40]=[190,210,240];frame[:,::40]=[190,210,240]
selector=Selector(monitor,frame,'select',previous=[120,140,640,400]);state=Controller.__new__(Controller);state.selectors=[selector]
result=[];selector.selected.connect(lambda *args:result.append(args))
def at(point):
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==selector.windowTitle())
    backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(80)
def click(widget):at(widget.mapTo(selector,widget.rect().center()));command('click 272');QTest.qWait(120)
def number(widget,text):
    click(widget);key(30,4)
    for digit in text:key(11 if digit=='0' else int(digit)+1)
    key(15)
def ratio(index):
    click(selector.aspect);key(102)
    for _ in range(index):key(108)
    key(28)
def drag(edge,dx,dy,shift=False):
    r=selector.selection;point=r.bottomRight() if edge=='rb' else QPoint(r.right(),r.center().y())
    at(point)
    if shift:command('mods 1')
    command('button 272 1');QTest.qWait(70);command(f'move {dx} {dy}');QTest.qWait(120);command('button 272 0');command('mods 0');QTest.qWait(150)
try:
    selector.showFullScreen();QTest.qWait(300);state.activate_selection(QPoint(300,300));QTest.qWait(250)
    ratio(2);assert selector.aspect.currentText()=='16:9' and selector.selection.size().toTuple()==(640,360)
    number(selector.height_box,'225');assert selector.selection.size().toTuple()==(400,225),selector.selection
    number(selector.width_box,'20000');r=selector.selection
    assert selector.rect().contains(r) and selector.width_box.value()==r.width() and selector.height_box.value()==r.height()
    assert abs(r.width()-r.height()*16/9)<2
    number(selector.width_box,'800');assert selector.selection.size().toTuple()==(800,450)
    drag('rb',-80,-10);assert selector.selection.size().toTuple()==(720,405),selector.selection
    key(108,5);assert selector.selection.size().toTuple()==(738,415),selector.selection
    ratio(0);assert selector.aspect.currentText()=='Free'
    drag('rb',-38,0,True);assert selector.selection.size().toTuple()==(700,394),selector.selection
    key(106,1);key(108);assert selector.selection.getRect()==(130,141,700,394),selector.selection
    selector.grab().save(str(out/'selection-precision.png'));key(28);assert len(result)==1
    rect,image,kind=result[0];assert rect==(130,141,700,394)
    assert image.size().toTuple()==(1120,630),image.size()
    image.save(str(out/'precise-capture.png'))
    selector.close();QTest.qWait(150);selector=Selector(monitor,frame,'select');state.selectors=[selector];selector.showFullScreen();QTest.qWait(200);state.activate_selection(QPoint(100,100));QTest.qWait(200)
    at(QPoint(100,100));command('mods 1');command('button 272 1');QTest.qWait(80);command('move 300 500');QTest.qWait(150);command('button 272 0');command('mods 0');QTest.qWait(150)
    assert selector.selection.getRect()==(100,100,501,501),selector.selection
    assert selector.width_box.value()==selector.height_box.value()==501
    cancelled=[];selector.cancelled.connect(lambda:cancelled.append(True));key(1);assert cancelled==[True]
    report=dict(native_aspect_choice=True,typed_height_updates_width=True,oversize_keeps_ratio_and_updates_fields=True,corner_resize_keeps_selected_aspect=True,ctrl_shift_arrow_resize=True,shift_resize_preserves_free_ratio=True,new_shift_drag_square=True,arrow_move=True,enter_capture=True,logical_region=rect,captured_pixels=image.size().toTuple())
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    selector.close();command('mods 0');command('button 272 0');fixture.stdin.close();fixture.wait(timeout=3)
