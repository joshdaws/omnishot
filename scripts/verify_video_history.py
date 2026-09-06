"""Native grouped undo/redo, branch edits and saved export state."""
import copy,hashlib,json,os,subprocess,sys,time
from pathlib import Path
import cv2
from PIL import Image
from PySide6.QtCore import QPoint,Qt,QTimer
from PySide6.QtWidgets import QApplication,QMenu,QFileDialog
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.recording import VideoEditor
from omnishot.studio import zoom_at
from omnishot.widgets import JOBS
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
app=QApplication([]);app.setStyle('Fusion');theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();QTest.qWait(1);time.sleep(.015)
    assert predicate()
def pointer(widget,point=None):
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==e.windowTitle())
    local=widget.mapTo(e,point or widget.rect().center());x,y=client['at'][0]+local.x(),client['at'][1]+local.y()
    backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(70)
def click(widget,point=None,right=False):
    assert widget.isVisible() and widget.isEnabled()
    pointer(widget,point);command('click 273' if right else 'click 272');QTest.qWait(120)
def enter(widget,value):
    click(widget);backend.copy_text(str(value));command('key 30 4');command('key 47 4');command('key 28 0');QTest.qWait(100)
def drag(widget,a,b,cancel=False):
    pointer(widget,a);command('button 272 1');QTest.qWait(70)
    for n in range(1,9):
        pointer(widget,a+(b-a)*n/8)
    if cancel:command('key 1 0');QTest.qWait(100)
    command('button 272 0');QTest.qWait(130)
def save_dialog(path):
    wait(lambda:any(isinstance(w,QFileDialog) and w.isVisible() for w in app.topLevelWidgets()))
    QTest.qWait(120);command('key 38 4');QTest.qWait(60);backend.copy_text(str(path));command('key 47 4');QTest.qWait(60);command('key 28 0')
def screenshot(name):
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==e.windowTitle())
    data=backend.grab_window(client);Image.fromarray(data).save(out/(name+'.png'));return data
source=out/'source.mp4';backend.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=red:size=640x360:rate=15:duration=6,drawbox=x=320:y=0:w=320:h=360:color=blue:t=fill','-c:v','libx264','-threads','1',source])
digest=hashlib.sha256(source.read_bytes()).hexdigest();store=backend.Store(out/'data');e=VideoEditor(source,store);e.player.pause();e.show();t=e.timeline;point=lambda seconds:QPoint(round(t.x(seconds)),44)
def shortcut(redo=False):
    click(t,QPoint(round(t.x(3)),16));command('key 44 '+('5' if redo else '4'));QTest.qWait(140)
try:
    wait(lambda:e.last_frame is not None and t.duration>=6);QTest.qWait(180);h=e.edit_history
    assert not h.past;initial=h.snapshot()
    drag(t,point(.5),point(2.5));wait(lambda:len(h.past)==1);created=h.snapshot();assert len(e.zooms)==1
    shortcut();assert h.snapshot()==initial and not e.zooms
    shortcut(True);assert h.snapshot()==created and len(e.zooms)==1
    click(t,point(1));panel=e.zoom_inspector;enter(panel.level_value,240);wait(lambda:len(h.past)==2);scaled=h.snapshot();assert e.zooms[0]['scale']==2.4
    click(e.undo_button);assert h.snapshot()==created
    click(e.redo_button);assert h.snapshot()==scaled
    click(t,point(1));drag(t,point(4),point(5.5),cancel=True);QTest.qWait(100);assert h.snapshot()==scaled and len(h.past)==2
    click(t,QPoint(round(t.x(3)),16));command('key 48 4');QTest.qWait(140);assert len(e.splits)==1
    shortcut();assert not e.splits and h.snapshot()==scaled
    click(e.tool_buttons['Motion']);drag(e.motion,QPoint(7,e.motion.height()//2),QPoint(e.motion.width()-8,e.motion.height()//2));QTest.qWait(150);assert e.motion.value()==3 and not h.future and not e.redo_button.isEnabled()
    motion=h.snapshot();click(e.undo_button);assert h.snapshot()==scaled and e.motion.value()==0
    click(e.redo_button);assert h.snapshot()==motion
    screenshot('history-editor');e.resize(900,650);QTest.qWait(150);screenshot('compact')
    e.end.setValue(1);e.fps.setValue(15);e.size.setCurrentText('400');h.flush(True)
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(lambda:save_dialog(out/'undo.omnishot-video'));timer.start(180);click(e.project_btn);wait(lambda:(out/'undo.omnishot-video').exists() and e.export_cancel is None)
    expected=e.edit_options();e.close();e=VideoEditor(out/'undo.omnishot-video',store);e.player.pause();wait(lambda:e.last_frame is not None);assert e.edit_options()==expected
    e.show();QTest.qWait(200);timer.timeout.disconnect();timer.timeout.connect(lambda:save_dialog(out/'undo.mp4'));timer.start(180);click(e.export_btn);wait(lambda:(out/'undo.mp4').exists() and e.export_cancel is None)
    probe=json.loads(backend.run(['ffprobe','-v','error','-show_entries','stream=width,height:format=duration','-of','json',out/'undo.mp4']));assert probe['streams'][0]['width']==400 and .9<float(probe['format']['duration'])<=1.1
    e.close();wait(lambda:not JOBS);assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    report=dict(native_shortcut_undo_redo=True,native_toolbar_undo_redo=True,drag_grouped_as_one_edit=True,percent_typing_grouped_as_one_edit=True,cancel_adds_no_edit=True,split_undo=True,new_edit_discards_redo=True,motion_state_restored=True,compact_layout=[900,650],portable_reopening_and_export=True,source_unchanged=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    fixture.stdin.close();fixture.wait(timeout=3)
    for widget in app.topLevelWidgets():widget.close()
