"""Native camera flip setup, live preview, recording, editing and portable export."""
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
assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
original_command=recording.recorder_command
def isolated_command(*args,**kwargs):
    command=original_command(*args,**kwargs);assert '-region' not in command;command[command.index('-w')+1]='screen';return command
recording.recorder_command=isolated_command
original_capture=cv2.VideoCapture
class GeneratedCamera:
    def isOpened(self):return True
    def set(self,*args):pass
    def read(self):
        time.sleep(1/30);frame=np.full((120,160,3),[30,30,220],np.uint8);frame[:,80:]=[220,30,30];return True,frame
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
class Pattern(QWidget):
    def paintEvent(self,event):p=QPainter(self);p.fillRect(self.rect(),QColor('#228844'))
base=Pattern();base.setWindowTitle('Generated camera framing source');base.showFullScreen();delay(.3)
try:
    from omnishot.video_position import camera_rect
    store=backend.Store(out/'data')
    setup=recording.RecordSetup(store);setup.show();delay(.2);assert not setup.camera_mirror.isChecked()
    click(setup.camera_mirror);assert setup.camera_mirror.isChecked()
    setup.grab().save(str(out/'camera-flip-setup.png'))
    click(setup.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok));assert setup.result()==setup.DialogCode.Accepted
    chosen=setup.options();setup.close();assert chosen['camera_mirror']
    cancelled=recording.RecordSetup(backend.Store(store.root));cancelled.show();delay(.15)
    assert cancelled.camera_mirror.isChecked();click(cancelled.camera_mirror)
    click(cancelled.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel));assert cancelled.result()==cancelled.DialogCode.Rejected
    reopened=recording.RecordSetup(backend.Store(store.root));assert reopened.camera_mirror.isChecked();reopened.close()
    opts=dict(mode='Fullscreen',format='MP4',fps=10,quality='high',size='960x540',system=False,mic=False,cursor=False,delay=0,studio=True,camera=True,camera_device='/omnishot-generated-camera',camera_shape='Rectangle',camera_size=.3,camera_mirror=chosen['camera_mirror'],keys=False,clicks=False,dnd=False,show_controls=True,show_time=True)
    rec=recording.Recorder(store,None,opts);results=[];rec.completed.connect(results.append);rec.show();wait(lambda:rec.ready or errors,10);assert not errors
    preview=rec.camera_preview;wait(lambda:rec.camera_track.latest is not None and client(preview));delay(.6)
    def image_sides(image,rect=None):
        r=rect or image.rect();return [image.pixelColor(round(r.x()+r.width()*fraction),round(r.y()+r.height()/2)).getRgb()[:3] for fraction in (.25,.75)]
    def mirrored(colors):return colors[0][2]>180 and colors[0][0]<70 and colors[1][0]>180 and colors[1][2]<70
    live_overlay=image_sides(preview.grab().toImage());assert mirrored(live_overlay),live_overlay
    click(preview);assert preview.fullscreen;delay(.5)
    live_fullscreen=image_sides(preview.grab().toImage());assert mirrored(live_fullscreen),live_fullscreen
    click(preview);assert not preview.fullscreen;delay(.7)
    click(rec.stop_btn);wait(lambda:results or errors,20);assert not errors;camera.cv2.VideoCapture=original_capture
    path=Path(results[0]);meta=json.loads(path.with_suffix('.studio.json').read_text());assert meta['capture_options']['camera_mirror']
    raw=Path(meta['source_path']);track=Path(meta['camera_path']);source_hash=hashlib.sha256(raw.read_bytes()).hexdigest();track_hash=hashlib.sha256(track.read_bytes()).hexdigest()
    full=next(e for e in meta['camera_framing'] if e['fullscreen']);restored=next(e for e in meta['camera_framing'] if not e['fullscreen'] and e['t']>full['t'])
    moments=[full['t']/2,(full['t']+restored['t'])/2,restored['t']+.2]
    def decoded_sides(path,compose=True):
        video=cv2.VideoCapture(str(path));colors=[]
        for moment in moments:
            video.set(cv2.CAP_PROP_POS_MSEC,moment*1000);ok,frame=video.read();assert ok
            image=camera.qimage(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            opts=options_at(meta,meta['capture_options'],moment)
            colors.append(image_sides(image,camera_rect(image.width(),image.height(),.75,opts)) if compose else image_sides(image))
        video.release();return colors
    exported=decoded_sides(path);assert all(mirrored(c) for c in exported),exported
    original_camera=decoded_sides(track,False);assert all(mirrored(c[::-1]) for c in original_camera),original_camera
    editor=recording.VideoEditor(path,store);editor.show();wait(lambda:editor.last_camera is not None);editor.player.pause();editor.player.setPosition(round(moments[2]*1000));delay(.2)
    click(editor.tool_buttons['Camera']);flip=editor.effect_controls['Camera'].fields['camera_mirror'];assert flip.isChecked()
    def editor_sides():
        image=editor.preview_image;options=options_at(editor.metadata,editor.studio_options(),moments[2]);return image_sides(image,camera_rect(image.width(),image.height(),.75,options))
    assert mirrored(editor_sides());click(flip);assert not flip.isChecked() and mirrored(editor_sides()[::-1])
    editor.edit_history.flush(True);command('key 44 4');delay(.15);assert flip.isChecked() and mirrored(editor_sides())
    command('key 44 5');delay(.15);assert not flip.isChecked() and mirrored(editor_sides()[::-1])
    command('key 44 4');delay(.15);assert flip.isChecked() and mirrored(editor_sides())
    editor.grab().save(str(out/'camera-flip-editor.png'))
    options=editor.edit_options();project=out/'camera-flip.omnishot-video';write_project(project,raw,editor.metadata,options)
    export_studio(raw,out/'mirrored.mp4',editor.metadata,{**options,'width':320,'fps':5});reexported=decoded_sides(out/'mirrored.mp4');assert all(mirrored(c) for c in reexported),reexported
    export_studio(raw,out/'unmirrored.mp4',editor.metadata,{**options,'camera_mirror':False,'width':320,'fps':5});unmirrored=decoded_sides(out/'unmirrored.mp4');assert all(mirrored(c[::-1]) for c in unmirrored),unmirrored
    editor.close();wait(lambda:not JOBS);editor=recording.VideoEditor(project,store);editor.show();wait(lambda:editor.last_camera is not None);editor.player.pause();editor.player.setPosition(round(moments[2]*1000));delay(.2)
    assert editor.effect_controls['Camera'].fields['camera_mirror'].isChecked() and mirrored(editor_sides())
    editor.close();wait(lambda:not JOBS)
    assert hashlib.sha256(raw.read_bytes()).hexdigest()==source_hash and hashlib.sha256(track.read_bytes()).hexdigest()==track_hash
    report=dict(native_setup_flip=True,saved_preference=True,native_cancel_preserves_preference=True,live_overlay_mirrored=True,live_fullscreen_mirrored=True,initial_export_mirrored=True,editor_inherits_recording_option=True,native_flip_override_undo_redo=True,mirrored_and_unmirrored_reexports=True,portable_reopen=True,screen_and_camera_sources_unchanged=True,physical_camera_used=False,theme_applied=bool(theme.applied),display_scale=1.6,live_overlay_sides=live_overlay,live_fullscreen_sides=live_fullscreen,export_sides=exported,original_camera_sides=original_camera,reexport_sides=reexported,unmirrored_sides=unmirrored)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    camera.cv2.VideoCapture=original_capture;command('mods 0');command('button 272 0')
    if editor:editor.close()
    if rec:rec.shutdown();rec.stopping=True;rec.close()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
