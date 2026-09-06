"""Native zoom creation, inspector, connected framing and portable editing."""
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
def action(label):
    wait(lambda:any(isinstance(w,QMenu) and w.isVisible() for w in app.topLevelWidgets()))
    menu=next(w for w in app.topLevelWidgets() if isinstance(w,QMenu) and w.isVisible())
    for _ in range(len(menu.actions())+1):
        if menu.activeAction() and menu.activeAction().text()==label:command('key 28 0');return
        command('key 108 0');QTest.qWait(35)
    raise AssertionError(label)
def context(label,seconds):
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(lambda:action(label));timer.start(180);click(t,point(seconds),right=True);QTest.qWait(150)
def save_dialog(path):
    wait(lambda:any(isinstance(w,QFileDialog) and w.isVisible() for w in app.topLevelWidgets()))
    QTest.qWait(120);command('key 38 4');QTest.qWait(60);backend.copy_text(str(path));command('key 47 4');QTest.qWait(60);command('key 28 0')
def screenshot(name):
    client=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==e.windowTitle())
    data=backend.grab_window(client);Image.fromarray(data).save(out/(name+'.png'));return data
source=out/'source.mp4';backend.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=red:size=640x360:rate=15:duration=18,drawbox=x=320:y=0:w=320:h=360:color=blue:t=fill','-c:v','libx264','-threads','1',source])
source.with_suffix('.studio.json').write_text(json.dumps(dict(version=1,cursor=[dict(t=0,x=.25,y=.5),dict(t=18,x=.75,y=.5)],events=[])))
digest=hashlib.sha256(source.read_bytes()).hexdigest();store=backend.Store(out/'data');e=VideoEditor(source,store);e.player.pause();e.show();t=e.timeline
point=lambda seconds:QPoint(round(t.x(seconds)),44)
try:
    wait(lambda:e.last_frame is not None and t.duration>17);QTest.qWait(250)
    click(t,point(2));assert len(e.zooms)==1 and e.inspector.currentWidget()==e.zoom_inspector
    panel=e.zoom_inspector;enter(panel.level_value,200);click(panel.modes[False]);assert panel.focus.isVisible()
    focus=panel.focus;r=focus.image_rect();drag(focus,focus.focus_rect().center().toPoint(),(focus.focus_rect().center()+QPoint(-round(r.width()*.25),0)).toPoint())
    assert .24<=e.zooms[0]['x']<=.27,e.zooms[0]
    before=copy.deepcopy(e.zooms);drag(focus,focus.focus_rect().center().toPoint(),(focus.focus_rect().center()+QPoint(35,0)).toPoint(),cancel=True);assert e.zooms==before
    drag(t,point(8),point(11));assert len(e.zooms)==2 and e.inspector.currentWidget()==panel
    enter(panel.level_value,250);click(panel.modes[False]);r=focus.image_rect();click(focus,QPoint(round(r.left()+r.width()*.86),round(r.center().y())))
    assert e.zooms[1]['x']>.7,e.zooms[1]
    click(panel.apply_all);assert all(z['scale']==2.5 for z in e.zooms)
    drag(t,point(9.5),point(6.5));assert e.zooms[0]['end']==e.zooms[1]['start'],e.zooms
    join=e.zooms[1]['start'];e.player.setPosition(round(join*1000));QTest.qWait(200);at_join=zoom_at(e.zooms,join)
    assert at_join[0]==2.5
    left=screenshot('joined-start');center=e.video.mapTo(e,e.video.rect().center());scale=e.devicePixelRatioF();pixel=left[round(center.y()*scale),round(center.x()*scale),:3].astype(int);assert pixel[0]>200 and pixel[2]<20,pixel
    e.player.setPosition(round((join+.4)*1000));QTest.qWait(200);right=screenshot('joined-end');pixel2=right[round(center.y()*scale),round(center.x()*scale),:3].astype(int);assert pixel2[2]>200 and pixel2[0]<20,pixel2
    click(panel.animation);assert e.tool_buttons['Motion'].isChecked();click(e.zoom_animation.buttons['Dynamic']);assert e.edit_options()['zoom_animation']=='Dynamic'
    click(t,point(6));e.player.setPosition(6000);QTest.qWait(100);command('key 48 5');QTest.qWait(150);assert len(e.zooms)==3
    context('Duplicate',7);assert len(e.zooms)==4
    command('key 14 0');QTest.qWait(130);assert len(e.zooms)==3
    before=copy.deepcopy(e.zooms);drag(t,point(14),point(16),cancel=True);assert e.zooms==before
    click(t,point(7));screenshot('zoom-inspector')
    e.resize(900,650);QTest.qWait(180);assert panel.width()<=284 and focus.width()<280
    assert focus.geometry().bottom()<panel.animation.geometry().top()
    panel.ensureWidgetVisible(panel.animation);QTest.qWait(100);screenshot('compact')
    click(panel.animation);assert e.tool_buttons['Motion'].isChecked()
    e.size.setCurrentText('320');e.fps.setValue(15);e.start.setValue(0);e.end.setValue(10)
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(lambda:save_dialog(out/'zoomed.mp4'));timer.start(180);click(e.export_btn);wait(lambda:(out/'zoomed.mp4').exists() and e.export_cancel is None)
    cap=cv2.VideoCapture(str(out/'zoomed.mp4'));colors=[]
    for seconds in (join,join+.4):
        cap.set(cv2.CAP_PROP_POS_MSEC,seconds*1000);ok,frame=cap.read();assert ok;colors.append(frame[frame.shape[0]//2,frame.shape[1]//2,::-1].astype(int).tolist())
    cap.release();assert colors[0][0]>200 and colors[0][2]<20 and colors[1][2]>200 and colors[1][0]<20,colors
    timer.timeout.disconnect();timer.timeout.connect(lambda:save_dialog(out/'zoomed.omnishot-video'));timer.start(180);click(e.project_btn);wait(lambda:(out/'zoomed.omnishot-video').exists() and e.export_cancel is None)
    expected=e.edit_options();e.close();e=VideoEditor(out/'zoomed.omnishot-video',store);e.player.pause();assert e.edit_options()==expected
    e.close();wait(lambda:not JOBS);assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    report=dict(native_click_and_drag_zoom_creation=True,inline_zoom_inspector=True,manual_focus_and_escape=True,apply_zoom_level_to_all=True,joined_zoom_scale=at_join[0],native_join_pixels=[pixel.tolist(),pixel2.tolist()],export_join_pixels=colors,smooth_dynamic_choices=True,keyboard_zoom_split=True,context_duplicate=True,backspace_removal=True,cancel_creation=True,compact_layout=[900,650],native_export_and_portable_reopening=True,source_unchanged=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    e.close();command('mods 0');command('button 272 0');fixture.stdin.close();fixture.wait(3)
