"""Native pin controls, click-through and independent Wayland file drops."""
import json,os,subprocess,sys,time
from pathlib import Path
if '--receiver' not in sys.argv and not os.environ.get('OMNISHOT_DRAG_TEST_LOADED'):
    os.environ['LD_PRELOAD']=str(Path(__file__).resolve().parents[1]/'native/drag-status.so')
    os.environ['OMNISHOT_DRAG_TEST_LOADED']='1';os.execv(sys.executable,[sys.executable,*sys.argv])
os.environ.pop('LD_PRELOAD',None)
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication,QLabel,QWidget
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager,color
from omnishot import backend
from omnishot.editor import Editor,Annotation
from omnishot.widgets import Pin,place_window
from shiboken6 import isValid

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
if '--receiver' in sys.argv:
    class Receiver(QLabel):
        def __init__(self):
            super().__init__('Drop generated annotations here');self.setWindowTitle('OmniShot Pin Drop Receiver');self.resize(380,280);self.setAcceptDrops(True);self.rows=[]
        def dragEnterEvent(self,event):
            if event.mimeData().hasUrls():event.acceptProposedAction()
        def dropEvent(self,event):
            path=Path(event.mimeData().urls()[0].toLocalFile());image=QImage(str(path));target=out/f'drop-{len(self.rows)}.png';image.save(str(target))
            self.rows.append(str(target));(out/'drops.json').write_text(json.dumps(self.rows));event.acceptProposedAction()
    receiver=Receiver();receiver.show();sys.exit(app.exec())

fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
receiver=subprocess.Popen([sys.executable,__file__,str(out),'--receiver'])
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=5):
    until=time.monotonic()+seconds
    while not predicate() and time.monotonic()<until:app.processEvents();time.sleep(.02)
    assert predicate(),'Native pin workflow timed out'
