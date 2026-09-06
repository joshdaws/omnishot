"""Native image-history reopening, filtering, preview/pin, delete and bad imports."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt,QPointF,QTimer
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QPushButton,QFileDialog,QMessageBox
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.app import Controller
from omnishot.editor import Editor
from omnishot.widgets import History,JOBS

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=10):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert predicate(),('History workflow timed out',[(w.windowTitle(),w.isVisible()) for w in app.topLevelWidgets()])
def pointer(window,point):
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==window.windowTitle())
    backend.move_cursor(client['at'][0]+point.x()-2,client['at'][1]+point.y());command('move 2 0');QTest.qWait(65)
def click(widget,window):pointer(window,widget.mapTo(window,widget.rect().center()));command('click 272');QTest.qWait(120)
def button(window,label):return next(w for w in window.findChildren(QPushButton) if w.text()==label)
def choose_first():
    QTest.qWait(app.doubleClickInterval()+40)
    pointer(history,history.list.viewport().mapTo(history,history.list.visualItemRect(history.list.item(0)).center()));command('click 272');QTest.qWait(90)
def text(field,value,window):
    click(field,window);command('key 30 4');QTest.qWait(30);backend.copy_text(value);command('key 47 4');QTest.qWait(100)
state=Controller(app);state.store.settings.update(overlay_timeout=0,background_preset='None')
source=out/'History Original.png';Image.new('RGB',(800,500),'#edf3fa').save(source);source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
bad=out/'Damaged Project.omnishot';bad.write_bytes(b'generated unreadable project');bad_hash=hashlib.sha256(bad.read_bytes()).hexdigest()
try:
    state.dispatch(dict(command='open',path=str(source)));wait(lambda:any(isinstance(w,Editor) for w in state.windows) and not JOBS)
    editor=next(w for w in state.windows if isinstance(w,Editor));QTest.qWait(150);path=editor.path
    click(editor.toolbar.widgetForAction(editor.tools['arrow']),editor)
    a,b=[editor.view.viewport().mapTo(editor,editor.view.mapFromScene(QPointF(*p))) for p in ((100,100),(500,300))]
    pointer(editor,a);command('button 272 1');QTest.qWait(50);command(f'move {b.x()-a.x()} {b.y()-a.y()}');QTest.qWait(70);command('button 272 0');QTest.qWait(100)
    assert len(editor.objects)==1;edited=editor.render();editor.close();QTest.qWait(100)
    state.history();history=next(w for w in state.windows if isinstance(w,History));QTest.qWait(170)
    assert history.list.count()==1 and history.list.item(0).data(Qt.ItemDataRole.AccessibleTextRole)==source.name
    command('key 33 4');QTest.qWait(100)
    text(history.search,'not present',history);assert history.list.count()==0
    text(history.search,'original',history);assert history.list.count()==1
    click(history.filters['video'],history);assert history.kind=='video' and history.list.count()==0
    click(history.filters['image'],history);assert history.kind=='image' and history.list.count()==1
    choose_first();command('click 272');wait(lambda:any(isinstance(w,Editor) for w in state.windows));editor=next(w for w in state.windows if isinstance(w,Editor));QTest.qWait(150)
    assert len(editor.objects)==1 and editor.render()==edited
    messages=[];stage=[0];dialog_timer=QTimer();dialog_timer.setInterval(80)
    def handle_dialog():
        modal=app.activeModalWidget()
        if isinstance(modal,QFileDialog) and stage[0]==0:
            stage[0]=1;command('key 38 4');QTest.qWait(50);backend.copy_text(str(bad));command('key 47 4');QTest.qWait(50);command('key 28 0')
        elif isinstance(modal,QMessageBox) and any(c['title']==modal.windowTitle() and c['pid']==os.getpid() for c in backend.hypr('clients')):
            messages.append(modal.text());dialog_timer.stop();click(modal.button(QMessageBox.StandardButton.Ok),modal)
    dialog_timer.timeout.connect(handle_dialog);dialog_timer.start();command('key 24 4');wait(lambda:bool(messages));QTest.qWait(100)
    assert 'Could not open image project' in messages[-1],messages
    assert editor.path==path and editor.render()==edited and len(state.store.history())==1
    editor.close();QTest.qWait(100)
    choose_first();click(history.restore_button,history);wait(lambda:bool(state.overlays));overlay=state.overlays[0]
    assert QImage(str(overlay.content_path)).convertToFormat(QImage.Format.Format_RGBA8888)==edited.convertToFormat(QImage.Format.Format_RGBA8888)
    overlay.close();QTest.qWait(100);assert state.last_closed==str(path)
    choose_first();command('key 25 4');wait(lambda:bool(state.pins));pin=state.pins[0]
    assert pin.image.convertToFormat(QImage.Format.Format_RGBA8888)==edited.convertToFormat(QImage.Format.Format_RGBA8888)
    pin.close();QTest.qWait(100);history.grab().save(str(out/'history.png'))
    choose_first();command('key 111 0');QTest.qWait(150);assert history.list.count()==0 and not path.exists()
    assert not state.store.image_edit_path(path).exists() and not state.store.image_edit_path(path).with_suffix('.png').exists()
    assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash and hashlib.sha256(bad.read_bytes()).hexdigest()==bad_hash
    report=dict(display_scale=backend.capture_monitors()[0]['scale'],native_annotation=True,history_search_and_type_filter=True,editable_history_reopen_exact=True,corrupt_project_dialog=True,failed_import_preserves_open_editor=True,failed_import_leaves_no_history=True,restore_overlay_pixels_exact=True,pin_pixels_exact=True,delete_cleans_history_and_draft=True,external_sources_unchanged=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    command('button 272 0');fixture.stdin.close();fixture.wait(timeout=3)
