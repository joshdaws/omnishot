"""Real recorder with generated V4L2 input: camera click/drag, pause and export."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
import cv2,numpy as np
from PySide6.QtCore import Qt,QPoint,QTimer
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QApplication,QWidget,QCheckBox,QScrollArea,QDialogButtonBox
from PySide6.QtTest import QTest
from omnishot import backend,recording,camera
from omnishot.widgets import JOBS
from omnishot.recording_checkpoint import read_checkpoint
from omnishot.video_project import write_project
from omnishot.studio import export_studio
from omnishot.theme import ThemeManager
from omnishot.camera_framing import options_at

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
widescreen='--widescreen' in sys.argv;portrait='--portrait-max' in sys.argv
feed_shape=(160,80) if portrait else (90,160) if widescreen else (120,160)
camera_aspect=feed_shape[0]/feed_shape[1];final_shape='Rectangle' if widescreen or portrait else 'Square';size_percent=80 if portrait else 35
assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
original_command=recording.recorder_command
def isolated_command(*args,**kwargs):
    command=original_command(*args,**kwargs);assert '-region' not in command;command[command.index('-w')+1]='screen';return command
recording.recorder_command=isolated_command
original_capture=cv2.VideoCapture
class GeneratedCamera:
    def isOpened(self):return True
    def set(self,*args):pass
    def read(self):time.sleep(1/30);return True,np.full((*feed_shape,3),[30,30,220],np.uint8)
    def release(self):pass
def capture(device,*args,**kwargs):return GeneratedCamera() if device=='/omnishot-generated-camera' else original_capture(device,*args,**kwargs)
camera.cv2.VideoCapture=capture
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False)
app.setStyle('Fusion');theme=ThemeManager(app);assert theme.applied
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
errors=[];recording.error=lambda parent,message:errors.append(str(message));rec=None;editor=None
def command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
def wait(predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    if not predicate():
        (out/'failure.json').write_text(json.dumps(dict(errors=errors,clients=backend.hypr('clients'),active=backend.hypr('activewindow')),indent=2))
        from PIL import Image
        Image.fromarray(backend.grab()).save(out/'failure-screen.png')
    assert predicate(),dict(errors=errors)
def delay(seconds):start=time.monotonic();wait(lambda:time.monotonic()-start>=seconds,seconds+1)
def client(widget):return next((c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==widget.windowTitle()),None)
def pointer(widget,point=None):
    top=widget.window();native=client(top);point=widget.mapTo(top,point or widget.rect().center());backend.move_cursor(native['at'][0]+point.x()-2,native['at'][1]+point.y());command('move 2 0');delay(.08)
def click(widget):
    for scroll in widget.window().findChildren(QScrollArea):
        if scroll.widget() and scroll.widget().isAncestorOf(widget):scroll.ensureWidgetVisible(widget);delay(.06)
    pointer(widget,QPoint(8,widget.height()//2) if isinstance(widget,QCheckBox) else None);command('click 272');delay(.15)
def shape_menu(preview,shape):
    def choose():
        menu=app.activePopupWidget()
        if menu is None:QTimer.singleShot(40,choose);return
        for _ in range(8):
            command('key 108 0');delay(.04)
            if menu.activeAction() and menu.activeAction().text()==shape:
                command('key 28 0');return
        raise AssertionError('Shape missing from camera context menu')
    pointer(preview);QTimer.singleShot(80,choose);command('click 273');delay(.2);assert preview.shape==shape
class Pattern(QWidget):
    def paintEvent(self,event):p=QPainter(self);p.fillRect(self.rect(),QColor('#228844'))
base=Pattern();base.setWindowTitle('Generated camera framing source');base.showFullScreen();delay(.3)
try:
    store=backend.Store(out/'data')
    setup=recording.RecordSetup(store);setup.show();delay(.25);click(setup.camera_size);backend.copy_text(str(size_percent));command('key 30 4');command('key 47 4');command('key 15 0');delay(.15);assert setup.camera_size.value()==size_percent
    setup.grab().save(str(out/'camera-size-setup.png'));click(setup.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok));assert setup.result()==setup.DialogCode.Accepted
    chosen=setup.options();setup.close();reopened_setup=recording.RecordSetup(backend.Store(store.root));assert reopened_setup.camera_size.value()==size_percent;reopened_setup.close()
    opts=dict(mode='Fullscreen',format='MP4',fps=10,quality='high',size='960x540',system=False,mic=False,cursor=False,delay=0,studio=True,camera=True,camera_device='/omnishot-generated-camera',camera_shape='Circle',camera_size=chosen['camera_size'],keys=False,clicks=False,dnd=False,show_controls=True,show_time=True)
    rec=recording.Recorder(store,None,opts);results=[];rec.completed.connect(results.append);rec.show();wait(lambda:rec.ready or errors,10);assert not errors
    preview=rec.camera_preview;wait(lambda:rec.camera_track.latest is not None and client(preview));delay(.5)
    assert preview.width()==int(min(round(preview.capture_rect[2]*size_percent/100),preview.capture_rect[3]-120))
    # Move remains a drag gesture and does not create a fullscreen change.
    before=client(preview)['at'];pointer(preview);command('button 272 1');delay(.06);command('move -50 30' if portrait else 'move -50 -30');delay(.08);command('move -70 45' if portrait else 'move -70 -45');delay(.08);command('button 272 0');delay(.2)
    assert not preview.fullscreen and not any(e['fullscreen'] for e in rec.camera_track.framing.events) and client(preview)['at']!=before
    assert len(rec.camera_track.framing.events)>1
    native=client(preview);cx,cy,cw,ch=preview.capture_rect
    expected=((native['at'][0]-cx)/cw,(native['at'][1]-cy)/ch,native['size'][0]/cw)
    assert max(abs(a-b) for a,b in zip(rec.camera_track.framing.events[-1]['placement'],expected))<1e-6
    normal=(*client(preview)['at'],preview.width(),preview.height());click(preview);wait(lambda:preview.fullscreen);delay(.6)
    assert (*client(preview)['at'],*client(preview)['size'])==tuple(preview.capture_rect)
    preview.grab().save(str(out/'fullscreen-camera.png'));assert preview.grab().toImage().pixelColor(10,10).alpha()==255
    click(rec.pause_btn);assert rec.paused;delay(.5)
    for shape in ('Square','Rounded','Rectangle','Circle',final_shape):
        shape_menu(preview,shape)
        ratio=1 if shape in ('Circle','Square') else camera_aspect
        expected_width=int(min(round(cw*size_percent/100),cw-40,(ch-120)/ratio))
        assert preview.normal_placement[2:]==(expected_width,round(expected_width*ratio))
    click(preview);wait(lambda:not preview.fullscreen);delay(.2)
    expected_normal=(*normal[:2],expected_width,round(expected_width*ratio))
    assert (*client(preview)['at'],*client(preview)['size'])==expected_normal
    click(rec.pause_btn);assert not rec.paused;delay(.9)
    checkpoint=read_checkpoint(rec.checkpoint.path);assert not checkpoint['camera_framing'][-1]['fullscreen'] and checkpoint['camera_framing'][-1]['shape']==final_shape and 'placement' in checkpoint['camera_framing'][-1]
    click(rec.stop_btn);wait(lambda:results or errors,20);assert not errors;camera.cv2.VideoCapture=original_capture
    path=Path(results[0]);meta=json.loads(path.with_suffix('.studio.json').read_text());events=meta['camera_framing'];full=next(e for e in events if e['fullscreen']);restored=next(e for e in events if not e['fullscreen'] and e['t']>full['t'])
    moments=[max(.05,full['t']/2),(full['t']+restored['t'])/2,restored['t']+.3]
    def centers(path):
        video=cv2.VideoCapture(str(path));colors=[]
        for moment in moments:
            video.set(cv2.CAP_PROP_POS_MSEC,moment*1000);ok,frame=video.read();assert ok;colors.append(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)[frame.shape[0]//2,frame.shape[1]//2].tolist())
        video.release();return colors
    raw=Path(meta['source_path']);source_hash=hashlib.sha256(raw.read_bytes()).hexdigest();raw_colors=centers(raw);rendered=centers(path)
    assert all(max(abs(np.array(value)-[34,136,68]))<10 for value in raw_colors),raw_colors
    assert max(abs(np.array(rendered[1])-[220,30,30]))<10,rendered
    if not portrait:assert all(max(abs(np.array(rendered[i])-[34,136,68]))<10 for i in (0,2)),rendered
    from omnishot.video_position import camera_rect
    video=cv2.VideoCapture(str(path));shape_pixels=[]
    for moment in (moments[0],moments[2]):
        video.set(cv2.CAP_PROP_POS_MSEC,moment*1000);ok,frame=video.read();assert ok
        r=camera_rect(frame.shape[1],frame.shape[0],camera_aspect,dict(options_at(meta,{},moment),camera_shape='Square'))
        shape_pixels.append(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)[round(r.y()+12),round(r.x()+12)].tolist())
    video.release();assert shape_pixels[0][0]<80 and shape_pixels[1][0]>200,shape_pixels
    def placement_bounds(path):
        video=cv2.VideoCapture(str(path));boxes=[]
        for moment in (moments[0],moments[2]):
            video.set(cv2.CAP_PROP_POS_MSEC,moment*1000);ok,frame=video.read();assert ok
            yy,xx=np.where((frame[:,:,2]>180)&(frame[:,:,1]<70)&(frame[:,:,0]<70));box=[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)]
            r=camera_rect(frame.shape[1],frame.shape[0],camera_aspect,options_at(meta,{},moment))
            assert max(abs(a-b) for a,b in zip(box,[r.x(),r.y(),r.right(),r.bottom()]))<3,(box,r.getRect())
            boxes.append(box)
        video.release();return boxes
    export_boxes=placement_bounds(path)
    editor=recording.VideoEditor(path,store);assert editor.camera_size.value()==size_percent;editor.show();wait(lambda:editor.last_camera is not None);editor.player.pause();editor.player.setPosition(round(moments[1]*1000));delay(.25)
    def center():return editor.preview_image.pixelColor(10,10).red() if portrait else editor.preview_image.pixelColor(editor.preview_image.width()//2,editor.preview_image.height()//2).red()
    assert center()>200;click(editor.tool_buttons['Camera']);assert editor.camera_recorded_framing.isVisible();click(editor.camera_recorded_framing);assert center()<80
    editor.edit_history.flush(True);command('key 44 4');delay(.15);assert editor.camera_recorded_framing.isChecked() and center()>200
    editor.player.setPosition(round(moments[2]*1000));delay(.25)
    def shape_red():
        image=editor.preview_image;r=camera_rect(image.width(),image.height(),camera_aspect,dict(options_at(editor.metadata,editor.studio_options(),moments[2]),camera_shape='Square'))
        return image.pixelColor(round(r.x()+r.width()*.1),round(r.y()+r.height()*.1)).red()
    assert shape_red()>200;click(editor.camera_recorded_framing);assert shape_red()<80
    editor.edit_history.flush(True);command('key 44 4');delay(.15);assert editor.camera_recorded_framing.isChecked() and shape_red()>200
    editor.grab().save(str(out/'camera-framing-editor.png'));options=editor.edit_options();project=out/'camera-framing.omnishot-video';write_project(project,raw,editor.metadata,options)
    export_studio(raw,out/'reexported.mp4',editor.metadata,{**options,'width':320,'fps':5});assert centers(out/'reexported.mp4')[1][0]>200;reexport_boxes=placement_bounds(out/'reexported.mp4')
    editor.close();wait(lambda:not JOBS);editor=recording.VideoEditor(project,store);assert editor.metadata['camera_framing']==events and editor.camera_recorded_framing.isChecked();editor.close();wait(lambda:not JOBS)
    assert hashlib.sha256(raw.read_bytes()).hexdigest()==source_hash
    report=dict(native_click_fullscreen=True,native_drag_moves_without_toggle=True,overlay_geometry_restored=True,pause_normalized_changes=True,checkpoint_retains_changes=True,actual_screen_and_camera_encoders=True,fullscreen_overlay_excluded_from_source=True,recorded_export_follows_changes=True,editor_preview_follows_changes=True,native_override_and_undo=True,reexport_and_portable_reopen=True,source_unchanged=True,physical_camera_used=False,display_scale=1.6,events=events,source_centers=raw_colors,export_centers=rendered)
    report.update(native_shape_menu=True,paused_shape_retained=True,export_shape_pixels=shape_pixels,editor_shape_override_and_undo=True,theme_applied=bool(theme.applied),native_placement_retained=True,export_placement_bounds=export_boxes,reexport_placement_bounds=reexport_boxes,native_camera_size_setup=True,saved_camera_size_percent=size_percent,preview_and_editor_size_match=True,camera_aspect=camera_aspect,live_aspect_and_fullscreen_return=True,portrait_maximum_size=portrait,native_pause_resume_stop_above_camera=True)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    camera.cv2.VideoCapture=original_capture;command('mods 0');command('button 272 0')
    if editor:editor.close()
    if rec:rec.shutdown();rec.stopping=True;rec.close()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
