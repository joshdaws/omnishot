"""SIGKILL a real recording app; recover its GSR video on native relaunch.

Run inside the isolated HEADLESS compositor only. All pixels are generated.
"""
import json,os,select,signal,subprocess,sys,time
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QApplication,QMessageBox,QWidget
from PySide6.QtTest import QTest
from omnishot.theme import ThemeManager
from omnishot import backend,recording
from omnishot.app import Controller
from omnishot.recording_journal import recover_interrupted
from omnishot.widgets import JOBS

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setQuitOnLastWindowClosed(False);theme=ThemeManager(app)
studio='--studio' in sys.argv;camera='--camera' in sys.argv

if '--child' in sys.argv:
    class Pattern(QWidget):
        def paintEvent(self,event):
            p=QPainter(self);p.fillRect(self.rect(),QColor('#22cc66'))
    source=Pattern();source.setWindowTitle('OmniShot Crash Test Pattern');source.showFullScreen();QTest.qWait(300)
    original_command=recording.recorder_command
    def isolated_command(*args,**kwargs):
        command=original_command(*args,**kwargs);assert '-p' in command
        command[command.index('-w')+1]='screen';return command
    recording.recorder_command=isolated_command
    if camera:
        from omnishot import camera as camera_module
        class GeneratedCamera:
            def __init__(self,*args):pass
            def isOpened(self):return True
            def set(self,*args):pass
            def read(self):time.sleep(1/30);return True,np.full((120,160,3),[180,80,30],dtype=np.uint8)
            def release(self):pass
        camera_module.cv2.VideoCapture=GeneratedCamera
    opts=dict(mode='Fullscreen',format='MP4',fps=15,quality='high',size='Native',system=False,mic=False,cursor=False,delay=0,studio=studio,camera=camera,camera_device='/omnishot-generated-camera',camera_shape='Circle',clicks=studio,keys=studio,commands_only=True,dnd=False,show_controls=True)
    rec=recording.Recorder(backend.Store(),None,opts);rec.show()
    def ready():
        if not rec.ready:QTimer.singleShot(100,ready);return
        (out/'live.json').write_text(json.dumps(dict(path=str(rec.path),encoder=rec.process.pid)))
        def publish():
            if '--paused' in sys.argv:rec.pause()
            QTimer.singleShot(150,lambda:(out/'ready.json').write_text(json.dumps(dict(path=str(rec.path),encoder=rec.process.pid,paused=rec.paused,camera_encoder=rec.camera_track.process.pid if rec.camera_track and rec.camera_track.process else None))))
        QTimer.singleShot(2600,publish)
    QTimer.singleShot(100,ready);sys.exit(app.exec())

child_log=(out/'child.log').open('wb')
child=subprocess.Popen([sys.executable,__file__,str(out),'--child',*sys.argv[2:]],stdout=child_log,stderr=child_log)
state=None;encoder_fd=None;fixture=None;camera_fd=None
def wait(predicate,seconds=15):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:app.processEvents();QTest.qWait(1);time.sleep(.02)
    assert predicate(),'Condition not reached'
