"""Native clip-edge trimming, restoration, undo, playback and portable export."""
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
source=out/'source.mp4';cmd=['ffmpeg','-v','error','-y']
for color in ('red','green','blue'):cmd+=['-f','lavfi','-i',f'color={color}:size=640x360:rate=15:duration=4']
backend.run(cmd+['-filter_complex','[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]','-map','[v]','-c:v','libx264','-threads','1',source])
digest=hashlib.sha256(source.read_bytes()).hexdigest();store=backend.Store(out/'data');e=VideoEditor(source,store);e.player.pause();e.show();t=e.timeline;point=lambda seconds:QPoint(round(t.x(seconds)),88)
try:
    wait(lambda:e.last_frame is not None and t.duration>=12);QTest.qWait(150)
    for seconds in (4,8):
        click(t,QPoint(round(t.x(seconds)),16));command('key 48 4');QTest.qWait(100)
    assert e.splits==[4.,8.];h=e.edit_history;h.flush(True);depth=len(h.past)
    click(t,point(6));drag(t,point(4),point(5));wait(lambda:len(h.past)==depth+1);assert e.cuts==[[4,5]]
    click(e.undo_button);assert not e.cuts
    click(e.redo_button);assert e.cuts==[[4,5]]
    click(t,point(6));drag(t,point(8),point(7));wait(lambda:e.cuts==[[4,5],[7,8]]);depth=len(h.past)
    drag(t,point(7),point(6),cancel=True);assert e.cuts==[[4,5],[7,8]] and len(h.past)==depth
    # Native extension restores source frames, clamped to each split boundary.
    drag(t,point(5),point(2));assert e.cuts==[[7,8]]
    drag(t,point(7),point(10));assert not e.cuts and t.clips()==[(0,4),(4,8),(8,12)]
    click(e.undo_button);click(e.undo_button);assert e.cuts==[[4,5],[7,8]]
    for position,destination in ((3900,5000),(6900,8000)):
        e.player.setPosition(position);e.player.play();wait(lambda:e.player.position()>destination);e.player.pause()
    e.resize(900,650);QTest.qWait(150);click(t,point(6))
    wait(lambda:all(t.thumbnails.images.get(k) is not None for k,_,_ in t.thumbnail_tiles()));QTest.qWait(100);screenshot('clip-trimming')
    e.fps.setValue(15);e.size.setCurrentText('400');h.flush(True)
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(lambda:save_dialog(out/'trim.omnishot-video'));timer.start(180);click(e.project_btn);wait(lambda:(out/'trim.omnishot-video').exists() and e.export_cancel is None)
    expected=e.edit_options();e.close();e=VideoEditor(out/'trim.omnishot-video',store);e.player.pause();wait(lambda:e.last_frame is not None);assert e.edit_options()==expected
    e.show();QTest.qWait(180);timer.timeout.disconnect();timer.timeout.connect(lambda:save_dialog(out/'trim.mp4'));timer.start(180);click(e.export_btn);wait(lambda:(out/'trim.mp4').exists() and e.export_cancel is None,12)
    cap=cv2.VideoCapture(str(out/'trim.mp4'));duration=cap.get(cv2.CAP_PROP_FRAME_COUNT)/cap.get(cv2.CAP_PROP_FPS);assert abs(duration-10)<.1
    colors=[]
    for seconds in (2,4.5,7):
        cap.set(cv2.CAP_PROP_POS_MSEC,seconds*1000);ok,frame=cap.read();assert ok;colors.append(frame[frame.shape[0]//2,frame.shape[1]//2,::-1].tolist())
    cap.release();assert [max(range(3),key=lambda i:c[i]) for c in colors]==[0,1,2],colors
    e.close();wait(lambda:not JOBS);assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    report=dict(native_clip_edge_drags=True,grouped_undo_redo=True,canceled_drag_no_history=True,restore_and_neighbor_limits=True,playback_skips_both_trimmed_gaps=True,portable_save_reopen=True,native_export_duration=duration,export_colors=colors,source_unchanged=True,compact_layout=[900,650])
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    command('button 272 0');command('mods 0');fixture.stdin.close();fixture.wait(timeout=3)
    for widget in app.topLevelWidgets():widget.close()
