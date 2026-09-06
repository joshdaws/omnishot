"""Native end-to-end scrolling controls, overlay, editor, clipboard and recording."""
import json
import os
from pathlib import Path
import sys
import time
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLabel,QScrollArea
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QImage,QPixmap,QPainter,QColor,QFont
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot.app import Controller
from omnishot.editor import Editor
from omnishot.widgets import place_window
from omnishot import backend
from omnishot.recording import Recorder,export_video

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ["OMNISHOT_DATA_DIR"]=str(out/"data")
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");theme=ThemeManager(app)
c=Controller(app)

def wait(predicate,timeout=8000):
    start=time.monotonic()
    while not predicate():
        app.processEvents();time.sleep(.02)
        if (time.monotonic()-start)*1000>timeout:
            if c.panel:
                print("SCROLL STATE",c.panel.status.text(),"auto",c.panel.auto,"busy",c.panel.busy,"frames",c.panel.stitcher.accepted,"scroll",area.verticalScrollBar().value(),"cursor",backend.hypr("cursorpos"),flush=True)
                c.panel.grab().save(str(out/"failure-panel.png"));c.panel.timer.stop()
            raise AssertionError("Timed out waiting for native UI")

window=QWidget();window.setWindowTitle("OmniShot Workflow Test Content");window.resize(790,740);layout=QVBoxLayout(window)
layout.addWidget(QLabel("OmniShot workflow verification"));area=QScrollArea();layout.addWidget(area)
image=QImage(710,3500,QImage.Format.Format_RGB888);image.fill(QColor("#f8f9fb"));p=QPainter(image);p.setFont(QFont("sans-serif",20))
for y in range(0,3500,85):
    p.fillRect(10,y+8,680,64,QColor("#e4ebf6" if y%170 else "#f8f9fb"));p.setPen(QColor("#20375b"));p.drawText(25,y+45,f"Workflow row {y//85+1:02d} — marker {y*37+32}")
p.end();label=QLabel();label.setPixmap(QPixmap.fromImage(image));area.setWidget(label);window.show();QTest.qWait(300);place_window(window,55,95);QTest.qWait(350)
client=next(v for v in backend.hypr("clients") if v["title"]==window.windowTitle());offset=area.viewport().mapTo(window,QPoint(0,0));rect=(client["at"][0]+offset.x(),client["at"][1]+offset.y(),700,area.viewport().height()-3)
c.scroll(rect);QTest.qWait(300);QTest.mouseClick(c.panel.start_btn,Qt.MouseButton.LeftButton);wait(lambda:c.panel.stitcher.accepted>=1)
QTest.mouseClick(c.panel.auto_btn,Qt.MouseButton.LeftButton);wait(lambda:c.panel.stitcher.accepted>=7,15000)
c.panel.auto=False;wait(lambda:not c.panel.busy);c.panel.grab().save(str(out/"scroll-controls.png"))
QTest.mouseClick(c.panel.done_btn,Qt.MouseButton.LeftButton);wait(lambda:len(c.overlays)>0)
overlay=c.overlays[-1];QTest.qWait(250);overlay.grab().save(str(out/"quick-overlay.png"));capture=QImage(str(overlay.path))
QTest.mouseClick(overlay.preview,Qt.MouseButton.LeftButton);wait(lambda:any(isinstance(w,Editor) for w in c.windows));e=next(w for w in c.windows if isinstance(w,Editor));QTest.qWait(200)
e.set_tool("arrow");a=e.view.mapFromScene(QPointF(110,130));b=e.view.mapFromScene(QPointF(400,360));QTest.mousePress(e.view.viewport(),Qt.MouseButton.LeftButton,pos=a);QTest.mouseMove(e.view.viewport(),b,80);QTest.mouseRelease(e.view.viewport(),Qt.MouseButton.LeftButton,pos=b)
assert len(e.objects)==1;e.grab().save(str(out/"annotate-workflow.png"));e.copy_image();assert b"image/png" in backend.run(["wl-paste","--list-types"])
e.write_project(out/"editable-verification.omnishot");assert (out/"editable-verification.omnishot").exists();e.close()
opts={"mode":"Area","format":"MP4","fps":30,"quality":"high","size":"Native","system":False,"mic":False,"cursor":True,"delay":0}
r=Recorder(c.store,rect,opts);recorded=[];r.completed.connect(recorded.append);r.show();wait(lambda:r.process is not None);QTest.qWait(1400);r.pause();QTest.qWait(350);r.pause();QTest.qWait(800);r.stop();wait(lambda:bool(recorded),30000)
probe=json.loads(backend.run(["ffprobe","-v","error","-show_entries","stream=codec_name,width,height:format=duration","-of","json",recorded[0]]))
assert float(probe["format"]["duration"])>1;assert probe["streams"][0]["codec_name"]=="h264"
gif=out/"export-verification.gif";export_video(recorded[0],gif,{"start":.1,"end":1.1,"speed":1,"fps":10,"width":480,"format":"GIF","padding":10,"background":"#304050","blur":0});assert gif.stat().st_size>500
report={"capture_size":[capture.width(),capture.height()],"scroll_frames":c.panel.stitcher.accepted,"annotation_objects":len(e.objects),"clipboard_png":True,"editable_project":True,"recording":probe,"gif_export_bytes":gif.stat().st_size}
(out/"workflow-report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));window.close();c.cleanup()
