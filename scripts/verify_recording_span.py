"""Record a region across private Wayland outputs using the production encoder."""
import json,os,subprocess,sys,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPainter,QColor
from PySide6.QtWidgets import QApplication,QWidget,QDialogButtonBox
from PySide6.QtTest import QTest
from omnishot import backend,recording
import omnishot.app as application
from omnishot.app import Controller
from omnishot.theme import ThemeManager
from omnishot.widgets import JOBS

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['OMNISHOT_DATA_DIR']=str(out/'data')
assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
config=Path(os.environ['XDG_RUNTIME_DIR'])/'hyprland.lua'
assert config.parent.name.startswith('os-') and config.parent.parent==Path('/tmp')
connector=next(p.name.split('-',1)[1] for p in Path('/sys/class/drm').glob('card*-*') if (p/'status').read_text().strip()=='connected')
left='--left' in sys.argv;gap='--gap' in sys.argv;assert not (left and gap)
sx=-1920 if left else 2100 if gap else 1800;sy=250 if gap else 0
config.write_text(config.read_text()+f'\nhl.monitor({{output="{connector}",mode="1920x1080@60",position="{sx}x{sy}",scale=1}})\n')
backend.run(['hyprctl','reload']);assert not backend.run(['hyprctl','configerrors']).strip()
backend.run(['hyprctl','output','create','headless',connector])
app=QApplication([]);app.setApplicationName('omnishot');app.setDesktopFileName('org.omarchy.OmniShot');app.setStyle('Fusion');theme=ThemeManager(app)
fixture=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);assert fixture.stdout.readline().strip()=='ready'
def command(text):fixture.stdin.write(text+'\n');fixture.stdin.flush()
errors=[]
def wait(predicate,seconds=8):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert predicate(),errors
def pointer(widget):
    top=widget.window();c=next(c for c in backend.hypr('clients') if c['pid']==os.getpid() and c['title']==top.windowTitle());p=widget.mapTo(top,widget.rect().center())
    backend.move_cursor(c['at'][0]+p.x()-2,c['at'][1]+p.y());command('move 2 0');QTest.qWait(80)
wait(lambda:len(app.screens())==2)
class Pattern(QWidget):
    def __init__(self,colors,y):super().__init__();self.colors=colors;self.offset=y
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor(self.colors[1]));p.fillRect(0,0,self.width(),350-self.offset,QColor(self.colors[0]))
sources=[]
for name,colors,y in [('HEADLESS-1',('#365faf','#c2a633'),0),(connector,('#2468ac','#22cc66'),sy)]:
    w=Pattern(colors,y);w.setWindowTitle('Generated recording span '+name);w.winId();w.windowHandle().setScreen(next(s for s in app.screens() if s.name()==name));w.showFullScreen();sources.append(w);QTest.qWait(200)
state=Controller(app);application.error=recording.error=lambda parent,message:errors.append(str(message))
state.store.settings.update(record_system_audio=False,record_microphone=False,record_cursor=False,record_clicks=False,record_keys=False,record_dnd=False,record_countdown=0,record_scale_video=True,record_max_resolution='Native',record_show_controls=True,fps=10,after_recording='edit',after_recording_extra=[])
rect=(-500 if left else 1700,200,600,300)
def accept():
    dialog=app.activeModalWidget()
    if not isinstance(dialog,recording.RecordSetup):timer.start(50);return
    pointer(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok));command('click 272')
timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(accept)
try:
    native_area='--native-area' in sys.argv
    timer.start(200);state.start_record_dialog(None if native_area else rect)
    if native_area:
        wait(lambda:len(state.selectors)==2);QTest.qWait(250)
        x,y,w,h=rect
        backend.move_cursor(x-2,y);command('move 2 0');QTest.qWait(100);command('button 272 1');QTest.qWait(100)
        backend.move_cursor(x+w-3,y+h-1);command('move 2 0');QTest.qWait(150);command('button 272 0');QTest.qWait(150)
        regions=[s.selection.translated(s.monitor['x'],s.monitor['y']).getRect() for s in state.selectors]
        assert all(r==rect for r in regions),regions
        for index,s in enumerate(state.selectors):s.grab().save(str(out/f'selection-{index}.png'))
        command('key 28 0')
    wait(lambda:state.recorder is not None and state.recorder.ready,12);rec=state.recorder
    assert rec.rect_capture==rect and rec.clean_capture.enabled and len(rec.clean_capture.parts)==2
    assert '-p' in Path(f'/proc/{rec.process.pid}/cmdline').read_bytes().decode().split('\0')
    rec.setStyleSheet('background:#ee3344;color:white;');QTest.qWait(200)
    control=next(c for c in backend.hypr('clients') if c['title']==rec.windowTitle())
    cx,cy=control['at'];cw,ch=control['size']
    assert sx<=cx and cx+cw<=sx+1920 and sy<=cy and cy+ch<=sy+1080,control
    pointer(rec.pause_btn);command('click 272');wait(lambda:rec.paused)
    QTest.qWait(250);pointer(rec.pause_btn);command('click 272');wait(lambda:not rec.paused)
    backend.move_window(control['address'],-480 if left else sx+20,370);QTest.qWait(200)
    backend.run(['hyprctl','dismissnotify','-1'])
    with ThreadPoolExecutor(max_workers=1) as pool:
        capture=pool.submit(backend.grab_window,control);wait(capture.done,12);visible=capture.result();Image.fromarray(visible).save(out/'controls.png')
    red=lambda a:(a[:,:,0]>180)&(a[:,:,1]<90)&(a[:,:,2]<110)
    assert red(visible).sum()>1000
    QTest.qWait(1400);pointer(rec.stop_btn);command('click 272')
    wait(lambda:state.recorder is None and len(state.store.history())==1 and not JOBS,15)
    wait(lambda:any(isinstance(w,recording.VideoEditor) for w in state.windows));editor=next(w for w in state.windows if isinstance(w,recording.VideoEditor))
    wait(lambda:editor.last_frame is not None);editor.player.pause()
    probe=json.loads(backend.run(['ffprobe','-v','error','-show_streams','-of','json',editor.path]));video=next(s for s in probe['streams'] if s['codec_type']=='video')
    assert (video['width'],video['height'])==(600,300),video
    frame=out/'recorded.png';backend.run(['ffmpeg','-v','error','-y','-ss','1','-i',editor.path,'-frames:v','1',frame]);image=Image.open(frame).convert('RGB')
    samples=[]
    for x,y in [(25,25),(25,225),(150,25),(150,225),(450,25),(450,125),(450,225),(575,225)]:
        gx,gy=rect[0]+x,rect[1]+y
        if 0<=gx<1800 and 0<=gy<1125:expected=(54,95,175) if gy<350 else (194,166,51)
        elif sx<=gx<sx+1920 and sy<=gy<sy+1080:expected=(36,104,172) if gy<350 else (34,204,102)
        else:expected=(0,0,0)
        actual=image.getpixel((x,y));assert max(abs(a-b) for a,b in zip(actual,expected))<8,((x,y),actual,expected)
        samples.append(dict(point=[x,y],actual=actual,expected=expected))
    assert not red(np.array(image)).any()
    assert not any(p['name']=='omnishot-clean-mirror' for p in backend.hypr('plugin list')) and not errors
    wait(lambda:editor.last_frame is not None);editor.grab().save(str(out/'editor.png'))
    report=dict(rect=rect,scales=[1.6,1],native_cross_display_drag=native_area,native_record_pause_resume_stop=True,default_controls_inside_output=True,production_encoder_command=True,source_pixels=samples,visible_control_red_pixels=int(red(visible).sum()),recorded_control_red_pixels=0,clean_capture_released=True,record_to_video_editor=True,negative_position=left,display_gap=gap,theme_applied=bool(theme.applied))
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    state.cleanup()
    for widget in app.topLevelWidgets():widget.close()
    fixture.stdin.close();fixture.wait(timeout=3)
