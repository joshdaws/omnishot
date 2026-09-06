"""Native clean recording check using a generated fullscreen test pattern.

No camera, microphone, or computer audio is opened. The test owns and closes
its windows, and unloads its compositor extension if it loaded it.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt,QRect
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtTest import QTest
from omnishot import backend, recording
from omnishot.clean_capture import NATIVE

root = Path(sys.argv[1]).resolve(); root.mkdir(parents=True, exist_ok=True)
app = QApplication([]); app.setApplicationName("omnishot"); app.setDesktopFileName("org.omarchy.OmniShot")
app.setQuitOnLastWindowClosed(False)
fixture=None
if '--fixture' in sys.argv:
    fixture=subprocess.Popen([sys.argv[sys.argv.index('--fixture')+1]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    assert fixture.stdout.readline().strip()=='ready'
def input_command(value):fixture.stdin.write(value+'\n');fixture.stdin.flush()
store = backend.Store(root / "data")
gif="--gif" in sys.argv
scale1x="--scale1x" in sys.argv
hidden="--hidden-controls" in sys.argv
bar_check="--bar" in sys.argv
dnd_check="--dnd" in sys.argv
dim_check="--dim" in sys.argv
if '--headless' in sys.argv:
    assert all(m['name'].startswith('HEADLESS-') for m in backend.hypr('monitors'))
    original_command=recording.recorder_command
    def isolated_command(*args,**kwargs):
        command=original_command(*args,**kwargs);assert '-p' in command
        command[command.index('-w')+1]='screen';return command
    recording.recorder_command=isolated_command
old_dnd=backend.run(["omarchy-shell","notifications","isDnd"]).decode().strip() if dnd_check else None
if gif:store.settings.update(gif_width=400,gif_fps=10,gif_quality=60,gif_optimize=True)
errors = []; recording.error = lambda parent, message: errors.append(str(message))
loaded = any(p.get("name") == "omnishot-clean-mirror" for p in backend.hypr("plugin list"))

class Pattern(QWidget):
    clicks=0
    def mousePressEvent(self,event):self.clicks+=1
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(0, 0, self.width(), self.height()//2, QColor("#2468ac"))
        p.fillRect(0, self.height()//2, self.width(), self.height(), QColor("#22cc66"))

def pointer_click(widget):
    client=next(c for c in backend.hypr("clients") if c["pid"]==os.getpid() and c["title"]==rec.windowTitle())
    point=widget.mapTo(rec,widget.rect().center())
    backend.move_cursor(client["at"][0]+point.x()-(2 if fixture else 0),client["at"][1]+point.y())
    if fixture:input_command('move 2 0')
    QTest.qWait(100)
    if fixture:input_command('click 272')
    else:backend.run([NATIVE/"scroll-helper","click","272"])
    QTest.qWait(120)

base = Pattern(); base.setWindowTitle("OmniShot Generated Recording Test")
camera = QWidget(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
camera.setWindowTitle("OmniShot Camera Preview"); camera.resize(160,160); camera.setStyleSheet("background:#ee3344;")
rec = None
try:
    base.showFullScreen(); QTest.qWait(600)
    client = next(c for c in backend.hypr("clients") if c["pid"] == os.getpid() and c["title"] == base.windowTitle())
    assert client["fullscreen"] == 2, "Generated pattern must cover the whole display before recording"
    opts = dict(mode="Fullscreen",format="GIF" if gif else "MP4",fps=10 if gif else 30,quality="high",size="Native",system=False,mic=False,
                cursor=False,delay=0,studio=False,camera=False,dnd=dnd_check,scale_video=scale1x,show_controls=not hidden,show_time=not hidden)
    rect=None
    if dim_check:
        from omnishot.clean_capture import capture_target
        x,y,w,h=capture_target(backend.hypr("monitors"))[2];rect=(x+(w-1000)//2,y+(h-600)//2,1000,600);opts["dim_screen"]=True
    rec = recording.Recorder(store, rect, opts); rec.setStyleSheet("background:#ee3344;color:white;")
    completed=[]; rec.completed.connect(completed.append); rec.show()
    deadline=time.monotonic()+12
    while not rec.ready and not errors and time.monotonic()<deadline:QTest.qWait(50)
    assert rec.ready,"Recorder never produced its first frame"
    assert not errors, errors
    assert rec.process and rec.process.poll() is None and rec.clean_capture.enabled
    if dnd_check:assert backend.run(["omarchy-shell","notifications","isDnd"]).decode().strip() in ("true","on")
    if dim_check:
        QTest.qWait(300);assert rec.dim_guides
        guide=rec.dim_guides[0]
        mapped=next(c for c in backend.hypr("clients") if c["pid"]==os.getpid() and c["title"]==guide.windowTitle());assert mapped["mapped"] and mapped["pinned"],mapped
        pixels=backend.grab_window(mapped);Image.fromarray(pixels).save(root/"visible-dim-guide.png")
        assert pixels[pixels.shape[0]//2,pixels.shape[1]//2,3]==0 and pixels[100,100,3]>80
        backend.move_cursor(50,80);QTest.qWait(100);backend.run([NATIVE/"scroll-helper","click","272"]);QTest.qWait(120);assert base.clicks==1
        # Deliberately cover the source with this owned guide to prove the clean
        # mirror excludes its pixels, independently of its normally clear hole.
        guide.capture=QRect(-1000,-1000,10,10);guide.update();QTest.qWait(150)
    camera.show(); recording.place_window(camera, client["at"][0]+100, client["at"][1]+100)
    QTest.qWait(1000)
    if bar_check:
        QTest.qWait(1300);bar=json.loads(backend.run(["omarchy-shell","local.omnishot","state"]))
        assert bar["recording"] and bar["show_time"]==(not hidden),bar
        assert (":" in bar["text"])==(not hidden),bar
    if hidden:
        assert not rec.isVisible() and not any(c["pid"]==os.getpid() and c["title"]==rec.windowTitle() and c.get("mapped") for c in backend.hypr("clients"))
        rec.pause();QTest.qWait(450);assert rec.paused;rec.pause();QTest.qWait(1000);rec.stop()
    else:
        controls=next(c for c in backend.hypr("clients") if c["pid"]==os.getpid() and c["title"]==rec.windowTitle())
        assert rec.isVisible() and controls["mapped"] and controls["pinned"], controls
        # Capture the actual control surface independently to confirm it is visible.
        Image.fromarray(backend.grab_window(controls)).save(root/"visible-controls.png")
        pointer_click(rec.pause_btn); QTest.qWait(450)
        assert rec.paused and rec.process.poll() is None
        pointer_click(rec.pause_btn); QTest.qWait(1000)
        pointer_click(rec.stop_btn)
    deadline=time.monotonic()+25
    while not completed and not errors and time.monotonic()<deadline: QTest.qWait(30)
    assert not errors,errors
    assert completed,"Recording did not finish"
    assert not rec.clean_capture.enabled,"Clean capture registration must be released after saving"
    if dim_check:assert not rec.dim_guides and not any(c["pid"]==os.getpid() and c["title"].startswith("OmniShot Recording Dim ") for c in backend.hypr("clients"))
    if dnd_check:assert backend.run(["omarchy-shell","notifications","isDnd"]).decode().strip()==old_dnd
    path=Path(completed[0])
    probe=json.loads(backend.run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",path]))
    video=next(s for s in probe["streams"] if s["codec_type"]=="video")
    if gif:assert video["codec_name"]=="gif" and video["width"]==400 and video["height"]==250,video
    if scale1x:
        from omnishot.clean_capture import capture_target
        logical=rect[2:] if rect else capture_target(backend.hypr("monitors"))[2][2:]
        assert all(abs(actual-expected)<=1 for actual,expected in zip((video["width"],video["height"]),logical)),(video,logical)
    assert not any(s["codec_type"]=="audio" for s in probe["streams"])
    frame=root/"recorded-frame.png"
    backend.run(["ffmpeg","-v","error","-y","-ss","1.0","-i",path,"-frames:v","1",frame])
    pixels=np.array(Image.open(frame).convert("RGB"));h,w=pixels.shape[:2]
    # Check orientation, the preview location, and the entire lower controls area.
    assert np.max(abs(pixels[h//4,w//2].astype(int)-[36,104,172]))<8
    assert np.max(abs(pixels[h*3//4,w//2].astype(int)-[34,204,102]))<8
    red=(pixels[:,:,0]>160)&(pixels[:,:,1]<100)&(pixels[:,:,2]<120)
    # The isolated compositor displays its own red startup warning in the top
    # 60 pixels. Both owned red test surfaces are below y=100 logical pixels.
    if '--headless' in sys.argv:red[:80]=False
    assert red.sum()==0,("Controls leaked into video",int(red.sum()))
    report=dict(codec=video["codec_name"],size=[w,h],duration=float(probe["format"]["duration"]),
                fullscreen=not dim_check,dim_guide_excluded=dim_check,dim_click_through=dim_check,scale1x=scale1x,visible_controls=not hidden,bar_timer_preference=bar_check,dnd_restored=dnd_check,excluded_camera_preview=True,pause_resume=True,
                registration_released=True,wayland_pointer_buttons=not hidden,controls_red_pixels=int(red.sum()),audio_tracks=0)
    (root/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    camera.close()
    if rec: rec.shutdown();rec.stopping=True;rec.close()
    base.close();QTest.qWait(100)
    if fixture:fixture.stdin.close();fixture.wait(timeout=3)
    if not loaded:
        subprocess.run(["hyprctl","plugin","unload",str((NATIVE/"clean-mirror.so").resolve())],capture_output=True,timeout=5)
