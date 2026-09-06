"""Run inside isolated Hyprland: real inter-process Wayland drag and auto-save."""
import json
import os
from pathlib import Path
import subprocess
import sys
if "--receiver" not in sys.argv and not os.environ.get("OMNISHOT_DRAG_TEST_LOADED"):
    os.environ["LD_PRELOAD"]=str(Path(__file__).resolve().parents[1]/"native/drag-status.so")
    os.environ["OMNISHOT_DRAG_TEST_LOADED"]="1";os.execv(sys.executable,[sys.executable,*sys.argv])
os.environ.pop("LD_PRELOAD",None)
import numpy as np
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLabel,QPushButton,QFileDialog
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.editor import Editor
from omnishot.widgets import QuickOverlay,Settings

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");app.setStyle("Fusion");theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
if "--receiver" in sys.argv:
    class Receiver(QLabel):
        def __init__(self):
            super().__init__("Drop the generated capture here");self.setWindowTitle("OmniShot Test Drop Receiver");self.setAlignment(Qt.AlignmentFlag.AlignCenter);self.setAcceptDrops(True);self.resize(380,280);self.rows=[]
        def dragEnterEvent(self,event):
            if event.mimeData().hasUrls():event.acceptProposedAction()
        def dropEvent(self,event):
            path=Path(event.mimeData().urls()[0].toLocalFile());image=QImage(str(path))
            self.rows.append(dict(path=str(path),width=image.width(),height=image.height()))
            (out/"drops.json").write_text(json.dumps(self.rows));event.acceptProposedAction();self.setText(f"Received {len(self.rows)} editable capture exports")
    receiver=Receiver();receiver.show();sys.exit(app.exec())

helper=Path(sys.argv[2]).resolve()
fixture=subprocess.Popen([helper],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=="ready"
receiver=subprocess.Popen([sys.executable,__file__,str(out),"--receiver"])
def command(value):fixture.stdin.write(value+"\n");fixture.stdin.flush()
def window(title):return next(c for c in backend.hypr("clients") if c["title"]==title)
def rows():return json.loads((out/"drops.json").read_text()) if (out/"drops.json").exists() else []
store=backend.Store(out/"data");store.settings["output_dir"]=str(out/"saved")
path=store.add(image=np.full((100,180,3),(28,145,210),np.uint8));store.rename(path,"Dragged capture")
editor=Editor(path,store);editor.rotate();editor.close();editor.deleteLater()
try:
    QTest.qWait(800);target=window("OmniShot Test Drop Receiver");backend.move_window(target["address"],800,100);QTest.qWait(200)
    def drag(keep=False,cancel=False):
        overlay=QuickOverlay(path,store);events=[];overlay.preview.drag_started.connect(lambda:events.append("started"));overlay.preview.drag_finished.connect(lambda *values:events.append(values));overlay.show();QTest.qWait(300)
        source=window(overlay.windowTitle());point=overlay.preview.mapTo(overlay,overlay.preview.rect().center());x,y=source["at"][0]+point.x(),source["at"][1]+point.y()
        before=len(rows());backend.move_cursor(x,y);QTest.qWait(150);command("button 272 1");QTest.qWait(100)
        if keep:command("mods 8");QTest.qWait(60)
        # The QDrag owns a nested Qt loop once the first movement reaches it.
        QTimer.singleShot(100,lambda:command("move 25 0"))
        tx,ty=(700,650) if cancel else (900,200)
        QTimer.singleShot(350,lambda:command(f"move {tx-x-25} {ty-y}"))
        QTimer.singleShot(700,lambda:command("button 272 0"))
        QTest.qWait(1100);command("mods 0");QTest.qWait(100)
        assert len(rows())==before+(not cancel),(rows(),cancel,overlay.dragging,events,source,window("OmniShot Test Drop Receiver"),overlay.preview.start)
        assert overlay.isVisible()==(keep or cancel),(keep,cancel,overlay.isVisible(),events)
        overlay.close()
    drag();drag(keep=True);drag(cancel=True)
    assert all((row["width"],row["height"])==(100,180) for row in rows()),rows()
    store.settings.update(overlay_timeout=1,overlay_auto_action="save")
    overlay=QuickOverlay(path,store);overlay.show();QTest.qWait(300);backend.move_cursor(700,50);QTest.qWait(1300)
    assert not overlay.isVisible() and (out/"saved/Dragged capture.png").is_file()
    store.settings["overlay_timeout"]=0
    for ask in (False,True):
        store.settings["ask_save_destination"]=ask;overlay=QuickOverlay(path,store);overlay.show();QTest.qWait(300)
        source=window(overlay.windowTitle());save=next(b for b in overlay.findChildren(QPushButton) if b.text()=="Save");point=save.mapTo(overlay,save.rect().center())
        backend.move_cursor(source["at"][0]+point.x(),source["at"][1]+point.y());QTest.qWait(100);command("mods 8");QTest.qWait(70)
        seen=[]
        def reject_picker():
            modal=app.activeModalWidget()
            if isinstance(modal,QFileDialog):seen.append(True);modal.reject()
        QTimer.singleShot(400,reject_picker);command("click 272");QTest.qWait(700);command("mods 0");QTest.qWait(60)
        assert bool(seen)==(not ask),(ask,seen)
        assert overlay.isVisible()==(not ask);overlay.close()
    assert (out/"saved/Dragged capture (2).png").is_file()
    settings=Settings(store);settings.show();QTest.qWait(200);settings.grab().save(str(out/"action-matrix.png"))
    settings.show_page("quickaccess");QTest.qWait(100);settings.grab().save(str(out/"quickaccess-settings.png"));settings.close()
    report=dict(interprocess_wayland_drop=True,current_annotations_exported=True,close_after_drop=True,alt_keeps_preview=True,cancel_keeps_preview=True,automatic_save_and_close=True,alt_save_switches_destination_behavior=True)
    (out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command("mods 0");command("button 272 0")
    for widget in app.topLevelWidgets():widget.close()
    receiver.terminate();receiver.wait(timeout=3);fixture.stdin.close();fixture.wait(timeout=3)
