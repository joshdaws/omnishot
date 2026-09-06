"""Independent Wayland image/file drag source → Annotate → editable project."""
import base64,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from PySide6.QtCore import Qt,QPointF,QMimeData,QUrl
from PySide6.QtGui import QImage,QColor,QPainter,QDrag,QPixmap
from PySide6.QtWidgets import QApplication,QLabel,QWidget,QVBoxLayout
from PySide6.QtTest import QTest
from omnishot import backend
from omnishot.editor import Editor
from omnishot.theme import ThemeManager
import omnishot.editor as module

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
if '--source' in sys.argv:
    class Source(QLabel):
        def __init__(self,mode):
            super().__init__(mode);self.mode=mode;self.setMinimumHeight(70);self.setStyleSheet('padding:15px;border:1px solid palette(highlight)');self.pressed=False
        def mousePressEvent(self,event):self.pressed=True
        def mouseReleaseEvent(self,event):self.pressed=False
        def mouseMoveEvent(self,event):
            if not self.pressed:return
            self.pressed=False;mime=QMimeData();image=QImage(str(out/'insert-0.png'))
            if self.mode=='Image data':mime.setImageData(image)
            elif self.mode=='Two files plus image':
                mime.setUrls([QUrl.fromLocalFile(str(out/f'insert-{i}.png')) for i in range(2)]);fallback=QImage(30,30,QImage.Format.Format_RGB32);fallback.fill(QColor('green'));mime.setImageData(fallback)
            else:mime.setUrls([QUrl('https://example.test/image.png')])
            drag=QDrag(self);drag.setMimeData(mime);drag.setPixmap(QPixmap.fromImage(image).scaledToWidth(80));drag.exec(Qt.DropAction.CopyAction)
            with (out/'source-completed.txt').open('a') as file:file.write(self.mode+'\n')
    source=QWidget();source.setWindowTitle('Generated image drag source');source.resize(380,300);layout=QVBoxLayout(source)
    for mode in ('Image data','Two files plus image','URL only'):layout.addWidget(Source(mode))
    source.show();QTest.qWait(150)
    (out/'source-labels.json').write_text(json.dumps({w.mode:[w.geometry().center().x(),w.geometry().center().y()] for w in source.findChildren(Source)}))
    sys.exit(app.exec())

assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
for i,color in enumerate(('#2378ac','#eb9c25')):
    image=QImage(120,90,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent);p=QPainter(image);p.fillRect(10,10,100,70,QColor(color));p.end();image.save(str(out/f'insert-{i}.png'))
base=QImage(700,400,QImage.Format.Format_RGB32);base.fill(QColor('#e8edf5'));store=backend.Store(out/'data');path=store.add(image=base);digest=hashlib.sha256(path.read_bytes()).hexdigest()
editor=Editor(path,store);editor.show();errors=[];
original_drop=editor.view.dropEvent
def observe_drop(event):
    (out/'event-position.json').write_text(json.dumps(dict(position=[event.position().x(),event.position().y()],scene=[editor.view.mapToScene(event.position().toPoint()).x(),editor.view.mapToScene(event.position().toPoint()).y()])));original_drop(event)
editor.view.dropEvent=observe_drop
module.error=lambda parent,message:errors.append(str(message))
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
source=subprocess.Popen([sys.executable,__file__,str(out),'--source'])
def same_pixels(a,b):
    a=a.convertToFormat(QImage.Format.Format_RGBA8888);b=b.convertToFormat(QImage.Format.Format_RGBA8888)
    return a.size()==b.size() and bytes(a.constBits())==bytes(b.constBits())
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate(),(errors,len(editor.objects))
def window(title):return next(c for c in backend.hypr('clients') if c['title']==title)
def point(x,y):backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(90)
def finished():return len((out/'source-completed.txt').read_text().splitlines()) if (out/'source-completed.txt').exists() else 0
def drag(mode):
    client=window('Generated image drag source');local=json.loads((out/'source-labels.json').read_text())[mode];x,y=client['at'][0]+local[0],client['at'][1]+local[1]
    target=editor.view.viewport().mapTo(editor,editor.view.mapFromScene(QPointF(230,160)));client=window(editor.windowTitle());tx,ty=client['at'][0]+target.x(),client['at'][1]+target.y()
    before=finished();point(x,y);command('button 272 1');QTest.qWait(80);command('move 20 0');QTest.qWait(100);command(f'move {tx-x-20} {ty-y}');QTest.qWait(100);command('move -10 0');QTest.qWait(70);command('move 10 0');QTest.qWait(100);(out/'pointer-before-drop.json').write_text(json.dumps(dict(cursor=backend.hypr('cursorpos'),client=window(editor.windowTitle()),requested=[tx,ty])));command('button 272 0');wait(lambda:finished()>before);QTest.qWait(180)
try:
    wait(lambda:(out/'source-labels.json').exists() and any(c['title']=='Generated image drag source' for c in backend.hypr('clients')))
    backend.move_window(window(editor.windowTitle())['address'],40,40);backend.move_window(window('Generated image drag source')['address'],1280,100);QTest.qWait(250)
    drag('Image data');assert len(editor.objects)==1
    obj=editor.objects[0];(out/'drop-state.json').write_text(json.dumps(dict(x=obj.x(),y=obj.y(),selected=obj.isSelected(),tool=editor.view.tool)));assert abs(obj.x()-230)<2 and abs(obj.y()-160)<2 and obj.isSelected(),(obj.x(),obj.y(),obj.isSelected(),editor.view.tool)
    inserted=QImage.fromData(base64.b64decode(obj.props['image']));inserted.save(str(out/'received.png'));assert same_pixels(inserted,QImage(str(out/'insert-0.png')))
    editor.undo();assert not editor.objects;editor.redo();assert len(editor.objects)==1
    drag('Two files plus image');assert len(editor.objects)==3
    for i,obj in enumerate(editor.objects[1:]):
        assert same_pixels(QImage.fromData(base64.b64decode(obj.props['image'])),QImage(str(out/f'insert-{i}.png')))
    assert editor.objects[2].pos()-editor.objects[1].pos()==QPointF(20,20)
    editor.undo();assert len(editor.objects)==1;editor.redo();assert len(editor.objects)==3
    drag('URL only');assert len(editor.objects)==3 and not errors
    project=out/'dropped-images.omnishot';editor.write_project(project);before=editor.render();other=Editor(project,store);assert other.render()==before and len(other.objects)==3;other.close()
    editor.grab().save(str(out/'editor.png'));assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    report=dict(native_wayland_drag_from_separate_app=True,image_payload_without_file=True,alpha_pixels_exact=True,native_pointer_position=True,files_preferred_over_duplicate_image=True,multi_file_cascade=True,one_undo_per_drop=True,remote_url_ignored=True,editable_project_reopens=True,source_unchanged=True,scale=backend.capture_monitors()[0]['scale'],theme='Omarchy')
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('button 272 0');editor.close();source.terminate();source.wait(timeout=3);fixture.stdin.close();fixture.wait(timeout=3)