try:
    if studio:
        wait(lambda:(out/'live.json').exists() or child.poll() is not None)
        assert child.poll() is None,(out/'child.log').read_text()
        fixture=subprocess.Popen([sys.argv[sys.argv.index('--fixture')+1]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        assert fixture.stdout.readline().strip()=='ready'
        def input(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
        client=next(c for c in backend.hypr('clients') if c['pid']==child.pid and c['title']=='OmniShot Crash Test Pattern')
        backend.focus_window(client['address']);backend.move_cursor(599,300);input('move 1 0');QTest.qWait(100)
        input('key 37 4');input('click 272');QTest.qWait(150)
        backend.move_cursor(800,500);input('move 1 0')
    wait(lambda:(out/'ready.json').exists() or child.poll() is not None)
    assert child.poll() is None,(out/'child.log').read_text()
    ready=json.loads((out/'ready.json').read_text());path=Path(ready['path']);encoder_fd=os.pidfd_open(ready['encoder'])
    store=backend.Store();markers=list(store.captures.glob('*.recording.json'))
    assert len(markers)==1 and recover_interrupted(store,markers)['pending'] and not store.history()
    if studio:
        from omnishot.recording_checkpoint import read_checkpoint
        checkpoint=path.with_suffix('.studio.checkpoint');captured=read_checkpoint(checkpoint)
        assert len(captured['cursor'])>10 and any(e.get('label')=='Ctrl+K' for e in captured['events']) and any(e['kind']=='click' for e in captured['events']),captured
        if ready['paused']:
            input('key 45 4');input('click 272');QTest.qWait(1300)
            assert not any(e.get('label')=='Ctrl+X' for e in read_checkpoint(checkpoint)['events'])
        if camera:
            assert captured.get('camera_path') and abs(captured['camera_offset'])<3,captured
            camera_path=Path(captured['camera_path'])
            # The camera encoder shares the same lifetime lease.
            camera_fd=os.pidfd_open(ready['camera_encoder'])
    if '--encoder-kill' in sys.argv:signal.pidfd_send_signal(encoder_fd,signal.SIGKILL)
    child.kill();child.wait(timeout=3);assert child.returncode==-signal.SIGKILL
    wait(lambda:bool(select.select([encoder_fd],[],[],0)[0]),8)
    if camera_fd is not None:wait(lambda:bool(select.select([camera_fd],[],[],0)[0]),8)
    recovered=[];warnings=[]
    def dismiss():
        modal=app.activeModalWidget()
        if isinstance(modal,QMessageBox):
            warnings.append(modal.text());modal.grab().save(str(out/'recovery-message.png'));modal.accept()
    timer=QTimer();timer.timeout.connect(dismiss);timer.start(100)
    state=Controller(app);original_recovered=state.recovered_recording
    def review(path,message):original_recovered(path,message);recovered.append(path)
    state.recovered_recording=review
    wait(lambda:bool(recovered) and not JOBS)
    assert warnings and len(store.history())==1 and not list(store.captures.glob('*.recording.json'))
    editor=next(w for w in state.windows if isinstance(w,recording.VideoEditor))
    wait(lambda:editor.last_frame is not None)
    preview=editor.last_frame;ph,pw=preview.shape[:2]
    assert np.max(abs(preview[ph//2,pw//2].astype(int)-[34,204,102]))<8
    assert editor.isVisible();editor.grab().save(str(out/'recovered-editor.png'))
    if studio:
        assert len(editor.metadata['cursor'])>=len(captured['cursor']) and any(e.get('label')=='Ctrl+K' for e in editor.metadata['events'])
        assert not any(e.get('label')=='Ctrl+X' for e in editor.metadata['events'])
        assert not checkpoint.exists()
        if camera:
            assert editor.metadata['camera_path']==str(camera_path) and abs(editor.metadata['camera_offset']-captured['camera_offset'])<.001
            wait(lambda:editor.last_camera is not None)
            assert np.max(abs(editor.last_camera[60,80].astype(int)-[30,80,180]))<8
            editor.camera_position.setCurrentText('Top Left');editor.camera_shape.setCurrentText('Rounded');editor.show_cursor.setChecked(True)
            editor.refresh_preview();editor.save_edits();editor.grab().save(str(out/'recovered-studio-edited.png'))
    frame=out/'recovered-frame.png';backend.run(['ffmpeg','-v','error','-y','-ss','0.5','-i',path,'-frames:v','1',frame])
    pixels=np.array(Image.open(frame).convert('RGB'));h,w=pixels.shape[:2]
    assert np.max(abs(pixels[h//2,w//2].astype(int)-[34,204,102]))<8
    export=out/'recovered-export.mp4'
    recording.export_video(path,export,dict(start=0,end=0,speed=1,fps=15,width=0,format='MP4',padding=0,background='#202633',blur=False))
    from omnishot.recording_recovery import valid_video
    assert valid_video(export)
    if studio:
        from omnishot.studio import export_studio
        studio_export=out/'recovered-studio-export.mp4'
        opts={**editor.studio_options(),"start":0,"end":1,"fps":10,"speed":1,"width":640,"hardware":False}
        export_studio(editor.source_path,studio_export,editor.metadata,opts)
        studio_frame=out/'recovered-studio-frame.png';backend.run(['ffmpeg','-v','error','-y','-ss','0.5','-i',studio_export,'-frames:v','1',studio_frame])
        studio_pixels=np.array(Image.open(studio_frame).convert('RGB'))
        if camera:assert np.max(abs(studio_pixels[70,90].astype(int)-[30,80,180]))<10
        assert valid_video(studio_export)
    report=dict(app_sigkill=True,paused=ready['paused'],encoder_sigkill='--encoder-kill' in sys.argv,encoder_exited=True,lease_prevented_active_recovery=True,relaunch_warning=True,editor_opened=True,editor_preview_verified=True,generated_pixels_preserved=True,reexport_valid=True,one_history_entry=True,studio_metadata_recovered=studio,paused_input_excluded=studio and ready['paused'],camera_recovered=camera)
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    if child.poll() is None:child.kill();child.wait(timeout=3)
    if encoder_fd is not None:
        if not select.select([encoder_fd],[],[],0)[0]:signal.pidfd_send_signal(encoder_fd,signal.SIGKILL)
        os.close(encoder_fd)
    if camera_fd is not None:
        if not select.select([camera_fd],[],[],0)[0]:signal.pidfd_send_signal(camera_fd,signal.SIGKILL)
        os.close(camera_fd)
    if fixture:fixture.stdin.close();fixture.wait(timeout=3)
    if state:state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    child_log.close()
