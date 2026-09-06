"""Native annotation editor gestures and an independent Wayland drop receiver."""
import json,os,subprocess,sys,time
from pathlib import Path
if '--receiver' not in sys.argv and not os.environ.get('OMNISHOT_DRAG_TEST_LOADED'):
    os.environ['LD_PRELOAD']=str(Path(__file__).resolve().parents[1]/'native/drag-status.so')
    os.environ['OMNISHOT_DRAG_TEST_LOADED']='1';os.execv(sys.executable,[sys.executable,*sys.argv])
os.environ.pop('LD_PRELOAD',None)
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication,QLabel
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.editor import Editor,Annotation

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
if '--receiver' in sys.argv:
    class Receiver(QLabel):
        def __init__(self):
            super().__init__('Drop generated annotations here');self.setWindowTitle('OmniShot Editor Drop Receiver');self.resize(380,280);self.setAcceptDrops(True);self.rows=[]
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
    assert predicate(),'Native editor drag timed out'
def window(title):return next(c for c in backend.hypr('clients') if c['title']==title)
def rows():return json.loads((out/'drops.json').read_text()) if (out/'drops.json').exists() else []
store=backend.Store(out/'data');store.settings['background_preset']='None';base=QImage(700,400,QImage.Format.Format_RGB32);base.fill(QColor('#e8edf5'))
try:
    wait(lambda:any(c['title']=='OmniShot Editor Drop Receiver' for c in backend.hypr('clients')))
    backend.move_window(window('OmniShot Editor Drop Receiver')['address'],1280,100)
    def drag(keep=False,cancel=False):
        path=store.add(image=base);editor=Editor(path,store);editor.show();QTest.qWait(250);backend.move_window(window(editor.windowTitle())['address'],40,40);QTest.qWait(120)
        text=Annotation(dict(kind='text',text='Original',text_style='Rounded',font_size=28,color='#20364b',x=35,y=65,w=600,h=80),editor);editor.objects.append(text);editor.scene.addItem(text);editor.commit()
        editor.edit_text(text);editor.inline.setPlainText('Annotation edited immediately before dragging')
        assert text.props['text']=='Original' and editor.inline is not None
        source=window(editor.windowTitle());local=editor.drag_handle.mapTo(editor,editor.drag_handle.rect().center());x,y=source['at'][0]+local.x(),source['at'][1]+local.y()
        before=len(rows());backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(80)
        if keep:command('mods 8');QTest.qWait(70)
        command('button 272 1');QTest.qWait(80)
        QTimer.singleShot(100,lambda:command('move 25 0'))
        tx,ty=(1250,1000) if cancel else (1400,200)
        QTimer.singleShot(350,lambda:command(f'move {tx-x-25} {ty-y}'))
        QTimer.singleShot(700,lambda:command('button 272 0'))
        QTest.qWait(1100);command('mods 0');QTest.qWait(100)
        assert len(rows())==before+(not cancel),(keep,cancel,rows())
        assert editor.isVisible()==(keep or cancel),(keep,cancel,editor.isVisible())
        assert editor.inline is None and text.props['text']=='Annotation edited immediately before dragging'
        if not cancel:
            expected=editor.render();expected.save(str(out/f'expected-{before}.png'));received=QImage(rows()[-1])
            assert received.convertToFormat(QImage.Format.Format_RGBA8888)==expected.convertToFormat(QImage.Format.Format_RGBA8888),('Dropped file must contain the current annotations',received.size(),expected.size(),received.devicePixelRatio(),expected.devicePixelRatio())
        if keep:editor.grab().save(str(out/'annotation-editor.png'))
        editor.close()
    drag();drag(keep=True);drag(cancel=True)
    report=dict(native_press_move_release=True,independent_wayland_receiver=True,exact_annotation_pixels=True,pending_inline_text_committed=True,accepted_drop_closes_editor=True,alt_keeps_editor=True,cancel_keeps_editor=True,theme='Omarchy',display_scale=backend.capture_monitors()[0]['scale'])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('mods 0');command('button 272 0')
    for widget in app.topLevelWidgets():widget.close()
    receiver.terminate();receiver.wait(timeout=3);fixture.stdin.close();fixture.wait(timeout=3)