def window(title):return next(c for c in backend.hypr('clients') if c['title']==title)
def rows():return json.loads((out/'drops.json').read_text()) if (out/'drops.json').exists() else []
store=backend.Store(out/'data');store.settings['background_preset']='None';base=QImage(700,400,QImage.Format.Format_RGB32);base.fill(QColor('#e8edf5'))
try:
    wait(lambda:any(c['title']=='OmniShot Pin Drop Receiver' for c in backend.hypr('clients')))
    backend.move_window(window('OmniShot Pin Drop Receiver')['address'],1280,100)
    class Underlying(QWidget):
        clicks=0
        def mousePressEvent(self,event):self.clicks+=1
    underlying=Underlying();underlying.setWindowTitle('OmniShot Click Target');underlying.resize(800,600);underlying.show();QTest.qWait(250);place_window(underlying,20,20)
    probe=Pin(store.add(image=base),99,store);probe.show();QTest.qWait(250);place_window(probe,40,40);QTest.qWait(100)
    def point_on(pin,point):
        client=window(pin.windowTitle());backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(100)
    def click_control(pin,control):
        top=control.window();point_on(top,control.mapTo(top,control.rect().center()));command('click 272');QTest.qWait(250)
    point_on(probe,probe.rect().center());assert probe.controls.drag.isVisible() and probe.controls.close.isVisible()
    probe.grab().save(str(out/'pin-hover.png'));click_control(probe,probe.controls.lock)
    assert probe.locked and probe.controls.unlock.isVisible() and not probe.controls.drag.isVisible() and not probe.controls.close.isVisible()
    previous_position=window(probe.windowTitle())['at'];probe.hide();QTest.qWait(150);assert not probe.controls.unlock.isVisible()
    probe.show();QTest.qWait(500);assert probe.controls.unlock.isVisible()
    locked=window(probe.windowTitle());unlock=window(probe.controls.unlock.windowTitle())
    assert locked['at']==previous_position,(locked['at'],previous_position)
    assert unlock['at']==[locked['at'][0]+probe.controls.lock.x(),locked['at'][1]+probe.controls.lock.y()],(locked['at'],unlock['at'])
    before=underlying.clicks
    point_on(probe,probe.rect().center());command('click 272');QTest.qWait(180);assert underlying.clicks==before+1
    from PIL import Image
    c=window(probe.windowTitle());locked_pixels=backend.grab((*c['at'],*c['size']));Image.fromarray(locked_pixels).save(out/'pin-locked.png')
    scale=locked_pixels.shape[1]/probe.width();sample=locked_pixels[round((probe.controls.lock.y()+11)*scale),round((probe.controls.lock.x()+3)*scale),:3]
    expected=color('background');assert all(abs(int(channel)-wanted)<=3 for channel,wanted in zip(sample,(expected.red(),expected.green(),expected.blue()))),('Unlock must be visible above the image',sample)
    probe.controls.unlock.grab().save(str(out/'unlock-button.png'))
    click_control(probe,probe.controls.unlock);assert not probe.locked and not probe.controls.unlock.isVisible()
    point_on(probe,probe.rect().center());command('click 272');QTest.qWait(150);assert underlying.clicks==before+1
    original=probe.size();backend.scroll_step(False,-1);QTest.qWait(200);assert probe.size()!=original
    command('mods 8');QTest.qWait(80);backend.scroll_step(False,1);QTest.qWait(200);command('mods 0');assert probe.opacity<1
    click_control(probe,probe.controls.close);assert not probe.isVisible() and not probe.controls.unlock.isVisible()
    underlying.close();QTest.qWait(200)
    def drag(keep=False,cancel=False):
        path=store.add(image=base);editor=Editor(path,store)
        text=Annotation(dict(kind='text',text='Pinned annotation',text_style='Rounded',font_size=28,color='#20364b',x=35,y=65,w=600,h=80),editor);editor.objects.append(text);editor.scene.addItem(text);editor.commit();editor.close()
        pin=Pin(path,len(rows()),store);pin.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);pin.show();QTest.qWait(250);place_window(pin,40,40);QTest.qWait(120)
        point_on(pin,pin.rect().center());assert pin.controls.drag.isVisible()
        source=window(pin.windowTitle());local=pin.controls.drag.mapTo(pin,pin.controls.drag.rect().center());x,y=source['at'][0]+local.x(),source['at'][1]+local.y()
        before=len(rows());backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(80)
        if keep:command('mods 8');QTest.qWait(70)
        command('button 272 1');QTest.qWait(80)
        QTimer.singleShot(100,lambda:command('move 25 0'))
        tx,ty=(1250,1000) if cancel else (1400,200)
        QTimer.singleShot(350,lambda:command(f'move {tx-x-25} {ty-y}'))
        QTimer.singleShot(700,lambda:command('button 272 0'))
        QTest.qWait(1100);command('mods 0');QTest.qWait(100)
        assert len(rows())==before+(not cancel),(keep,cancel,rows())
        assert isValid(pin)==(keep or cancel),(keep,cancel,isValid(pin))
        if isValid(pin):assert pin.isVisible()
        if not cancel:
            expected=editor.render();received=QImage(rows()[-1])
            assert received.convertToFormat(QImage.Format.Format_RGBA8888)==expected.convertToFormat(QImage.Format.Format_RGBA8888),'Dropped file must contain the annotations without pin decorations'
        if isValid(pin):pin.close()
    drag();drag(keep=True);drag(cancel=True)
    report=dict(native_hover_controls=True,native_lock_button=True,image_clicks_pass_through=True,native_unlock_button=True,unlock_visible_above_image=True,locked_hide_restore_position=True,native_close_button=True,native_wheel_resize=True,native_alt_wheel_opacity=True,native_press_move_release=True,independent_wayland_receiver=True,exact_annotation_pixels_without_decoration=True,accepted_drop_closes_and_deletes_pin=True,alt_keeps_pin=True,cancel_keeps_pin=True,theme='Omarchy',display_scale=backend.capture_monitors()[0]['scale'])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('mods 0');command('button 272 0')
    for widget in app.topLevelWidgets():widget.close()
    receiver.terminate();receiver.wait(timeout=3);fixture.stdin.close();fixture.wait(timeout=3)
