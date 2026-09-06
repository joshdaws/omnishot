"""Exercise real screen capture + native virtual-pointer scroll on a test window."""
import json
import sys
import time
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLabel,QScrollArea
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QPixmap,QImage,QPainter,QColor,QFont
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.stitch import ScrollStitcher
from omnishot.widgets import place_window
from omnishot.editor import qimage

out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
horizontal="--horizontal" in sys.argv
app=QApplication([]);app.setApplicationName("omnishot-test");app.setDesktopFileName("org.omarchy.OmniShot");theme=ThemeManager(app)
window=QWidget();window.setWindowTitle("OmniShot Scrolling Verification");window.resize(840,770)
layout=QVBoxLayout(window);layout.addWidget(QLabel("OmniShot native scrolling verification — generated test content"))
area=QScrollArea();layout.addWidget(area)
image=QImage(4200 if horizontal else 760,680 if horizontal else 4200,QImage.Format.Format_RGB888);image.fill(QColor("#f3f5fa"));p=QPainter(image);p.setFont(QFont("sans-serif",18))
if horizontal:
    for x in range(0,4200,170):
        for y in range(0,680,85):
            p.fillRect(x+10,y+10,150,66,QColor.fromHsv((x+y)%360,65,245));p.setPen(QColor("#243756"));p.drawText(x+20,y+44,f"{x//170+1:02d} / {y//85+1}")
else:
    for y in range(0,4200,90):
        p.fillRect(25,y+12,710,68,QColor("#e1e8f6" if y%180 else "#ffffff"));p.setPen(QColor("#243756"));p.drawText(45,y+48,f"Capture row {y//90+1:02d} · unique marker {y*79+173}")
        p.fillRect(645,y+25,65,35,QColor.fromHsv(y%360,150,220))
p.end();label=QLabel();label.setPixmap(QPixmap.fromImage(image));area.setWidget(label);window.show();QTest.qWait(300);place_window(window,70,90);QTest.qWait(400)
client=next(c for c in backend.hypr("clients") if c["title"]==window.windowTitle())
offset=area.viewport().mapTo(window,__import__("PySide6.QtCore",fromlist=["QPoint"]).QPoint(0,0))
x=client["at"][0]+offset.x();y=client["at"][1]+offset.y();w=min(750,area.viewport().width()-8);h=min(image.height(),area.viewport().height())-4
rect=(x,y,w,h);backend.move_cursor(x+w//2,y+h//2)
stitch=ScrollStitcher(horizontal=horizontal);positions=[];messages=[]
for i in range(11):
    QTest.qWait(280)
    frame=backend.grab(rect);positions.append((area.horizontalScrollBar() if horizontal else area.verticalScrollBar()).value());changed,msg=stitch.push(frame);messages.append(msg)
    if i==0:Image.fromarray(frame).save(out/"native-first-frame.png")
    if i<10:backend.scroll_step(horizontal=horizontal,amount=3)
Image.fromarray(stitch.output).save(out/"native-scrolling-result.png")
report={"geometry":rect,"scroll_positions":positions,"messages":messages,"result_size":[stitch.output.shape[1],stitch.output.shape[0]],"accepted":stitch.accepted}
(out/"native-scroll-report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));window.close()
assert positions[-1]>positions[0],"Native scroll input did not reach the test widget"
axis=1 if horizontal else 0
assert stitch.output.shape[axis]>frame.shape[axis]*2,"Scrolling capture did not assemble multiple screens"
assert stitch.accepted>=8,"Too many frames failed to align"
