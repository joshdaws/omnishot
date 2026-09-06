"""Force a GIF post-processing failure after generating a valid source video."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from omnishot.theme import ThemeManager
from omnishot import backend,recording
from omnishot.app import Controller

out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");app.setStyle("Fusion");theme=ThemeManager(app);app.setQuitOnLastWindowClosed(False)
source=out/"generated.mp4";backend.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","lavfi","-i","color=c=0x2468ac:s=240x160:r=15:d=1","-c:v","libx264","-threads","1","-pix_fmt","yuv420p",source])
unexpected="--unexpected" in sys.argv
store=backend.Store(out/"data");opts=dict(format="MP4" if unexpected else "GIF",fps=15,cursor=False,studio=False,delay=99)
rec=recording.Recorder(store,None,opts);shutil.copy2(source,rec.path);rec.log_path.write_text("Generated source for recovery test")
class FinishedEncoder:
    def poll(self):return 0
    def wait(self,timeout=None):return 0
if unexpected:
    rec.process=subprocess.Popen([sys.executable,"-c","raise SystemExit(7)"]);rec.process.wait(timeout=3)
else:rec.process=FinishedEncoder()
controller=Controller.__new__(Controller);controller.store=store;controller.windows=[];controller.hidden_for_capture=[];controller.recorder=rec
rec.recovered.connect(controller.recovered_recording);completed=[];rec.completed.connect(completed.append);recovered=[];rec.recovered.connect(lambda *args:recovered.append(args))
original_export=recording.export_video
def fail_export(*args,**kwargs):raise RuntimeError("Synthetic GIF export failure")
if not unexpected:recording.export_video=fail_export
acknowledged=[]
def dismiss_warning():
    modal=app.activeModalWidget()
    if isinstance(modal,QMessageBox):
        acknowledged.append(modal.text());modal.grab().save(str(out/"recovery-message.png"));modal.accept()
timer=QTimer();timer.timeout.connect(dismiss_warning);timer.start(100)
try:
    rec.show()
    if unexpected:rec.tick()
    else:rec.stop()
    deadline=time.monotonic()+12
    while not recovered and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
    assert recovered and acknowledged and not completed,(recovered,acknowledged,completed)
    path=Path(recovered[0][0]);assert path.is_file() and store.history()[0]["path"]==str(path)
    editor=next(w for w in controller.windows if isinstance(w,recording.VideoEditor));QTest.qWait(350)
    assert editor.isVisible() and editor.source_path.is_file()
    assert path.read_bytes()==source.read_bytes() and editor.source_path.read_bytes()==source.read_bytes()
    editor.grab().save(str(out/"recovered-editor.png"));recording.export_video=original_export
    output=out/"recovered-export.mp4";recording.export_video(editor.source_path,output,dict(start=0,end=0,speed=1,fps=15,width=0,format="MP4",padding=0,background="#202633",blur=False))
    from omnishot.recording_recovery import valid_video
    assert valid_video(output) and editor.source_path.read_bytes()==source.read_bytes()
    assert not json.loads(rec.status_path.read_text())["recording"]
    report=dict(forced_gif_export_failure=not unexpected,unexpected_encoder_exit=unexpected,original_in_history=True,recovery_warning=True,video_editor_opened=True,reexport_succeeded=True,source_preserved=True,recording_status_cleared=True)
    (out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    timer.stop();recording.export_video=original_export
    for widget in app.topLevelWidgets():widget.close()
