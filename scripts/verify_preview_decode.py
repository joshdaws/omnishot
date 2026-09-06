"""Native keystroke inspector controls, filtering and export."""
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
source=out/'source.mp4';backend.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=1920x1080:rate=60:duration=4','-c:v','libx264','-preset','ultrafast','-threads','2',source])
e=VideoEditor(source,backend.Store(out/'data'));e.show();times=[];e.sink.videoFrameChanged.connect(lambda frame:times.append(time.monotonic()))
try:
    wait(lambda:e.last_frame is not None);e.player.play();wait(lambda:e.player.position()>500)
    times.clear();started=time.monotonic();wait(lambda:e.player.position()>3500);elapsed=time.monotonic()-started;e.player.pause()
    fps=len(times)/elapsed;assert fps>=50,(len(times),elapsed,fps)
    report=dict(resolution=[1920,1080],source_fps=60,delivered_frames=len(times),elapsed=elapsed,preview_fps=fps,decoder_preference=os.environ.get('QT_FFMPEG_DECODING_HW_DEVICE_TYPES'))
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));e.close();wait(lambda:not JOBS)
finally:
    fixture.stdin.close();fixture.wait(timeout=3)
    for widget in app.topLevelWidgets():widget.close()
