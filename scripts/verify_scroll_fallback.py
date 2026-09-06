"""Native scrolling guide, controls, live preview and annotation handoff."""
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QImage,QPainter,QColor,QFont,QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QScrollArea,QLabel
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.widgets import ScrollPanel,QuickOverlay,place_window
from omnishot.editor import Editor

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);horizontal="--horizontal" in sys.argv
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");app.setStyle("Fusion");theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=="ready"
def command(value):fixture.stdin.write(value+"\n");fixture.stdin.flush()
def wait(predicate,seconds=12):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:
        app.processEvents();time.sleep(.02)
    if not predicate():
        Image.fromarray(backend.grab()).save(out/"capture-failure-screen.png")
        raise AssertionError((panel.status.text(),panel.stitcher.accepted,panel.busy,panel.auto,area.verticalScrollBar().value(),area.horizontalScrollBar().value(),backend.hypr("cursorpos")))
def click(widget,window):
    client=next(c for c in backend.hypr("clients") if c["title"]==window.windowTitle())
    point=widget.mapTo(window,widget.rect().center());backend.move_cursor(client["at"][0]+point.x()-2,client["at"][1]+point.y())
    command("move 2 0");QTest.qWait(70);command("click 272");QTest.qWait(20);backend.move_cursor(1,1);command("move 1 0");QTest.qWait(130)
store=backend.Store(out/"data");store.settings.update(scroll_interval=400,scroll_step=3,overlay_timeout=0)
window=QWidget();window.setWindowTitle("OmniShot Scroll Interface Test");window.resize(1784,1070)
layout=QVBoxLayout(window);layout.addWidget(QLabel("Generated scrolling content"));area=QScrollArea();layout.addWidget(area)
image=QImage(3600 if horizontal else 710,550 if horizontal else 3600,QImage.Format.Format_RGB888);image.fill(QColor("white"));painter=QPainter(image);painter.setFont(QFont("sans-serif",18))
if horizontal:
    for x in range(0,3600,130):
        for y in range(0,550,80):
            painter.fillRect(x+5,y+5,120,70,QColor.fromHsv((x+y)%360,70,240));painter.setPen(QColor("#243756"));painter.drawText(x+12,y+46,f"{x//130+1:02d} / {y//80+1}")
else:
    for y in range(0,3600,80):
        painter.fillRect(10,y+5,690,70,QColor("#e6eef8" if y%160 else "white"));painter.setPen(QColor("#243756"));painter.drawText(25,y+46,f"Row {y//80+1:02d} · unique marker {y*73+42}")
painter.end();label=QLabel();label.setPixmap(QPixmap.fromImage(image));area.setWidget(label);window.show();QTest.qWait(150);place_window(window,8,45);QTest.qWait(250)
client=next(c for c in backend.hypr("clients") if c["title"]==window.windowTitle());offset=area.viewport().mapTo(window,QPoint(0,0))
rect=(client["at"][0]+offset.x(),client["at"][1]+offset.y(),1750,min(1000,area.viewport().height()-4))
backend.move_cursor(1,1);command("move 1 0");QTest.qWait(100)
baseline=backend.grab(rect);panel=ScrollPanel(rect,store,horizontal);received=[];panel.completed.connect(received.append)
cancelled=[];panel.cancelled.connect(lambda:cancelled.append(True));frames=[];original_grab=backend.grab

def capture(rectangle=None,*args,**kwargs):
    frame=original_grab(rectangle,*args,**kwargs)
    if rectangle==rect:frames.append(frame.copy())
    return frame
backend.grab=capture
try:
    panel.show();QTest.qWait(400)
    assert not panel.outside
    click(panel.start_btn,panel);wait(lambda:panel.stitcher.accepted>=1)
    panel.timer.stop();wait(lambda:not panel.busy);QTest.qWait(300)
    assert panel.preview.isVisible() and not panel.visuals.preview_outside
    Image.fromarray(original_grab()).save(out/"fallback-screen.png")
    panel.tick();wait(lambda:not panel.busy);QTest.qWait(300)
    assert len(frames)==2,len(frames)
    for index,frame in enumerate(frames):
        Image.fromarray(frame).save(out/f"frame-{index}.png")
        if not np.array_equal(frame,baseline):
            Image.fromarray(baseline).save(out/"baseline.png")
            yy,xx=np.where(np.any(frame!=baseline,axis=2))
            raise AssertionError((index,[int(xx.min()),int(yy.min()),int(xx.max()),int(yy.max())],int(len(xx))))
    assert panel.isVisible() and panel.preview.isVisible()
    click(panel.cancel_btn,panel);wait(lambda:panel.closed)
    assert cancelled==[True] and not received
    assert not any(g.isVisible() for g in panel.visuals.guides) and not panel.preview.isVisible()
    report=dict(display_scale=backend.capture_monitors()[0]["scale"],overlapping_controls_excluded=True,overlapping_preview_excluded=True,frames=len(frames),native_cancel=True,guide_cleanup=True)
    (out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    panel.close();wait(lambda:not panel.busy,4)
    for widget in app.topLevelWidgets():widget.close()
    command("button 272 0");fixture.stdin.close();fixture.wait(timeout=3)
