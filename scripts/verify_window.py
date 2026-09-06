"""Exercise native window selection, alpha capture and editable shadow preview."""
import argparse,json,os,time
from pathlib import Path
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QApplication,QWidget
from PIL import Image
import numpy as np
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot import app as app_module
from omnishot.app import Controller
from omnishot.widgets import place_window

parser=argparse.ArgumentParser();parser.add_argument("output",type=Path);args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);os.environ["OMNISHOT_DATA_DIR"]=str(out/"data")
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");theme=ThemeManager(app);controller=Controller(app);results=[];errors=[]
app_module.error=lambda parent,message:(errors.append(str(message)),app.quit())
class Window(QWidget):
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setBrush(QColor("#4a8ddd"));p.setPen(Qt.PenStyle.NoPen);p.drawRoundedRect(20,20,self.width()-40,self.height()-40,18,18);p.setPen(QColor("white"));p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,"OmniShot isolated window capture")
window=Window();window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground);window.setWindowTitle("OmniShot Window Verification");window.resize(500,340);window.show();place_window(window,120,120)
select=backend.select_window
def own_window_only():
    client=select()
    if client["title"]!=window.windowTitle():raise RuntimeError("Selection did not target the generated test window; no capture was taken")
    return client
backend.select_window=own_window_only
original_overlay=controller.overlay
def captured(path):
    original_overlay(path);results.append(path);QTimer.singleShot(300,finish)
controller.overlay=captured
def finish():
    try:
        path=results[0];pixels=np.asarray(Image.open(path));assert pixels.shape[2]==4 and pixels[0,0,3]==0 and pixels[pixels.shape[0]//2,pixels.shape[1]//2,3]==255
        preview=controller.store.display_image(path);assert preview!=path;assert controller.store.image_edit_path(path).exists()
        image=Image.open(preview);assert image.width>pixels.shape[1] and image.height>pixels.shape[0]
        controller.overlays[-1].grab().save(str(out/"overlay.png"))
        report={"native_window_selection":True,"alpha_preserved":True,"native_pixels":[pixels.shape[1],pixels.shape[0]],"editable_shadow_pixels":list(image.size),"capture":str(path)};(out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    except Exception as exc:errors.append(str(exc))
    app.quit()
def choose():
    c=next(c for c in backend.hypr("clients") if c["title"]==window.windowTitle());backend.move_cursor(c["at"][0]+c["size"][0]//2,c["at"][1]+c["size"][1]//2);backend.run([Path(__file__).resolve().parent.parent/"native/scroll-helper","click","272"])
QTimer.singleShot(600,lambda:controller.capture("window",{"action":"overlay"}));QTimer.singleShot(1300,choose);QTimer.singleShot(12000,app.quit)
app.exec();window.close()
for overlay in list(controller.overlays):overlay.close()
if errors or not results:raise RuntimeError(errors or "Window capture timed out")
