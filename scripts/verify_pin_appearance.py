"""Native pin appearance, live changes, input shape and unmodified exports."""
import json,subprocess,sys
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QWidget
from PySide6.QtTest import QTest
from PIL import Image
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.widgets import Pin,Settings,place_window
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
def click(widget,indicator=False):
    top=widget.window();client=next(c for c in backend.hypr('clients') if c['pid']==__import__('os').getpid() and c['title']==top.windowTitle());point=widget.mapTo(top,QPoint(8,widget.height()//2) if indicator else widget.rect().center());backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(80);command('click 272');QTest.qWait(100)
class Underlying(QWidget):
    clicks=0
    def mousePressEvent(self,event):self.clicks+=1
underlying=Underlying();underlying.setStyleSheet('background:#dddddd');underlying.setWindowTitle('OmniShot Click Target');underlying.showFullScreen();QTest.qWait(150)
store=backend.Store(out/'data');source=out/'source.png';Image.new('RGB',(320,200),'#2070b0').save(source);owned=store.import_file(source);pin=Pin(owned,0,store)
try:
    pin.show();QTest.qWait(300);place_window(pin,40,60);QTest.qWait(150);initial_size=pin.content_rect().size();rounded=pin.grab().toImage();ratio=rounded.devicePixelRatio();assert rounded.pixelColor(0,0).alpha()==0
    settings=Settings(store,'advanced');settings.accepted.connect(pin.refresh_appearance);settings.show();QTest.qWait(250)
    for field in ('pin_rounded','pin_shadow','pin_border'):click(settings.fields[field],True)
    click(settings.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save));QTest.qWait(200)
    restored=backend.Store(store.root);assert not restored.settings['pin_rounded'] and restored.settings['pin_shadow'] and restored.settings['pin_border']
    assert pin.content_rect().size()==initial_size and pin.shadow_window.isVisible(),(initial_size,pin.content_rect().size())
    shot=pin.grab().toImage();ratio=shot.devicePixelRatio();sample=lambda x,y:shot.pixelColor(round(x*ratio),round(y*ratio))
    assert sample(0,0).alpha()==255
    assert sample(13,13).alpha()==255
    assert sample(0,60).red()>sample(30,60).red()
    assert not pin.windowHandle().mask().contains(QPoint(-2,-2)) and pin.windowHandle().mask().contains(QPoint(40,40))
    pin.lock();assert not pin.windowHandle().mask().contains(QPoint(40,40));pin.unlock();assert pin.windowHandle().mask().contains(QPoint(40,40));QTest.qWait(250)
    def pin_click(point):
        client=next(c for c in backend.hypr('clients') if c['title']==pin.windowTitle());backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(80);command('click 272');QTest.qWait(100)
    before=underlying.clicks;pin_click(QPoint(-5,60));assert underlying.clicks==before+1
    pin_click(QPoint(60,60));assert underlying.clicks==before+1
    pin.lock();QTest.qWait(100);pin_click(QPoint(60,60));assert underlying.clicks==before+2;pin.unlock();QTest.qWait(100)
    pin_click(QPoint(60,60));old=next(c for c in backend.hypr('clients') if c['title']==pin.windowTitle())['at']
    command('button 272 1');QTest.qWait(50);command('move 30 20');QTest.qWait(80);command('move 80 50');QTest.qWait(80);command('button 272 0');QTest.qWait(120)
    moved=next(c for c in backend.hypr('clients') if c['title']==pin.windowTitle())['at'];assert moved!=old,(old,moved)
    pin_click(QPoint(60,60));before_size=pin.size();backend.scroll_step(False,-1);QTest.qWait(200);assert pin.size()!=before_size
    native=next(c for c in backend.hypr('clients') if c['title']==pin.windowTitle());assert native['size']==[pin.width(),pin.height()]
    client=next(c for c in backend.hypr('clients') if c['title']==pin.windowTitle());x,y=client['at'];w,h=client['size'];backend.move_cursor(1500,950);QTest.qWait(80)
    with_shadow=backend.grab((x-12,y-12,w+24,h+24));store.settings['pin_shadow']=False;pin.refresh_appearance();QTest.qWait(150);without_shadow=backend.grab((x-12,y-12,w+24,h+24))
    import numpy as np
    scale=with_shadow.shape[1]/(w+24);px,py=round(7*scale),round(72*scale)
    assert np.all(with_shadow[py,px,:3]<without_shadow[py,px,:3]),(with_shadow[py,px],without_shadow[py,px])
    Image.fromarray(with_shadow).save(out/'pin-shadow-native.png');store.settings['pin_shadow']=True;pin.refresh_appearance()
    pin.copy();copied=Image.open(__import__('io').BytesIO(backend.run(['wl-paste','--type','image/png'])));assert copied.size==(320,200) and copied.getpixel((0,0))==(32,112,176)
    shot.save(str(out/'pin-styled.png'));rounded.save(str(out/'pin-rounded.png'))
    report=dict(native_preferences=True,live_pin_update=True,content_size_preserved=True,rounded_corners=True,optional_shadow_and_border=True,native_shadow_pixels=True,shadow_input_passes_through=True,lock_unlock_input=True,native_wheel_resize=True,native_drag_moves_shadow=True,clipboard_excludes_pin_decoration=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3);backend.run(['wl-copy','--clear'])
